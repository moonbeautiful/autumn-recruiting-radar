#!/usr/bin/env python3
"""Cross-platform daily scheduler for the autumn recruiting radar.

This replicates the "定点运行 / 每天固定时间推送" flow by registering an
OS-native scheduled task that re-runs the skill's daily entry point:

  - macOS   -> a per-user launchd agent (~/Library/LaunchAgents)
  - Linux   -> a crontab line for the current user
  - Windows -> a Scheduled Task via schtasks

Design principles (this is an open-source, redistributable skill):
  - Nothing is hardcoded to one machine. Paths are resolved at runtime from
    this file's location, so every user who clones the repo gets their own
    correct paths.
  - The time is chosen by the user, not baked into the template.
  - The default action is "print" (dry-run): it only shows what WOULD be
    installed, causing no side effects, so a caller can preview safely.

Honesty note about what a scheduled run can and cannot do:
  A bare scheduled run of run_daily.py only RE-PROCESSES the existing input
  (dedupe, change detection, deadline expiry). To actually RE-SEARCH the web
  for new postings on a schedule, the host must expose a background-capable
  agent command in project.json -> collector.command. If that is empty, the
  scheduled task can still expire past-deadline jobs and re-emit changes, but
  it cannot discover brand-new jobs on its own.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
LABEL = "com.autumn-recruiting-radar.daily"
CRON_TAG = "# autumn-recruiting-radar"


def parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":")
        hour, minute = int(hour_text), int(minute_text)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError("time must be HH:MM (24h), e.g. 08:00")
    return hour, minute


def daily_command(project_config: Path) -> list[str]:
    """The command the scheduler fires each day."""
    return [
        sys.executable,
        str(SKILL_DIR / "scripts" / "run_daily.py"),
        "--project-config",
        str(project_config),
        "--heartbeat",
    ]


def shell_join(parts: list[str]) -> str:
    quoted = []
    for part in parts:
        if any(ch.isspace() for ch in part) or '"' in part:
            quoted.append('"' + part.replace('"', '\\"') + '"')
        else:
            quoted.append(part)
    return " ".join(quoted)


# --------------------------------------------------------------------------- #
# macOS: launchd
# --------------------------------------------------------------------------- #
def macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def macos_plist_text(hour: int, minute: int, project_config: Path) -> str:
    args = daily_command(project_config)
    program_args = "\n".join(f"    <string>{arg}</string>" for arg in args)
    log_path = SKILL_DIR / "runtime" / "state" / "schedule.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{program_args}
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>{hour}</integer>
    <key>Minute</key><integer>{minute}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>{log_path}</string>
  <key>StandardErrorPath</key>
  <string>{log_path}</string>
</dict>
</plist>
"""


def macos_install(hour: int, minute: int, project_config: Path) -> None:
    plist = macos_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    (SKILL_DIR / "runtime" / "state").mkdir(parents=True, exist_ok=True)
    plist.write_text(macos_plist_text(hour, minute, project_config), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist)], check=False,
                   capture_output=True)
    subprocess.run(["launchctl", "load", str(plist)], check=True)
    print(f"installed launchd agent: {plist}")
    print(f"daily at {hour:02d}:{minute:02d} (local time)")


def macos_remove() -> None:
    plist = macos_plist_path()
    if plist.exists():
        subprocess.run(["launchctl", "unload", str(plist)], check=False,
                       capture_output=True)
        plist.unlink()
        print(f"removed launchd agent: {plist}")
    else:
        print("no launchd agent installed")


def macos_status() -> None:
    plist = macos_plist_path()
    print(f"plist: {plist} ({'present' if plist.exists() else 'absent'})")
    result = subprocess.run(["launchctl", "list"], check=False,
                            capture_output=True, text=True)
    print("loaded" if LABEL in result.stdout else "not loaded")


def macos_print(hour: int, minute: int, project_config: Path) -> None:
    print(f"# macOS launchd agent -> {macos_plist_path()}")
    print(macos_plist_text(hour, minute, project_config))
    print("# load with: launchctl load " + str(macos_plist_path()))


# --------------------------------------------------------------------------- #
# Linux: cron
# --------------------------------------------------------------------------- #
def cron_line(hour: int, minute: int, project_config: Path) -> str:
    return f"{minute} {hour} * * * {shell_join(daily_command(project_config))} {CRON_TAG}"


def cron_current() -> list[str]:
    result = subprocess.run(["crontab", "-l"], check=False,
                            capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines()]


def cron_write(lines: list[str]) -> None:
    payload = "\n".join(line for line in lines if line.strip()) + "\n"
    subprocess.run(["crontab", "-"], input=payload, text=True, check=True)


def cron_install(hour: int, minute: int, project_config: Path) -> None:
    lines = [line for line in cron_current() if CRON_TAG not in line]
    lines.append(cron_line(hour, minute, project_config))
    cron_write(lines)
    print(f"installed crontab entry, daily at {hour:02d}:{minute:02d} (local time)")


def cron_remove() -> None:
    lines = [line for line in cron_current() if CRON_TAG not in line]
    cron_write(lines)
    print("removed crontab entry")


def cron_status() -> None:
    present = any(CRON_TAG in line for line in cron_current())
    print("crontab entry: " + ("present" if present else "absent"))


def cron_print(hour: int, minute: int, project_config: Path) -> None:
    print("# Linux crontab line (add via `crontab -e`):")
    print(cron_line(hour, minute, project_config))


# --------------------------------------------------------------------------- #
# Windows: schtasks
# --------------------------------------------------------------------------- #
TASK_NAME = "AutumnRecruitingRadar"


def windows_command(project_config: Path) -> str:
    return shell_join(daily_command(project_config))


def windows_install(hour: int, minute: int, project_config: Path) -> None:
    subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "DAILY",
         "/ST", f"{hour:02d}:{minute:02d}", "/TR", windows_command(project_config),
         "/F"],
        check=True,
    )
    print(f"created scheduled task {TASK_NAME}, daily at {hour:02d}:{minute:02d}")


def windows_remove() -> None:
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=False)
    print(f"deleted scheduled task {TASK_NAME}")


def windows_status() -> None:
    result = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                            check=False, capture_output=True, text=True)
    print("task: " + ("present" if result.returncode == 0 else "absent"))


def windows_print(hour: int, minute: int, project_config: Path) -> None:
    print("# Windows Scheduled Task (run in a terminal):")
    print(shell_join(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "DAILY",
         "/ST", f"{hour:02d}:{minute:02d}", "/TR", windows_command(project_config),
         "/F"]
    ))


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--action", choices=("print", "install", "remove", "status"),
                        default="print",
                        help="print (dry-run, default), install, remove, or status")
    parser.add_argument("--time", type=parse_hhmm, default="09:00",
                        help="daily local time as HH:MM (default 09:00)")
    parser.add_argument("--project-config",
                        default=str(SKILL_DIR / "config" / "project.json"))
    args = parser.parse_args()

    hour, minute = args.time
    project_config = Path(args.project_config).expanduser().resolve()
    system = platform.system()

    handlers = {
        "Darwin": (macos_print, macos_install, macos_remove, macos_status),
        "Linux": (cron_print, cron_install, cron_remove, cron_status),
        "Windows": (windows_print, windows_install, windows_remove, windows_status),
    }
    if system not in handlers:
        print(f"error: unsupported platform {system!r}; schedule manually",
              file=sys.stderr)
        return 1

    do_print, do_install, do_remove, do_status = handlers[system]
    try:
        if args.action == "print":
            do_print(hour, minute, project_config)
        elif args.action == "install":
            do_install(hour, minute, project_config)
        elif args.action == "remove":
            do_remove()
        else:
            do_status()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
