"""Dry-run and transactional recovery helpers for HMS."""

from contextvars import ContextVar
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from hms_manifest import ManifestStore


_DRY_RUN = ContextVar("hms_dry_run", default=False)


def set_dry_run(enabled: bool) -> None:
    _DRY_RUN.set(bool(enabled))


def is_dry_run() -> bool:
    return _DRY_RUN.get()


def ensure_rollback_root(root_dir: Path | None = None) -> Path:
    rollback_root = (root_dir or Path.cwd()).resolve() / "rollback"
    rollback_root.mkdir(parents=True, exist_ok=True)
    return rollback_root


def backup_file(source_file: str | Path, run_dir: str | Path) -> bool:
    source_path = Path(source_file)
    if not source_path.is_file():
        return False
    backup_dir = Path(run_dir) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, backup_dir / source_path.name)
    return True


def save_rename_map(run_dir: str | Path, rename_map: list[dict]) -> None:
    ManifestStore.write_json_atomic(Path(run_dir) / "rename_map.json", rename_map)


def load_rename_map(run_dir: str | Path) -> list[dict]:
    rename_path = Path(run_dir) / "rename_map.json"
    if not rename_path.is_file():
        return []
    data = json.loads(rename_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Invalid rename map: {rename_path}")
    return data


class RollbackStore(ManifestStore):
    """Stores backups and safely restores a complete or failed pipeline run."""

    OUTPUT_SUFFIXES = (
        "_hooktimestamp.txt",
        "_thebeats.txt",
        "_master_audio.wav",
        "_davinci_timeline.xml",
    )

    def begin_run(self, slug: str, audio_input: str, renders_dir: str) -> str:
        if not slug or Path(slug).name != slug or any(char in slug for char in ("/", "\\")):
            raise ValueError(f"Invalid output slug: {slug!r}")

        run_id, run_dir = self.reserve_run_dir()
        try:
            backup_dir = run_dir / "backups"
            backup_dir.mkdir()
            output_dir = (self.root_dir / "output").resolve()
            backed_up_outputs = []
            for suffix in self.OUTPUT_SUFFIXES:
                output_path = output_dir / f"{slug}{suffix}"
                existed_before = backup_file(output_path, run_dir)
                backed_up_outputs.append(
                    {
                        "name": output_path.name,
                        "existed_before": existed_before,
                        "backup": (
                            f"backups/{output_path.name}" if existed_before else None
                        ),
                    }
                )
            timestamp = datetime.now(timezone.utc).isoformat()
            manifest = {
                "schema_version": 1,
                "timestamp": timestamp,
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
                "started_at": timestamp,
            }
            self.create_run(run_id, manifest)
        except Exception:
            self.discard_run(run_id)
            raise
        return run_id

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
                raise ValueError(
                    "Restore blocked. Output backup manifest contains an unsafe entry."
                )
            declared_names.add(entry["name"])
            if entry["existed_before"] and entry.get("backup") != f"backups/{entry['name']}":
                raise ValueError("Restore blocked. Output backup path is unsafe.")
        if declared_names != expected_names:
            raise ValueError("Restore blocked. Output backup manifest is incomplete.")
        missing_backups = [
            run_dir / "backups" / entry["name"]
            for entry in backed_up_outputs
            if entry["existed_before"]
            and not (run_dir / "backups" / entry["name"]).is_file()
        ]
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


def restore_run(run_id: str, root_dir: Path | None = None) -> dict:
    return RollbackStore(root_dir).restore_run(run_id)


def rollback_last_run(root_dir: Path | None = None) -> dict:
    return RollbackStore(root_dir).rollback_last_run()
