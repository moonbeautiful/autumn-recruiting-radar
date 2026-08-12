# Autumn Recruiting Radar

[简体中文](README.md) | **English**

An AI-agent Skill for tracking campus-recruitment, internship, and intern-to-fulltime openings (focused on mainland China). Inside any web-capable AI client, it searches live openings by your graduation year, target roles, cities, and company type; prefers to verify against employers' official career pages; then automatically deduplicates across sources, performs field-level change detection and deadline archiving, and replies only the new and changed valid jobs straight into the current chat.

## Quick start

1. **Get the Skill**: `git clone https://github.com/moonbeautiful/autumn-recruiting-radar`, or copy the whole directory into your project.
2. **Invoke it inside a web-capable AI client** (Trae, Claude, etc.): just say "help me collect autumn-recruiting jobs." On first use it confirms your graduation year, target roles, cities, employment types, and company type via prompts — no manual JSON editing.
3. **Zero dependencies**: pure Python 3.8+ standard library, works on Windows / macOS / Linux; installs nothing, never drives your browser, costs nothing.
4. **Verify locally first (optional)**:

   ```bash
   python3 scripts/bootstrap.py            # initialize runtime/
   bash   scripts/validate_skill.sh        # run the built-in 8 checks; all green = ready
   ```

> Job discovery is performed live by the AI in-conversation using the host client's own web search. If the client has no web access, the Skill honestly tells you to switch to a web-capable client and never fabricates jobs. See [SKILL.md](SKILL.md).

## Core capabilities

- Asks for target cities by default on first use;
- Outputs salary, employment type, publish date, deadline, source, requirement keywords, and highlights;
- Accepts only three source tiers — employer official site / official WeChat account / recruiting platform — and rejects aggregator landing pages and media links;
- Deduplicates the same job across official site, WeChat, and platforms;
- Stores field snapshots and identifies exactly which fields changed;
- Pushes only new and changed valid jobs;
- Auto-archives when the official page closes or the deadline has passed;
- Auto-archives historical jobs by their known deadline even if not re-discovered this run;
- Strictly separates user preferences, project strategy, and runtime state;
- Replies new and changed jobs directly into the current chat after collection;
- Optional "update notification (heartbeat)": once enabled, each re-run replies only when there is something new/changed — no OS notifications.

## Cross-platform & cross-model

Built for open-source distribution; anyone can clone and install it:

- Scripts are pure Python 3.8+ standard library, uniform across Windows / macOS / Linux, with no OS-specific commands and no hardcoded paths;
- Discovery uses only the host client's built-in background web search / page reading: no extra tools, no browser control, no added cost; mainstream AI clients (Trae, Claude, etc.) ship this, so users do nothing;
- If the client has no web access at all, it honestly asks the user to re-run in a web-capable client and never fabricates jobs from memory;
- Notifications use a "re-run + compare against history" heartbeat, relying on no single OS's notification mechanism.

## Layout

```text
autumn-recruiting-radar/
├── SKILL.md
├── README.md            # 简体中文
├── README.en.md         # English
├── LICENSE
├── config/
│   ├── project.json
│   └── user-preferences.example.json
├── references/
│   ├── configuration.md
│   ├── data-contract.md
│   ├── source-strategy.md
│   └── fixtures/
└── scripts/
    ├── bootstrap.py
    ├── radar.py
    ├── run_daily.py
    ├── schedule_task.py
    ├── test_radar.py
    └── validate_skill.sh
```

`runtime/` is created only after the first `bootstrap.py` run. It holds user preferences, candidate jobs, and runtime state, and is not part of the distributable template.

## Configuration boundary

Users can change via conversation:

- Graduation year;
- Target roles;
- Target cities;
- Campus / internship / intern-to-fulltime;
- Which company type (big-tech / AI unicorn·LLM / vertical·industry / all) plus extra company & industry preferences;
- The daily run time, only when the user explicitly asks for scheduling.

> Discovery is two-staged and streamed: first build a **live company queue** by "city + role + company type", then **verify company by company, delivering each as it finishes**; the user can stop anytime. The company list is never hardcoded — it comes from the live search. See Step 1 in [SKILL.md](SKILL.md) and [source-strategy.md](references/source-strategy.md).

Maintainer-only configuration:

- Source priority;
- Matching weights;
- Dedupe key;
- Change-detection fields;
- Deadline rules;
- Staged streaming-discovery params (`discovery`: queue order, per-batch company count, concurrency cap, employer ranking anchors);
- Background collector command;
- State retention and chat-list rules.

See [references/configuration.md](references/configuration.md).

## Quick validation

```bash
cd "/path/to/autumn-recruiting-radar"
bash scripts/validate_skill.sh
```

Coverage:

- Official-first cross-source dedupe;
- First-seen `new`, later `seen`;
- Job changes and the exact changed fields;
- Official page explicitly closed;
- Historical deadline auto-expiry;
- Seen and expired jobs excluded from the chat list;
- Full job fields present in the chat list;
- Default command outputs chat-ready results.

## Manual run

Initialize:

```bash
python3 scripts/bootstrap.py
```

After the agent finishes the first-use Q&A, it should update `runtime/user-preferences.json`, then collect public jobs per `SKILL.md` and write them to `runtime/inbox/jobs-input.json`.

Process candidates:

```bash
python3 scripts/radar.py run \
  --input runtime/inbox/jobs-input.json \
  --preferences runtime/user-preferences.json \
  --project-config config/project.json \
  --state-dir runtime/state
```

The command's output is exactly what should be replied to the user. `runtime/state/daily/` and `outbox/` are internal state/audit only; users need not open them.

## Scheduled run

`run_daily.py` supports two modes:

1. When the current agent has already written the latest candidates, process the input directly;
2. When the project configures a background-executable `collector.command`, collect first, then process.

Test existing input:

```bash
python3 scripts/run_daily.py \
  --project-config config/project.json \
  --skip-collector
```

After the first run and job list, it asks once whether notifications are allowed on new/changed jobs. If yes, set `notify_on_update` to `true` in preferences; the user can flip it back to `false` anytime by saying "stop notifying." Once on, each re-run of the Skill (which the host's scheduler can trigger) replies to the current chat only when there is something new/changed, staying silent otherwise — no OS notifications / email / webhook:

```bash
python3 scripts/run_daily.py \
  --project-config config/project.json --heartbeat
```

For "auto-push at a fixed time each day": prefer the host client's own scheduling; if the host has none, use the cross-platform script to register an OS-native scheduled task (macOS launchd / Linux cron / Windows Task Scheduler). Paths are resolved at runtime and bound to no device:

```bash
python3 scripts/schedule_task.py --action print   --time 08:00  # preview (safe, no system change)
python3 scripts/schedule_task.py --action install --time 08:00  # install after confirmation
python3 scripts/schedule_task.py --action remove                # uninstall
```

Two honest limits to tell users: ① an OS scheduled task fires only while the computer is **powered on** and does not catch up after shutdown; ② by default a scheduled run only re-processes existing input — discovering **brand-new jobs** without anyone in the chat still requires the AI's live search, so new-job discovery genuinely happens when someone is using the AI. Do not disguise an OS task as cloud auto-push. (New-job discovery is designed to happen at "session start auto incremental collection," so `collector.command` is intentionally left empty; see SKILL.md Step 6.)

## Output statuses

- `new`: first appearance;
- `changed`: a stable field changed;
- `seen`: appeared before, unchanged this run;
- `expired`: official page explicitly closed, or deadline passed;
- `rejected`: fields, URL, or enum violate the data contract.

Chat returns only `new` and `changed`. Duplicate, seen, and expired jobs never repeat.

## Safety boundary

- Accesses only public recruiting pages;
- Stores no cookies, passwords, or private contact info;
- Does not bypass login, captcha, anti-scraping, or rate limits;
- Writes `unknown` when a date is unknown;
- Always re-confirm on the employer's official career page before applying.
