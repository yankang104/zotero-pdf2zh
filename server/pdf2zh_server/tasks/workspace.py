"""Isolate uploads, engine configuration and outputs for one PDF operation."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path

_PUBLISH_LOCK = threading.Lock()


class JobWorkspace:
    def __init__(self, output_root):
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.jobs_root = self.output_root / ".jobs"
        self.jobs_root.mkdir(exist_ok=True)
        self.jobs_root = self._within(self.jobs_root, self.output_root)
        self.root = Path(tempfile.mkdtemp(prefix="job-", dir=self.jobs_root))
        self.input_dir = self.root / "input"
        self.output_dir = self.root / "output"
        self.config_dir = self.root / "config"
        for directory in (self.input_dir, self.output_dir, self.config_dir):
            directory.mkdir()
        self._published = {}

    @staticmethod
    def _within(path, parent):
        resolved = Path(path).resolve()
        if resolved == parent or not resolved.is_relative_to(parent):
            raise ValueError("Task path is outside its workspace")
        return resolved

    def upload(self, filename, content):
        if (
            not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or os.path.basename(filename) != filename
        ):
            raise ValueError("Invalid PDF filename")
        path = self._within(self.input_dir / filename, self.root.resolve())
        path.write_bytes(content)
        return str(path)

    def copy_input(self, source):
        path = self._within(self.input_dir / Path(source).name, self.root.resolve())
        shutil.copyfile(source, path)
        return str(path)

    def publish(self, paths):
        """Publish flat basenames without replacing an earlier job's PDF."""
        result = []
        for source in paths:
            source = self._within(source, self.root.resolve())
            if not source.is_file():
                continue
            key = str(source)
            if key in self._published:
                result.append(self._published[key])
                continue
            with _PUBLISH_LOCK:
                name = source.name
                candidate = self.output_root / name
                index = 0
                while True:
                    # The semantic PDF suffix stays at the end. Both old
                    # plugins and the download route continue to use a basename.
                    if index:
                        prefix = self.root.name
                        if index > 1:
                            prefix += f"-{index}"
                        candidate = self.output_root / f"{prefix}-{name}"
                    candidate = self._within(candidate, self.output_root)
                    created = False
                    try:
                        with candidate.open("xb") as target:
                            created = True
                            with source.open("rb") as data:
                                shutil.copyfileobj(data, target)
                        break
                    except FileExistsError:
                        index += 1
                    except Exception:
                        # Only this call's exclusively-created file is removed.
                        if created:
                            candidate.unlink(missing_ok=True)
                        raise
                published = str(candidate)
                self._published[key] = published
                result.append(published)
        return result

    def cleanup(self):
        if not self.root.exists():
            return
        # Check the final absolute path before any recursive deletion, including
        # on Windows. A replaced/symlinked workspace must never escape .jobs.
        jobs_root = self._within(self.jobs_root, self.output_root)
        target = self._within(self.root, jobs_root)
        if not target.name.startswith("job-"):
            raise ValueError("Invalid task workspace")
        shutil.rmtree(target)
