# dy-cli 定制版

基于 [Youhai020616/douyin](https://github.com/Youhai020616/douyin) 的 `5267065` 提交维护，当前版本 **0.2.3+zhou.1**。保留搜索、下载、热榜、直播、互动和数据接口，加入实际使用中的视频发布改进与 Windows 兼容处理。

本仓库仅提供 dy。原项目的普通 PyPI 安装不会带上这些定制改动，请从本仓库安装。

## Windows 安装

准备 **Google Chrome、Git 和 uv**。建议使用 Python 3.12，uv 可在本机缺少该版本时安装。uv 安装方式见[官方说明](https://docs.astral.sh/uv/getting-started/installation/)。在 PowerShell 执行：

```powershell
uv tool install --python 3.12 "git+https://github.com/zhouyuxiang0/douyin.git"
uv tool update-shell
```

重新打开终端和 AI 工具，让它们读取更新后的 PATH，然后检查：

```powershell
Get-Command dy
dy --version
dy --help
dy init --no-proxy --skip-login
```

版本应包含 `0.2.3+zhou.1`。初始化会实际启动并关闭系统 Chrome，不下载 Playwright 专用 Chromium；最后一条命令会保存本机配置，但不会登录或发布。已有 dy 时先确认 `Get-Command dy` 指向哪个环境，再在确认要替换后给安装命令加 `--force`，避免调用到旧版。

由用户运行 `dy login` 完成扫码，然后使用 `dy status --json-output` 检查登录状态。每台电脑独立登录；仓库不包含 Cookie、发布会话或个人配置。

如果使用下载的源码 ZIP，装好 Python 3.10+ 和 Chrome 后，在解压目录运行 `setup.bat`。它会创建独立 `.venv`；之后直接运行 `.venv\Scripts\dy.exe`，或在命令提示符中执行 `.venv\Scripts\activate.bat`。macOS/Linux 的源码安装入口仍为 `bash setup.sh`。

## 交给其他电脑上的 AI

将本仓库链接和下面这段话交给能运行本机终端的 AI：

> 按 README 安装这个 dy-cli 定制版，核对命令路径、版本和 Chrome 启动。复用本机已有依赖；已有 dy 时先说明将替换哪个版本。完成后让我扫码登录，不执行发布、评论、点赞或关注操作。操作前阅读仓库的 SKILL.md 和相关发布说明。

AI 可以直接调用 `dy`，无需额外的 MCP 服务。操作约定在 [SKILL.md](SKILL.md)；机器可读结果使用 `--json-output`。需要助手自动发现 dy 操作指南时，可用其技能安装功能安装本仓库自带的 `douyin` 技能，这与 CLI 安装是两个步骤。

## 本版改动

- 独立横竖封面、准确话题选择、完整文案回读和可见范围检查。
- 发布前预览、持久化凭据、草稿恢复、作品结果核验与防重复提交。
- 等待封面异步保存稳定，保留预览后变化检测。
- 所有浏览器入口使用系统 Chrome；保留 30 分钟扫码等待，不全局终止其他浏览器窗口。
- Windows 使用原生字节范围文件锁，macOS/Linux 保留 flock；统一跨平台系统信息与 UTF-8 凭据读取。
- 当前视频流程明确拒绝尚未验证的定时发布；图文发布仍沿用旧流程，不继承视频流程的全部核验保证。

## 命令

### 搜索与查看

```bash
dy search "关键词"                        # 搜索视频
dy search "咖啡" --sort 最多点赞          # 按点赞排序
dy search "风景" --type atlas             # 搜索图文
dy search "日食记" --type user            # 搜索用户
dy search "AI" -o results.csv            # 导出为 CSV
dy read 1                                # 查看第 1 条结果（短索引）
dy detail AWEME_ID                       # 按 ID 查看详情
dy comments 1                            # 查看评论（Playwright）
```

### 下载

```bash
dy dl 1                                  # 按短索引下载
dy download https://v.douyin.com/xxx     # 按分享链接下载
dy download 1234567890 --music           # 同时下载背景音乐
dy dl 1 --list-quality                   # 列出可用画质
dy dl 1 -q 720                           # 指定画质 (best/worst/2160/1440/1080/720/540)
dy dl SEC_USER_ID --user --limit 20      # 批量下载该用户作品
dy dl SEC_USER_ID --user -q 1080         # 批量下载并指定画质
```

### 热榜与直播

```bash
dy trending                              # 热榜 Top 50
dy trending --count 10 -o hot.json       # 导出前 10 条
dy trending --watch                      # 每 5 分钟自动刷新
dy live list                             # 推荐直播间
dy live list --count 10                  # 显示 10 个直播间
dy live info ROOM_ID                     # 直播间信息
dy live record ROOM_ID                   # 使用 ffmpeg 录制
```

### 发布

```powershell
dy publish -t "已确认标题" --content-file description.txt -v final.mp4 --thumbnail-horizontal cover-4x3.png --thumbnail-vertical cover-3x4.png --tags 科普 --visibility 公开 --receipt publication.json --review --json-output
dy publish --resume publication.json --review --json-output
dy publish-verify publication.json --json-output
```

`--dry-run` 仅检查本地参数，`--prepare-only` 会上传并保存草稿。视频必须提供双封面或通用 `--thumbnail`；当前视频流程不支持定时发布，传入定时参数会停止。发布结果未知时只核验，不重复投稿。完整说明见[发布与核验](references/publishing.md)。

### 互动

```bash
dy like 1                                # 点赞（短索引）
dy like 1 --unlike                       # 取消点赞
dy fav 1                                 # 收藏
dy comment 1 -c "好看!"                  # 评论
dy follow SEC_USER_ID                    # 关注用户
```

### 主页与数据

```bash
dy me                                    # 我的登录信息
dy profile SEC_USER_ID --posts           # 用户主页 + 作品列表
dy analytics                             # 创作者数据看板
dy notifications                         # 通知消息
```

### 账号与配置

```bash
dy login                                 # 扫码登录
dy login --browser                       # 从浏览器提取 Cookie
dy status                                # 登录状态
dy account list                          # 列出账号
dy account add NAME                      # 添加账号并登录
dy config show                           # 查看配置
dy config set api.proxy http://...       # 设置代理
```

### 别名

| 简写 | 命令 | | 简写 | 命令 |
|------|------|---|------|------|
| `dy s` | `search` | | `dy r` / `dy read` | `detail` |
| `dy dl` | `download` | | `dy t` | `trending` |
| `dy pub` | `publish` | | `dy fav` | `favorite` |
| `dy cfg` | `config` | | `dy acc` | `account` |

## 面向 AI Agent 的结构化输出

几乎所有命令支持 `--json-output`：stdout 只输出一个 JSON 信封，进度提示全部走 stderr，可直接管道给 `jq` 或由 Agent 解析：

```bash
dy trending --count 3 --json-output | jq '.data[].word'
dy status --json-output | jq '.data.authenticated'
dy like 1 --json-output            # 变更类命令也返回结构化结果
```

```json
{ "ok": true,  "schema_version": "1", "data": ... }
{ "ok": false, "schema_version": "1", "error": { "code": "not_authenticated", "message": "..." } }
```

失败时退出码为 1，`error.code` 取值固定（`not_authenticated` / `invalid_argument` / `api_error` / `playwright_error` 等）。完整约定见 [SCHEMA.md](./SCHEMA.md)，在 Claude Code / Cursor 中作为 Skill 使用见 [docs/claude-code-integration.md](./docs/claude-code-integration.md)。

## 配置

| 路径 | 用途 |
|------|------|
| `~/.dy/config.json` | 全局配置 |
| `~/.dy/cookies/<账号名>.json` | 各账号 Cookie（多账号隔离） |
| `~/Downloads/douyin` | 默认下载目录 |

默认配置（`dy config show`）：

```json
{
  "api":        { "cookie_file": "~/.dy/cookies/default.json", "proxy": "", "timeout": 30 },
  "playwright": { "headless": false, "slow_mo": 0 },
  "default":    { "account": "default", "engine": "auto", "output": "table", "download_dir": "~/Downloads/douyin" }
}
```

用 `dy config set <key> <value>` 修改（布尔值 / 数字会自动转换类型）：

```bash
dy config set api.proxy http://127.0.0.1:7897      # 代理
dy config set api.timeout 60                       # 请求超时（秒）
dy config set playwright.headless true             # 无头模式，不弹出浏览器
dy config set default.engine api                   # 引擎：auto | api | playwright
dy config set default.download_dir ~/Videos/douyin # 下载目录
dy config get api.proxy                            # 读取单项
dy config reset                                    # 恢复默认
```

## 验证与维护

```powershell
python -m pip install -e . pytest ruff build
python -m pytest tests -q
python -m build
```

真实本机 Chrome 测试使用合成本地页面，不连接抖音、不需要账号：PowerShell 先执行 `$env:DY_LOCAL_BROWSER_TESTS="1"`，再运行 `python -m pytest tests/test_publish_browser.py -q`。macOS/Linux 可在命令前加 `DY_LOCAL_BROWSER_TESTS=1`。

CI 对 Windows 和 Linux 运行安装、命令及回归测试；浏览器测试只验证本地页面中的封面、话题与等待逻辑。登录、平台实时接口和真实发布仍需要目标电脑上的实际验证；测试通过不代表以后抖音页面不会变化。

## 来源与许可

保留原项目 [MIT 许可](LICENSE) 和作者声明。本分支的发布流程、浏览器整合与 Windows 适配采用同一许可。上游项目链接仅用于溯源，安装本定制版请使用本仓库地址。
