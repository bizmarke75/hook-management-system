"""Run-history, dry-run, and restore utilities for HMS."""

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class RollbackStore:
    """Stores run manifests and snapshots needed to safely undo a pipeline run."""

    OUTPUT_SUFFIXES = (
        "_hooktimestamp.txt",
        "_thebeats.txt",
        "_master_audio.wav",
        "_davinci_timeline.xml",
    )

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.rollback_root = self.root_dir / "rollback"
        self.index_path = self.rollback_root / "manifest_index.json"

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"schema_version": 1, "runs": []}
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        if index.get("schema_version") != 1 or not isinstance(index.get("runs"), list):
            raise ValueError(f"Unsupported or invalid run index: {self.index_path}")
        return index

    def _write_json(self, path: Path, data: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        try:
            temp_path.replace(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _manifest_path(self, run_id: str) -> Path:
        if Path(run_id).name != run_id or not run_id.startswith("run_"):
            raise ValueError(f"Invalid run ID: {run_id!r}")
        return self.rollback_root / run_id / "manifest.json"

    def list_runs(self) -> list[dict]:
        index = self._load_index()
        manifests = []
        for run_id in index["runs"]:
            path = self._manifest_path(run_id)
            if not path.is_file():
                raise RuntimeError(f"Run index references missing manifest: {path}")
            manifests.append(json.loads(path.read_text(encoding="utf-8")))
        return manifests

    def begin_run(self, slug: str, audio_input: str, renders_dir: str) -> str:
        if not slug or Path(slug).name != slug or any(char in slug for char in ("/", "\\")):
            raise ValueError(f"Invalid output slug: {slug!r}")
        self.rollback_root.mkdir(parents=True, exist_ok=True)
        index = self._load_index()
        run_numbers = [
            int(run_id[4:])
            for run_id in index["runs"]
            if run_id.startswith("run_") and run_id[4:].isdigit()
        ]
        run_numbers.extend(
            int(path.name[4:])
            for path in self.rollback_root.glob("run_*")
            if path.is_dir() and path.name[4:].isdigit()
        )
        run_id = f"run_{max(run_numbers, default=0) + 1:03d}"
        run_dir = self.rollback_root / run_id
        run_dir.mkdir()
        try:
            backup_dir = run_dir / "backups"
            backup_dir.mkdir()

            output_dir = (Path.cwd() / "output").resolve()
            backed_up_outputs = []
            for suffix in self.OUTPUT_SUFFIXES:
                output_path = output_dir / f"{slug}{suffix}"
                existed_before = output_path.is_file()
                backup_name = output_path.name if existed_before else None
                if existed_before:
                    shutil.copy2(output_path, backup_dir / backup_name)
                backed_up_outputs.append(
                    {
                        "name": output_path.name,
                        "existed_before": existed_before,
                        "backup": f"backups/{backup_name}" if backup_name else None,
                    }
                )

            manifest = {
                "schema_version": 1,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "running",
                "slug": slug,
                "audio_input": str(Path(audio_input).resolve()),
                "renders_dir": str(Path(renders_dir).resolve()),
                "output_dir": str(output_dir),
                "xml": f"{slug}_davinci_timeline.xml",
                "wav": f"{slug}_master_audio.wav",
                "beats": f"{slug}_thebeats.txt",
                "hooktimestamp": f"{slug}_hooktimestamp.txt",
                "renamed_clips": 0,
                "marker_count": 0,
                "rename_map": [],
                "rename_state": "planned",
                "backed_up_outputs": backed_up_outputs,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            self._write_json(run_dir / "manifest.json", manifest)
            self._write_json(run_dir / "rename_map.json", [])
            index["runs"].append(run_id)
            self._write_json(self.index_path, index)
        except Exception:
            shutil.rmtree(run_dir)
            raise
        return run_id

    def _read_manifest(self, run_id: str) -> dict:
        path = self._manifest_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(f"Run manifest not found: {path}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("run_id") != run_id:
            raise ValueError(f"Run ID mismatch in manifest: {path}")
        return manifest

    def _save_manifest(self, manifest: dict) -> None:
        self._write_json(
            self._manifest_path(manifest["run_id"]),
            manifest,
        )

    def set_rename_map(
        self, run_id: str, rename_map: list[dict], state: str = "planned"
    ) -> None:
        if state not in ("planned", "completed", "restored"):
            raise ValueError(f"Invalid rename state: {state}")
        manifest = self._read_manifest(run_id)
        normalized = []
        original_names = set()
        new_names = set()
        for item in rename_map:
            original = item.get("original")
            new = item.get("new")
            if (
                not original
                or not new
                or Path(original).name != original
                or Path(new).name != new
                or "/" in original
                or "\\" in original
                or "/" in new
                or "\\" in new
            ):
                raise ValueError("Rename map entries must contain safe file basenames.")
            if original.casefold() in original_names or new.casefold() in new_names:
                raise ValueError("Rename map entries must have unique original and target filenames.")
            original_names.add(original.casefold())
            new_names.add(new.casefold())
            normalized.append({"original": original, "new": new})
        manifest["rename_map"] = normalized
        manifest["rename_state"] = state
        manifest["renamed_clips"] = sum(
            item["original"] != item["new"] for item in normalized
        )
        self._write_json(
            self._manifest_path(run_id).parent / "rename_map.json",
            normalized,
        )
        self._save_manifest(manifest)

    def finish_run(
        self,
        run_id: str,
        status: str,
        marker_count: int = 0,
        error: str | None = None,
    ) -> None:
        if status not in ("completed", "failed"):
            raise ValueError(f"Invalid final run status: {status}")
        manifest = self._read_manifest(run_id)
        manifest["status"] = status
        manifest["marker_count"] = int(marker_count)
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        if error:
            manifest["error"] = error
        self._save_manifest(manifest)

    def _preflight_restore(
        self, manifest: dict
    ) -> tuple[Path, Path, list[tuple[Path, Path, Path, Path]]]:
        renders_dir = Path(manifest["renders_dir"]).resolve()
        output_dir = Path(manifest["output_dir"]).resolve()
        rename_map = manifest.get("rename_map", [])
        if not isinstance(rename_map, list):
            raise ValueError("Restore blocked. Invalid rename map.")
        for item in rename_map:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("original"), str)
                or not isinstance(item.get("new"), str)
                or not item["original"]
                or not item["new"]
                or Path(item["original"]).name != item["original"]
                or Path(item["new"]).name != item["new"]
                or any(char in item["original"] + item["new"] for char in ("/", "\\"))
            ):
                raise ValueError("Restore blocked. Rename map contains an unsafe filename.")
        if manifest.get("rename_state") == "restored":
            rename_map = []
        else:
            original_names = [item["original"].casefold() for item in rename_map]
            new_names = [item["new"].casefold() for item in rename_map]
            if len(set(original_names)) != len(original_names) or len(set(new_names)) != len(new_names):
                raise ValueError("Restore blocked. Rename map contains duplicate filenames.")
        restoring = manifest.get("status") == "restoring"
        expected_sources = []
        destinations = []
        moves = []
        missing = []
        for index, item in enumerate(rename_map):
            if item["new"] == item["original"]:
                continue
            source = renders_dir / item["new"]
            destination = renders_dir / item["original"]
            temporary = renders_dir / f"__hms_restore_{manifest['run_id']}_{index}.tmp"
            expected_sources.append(source)
            destinations.append(destination)
            if source.is_file() and temporary.exists():
                raise RuntimeError(
                    f"Restore blocked. Both source and recovery temporary exist: {source}, {temporary}"
                )
            if source.is_file():
                moves.append((source, destination, source, temporary))
            elif restoring and temporary.is_file():
                moves.append((temporary, destination, source, temporary))
            elif not (restoring and destination.is_file()):
                missing.append(source)
        if missing:
            raise RuntimeError(
                "Restore blocked. Missing renamed render files: "
                + ", ".join(str(path) for path in missing)
            )

        source_names = {path.name.casefold() for path in expected_sources}
        collisions = [
            path
            for path in destinations
            if path.exists() and path.name.casefold() not in source_names
        ]
        if collisions:
            raise RuntimeError(
                "Restore blocked. Original filenames are occupied: "
                + ", ".join(str(path) for path in collisions)
            )

        run_dir = self._manifest_path(manifest["run_id"]).parent
        backed_up_outputs = manifest.get("backed_up_outputs")
        if not isinstance(backed_up_outputs, list):
            raise ValueError("Restore blocked. Invalid output backup manifest.")
        expected_names = {
            f"{manifest['slug']}{suffix}" for suffix in self.OUTPUT_SUFFIXES
        }
        declared_names = set()
        for entry in backed_up_outputs:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("name"), str)
                or entry["name"] not in expected_names
                or entry["name"] in declared_names
                or not isinstance(entry.get("existed_before"), bool)
            ):
                raise ValueError("Restore blocked. Output backup manifest contains an unsafe entry.")
            declared_names.add(entry["name"])
            if entry["existed_before"] and entry.get("backup") != f"backups/{entry['name']}":
                raise ValueError("Restore blocked. Output backup path is unsafe.")
        if declared_names != expected_names:
            raise ValueError("Restore blocked. Output backup manifest is incomplete.")
        missing_backups = []
        for entry in backed_up_outputs:
            if not entry["existed_before"]:
                continue
            backup_path = run_dir / "backups" / entry["name"]
            if not backup_path.is_file():
                missing_backups.append(backup_path)
        invalid_outputs = [
            output_dir / entry["name"]
            for entry in backed_up_outputs
            if (output_dir / entry["name"]).exists()
            and not (output_dir / entry["name"]).is_file()
        ]
        if missing_backups:
            raise RuntimeError(
                "Restore blocked. Missing output backups: "
                + ", ".join(str(path) for path in missing_backups)
            )
        if invalid_outputs:
            raise RuntimeError(
                "Restore blocked. Expected output files but found non-files: "
                + ", ".join(str(path) for path in invalid_outputs)
            )
        return renders_dir, output_dir, moves

    def restore_run(self, run_id: str) -> dict:
        manifest = self._read_manifest(run_id)
        if manifest.get("status") == "restored":
            raise RuntimeError(f"Run {run_id} has already been restored.")
        if manifest.get("status") == "running":
            raise RuntimeError(f"Run {run_id} is still marked as running; refusing restore.")
        was_restoring = manifest.get("status") == "restoring"
        renders_dir, output_dir, moves = self._preflight_restore(manifest)

        staged = []
        completed = []
        staged_outputs = []
        run_dir = self._manifest_path(run_id).parent
        manifest["status"] = "restoring"
        self._save_manifest(manifest)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            for entry in manifest["backed_up_outputs"]:
                if not entry["existed_before"]:
                    continue
                output_path = output_dir / entry["name"]
                temp_output = output_path.with_name(f".{output_path.name}.{run_id}.restore")
                if temp_output.exists() and not was_restoring:
                    raise FileExistsError(f"Restore temporary path already exists: {temp_output}")
                staged_outputs.append((temp_output, output_path))
                shutil.copy2(run_dir / "backups" / entry["name"], temp_output)

            for entry in manifest["backed_up_outputs"]:
                output_path = output_dir / entry["name"]
                if entry["existed_before"]:
                    temp_output = next(
                        temp for temp, destination in staged_outputs if destination == output_path
                    )
                    temp_output.replace(output_path)
                elif output_path.exists():
                    output_path.unlink()
            for current, destination, original_new_path, temporary in moves:
                if current != temporary:
                    if temporary.exists():
                        raise FileExistsError(f"Restore temporary path already exists: {temporary}")
                    current.rename(temporary)
                staged.append((temporary, original_new_path, destination))
            for temporary, original_new_path, destination in staged:
                temporary.rename(destination)
                completed.append((destination, original_new_path))
        except Exception:
            for current, original_new_path in reversed(completed):
                if current.exists() and not original_new_path.exists():
                    current.rename(original_new_path)
            for temporary, original_new_path, _ in reversed(staged):
                if temporary.exists() and not original_new_path.exists():
                    temporary.rename(original_new_path)
            for temp_output, _ in staged_outputs:
                temp_output.unlink(missing_ok=True)
            raise

        manifest["rename_state"] = "restored"
        manifest["status"] = "restored"
        manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
        self._save_manifest(manifest)
        return manifest

    def rollback_last_run(self) -> dict:
        candidates = [
            manifest
            for manifest in self.list_runs()
            if manifest.get("status") in ("completed", "failed", "restoring")
        ]
        if not candidates:
            raise RuntimeError("No completed or failed runs are available to roll back.")
        return self.restore_run(candidates[-1]["run_id"])


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HMS run history and recovery")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--rollback", action="store_true", help="restore the latest completed or failed run")
    actions.add_argument("--restore", metavar="RUN_ID", help="restore a specific run, such as run_003")
    actions.add_argument("--verify-only", action="store_true", help="verify existing outputs without changing files")
    parser.add_argument("--dry-run", action="store_true", help="show planned operations without writing or renaming")
    parser.add_argument("--audio", help="master audio source path")
    parser.add_argument("--renders", help="directory containing render clips")
    parser.add_argument("--slug", help="track slug used for output names")
    parser.add_argument("--bpm", type=float, default=170.0)
    parser.add_argument("--duration", type=float, default=40.0)
    return parser


def dispatch_cli(args, gui_factory=None):
    """Run a requested CLI operation; return False when the GUI should open."""
    store = RollbackStore()
    if args.dry_run and (args.rollback or args.restore or args.verify_only):
        raise ValueError("--dry-run cannot be combined with rollback, restore, or verify-only.")
    if (args.rollback or args.restore) and (args.audio or args.renders or args.slug):
        raise ValueError("Rollback and restore cannot be combined with pipeline arguments.")
    if args.rollback:
        manifest = store.rollback_last_run()
        print(f"[SUCCESS] Restored latest run {manifest['run_id']}.")
        return True
    if args.restore:
        manifest = store.restore_run(args.restore)
        print(f"[SUCCESS] Restored run {manifest['run_id']}.")
        return True
    if args.verify_only:
        if args.audio:
            raise ValueError("--verify-only does not accept --audio.")
        if not args.slug:
            raise ValueError("--verify-only requires --slug.")
        from hms_master_gui import verify_pipeline_outputs

        verify_pipeline_outputs(args.slug, args.renders, args.duration)
        return True

    cli_run_requested = bool(args.audio or args.renders or args.slug)
    if args.dry_run or cli_run_requested:
        if not args.audio or not args.renders or not args.slug:
            if args.dry_run and not cli_run_requested and gui_factory is not None:
                return False
            raise ValueError("--dry-run pipeline execution requires --audio, --renders, and --slug.")
        from hms_master_gui import execute_pipeline

        execute_pipeline(
            args.audio,
            args.renders,
            args.slug,
            args.bpm,
            args.duration,
            dry_run=args.dry_run,
        )
        return True
    return False


if __name__ == "__main__":
    arguments = build_argument_parser().parse_args()
    if not dispatch_cli(arguments):
        build_argument_parser().print_help()
