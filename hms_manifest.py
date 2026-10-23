"""Persistent run manifests and rename-map tracking for HMS."""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class ManifestStore:
    """Read and write validated run history under the rollback directory."""

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.rollback_root = self.root_dir / "rollback"
        self.index_path = self.rollback_root / "manifest_index.json"

    def ensure_root(self) -> None:
        self.rollback_root.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {"schema_version": 1, "runs": []}
        index = json.loads(self.index_path.read_text(encoding="utf-8"))
        if index.get("schema_version") != 1 or not isinstance(index.get("runs"), list):
            raise ValueError(f"Unsupported or invalid run index: {self.index_path}")
        return index

    def _write_json(self, path: Path, data: dict | list) -> None:
        self.write_json_atomic(path, data)

    @staticmethod
    def write_json_atomic(path: Path, data: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            temp_path.replace(path)
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise

    def _manifest_path(self, run_id: str) -> Path:
        if (
            Path(run_id).name != run_id
            or not run_id.startswith("run_")
            or not run_id[4:].isdigit()
        ):
            raise ValueError(f"Invalid run ID: {run_id!r}")
        return self.rollback_root / run_id / "manifest.json"

    def reserve_run_dir(self) -> tuple[str, Path]:
        self.ensure_root()
        index = self._load_index()
        run_numbers = [
            int(run_id[4:])
            for run_id in index["runs"]
            if isinstance(run_id, str)
            and run_id.startswith("run_")
            and run_id[4:].isdigit()
        ]
        run_numbers.extend(
            int(path.name[4:])
            for path in self.rollback_root.glob("run_*")
            if path.is_dir() and path.name[4:].isdigit()
        )
        run_id = f"run_{max(run_numbers, default=0) + 1:03d}"
        run_dir = self.rollback_root / run_id
        run_dir.mkdir()
        return run_id, run_dir

    def create_run(self, run_id: str, manifest: dict) -> None:
        manifest_path = self._manifest_path(run_id)
        if not manifest_path.parent.is_dir():
            raise FileNotFoundError(f"Run directory not found: {manifest_path.parent}")
        index = self._load_index()
        if run_id in index["runs"]:
            raise ValueError(f"Run already exists in history: {run_id}")
        manifest["run_id"] = run_id
        self._write_json(manifest_path, manifest)
        self._write_json(manifest_path.parent / "rename_map.json", [])
        index["runs"].append(run_id)
        self._write_json(self.index_path, index)

    def discard_run(self, run_id: str) -> None:
        run_dir = self._manifest_path(run_id).parent
        index = self._load_index()
        if run_id in index["runs"]:
            index["runs"].remove(run_id)
            self._write_json(self.index_path, index)
        if run_dir.exists():
            shutil.rmtree(run_dir)

    def list_runs(self) -> list[dict]:
        index = self._load_index()
        manifests = []
        for run_id in index["runs"]:
            path = self._manifest_path(run_id)
            if not path.is_file():
                raise RuntimeError(f"Run index references missing manifest: {path}")
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("run_id") != run_id:
                raise ValueError(f"Run ID mismatch in manifest: {path}")
            manifests.append(manifest)
        return manifests

    def _read_manifest(self, run_id: str) -> dict:
        path = self._manifest_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(f"Run manifest not found: {path}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("run_id") != run_id:
            raise ValueError(f"Run ID mismatch in manifest: {path}")
        return manifest

    def _save_manifest(self, manifest: dict) -> None:
        self._write_json(self._manifest_path(manifest["run_id"]), manifest)

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
                not isinstance(original, str)
                or not isinstance(new, str)
                or not original
                or not new
                or Path(original).name != original
                or Path(new).name != new
                or any(char in original + new for char in ("/", "\\"))
            ):
                raise ValueError("Rename map entries must contain safe file basenames.")
            if original.casefold() in original_names or new.casefold() in new_names:
                raise ValueError(
                    "Rename map entries must have unique original and target filenames."
                )
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
