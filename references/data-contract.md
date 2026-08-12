# 数据合同

## 用户偏好

```json
{
  "schema_version": 1,
  "onboarded": true,
  "graduation_years": ["2027"],
  "role_keywords": ["AI产品", "AI运营", "AI解决方案"],
  "cities": ["北京", "上海", "杭州"],
  "employment_types": ["campus", "conversion"],
  "company_preferences": ["互联网大厂", "AI创业公司"],
  "industry_preferences": ["人工智能", "企业服务"],
  "schedule": {
    "enabled": true,
    "time": "08:00",
    "timezone": "Asia/Shanghai",
    "notify_on_update": true
  }
}
```

空数组表示该维度不限制。`employment_types` 只能使用：

- `campus`：正式校招；
- `internship`：普通实习；
- `conversion`：实习转正。

`schedule.notify_on_update` 为 `true` 时，定时运行只在有新增或变化岗位时把清单发到对话（心跳推送）；没有更新则保持安静。

## 岗位输入

`runtime/inbox/jobs-input.json` 是 JSON 数组，每项字段如下：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `company` | 是 | 公司名称 |
| `title` | 是 | 岗位名称 |
| `city` | 是 | 城市，多城市用` / `分隔；未知写`unknown` |
| `graduation_year` | 是 | 如`2027`；未知写`unknown` |
| `employment_type` | 是 | `campus`、`internship`或`conversion` |
| `published_at` | 是 | `YYYY-MM-DD`或`unknown` |
| `deadline` | 是 | `YYYY-MM-DD`或`unknown` |
| `source_status` | 是 | `open`、`closed`或`unknown` |
| `source_url` | 是 | 可核验的绝对 HTTP(S) URL |
| `source_name` | 是 | 来源名称 |
| `source_tier` | 是 | `official`、`official_wechat`或`platform`（不接受聚合/媒体，无`other`档） |
| `salary` | 否 | 薪资待遇原文，如`25-40K·15薪`；未知写`unknown` |
| `requirements` | 否 | 岗位要求原文要点数组 |
| `requirement_keywords` | 否 | 从岗位要求中提炼的重要关键词数组 |
| `match_evidence` | 否 | 支持岗位匹配的原文片段数组 |
| `highlights` | 否 | 岗位亮点数组 |
| `alternate_sources` | 否 | 其他来源对象数组 |
| `fetched_at` | 是 | ISO 8601 时间 |

示例：

```json
{
  "company": "示例科技",
  "title": "AI产品经理-校园招聘",
  "city": "北京 / 杭州",
  "graduation_year": "2027",
  "employment_type": "campus",
  "published_at": "2026-08-10",
  "deadline": "2026-09-30",
  "source_status": "open",
  "source_url": "https://jobs.example.com/campus/123",
  "source_name": "示例科技校园招聘官网",
  "source_tier": "official",
  "salary": "25-40K·15薪",
  "requirements": ["参与AI产品需求分析", "能够独立完成原型"],
  "requirement_keywords": ["大模型", "Agent", "数据分析"],
  "match_evidence": ["2027届", "AI产品经理"],
  "highlights": ["接受非技术专业", "提供业务轮岗"],
  "alternate_sources": [
    {
      "source_name": "牛客校招",
      "source_url": "https://www.nowcoder.com/jobs/123",
      "source_tier": "platform"
    }
  ],
  "fetched_at": "2026-08-11T08:00:00+08:00"
}
```

## 去重主键

跨来源去重不使用 URL。默认由以下标准化字段组成：

- 公司；
- 岗位名称；
- 城市；
- 届次；
- 招聘类型。

同一岗位在官网和聚合平台同时出现时，保留来源等级更高的记录，并把其他链接合并进 `alternate_sources`。

主键标准化会：

- 去除公司名中的常见工商后缀；
- 去除岗位名中的届次、校园招聘等展示噪声；
- 将多城市拆分、标准化并排序；
- 保留届次和招聘类型，避免把校招与实习误合并。

## 变化检测

参与变化检测的字段由 `config/project.json` 固定。默认包括：

- 城市；
- 届次；
- 招聘类型；
- 薪资待遇；
- 发布时间；
- 截止时间；
- 页面开放状态；
- 主来源名称、等级和链接；
- 岗位要求；
- 岗位关键词；
- 匹配证据；
- 岗位亮点。

`fetched_at` 不参与变化检测，否则每次抓取都会误报。输出的 `changed_fields` 必须给出发生变化的字段名。

## 截止识别

满足任一条件即标记 `expired`：

1. `source_status` 为 `closed`；
2. `deadline` 是有效日期且早于本次运行日期；
3. 历史状态中的截止日期已经过去，即使本次没有再次发现该岗位。

`deadline` 等于运行日期时，当天仍视为有效。没有明确日期且页面状态不明时，不得猜测为截止。

## 输出

- `jobs.json`：本次匹配且仍有效的岗位；
- `expired.json`：本次或历史自动识别为截止的岗位；
- `seen.json`：跨次状态、指纹和快照；
- `rejected.json`：不满足合同的输入；
- `daily/*.md`：完整内部快照；
- `outbox/*.md`：仅新增和变化且未截止的聊天清单副本。

JSON 使用 UTF-8 和两个空格缩进。CSV 使用 UTF-8 BOM。

默认命令必须把 `outbox` 的同一份内容直接输出到标准输出，由 Agent 原样回复当前聊天。文件不是用户交互入口。
