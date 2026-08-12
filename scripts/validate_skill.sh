#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR=$(cd "$(dirname "$0")/.." && pwd)

python3 - "$SKILL_DIR" <<'PY'
import json,re,sys
from pathlib import Path

root=Path(sys.argv[1])
skill=(root/"SKILL.md").read_text(encoding="utf-8")
assert skill.startswith('---\nname: "autumn-recruitment-tracker-pro"\n')
match=re.search(r'^description: "(.+)"\n---$', skill, re.M)
assert match, "missing frontmatter description"
assert "Invoke when" in match.group(1)
assert len(match.group(1)) < 200

required=[
    "README.md",
    "config/project.json",
    "config/user-preferences.example.json",
    "references/configuration.md",
    "references/data-contract.md",
    "references/source-strategy.md",
    "references/fixtures/preferences.json",
    "references/fixtures/jobs-baseline.json",
    "references/fixtures/jobs-changed.json",
    "scripts/bootstrap.py",
    "scripts/radar.py",
    "scripts/run_daily.py",
    "scripts/schedule_task.py",
    "scripts/test_radar.py",
]
for relative in required:
    assert (root/relative).is_file(), relative

for path in root.rglob("*.json"):
    json.loads(path.read_text(encoding="utf-8"))

for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)', skill):
    if "://" in link or link.startswith("#"):
        continue
    assert (root/link).exists(), f"broken relative link: {link}"

project=json.loads((root/"config/project.json").read_text(encoding="utf-8"))
assert "source_ranks" in project
assert "change_detection" in project
assert "deadline" in project
assert "collector" in project

preferences=json.loads(
    (root/"config/user-preferences.example.json").read_text(encoding="utf-8")
)
for field in [
    "graduation_years",
    "role_keywords",
    "cities",
    "employment_types",
    "company_preferences",
    "industry_preferences",
    "schedule",
]:
    assert field in preferences, field
print("structure/frontmatter/links/json/config-boundary: OK")
PY

python3 -m py_compile \
  "$SKILL_DIR/scripts/bootstrap.py" \
  "$SKILL_DIR/scripts/radar.py" \
  "$SKILL_DIR/scripts/run_daily.py" \
  "$SKILL_DIR/scripts/schedule_task.py" \
  "$SKILL_DIR/scripts/test_radar.py"

python3 "$SKILL_DIR/scripts/test_radar.py"
echo "autumn-recruitment-tracker-pro: VALID"
