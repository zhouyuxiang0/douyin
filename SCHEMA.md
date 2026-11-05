# 结构化输出约定

`dy-cli` 在 `--json-output` 模式下使用统一信封，便于 AI Agent 与脚本解析。

## 输出通道

- **stdout** 只承载数据：TTY 模式下是表格，`--json-output` 模式下是且仅是一个 JSON 文档
- **stderr** 承载进度、状态与错误提示（`ℹ` / `✓` / `⚠` / `✗`）
- 因此 `dy trending --json-output | jq .data` 可直接使用

## 成功

```json
{
  "ok": true,
  "schema_version": "1",
  "data": ...
}
```

`data` 为该命令的结果：`trending` / `live list` / `account list` 等为数组，`search` / `detail` / `status` 等为对象（API 类命令保留原始字段）。

## 失败

一般错误退出码为 `1`。`--json-output` 模式下 stdout 输出错误信封，否则 stderr 输出 `✗ message`。视频发布或核验尚未完全确认时也可能返回退出码 `2`，并保留带业务状态的 `data` 信封；此时不得因 `ok: true` 而认定已发布，更不能自动重发。

```json
{
  "ok": false,
  "schema_version": "1",
  "error": { "code": "not_authenticated", "message": "未登录，请先运行: dy login" }
}
```

| `error.code` | 含义 |
|---|---|
| `not_authenticated` | 未登录 / Cookie 失效 / 登录超时 |
| `invalid_argument` | 参数无效、短索引越界、文件不存在 |
| `api_error` | 抖音 API 请求失败 |
| `playwright_error` | 浏览器自动化失败 |
| `action_failed` | 互动操作未生效（未找到按钮 / 输入框） |
| `not_found` | 账号或配置项不存在 |
| `not_live` | 直播间未开播 |
| `missing_dependency` | 缺少外部依赖（如 ffmpeg） |

以上是 `dy_cli.utils.envelope.ERROR_CODES` 中的通用错误。视频发布还会返回 `invalid_receipt`、`unsafe_receipt`、`run_in_progress`、`missing_covers`、`unsupported_schedule`、`media_changed`、`cover_changed` 等具体流程错误；消费者应保留未知错误码并停止自动提交。

## 支持 `--json-output` 的命令

| 类别 | 命令 | `data` 形态 |
|---|---|---|
| 查询 | `search` `detail` `comments` `trending` `live list` `live info` `profile` `analytics` `notifications` | API 原始结果 |
| | `download` | `{video_url, music_url, images, desc, author, aweme_id, quality, available_qualities}`；`quality` 在 `-q auto`（默认）或无画质信息时为 `null`；`available_qualities` 按分辨率、码率降序，每项 `{label, gear_name, bit_rate, width, height, codec}` |
| 账号态 | `status` | `{authenticated, reason, account, cookie_file}`，`reason` ∈ `null` / `no_cookie` / `expired` / `check_failed` |
| | `me` | `{authenticated: true, account, cookie_file}` |
| | `login` | `{authenticated: true, method, account, cookie_file}`，`method` ∈ `existing` / `browser` / `qrcode`；已登录时不再交互询问 |
| | `logout` | `{logged_out, account, cookie_file}` |
| | `account list` | `[{name, cookie_file, has_cookie, is_default}]` |
| 变更 | `publish`（视频） | 发布凭据，包含 `status`、`spec`、提交标记及可用的作品/核验信息；`--dry-run` 时为预览参数 |
| 核验 | `publish-verify` | 更新后的发布凭据；不上传、不重发，但会写入本地凭据文件 |
| 变更 | `publish`（图文） | 旧流程结果；其 `published` 返回值不提供视频流程的核验保证 |
| | `like` `favorite` `comment` `follow` | `{action, aweme_id \| sec_user_id, success: true}` |

`detail --comments --json-output` 返回 `{detail, comments}`；评论加载失败时 `comments` 为 `null` 并在 stderr 给出警告。

视频凭据的 `status` 包括 `prepared`（已保存草稿）、`submitting`、`reviewing`、`published`、`submitted_unverified`、`verification_failed`，也可能保留 `unknown` 或 `unavailable` 平台状态。只有 `published` 表示已通过 CLI 的发布核验；截图视觉质量仍需审看。详见[发布与核验](references/publishing.md)。

## 尚无 `--json-output` 的命令

`init`、`live record`、`account add / remove / default`、`config *` — 均为交互式或纯本地操作。
