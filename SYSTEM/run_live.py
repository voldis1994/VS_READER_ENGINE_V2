#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from engine.core.lifecycle import run_live_main
from engine.core.paths import SystemPaths

CONFIG_RELATIVE_PATH = Path("config") / "system.json"


def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parent


def _sync_config_root_path(config_path: Path, project_root: Path) -> None:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    system = payload.get("system")
    if not isinstance(system, dict):
        return

    desired_root = str(project_root.resolve())
    current_root = str(Path(str(system.get("root_path", ""))).expanduser().resolve())
    if current_root == desired_root:
        return

    system["root_path"] = desired_root
    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Updated config system.root_path -> {desired_root}",
        file=sys.stderr,
    )


def setup_only(project_root: Path | None = None) -> int:
    root = project_root or _resolve_project_root()
    config_path = root / CONFIG_RELATIVE_PATH
    if not config_path.is_file():
        print(f"setup failed: config file not found at {config_path}", file=sys.stderr)
        return 1

    _sync_config_root_path(config_path, root)
    SystemPaths(root).ensure_directories()
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--setup-only":
        return setup_only()

    project_root = _resolve_project_root()
    config_path = project_root / CONFIG_RELATIVE_PATH
    if not config_path.is_file():
        print(
            f"startup failed: config file not found at {config_path}",
            file=sys.stderr,
        )
        return 1

    _sync_config_root_path(config_path, project_root)
    return run_live_main(root_path=project_root, config_path=config_path)


if __name__ == "__main__":
    sys.exit(main())
