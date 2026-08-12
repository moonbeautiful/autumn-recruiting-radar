#!/usr/bin/env python3
"""Create runtime directories and a user preference file without overwriting data."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = SKILL_DIR / "runtime"
PREFERENCES = RUNTIME_DIR / "user-preferences.json"
PREFERENCES_EXAMPLE = SKILL_DIR / "config" / "user-preferences.example.json"


def main() -> int:
    for relative in ("inbox", "state/daily", "state/outbox"):
        (RUNTIME_DIR / relative).mkdir(parents=True, exist_ok=True)

    if not PREFERENCES.exists():
        shutil.copyfile(PREFERENCES_EXAMPLE, PREFERENCES)
        print(f"created: {PREFERENCES}")
    else:
        json.loads(PREFERENCES.read_text(encoding="utf-8"))
        print(f"kept: {PREFERENCES}")

    input_path = RUNTIME_DIR / "inbox" / "jobs-input.json"
    if not input_path.exists():
        input_path.write_text("[]\n", encoding="utf-8")
        print(f"created: {input_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
