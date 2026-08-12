#!/usr/bin/env python3
"""End-to-end regression tests for dedupe, changes, expiry, and daily runs."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict


SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_DIR / "references" / "fixtures"
PROJECT_CONFIG = SKILL_DIR / "config" / "project.json"


def run_snapshot(
    input_path: Path,
    state_dir: Path,
    run_date: str,
    preferences: Path = FIXTURES / "preferences.json",
    project_config: Path = PROJECT_CONFIG,
) -> Dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "scripts" / "radar.py"),
            "run",
            "--input",
            str(input_path),
            "--preferences",
            str(preferences),
            "--project-config",
            str(project_config),
            "--state-dir",
            str(state_dir),
            "--date",
            run_date,
            "--output-format",
            "json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def status_counts(state_dir: Path) -> Dict[str, int]:
    counts = {"new": 0, "changed": 0, "seen": 0}
    for job in read_json(state_dir / "jobs.json"):
        counts[job["status"]] += 1
    return counts


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="autumn-tracker-test-") as temp:
        root = Path(temp)
        state_dir = root / "state"

        first = run_snapshot(
            FIXTURES / "jobs-baseline.json",
            state_dir,
            "2026-08-11",
        )
        assert first["matched"] == 2
        assert first["new"] == 2
        assert first["changed"] == 0
        assert first["seen"] == 0
        assert first["expired_now"] == 0
        assert first["rejected"] == 2
        assert status_counts(state_dir) == {"new": 2, "changed": 0, "seen": 0}

        jobs = read_json(state_dir / "jobs.json")
        ali = next(job for job in jobs if job["company"] == "阿里巴巴")
        assert ali["source_tier"] == "official"
        assert ali["source_url"] == "https://campus.example.com/alibaba/ai-pm"
        assert len(ali["alternate_sources"]) == 1
        assert ali["alternate_sources"][0]["source_tier"] == "platform"

        first_report = (state_dir / "daily" / "2026-08-11.md").read_text(
            encoding="utf-8"
        )
        for heading in (
            "招聘类型",
            "薪资待遇",
            "截止时间",
            "信息来源",
            "岗位关键词",
            "岗位亮点",
            "变化字段",
        ):
            assert heading in first_report

        second = run_snapshot(
            FIXTURES / "jobs-baseline.json",
            state_dir,
            "2026-08-11",
        )
        assert second["new"] == 0
        assert second["changed"] == 0
        assert second["seen"] == 2
        second_outbox = (state_dir / "outbox" / "2026-08-11.md").read_text(
            encoding="utf-8"
        )
        assert "本次没有找到符合条件的新增或变化岗位" in second_outbox
        assert "阿里巴巴" not in second_outbox

        third = run_snapshot(
            FIXTURES / "jobs-changed.json",
            state_dir,
            "2026-08-12",
        )
        assert third["new"] == 1
        assert third["changed"] == 1
        assert third["seen"] == 1
        assert third["expired_now"] == 1
        assert third["expired_total"] == 1
        assert third["rejected"] == 0
        assert status_counts(state_dir) == {"new": 1, "changed": 1, "seen": 1}

        jobs = read_json(state_dir / "jobs.json")
        ali = next(job for job in jobs if job["company"] == "阿里巴巴")
        assert ali["status"] == "changed"
        assert "deadline" in ali["changed_fields"]
        assert "highlights" in ali["changed_fields"]
        assert "salary" in ali["changed_fields"]
        expired = read_json(state_dir / "expired.json")
        assert any(job["company"] == "腾讯" for job in expired)

        third_outbox = (state_dir / "outbox" / "2026-08-12.md").read_text(
            encoding="utf-8"
        )
        assert "联想" in third_outbox
        assert "阿里巴巴" in third_outbox
        assert "字节跳动" not in third_outbox
        assert "腾讯" not in third_outbox
        assert "薪资待遇" in third_outbox
        assert "岗位关键词" in third_outbox

        fourth = run_snapshot(
            FIXTURES / "jobs-changed.json",
            state_dir,
            "2026-08-12",
        )
        assert fourth["new"] == 0
        assert fourth["changed"] == 0
        assert fourth["seen"] == 3
        assert fourth["expired_now"] == 0
        assert fourth["expired_total"] == 1

        expiry_state = root / "expiry-state"
        run_snapshot(
            FIXTURES / "jobs-baseline.json",
            expiry_state,
            "2026-08-11",
        )
        empty_input = root / "empty.json"
        empty_input.write_text("[]\n", encoding="utf-8")
        historical_expiry = run_snapshot(
            empty_input,
            expiry_state,
            "2026-08-16",
        )
        assert historical_expiry["expired_now"] == 1
        expired = read_json(expiry_state / "expired.json")
        assert any(
            job["company"] == "阿里巴巴"
            and job["expired_reason"] == "deadline_passed"
            for job in expired
        )
        expiry_outbox = (expiry_state / "outbox" / "2026-08-16.md").read_text(
            encoding="utf-8"
        )
        assert "阿里巴巴" not in expiry_outbox

        daily_root = root / "daily"
        daily_root.mkdir()
        preferences_path = daily_root / "preferences.json"
        preferences_path.write_text(
            (FIXTURES / "preferences.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        input_path = daily_root / "jobs.json"
        input_path.write_text(
            (FIXTURES / "jobs-changed.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        project = read_json(PROJECT_CONFIG)
        project["paths"] = {
            "input": str(input_path),
            "preferences": str(preferences_path),
            "state_dir": str(daily_root / "state"),
        }
        project_path = daily_root / "project.json"
        project_path.write_text(
            json.dumps(project, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        daily_completed = subprocess.run(
            [
                sys.executable,
                str(SKILL_DIR / "scripts" / "run_daily.py"),
                "--project-config",
                str(project_path),
                "--date",
                "2026-08-12",
                "--skip-collector",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        daily_outbox = daily_root / "state" / "outbox" / "2026-08-12.md"
        assert daily_outbox.exists()
        chat_output = daily_outbox.read_text(encoding="utf-8")
        assert "今日岗位更新" in chat_output
        assert "信息来源" in chat_output
        assert daily_completed.stdout == chat_output

        # Heartbeat mode: silent when nothing new/changed, speaks up on updates.
        heartbeat_state = root / "heartbeat-state"

        def run_heartbeat(input_path: Path, run_date: str) -> str:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_DIR / "scripts" / "radar.py"),
                    "run",
                    "--input",
                    str(input_path),
                    "--preferences",
                    str(FIXTURES / "preferences.json"),
                    "--project-config",
                    str(PROJECT_CONFIG),
                    "--state-dir",
                    str(heartbeat_state),
                    "--date",
                    run_date,
                    "--heartbeat",
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            return completed.stdout

        first_beat = run_heartbeat(FIXTURES / "jobs-baseline.json", "2026-08-11")
        assert "今日岗位更新" in first_beat
        silent_beat = run_heartbeat(FIXTURES / "jobs-baseline.json", "2026-08-11")
        assert silent_beat.strip() == ""

        # Aggregator/media sources (source_tier other) must be rejected.
        other_state = root / "other-state"
        other_input = root / "other.json"
        other_input.write_text(
            json.dumps(
                [
                    {
                        "company": "示例公司",
                        "title": "AI产品经理",
                        "city": "杭州",
                        "graduation_year": "2027",
                        "employment_type": "campus",
                        "published_at": "2026-08-01",
                        "deadline": "2026-09-01",
                        "source_status": "open",
                        "source_url": "https://www.offershow.cn/jobs/table",
                        "source_name": "OfferShow 聚合页",
                        "source_tier": "other",
                        "fetched_at": "2026-08-11T08:00:00+08:00",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        other_result = run_snapshot(other_input, other_state, "2026-08-11")
        assert other_result["matched"] == 0
        assert other_result["rejected"] == 1

    print("PASS: official-source cross-source dedupe")
    print("PASS: new -> seen and changed -> seen state transitions")
    print("PASS: changed_fields and new/changed-only chat output")
    print("PASS: closed-source and historical deadline expiry")
    print("PASS: salary/keyword columns and salary change detection")
    print("PASS: heartbeat stays silent without updates, speaks on updates")
    print("PASS: aggregator/media source_tier rejected")
    print("PASS: portable daily runner prints chat-ready results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
