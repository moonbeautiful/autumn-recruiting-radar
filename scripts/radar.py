#!/usr/bin/env python3
"""Deterministic job matching, cross-source dedupe, change and expiry tracking."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REQUIRED_FIELDS = (
    "company",
    "title",
    "city",
    "graduation_year",
    "employment_type",
    "published_at",
    "deadline",
    "source_status",
    "source_url",
    "source_name",
    "source_tier",
    "fetched_at",
)

LIST_FIELDS = (
    "requirements",
    "match_evidence",
    "highlights",
    "alternate_sources",
)

EMPLOYMENT_LABELS = {
    "campus": "校招",
    "internship": "实习",
    "conversion": "实习转正",
}

STATUS_ORDER = {"new": 0, "changed": 1, "seen": 2, "expired": 3}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def normalize(value: Any) -> str:
    text = str(value or "").lower().strip()
    return re.sub(r"[\s/|,，、·._\-—（）()【】\[\]]+", "", text)


def stable_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    if all(isinstance(item, dict) for item in value):
        unique = {
            json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in value
        }
        return [unique[key] for key in sorted(unique)]
    return sorted({str(item).strip() for item in value if str(item).strip()})


def parse_iso_date(value: str) -> date | None:
    if value == "unknown":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def valid_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def clean_url(url: str, volatile_prefixes: Iterable[str]) -> str:
    parts = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not any(key.lower().startswith(prefix) for prefix in volatile_prefixes)
    ]
    kept.sort()
    return urlunsplit(
        (parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(kept), "")
    )


def validate_preferences(preferences: Any) -> Dict[str, Any]:
    if not isinstance(preferences, dict):
        raise ValueError("preferences must be a JSON object")
    if preferences.get("onboarded") is not True:
        raise ValueError("preferences are not onboarded; complete the five setup questions")
    list_fields = (
        "graduation_years",
        "role_keywords",
        "cities",
        "employment_types",
        "company_preferences",
        "industry_preferences",
    )
    output = dict(preferences)
    for field in list_fields:
        value = output.get(field, [])
        if not isinstance(value, list):
            raise ValueError(f"preferences.{field} must be an array")
        output[field] = [str(item).strip() for item in value if str(item).strip()]
    invalid_types = set(output["employment_types"]) - set(EMPLOYMENT_LABELS)
    if invalid_types:
        raise ValueError(
            "preferences.employment_types contains unsupported values: "
            + ", ".join(sorted(invalid_types))
        )
    return output


def normalize_alternate_sources(value: Any, prefixes: Iterable[str]) -> List[Dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("alternate_sources must be an array")
    output: Dict[str, Dict[str, str]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("alternate_sources items must be objects")
        name = str(item.get("source_name", "")).strip()
        url = str(item.get("source_url", "")).strip()
        tier = str(item.get("source_tier", "")).strip()
        if not name or not valid_http_url(url) or not tier:
            raise ValueError("alternate source requires name, HTTP(S) URL, and tier")
        cleaned = clean_url(url, prefixes)
        output[cleaned] = {
            "source_name": name,
            "source_url": cleaned,
            "source_tier": tier,
        }
    return [output[key] for key in sorted(output)]


def validate_job(
    raw: Any,
    index: int,
    project: Dict[str, Any],
) -> Tuple[Dict[str, Any] | None, str | None]:
    if not isinstance(raw, dict):
        return None, f"{index}: job must be an object"
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        return None, f"{index}: missing required fields: {', '.join(missing)}"

    job = dict(raw)
    for field in REQUIRED_FIELDS:
        if job[field] is None or str(job[field]).strip() == "":
            return None, f"{index}: {field} must not be empty"
        job[field] = str(job[field]).strip()

    if not valid_http_url(job["source_url"]):
        return None, f"{index}: source_url must be an absolute HTTP(S) URL"

    source_ranks = project["source_ranks"]
    if job["source_tier"] not in source_ranks:
        return None, (
            f"{index}: source_tier must be one of "
            f"{', '.join(sorted(source_ranks))} (aggregators/media are not allowed)"
        )
    if job["employment_type"] not in EMPLOYMENT_LABELS:
        return None, f"{index}: unsupported employment_type"
    if job["source_status"] not in ("open", "closed", "unknown"):
        return None, f"{index}: source_status must be open, closed, or unknown"

    for field in ("published_at", "deadline"):
        if job[field] != "unknown" and parse_iso_date(job[field]) is None:
            return None, f"{index}: {field} must be YYYY-MM-DD or unknown"

    prefixes = project["deduplication"]["volatile_query_prefixes"]
    job["source_url"] = clean_url(job["source_url"], prefixes)
    for field in ("requirements", "match_evidence", "highlights", "requirement_keywords"):
        job[field] = stable_list(job.get(field, []))
    job["salary"] = str(job.get("salary", "unknown") or "unknown").strip() or "unknown"
    try:
        job["alternate_sources"] = normalize_alternate_sources(
            job.get("alternate_sources", []), prefixes
        )
    except ValueError as exc:
        return None, f"{index}: {exc}"
    job["_input_index"] = index
    return job, None


def preference_values(preferences: Dict[str, Any], field: str) -> List[str]:
    return [str(item).strip() for item in preferences.get(field, []) if str(item).strip()]


def includes_any(haystack: str, needles: Iterable[str]) -> List[str]:
    normalized_haystack = normalize(haystack)
    return [needle for needle in needles if normalize(needle) in normalized_haystack]


def match_job(
    job: Dict[str, Any],
    preferences: Dict[str, Any],
    project: Dict[str, Any],
) -> Tuple[bool, int, List[str]]:
    cfg = project["matching"]
    graduation_years = preference_values(preferences, "graduation_years")
    role_keywords = preference_values(preferences, "role_keywords")
    cities = preference_values(preferences, "cities")
    employment_types = preference_values(preferences, "employment_types")
    company_preferences = preference_values(preferences, "company_preferences")
    industry_preferences = preference_values(preferences, "industry_preferences")

    score = 0
    reasons: List[str] = []
    corpus = " ".join(
        [
            job["company"],
            job["title"],
            job["city"],
            " ".join(job["requirements"]),
            " ".join(job.get("requirement_keywords", [])),
            " ".join(job["match_evidence"]),
            " ".join(job["highlights"]),
        ]
    )

    if graduation_years:
        if job["graduation_year"] in graduation_years:
            score += int(cfg["graduation_year_weight"])
            reasons.append(f"届次匹配：{job['graduation_year']}")
        elif job["graduation_year"] == "unknown" and cfg.get(
            "allow_unknown_graduation_year", False
        ):
            reasons.append("届次待核验")
        else:
            return False, 0, []

    if role_keywords:
        matched_roles = includes_any(corpus, role_keywords)
        if not matched_roles:
            return False, 0, []
        score += int(cfg["role_weight"])
        reasons.append(f"岗位匹配：{' / '.join(matched_roles)}")

    if cities:
        nationwide = includes_any(job["city"], cfg.get("nationwide_city_terms", []))
        matched_cities = includes_any(job["city"], cities)
        if not nationwide and not matched_cities:
            return False, 0, []
        score += int(cfg["city_weight"])
        reasons.append(
            "城市匹配：全国/多地"
            if nationwide
            else f"城市匹配：{' / '.join(matched_cities)}"
        )

    if employment_types:
        if job["employment_type"] not in employment_types:
            return False, 0, []
        score += int(cfg["employment_type_weight"])
        reasons.append(f"类型匹配：{EMPLOYMENT_LABELS[job['employment_type']]}")

    company_hits = includes_any(corpus, company_preferences)
    industry_hits = includes_any(corpus, industry_preferences)
    if company_hits:
        score += int(cfg["company_preference_weight"])
        reasons.append(f"公司偏好：{' / '.join(company_hits)}")
    if industry_hits:
        score += int(cfg["industry_preference_weight"])
        reasons.append(f"行业偏好：{' / '.join(industry_hits)}")

    if job["source_tier"] == "official":
        score += int(cfg["official_source_weight"])
        reasons.append("企业招聘官网")
    elif job["source_tier"] in ("official_wechat", "platform"):
        score += int(cfg["platform_source_weight"])
        reasons.append("可核验招聘来源")

    return True, score, reasons


def canonical_value(field: str, value: Any, project: Dict[str, Any]) -> str:
    text = str(value or "")
    dedupe = project["deduplication"]
    if field == "company":
        for suffix in dedupe.get("company_suffixes", []):
            text = text.replace(str(suffix), "")
    elif field == "title":
        for pattern in dedupe.get("title_noise_patterns", []):
            text = re.sub(str(pattern), "", text, flags=re.IGNORECASE)
    elif field == "city":
        parts = [
            normalize(part)
            for part in re.split(r"[/|,，、]+", text)
            if normalize(part)
        ]
        return "/".join(sorted(set(parts)))
    return normalize(text)


def canonical_key(job: Dict[str, Any], project: Dict[str, Any]) -> str:
    fields = project["deduplication"]["key_fields"]
    payload = "|".join(
        canonical_value(field, job.get(field, ""), project) for field in fields
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_record(job: Dict[str, Any]) -> Dict[str, str]:
    return {
        "source_name": job["source_name"],
        "source_url": job["source_url"],
        "source_tier": job["source_tier"],
    }


def merge_alternate_sources(
    winner: Dict[str, Any],
    loser: Dict[str, Any],
) -> None:
    candidates = (
        winner.get("alternate_sources", [])
        + loser.get("alternate_sources", [])
        + [source_record(loser)]
    )
    merged: Dict[str, Dict[str, str]] = {}
    for item in candidates:
        if item["source_url"] == winner["source_url"]:
            continue
        merged[item["source_url"]] = item
    winner["alternate_sources"] = [merged[key] for key in sorted(merged)]


def select_deduplicated(
    jobs: List[Dict[str, Any]],
    project: Dict[str, Any],
    rejected: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    selected: Dict[str, Dict[str, Any]] = {}
    ranks = project["source_ranks"]
    for job in jobs:
        key = canonical_key(job, project)
        incumbent = selected.get(key)
        if incumbent is None:
            selected[key] = job
            continue
        current_rank = (int(ranks[job["source_tier"]]), int(job["score"]))
        incumbent_rank = (
            int(ranks[incumbent["source_tier"]]),
            int(incumbent["score"]),
        )
        if current_rank > incumbent_rank:
            merge_alternate_sources(job, incumbent)
            rejected.append(
                {
                    "index": str(incumbent.get("_input_index", "unknown")),
                    "reason": "duplicate replaced by stronger source",
                }
            )
            selected[key] = job
        else:
            merge_alternate_sources(incumbent, job)
            rejected.append(
                {
                    "index": str(job.get("_input_index", "unknown")),
                    "reason": "duplicate ignored; stronger source retained",
                }
            )
    return list(selected.values())


def stable_value(value: Any) -> Any:
    if isinstance(value, list):
        return stable_list(value)
    if isinstance(value, dict):
        return {key: stable_value(value[key]) for key in sorted(value)}
    return str(value)


def snapshot(job: Dict[str, Any], project: Dict[str, Any]) -> Dict[str, Any]:
    fields = project["change_detection"]["fields"]
    return {field: stable_value(job.get(field, "")) for field in fields}


def fingerprint(snap: Dict[str, Any]) -> str:
    payload = json.dumps(snap, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def changed_fields(previous: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
    fields = sorted(set(previous) | set(current))
    return [field for field in fields if previous.get(field) != current.get(field)]


def expiry_reason(
    job: Dict[str, Any],
    run_day: date,
    project: Dict[str, Any],
) -> str | None:
    cfg = project["deadline"]
    if cfg.get("auto_expire_on_closed_status") and job["source_status"] == "closed":
        return "source_marked_closed"
    deadline = parse_iso_date(job["deadline"])
    if cfg.get("auto_expire_on_past_deadline") and deadline and deadline < run_day:
        return "deadline_passed"
    return None


def ending_soon(job: Dict[str, Any], run_day: date, project: Dict[str, Any]) -> bool:
    deadline = parse_iso_date(job["deadline"])
    if not deadline:
        return False
    days = (deadline - run_day).days
    return 0 <= days <= int(project["deadline"].get("ending_soon_days", 3))


def expire_historical(
    seen: Dict[str, Any],
    current_keys: set[str],
    run_day: date,
    run_date: str,
    project: Dict[str, Any],
) -> List[Dict[str, Any]]:
    newly_expired: List[Dict[str, Any]] = []
    for key, entry in seen.items():
        if key in current_keys or entry.get("current_status") == "expired":
            continue
        snap = entry.get("snapshot", {})
        deadline = parse_iso_date(str(snap.get("deadline", "unknown")))
        if (
            project["deadline"].get("auto_expire_on_past_deadline")
            and deadline
            and deadline < run_day
        ):
            entry["current_status"] = "expired"
            entry["expired_on"] = run_date
            entry["expired_reason"] = "deadline_passed"
            newly_expired.append({**snap, **state_metadata(entry), "status": "expired"})
    return newly_expired


def prune_expired_state(
    seen: Dict[str, Any],
    run_day: date,
    retention_days: int,
) -> None:
    if retention_days <= 0:
        return
    for key, entry in list(seen.items()):
        if entry.get("current_status") != "expired":
            continue
        expired_on = parse_iso_date(str(entry.get("expired_on", "unknown")))
        if expired_on and (run_day - expired_on).days > retention_days:
            del seen[key]


def state_metadata(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "first_seen": entry.get("first_seen", ""),
        "last_seen": entry.get("last_seen", ""),
        "expired_on": entry.get("expired_on", ""),
        "expired_reason": entry.get("expired_reason", ""),
    }


def markdown_escape(value: Any) -> str:
    if isinstance(value, list):
        value = "；".join(str(item) for item in value)
    return str(value).replace("|", r"\|").replace("\n", " ")


def report_table(jobs: List[Dict[str, Any]]) -> str:
    if not jobs:
        return "| - | 暂无 | - | - | - | - | - | - | - | - | - |\n"
    rows = []
    for job in jobs:
        source = f"{job['source_name']}（{job['source_tier']}）"
        changes = " / ".join(job.get("changed_fields", [])) or "-"
        status = job["status"] + (" / 即将截止" if job.get("ending_soon") else "")
        rows.append(
            "| {status} | {company} | [{title}]({url}) | {city} | {kind} | "
            "{salary} | {deadline} | {source} | {keywords} | {highlights} | {changes} |".format(
                status=markdown_escape(status),
                company=markdown_escape(job["company"]),
                title=markdown_escape(job["title"]),
                url=job["source_url"],
                city=markdown_escape(job["city"]),
                kind=EMPLOYMENT_LABELS[job["employment_type"]],
                salary=markdown_escape(job.get("salary", "unknown")),
                deadline=job["deadline"],
                source=markdown_escape(source),
                keywords=markdown_escape(job.get("requirement_keywords") or ["-"]),
                highlights=markdown_escape(job["highlights"] or ["-"]),
                changes=markdown_escape(changes),
            )
        )
    return "\n".join(rows) + "\n"


def report_markdown(
    run_date: str,
    jobs: List[Dict[str, Any]],
    rejected: List[Dict[str, str]],
    newly_expired: List[Dict[str, Any]],
) -> str:
    groups = {
        status: [job for job in jobs if job["status"] == status]
        for status in ("new", "changed", "seen")
    }
    lines = [
        f"# 秋招信息增量报告 · {run_date}",
        "",
        f"- 本次有效岗位：{len(jobs)}",
        f"- 今日新增：{len(groups['new'])}",
        f"- 有变化：{len(groups['changed'])}",
        f"- 已见岗位：{len(groups['seen'])}",
        f"- 本次截止归档：{len(newly_expired)}",
        f"- 拒绝/重复：{len(rejected)}",
        "",
    ]
    for heading, status in (
        ("今日新增", "new"),
        ("有变化", "changed"),
        ("已见岗位", "seen"),
    ):
        lines.extend(
            [
                f"## {heading}",
                "",
                "| 状态 | 公司 | 岗位 | 城市 | 招聘类型 | 薪资待遇 | 截止时间 | 信息来源 | 岗位关键词 | 岗位亮点 | 变化字段 |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                report_table(groups[status]).rstrip(),
                "",
            ]
        )
    lines.extend(["## 拒绝或重复", ""])
    if rejected:
        lines.extend(
            f"- `{markdown_escape(item['index'])}` {markdown_escape(item['reason'])}"
            for item in rejected
        )
    else:
        lines.append("- 暂无")
    return "\n".join(lines) + "\n"


def chat_markdown(
    run_date: str,
    jobs: List[Dict[str, Any]],
    chat_statuses: set[str],
) -> str:
    pushed = [job for job in jobs if job["status"] in chat_statuses]
    new_count = sum(job["status"] == "new" for job in pushed)
    changed_count = sum(job["status"] == "changed" for job in pushed)
    lines = [
        f"## 今日岗位更新 · {run_date}",
        "",
        f"本次新增 {new_count} 个，变化 {changed_count} 个。",
        "",
    ]
    if not pushed:
        lines.append("本次没有找到符合条件的新增或变化岗位。")
        return "\n".join(lines) + "\n"

    def display(value: Any) -> str:
        text = str(value)
        return "未注明" if text == "unknown" else text

    for index, job in enumerate(pushed, start=1):
        status = "新增" if job["status"] == "new" else "有变化"
        lines.extend(
            [
                f"### {index}. {job['company']}｜{job['title']}（{status}）",
                "",
                f"- 城市：{display(job['city'])}",
                f"- 招聘类型：{EMPLOYMENT_LABELS[job['employment_type']]}",
                f"- 薪资待遇：{display(job.get('salary', 'unknown'))}",
                f"- 发布时间：{display(job['published_at'])}",
                f"- 截止时间：{display(job['deadline'])}",
                f"- 岗位关键词：{'、'.join(job.get('requirement_keywords', [])) if job.get('requirement_keywords') else '未注明'}",
                f"- 岗位亮点：{'；'.join(job['highlights']) if job['highlights'] else '未注明'}",
                f"- 信息来源：[{job['source_name']}]({job['source_url']})",
            ]
        )
        if job.get("changed_fields"):
            lines.append(f"- 本次变化：{' / '.join(job['changed_fields'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_csv(path: Path, jobs: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "status",
        "changed_fields",
        "score",
        "company",
        "title",
        "city",
        "graduation_year",
        "employment_type",
        "salary",
        "published_at",
        "deadline",
        "source_status",
        "source_name",
        "source_tier",
        "source_url",
        "requirement_keywords",
        "highlights",
        "match_reason",
        "fetched_at",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for job in jobs:
            row = dict(job)
            for field in ("changed_fields", "highlights", "requirement_keywords"):
                row[field] = "；".join(row.get(field, []))
            writer.writerow(row)


def run(args: argparse.Namespace) -> Dict[str, Any]:
    input_path = Path(args.input).expanduser().resolve()
    preferences_path = Path(args.preferences).expanduser().resolve()
    project_path = Path(args.project_config).expanduser().resolve()
    state_dir = Path(args.state_dir).expanduser().resolve()
    run_date = args.date or date.today().isoformat()
    run_day = date.fromisoformat(run_date)

    raw_jobs = read_json(input_path)
    preferences = validate_preferences(read_json(preferences_path))
    project = read_json(project_path)
    seen: Dict[str, Any] = read_json(state_dir / "seen.json", {})
    if not isinstance(raw_jobs, list):
        raise ValueError("input must be a JSON array")
    if not isinstance(project, dict):
        raise ValueError("project config must be a JSON object")
    if not isinstance(seen, dict):
        raise ValueError("seen.json must be a JSON object")

    rejected: List[Dict[str, str]] = []
    matched: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_jobs):
        job, error = validate_job(raw, index, project)
        if error:
            rejected.append({"index": str(index), "reason": error.split(": ", 1)[-1]})
            continue
        assert job is not None
        is_match, score, reasons = match_job(job, preferences, project)
        if not is_match:
            continue
        job["score"] = score
        job["match_reasons"] = reasons
        job["match_reason"] = "；".join(reasons)
        matched.append(job)

    matched = select_deduplicated(matched, project, rejected)
    output_jobs: List[Dict[str, Any]] = []
    current_keys: set[str] = set()
    newly_expired: List[Dict[str, Any]] = []

    for job in matched:
        key = canonical_key(job, project)
        current_keys.add(key)
        snap = snapshot(job, project)
        digest = fingerprint(snap)
        previous = seen.get(key)
        reason = expiry_reason(job, run_day, project)

        if previous is None:
            first_seen = run_date
            previous_snapshot: Dict[str, Any] = {}
        else:
            first_seen = previous.get("first_seen", run_date)
            previous_snapshot = previous.get("snapshot", {})

        new_expiry = bool(
            reason and (previous is None or previous.get("current_status") != "expired")
        )
        if reason:
            status = "expired"
            changes = changed_fields(previous_snapshot, snap) if previous else []
        elif previous is None or previous.get("current_status") == "expired":
            status = "new"
            changes = []
        elif previous.get("fingerprint") != digest:
            status = "changed"
            changes = changed_fields(previous_snapshot, snap)
        else:
            status = "seen"
            changes = []

        entry = {
            "first_seen": first_seen,
            "last_seen": run_date,
            "current_status": status,
            "fingerprint": digest,
            "snapshot": snap,
        }
        if reason:
            entry["expired_on"] = run_date
            entry["expired_reason"] = reason
        seen[key] = entry

        job["status"] = status
        job["changed_fields"] = changes
        job["ending_soon"] = ending_soon(job, run_day, project)
        job.pop("_input_index", None)
        if status == "expired" and new_expiry:
            newly_expired.append(
                {**job, "expired_on": run_date, "expired_reason": reason}
            )
        else:
            output_jobs.append(job)

    newly_expired.extend(
        expire_historical(seen, current_keys, run_day, run_date, project)
    )
    prune_expired_state(
        seen,
        run_day,
        int(project.get("retention", {}).get("expired_days", 180)),
    )

    output_jobs.sort(
        key=lambda item: (
            STATUS_ORDER[item["status"]],
            -int(item["score"]),
            item["company"],
            item["title"],
        )
    )
    expired_jobs = []
    for entry in seen.values():
        if entry.get("current_status") != "expired":
            continue
        expired_jobs.append(
            {
                **entry.get("snapshot", {}),
                **state_metadata(entry),
                "status": "expired",
            }
        )
    expired_jobs.sort(
        key=lambda item: (
            item.get("expired_on", ""),
            str(item.get("company", "")),
            str(item.get("title", "")),
        ),
        reverse=True,
    )

    state_dir.mkdir(parents=True, exist_ok=True)
    write_json(state_dir / "jobs.json", output_jobs)
    write_json(state_dir / "seen.json", seen)
    write_json(state_dir / "expired.json", expired_jobs)
    write_json(state_dir / "rejected.json", rejected)
    write_csv(state_dir / "jobs.csv", output_jobs)

    daily_path = state_dir / "daily" / f"{run_date}.md"
    outbox_path = state_dir / "outbox" / f"{run_date}.md"
    daily_path.parent.mkdir(parents=True, exist_ok=True)
    outbox_path.parent.mkdir(parents=True, exist_ok=True)
    chat_statuses = set(project["reports"].get("chat_statuses", ["new", "changed"]))
    daily_path.write_text(
        report_markdown(
            run_date,
            output_jobs,
            rejected,
            newly_expired,
        ),
        encoding="utf-8",
    )
    chat_text = chat_markdown(run_date, output_jobs, chat_statuses)
    outbox_path.write_text(chat_text, encoding="utf-8")

    result = {
        "run_date": run_date,
        "matched": len(output_jobs),
        "new": sum(job["status"] == "new" for job in output_jobs),
        "changed": sum(job["status"] == "changed" for job in output_jobs),
        "seen": sum(job["status"] == "seen" for job in output_jobs),
        "expired_now": len(newly_expired),
        "expired_total": len(expired_jobs),
        "rejected": len(rejected),
        "daily": str(daily_path),
        "outbox": str(outbox_path),
    }
    has_update = (result["new"] + result["changed"]) > 0
    if args.output_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.heartbeat and not has_update:
        # Heartbeat mode: stay silent when there is nothing new or changed,
        # so a scheduled run only speaks up on real updates.
        pass
    else:
        print(chat_text, end="")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("run")
    command.add_argument("--input", required=True)
    command.add_argument("--preferences", required=True)
    command.add_argument("--project-config", required=True)
    command.add_argument("--state-dir", required=True)
    command.add_argument("--date")
    command.add_argument(
        "--output-format",
        choices=("chat", "json"),
        default="chat",
    )
    command.add_argument(
        "--heartbeat",
        action="store_true",
        help="stay silent when there is no new or changed job (for scheduled runs)",
    )
    command.set_defaults(func=run)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
