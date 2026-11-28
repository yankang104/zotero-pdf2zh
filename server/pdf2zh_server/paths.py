"""Stable installation and data paths, independent of application module locations."""

from dataclasses import dataclass
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent / "web"


@dataclass(frozen=True)
class ServerPaths:
    root: Path = SERVER_ROOT
    output: Path | None = None

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root))
        object.__setattr__(
            self,
            "output",
            Path(self.output) if self.output is not None else self.root / "translated",
        )

    @property
    def config_paths(self):
        return {
            "pdf2zh_next": str(self.root / "config" / "config.toml"),
            "venv": str(self.root / "config" / "venv.json"),
        }

    @property
    def web(self):
        return WEB_ROOT
