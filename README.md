# 秋招信息搜集 Skill

**简体中文** | [English](README.en.md)

面向中国大陆校招、实习和实习转正的岗位搜集 Skill：在支持联网的 AI 客户端里，按你的届次、岗位、城市和公司类型实时搜出在招岗位，优先回企业招聘官网核验，自动跨来源去重、做字段级变化检测与截止归档，只把新增和有变化的有效岗位直接回复到当前聊天。

## 快速开始

1. **拿到 Skill**：`git clone https://github.com/moonbeautiful/autumn-recruiting-radar` 到本地，或复制整个目录到你的项目。
2. **在支持联网搜索的 AI 客户端里唤起它**（Trae、Claude 等）：直接说“帮我搜集秋招岗位”即可。首次会用弹窗/提问确认你的毕业届次、目标岗位、城市、招聘类型和公司类型，无需手动编辑任何 JSON。
3. **零依赖**：脚本是纯 Python 3.8+ 标准库，Windows / macOS / Linux 通用，不装第三方包、不控制浏览器、不产生任何费用。
4. **想先本地验证**（可选）：

   ```bash
   python3 scripts/bootstrap.py            # 初始化 runtime/
   bash   scripts/validate_skill.sh        # 跑内置 8 项验收，全绿即可用
   ```

> 岗位发现由对话中的 AI 用宿主自带联网搜索实时完成；若客户端无联网能力，Skill 会如实提示你换一个支持联网的客户端，绝不编造岗位。详见 [SKILL.md](SKILL.md)。

## 核心能力

- 首次使用默认询问目标城市；
- 输出薪资待遇、招聘类型、发布时间、截止时间、来源、岗位关键词和岗位亮点；
- 只接受企业官网 / 官方公众号 / 招聘平台三类来源，拒绝聚合导流页和媒体链接；
- 同一岗位跨官网、公众号和招聘平台去重；
- 保存字段快照，识别具体发生变化的字段；
- 只推送新增和有变化的有效岗位；
- 官方页面关闭或截止日期过去时自动归档；
- 历史岗位即使本次未再次发现，也会按已知截止日期自动归档；
- 用户偏好、项目策略和运行状态严格分离；
- 搜集完成后直接把新增和变化岗位回复到当前聊天；
- 可选“更新通知（心跳）”：允许后每次重跑只在有新增/变化时才回复，不做系统通知。

## 跨平台与跨模型

面向开源分发，任何人可克隆到自己电脑安装：

- 脚本是纯 Python 3.8+ 标准库，Windows / macOS / Linux 通用，无系统专有命令、无写死路径；
- 发现岗位只用宿主客户端自带的后台联网搜索 / 网页读取能力：不额外安装工具、不控制用户浏览器、不产生额外费用；主流 AI 客户端（Trae、Claude 等）都自带，用户零操作；
- 万一客户端没有任何联网能力，就如实提示用户在支持联网的客户端里再运行，绝不凭记忆编造岗位；
- 通知采用“重跑 + 与历史对比”的心跳，不依赖任何一个操作系统的通知机制。

## 目录

```text
秋招信息搜集skill/
├── SKILL.md
├── README.md
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

首次执行 `bootstrap.py` 后才会创建 `runtime/`。该目录保存用户偏好、候选岗位和运行状态，不属于可分发模板。

## 配置边界

用户可以通过对话修改：

- 毕业届次；
- 目标岗位；
- 目标城市；
- 校招、实习、实习转正；
- 想找哪类公司（互联网大厂 / AI独角兽·大模型 / 垂类·行业 / 都要）及额外公司、行业偏好；
- 用户主动要求定时时的每日执行时间。

> 发现是**深度优先、一次一家**：先按“城市＋岗位＋公司类型”**实时搜出公司队列**（只排顺序），再**从第一家开始逐家深挖——把这家所有符合条件的岗位挖全、交付，再问要不要下一家**，用户随时可喊停；具体公司名单不写死，由运行时搜索得到。只用宿主自带联网搜索、不操控浏览器。详见 [SKILL.md](SKILL.md) 第 1 步与 [source-strategy.md](references/source-strategy.md)。

维护者配置：

- 来源优先级；
- 匹配权重；
- 去重主键；
- 变化字段；
- 截止判断；
- 深度优先发现参数（`discovery`：队列顺序、每家岗位数上限、单家内部并发上限、雇主排序锚点）；
- 后台搜集命令；
- 状态保留和聊天清单规则。

详见 [references/configuration.md](references/configuration.md)。

## 快速验收

```bash
cd "/path/to/秋招信息搜集skill"
bash scripts/validate_skill.sh
```

验收覆盖：

- 官网优先的跨来源去重；
- 首次新增、再次已见；
- 岗位变化及具体变化字段；
- 官网明确关闭；
- 历史截止日期自动过期；
- 已见和已截止岗位不进入聊天清单；
- 完整岗位字段进入聊天清单；
- 默认命令直接输出可回复到聊天的结果。

## 手动运行

初始化：

```bash
python3 scripts/bootstrap.py
```

Agent 完成首次问答后，应更新 `runtime/user-preferences.json`，再按 `SKILL.md` 搜集公开岗位并写入 `runtime/inbox/jobs-input.json`。

处理候选岗位：

```bash
python3 scripts/radar.py run \
  --input runtime/inbox/jobs-input.json \
  --preferences runtime/user-preferences.json \
  --project-config config/project.json \
  --state-dir runtime/state
```

命令输出就是要回复给用户的内容。`runtime/state/daily/` 和 `outbox/` 只承担内部状态和追溯，不要求用户打开。

## 定时运行

`run_daily.py` 支持两种模式：

1. 当前 Agent 已经写好最新候选岗位时，直接处理输入；
2. 项目配置了后台可执行的 `collector.command` 时，先搜集再处理。

测试现有输入：

```bash
python3 scripts/run_daily.py \
  --project-config config/project.json \
  --skip-collector
```

首次运行、给出岗位清单后，会再问一次“岗位有新增或变化时是否允许通知”。允许则把偏好里的 `notify_on_update` 设为 `true`；用户之后说“不想要通知了”就改回 `false`，随时可反复开关。开启后，每次重跑本 Skill（可用宿主定时能力触发）只在有新增/变化时把清单发到当前聊天，没更新就安静，不做系统通知/邮件/Webhook：

```bash
python3 scripts/run_daily.py \
  --project-config config/project.json --heartbeat
```

想要“每天固定时间自动推送”时：优先用宿主客户端自带的定时能力；宿主没有时，可用跨平台脚本注册操作系统原生定时任务（macOS launchd / Linux cron / Windows 计划任务），路径按运行时解析、不绑定任何设备：

```bash
python3 scripts/schedule_task.py --action print   --time 08:00  # 预览（安全，不改系统）
python3 scripts/schedule_task.py --action install --time 08:00  # 确认后安装到本机
python3 scripts/schedule_task.py --action remove                # 卸载
```

两条真实限制须如实告知用户：① 系统定时只在电脑**开机**时触发，关机不补跑；② 定时任务默认只重新处理已有输入（去重/变化/截止），本身不联网搜岗。**新岗发现由“会话开始即自动联网增量搜集”承担，对所有用户零配置零成本，因此 `config/project.json` 的 `collector.command` 默认留空且应保持留空（见其 `command_note`），不要为让定时任务搜新岗而硬编分发。** 都不满足时，退回“下次来用即自动增量刷新，或主动说‘查一下’”，不用系统任务伪装成云端推送。

## 输出状态

- `new`：首次出现；
- `changed`：稳定字段发生变化；
- `seen`：已出现且本次无变化；
- `expired`：官网明确关闭或截止日期已过去；
- `rejected`：字段、URL或枚举不符合数据合同。

聊天只返回 `new` 和 `changed`。重复岗位、已见岗位和已截止岗位不会反复出现。

## 安全边界

- 只访问公开招聘页面；
- 不保存 Cookie、账号密码或私密联系人信息；
- 不绕过登录、验证码、反爬和访问限制；
- 日期未知时写 `unknown`；
- 投递前回到企业招聘官网确认。
