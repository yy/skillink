"""Find user configuration independently of the tool checkout or working directory."""

import os
from pathlib import Path


def manifest_path(explicit: Path | None = None) -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = explicit or os.environ.get("SKILLINK_MANIFEST")
    path = Path(path) if path else config_home / "skillink/skills.toml"
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(
            f"manifest not found: {path}. Link your manifest here, "
            "set SKILLINK_MANIFEST, or pass --manifest /path/to/skills.toml"
        )
    return resolved
