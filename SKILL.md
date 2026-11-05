---
name: douyin
description: |
  抖音全能 Skill：搜索、下载、发布、互动、热榜、直播、数据看板。
  API Client 负责搜索/下载/采集（即时），Playwright 负责发布/登录/数据分析（按需浏览器）。
metadata:
  trigger: 抖音相关操作（搜索、下载、发布、热榜、直播、数据、评论）
---

# 抖音统一 Skill

本 Skill 整合两套引擎：
- **API Client**（httpx 逆向 API）：搜索、下载、评论、热榜、直播、用户 — 即时响应
- **Playwright**（浏览器自动化）：发布、登录、数据看板、通知 — 按需启动

## 目录结构

```
douyin/
├── SKILL.md
├── src/dy_cli/
│   ├── main.py
│   ├── engines/
│   │   ├── api_client.py
│   │   └── playwright_client.py
│   ├── commands/
│   │   ├── search.py, download.py, publish.py
│   │   ├── trending.py, live.py, analytics.py
│   │   └── auth.py, profile.py, interact.py, ...
│   └── utils/
│       ├── config.py, output.py, signature.py
├── scripts/
│   ├── douyin_login.py
│   ├── douyin_publisher.py
│   ├── douyin_analytics.py
│   └── chrome_launcher.py
└── config/
    └── accounts.json.example
```

## 工具选择指南

| 操作 | 用哪个 | 命令 |
|------|--------|------|
| 搜索视频 | API | `dy search "关键词"` |
| 无水印下载 | API | `dy download URL` |
| 热榜 | API | `dy trending` |
| 视频详情 | API | `dy detail AWEME_ID` |
| 评论列表 | API | `dy comments AWEME_ID` |
| 用户资料 | API | `dy profile SEC_USER_ID` |
| 直播信息 | API | `dy live info ROOM_ID` |
| 直播录制 | API + ffmpeg | `dy live record ROOM_ID` |
| **发布视频/图文** | Playwright | `dy publish`（视频支持独立双封面、检查、草稿续发） |
| **核验发布结果** | 只读作品列表 | `dy publish-verify publication.json` |
| **扫码登录** | Playwright | `dy login` |
| **数据看板** | Playwright | `dy analytics` |
| **通知消息** | Playwright | `dy notifications` |

---

## Part 1: API 工具（搜索/下载/采集）

### 搜索

```bash
dy search "AI创业"
dy search "咖啡" --sort 最多点赞 --time 一天内
dy search "科技" --type video --count 50 --json-output
dy search "风景" --type atlas                          # 图文搜索
```

参数:
- `--sort`: 综合 | 最多点赞 | 最新发布
- `--time`: 不限 | 一天内 | 一周内 | 半年内
- `--type`: general | video | user

### 下载

```bash
dy download https://v.douyin.com/xxxxx/
dy download 1234567890
dy download URL --music --output-dir ~/Videos
dy download URL --json-output    # 仅输出链接
```

### 热榜

```bash
dy trending
dy trending --count 20
dy trending --watch              # 每 5 分钟刷新
dy trending --json-output
```

### 视频详情

```bash
dy detail AWEME_ID
dy detail AWEME_ID --comments
dy detail AWEME_ID --json-output
```

### 评论

```bash
dy comments AWEME_ID
dy comments AWEME_ID --count 50 --json-output
```

### 用户

```bash
dy profile SEC_USER_ID
dy profile SEC_USER_ID --posts --post-count 30
dy me
```

### 直播

```bash
dy live info ROOM_ID
dy live info ROOM_ID --json-output
dy live record ROOM_ID                   # 需要 ffmpeg
dy live record ROOM_ID --quality HD1
```

---

## Part 2: Playwright 工具（发布/登录/数据）

### 前置条件

```bash
pip install playwright
python -m dy_cli.utils.browser  # 检查已安装的 Google Chrome，实际启动后自动关闭
```

所有 CLI 与附带脚本统一使用系统 Google Chrome（`channel="chrome"`）；请先安装 Chrome。无需下载 Playwright 专用 Chromium，也不使用其缓存目录。`playwright.chromium_path` 是未生效的旧配置，已从默认配置移除；旧值保留时忽略。

### 登录

```bash
dy login                        # 打开浏览器扫码
dy status                       # 检查登录状态
dy logout                       # 退出登录
```

Cookie 存储位置: `~/.dy/cookies/{account}.json`

### 发布

视频发布前读取 [references/publishing.md](references/publishing.md)。优先通过 CLI 完成独立横竖封面、标题全文、真实话题、可见范围、发布前预览及结果核验，复用已有登录。封面可由独立图片提供，分别适配4:3和3:4；不要默认从视频取帧或直接自动裁切同一张截图。

```bash
dy publish -t "已确认标题" --content-file description.txt -v final.mp4 \
  --tags 心理学 --tags 科普 --visibility 公开 \
  --thumbnail-horizontal cover-4x3.png --thumbnail-vertical cover-3x4.png \
  --receipt publication.json --review --json-output
```

- `--dry-run`：仅本地参数预览，不上传。
- `--review`：上传配置后保存截图并暂停；核对后从 stdin 输入 `publish` 提交或 `save` 暂存。
- `--prepare-only`：上传配置并验证保存草稿，不发布。
- `--resume publication.json`：恢复原草稿和参数，不重复上传。
- `dy publish-verify publication.json --json-output`：只读查线上状态并更新本地凭据，不重发。

提交前按当前项目/用户要求对齐标题、全文、话题、实际封面和设置；不要额外添加未确认的文案或把发布前检查变成重复索要已有授权。只有已核实的 `published` 才能报告已发布，审核中和未知结果分别报告。详情API为空时不能重发，应核对作品管理和实际作品。

图文仍可使用 `dy publish -t "标题" -c "描述" -i img1.jpg -i img2.jpg`；新的视频核验保证不覆盖图文旧流程。当前新版视频路径不支持定时，明确报错，不自动改成立即发布。

用户要求归档时，读取 [references/archiving.md](references/archiving.md)，依据项目已有的保留/删除约定执行，发布本身不自动触发清理。

### 数据看板

```bash
dy analytics
dy analytics --csv data.csv
dy analytics --json-output
```

### 通知

```bash
dy notifications
dy notifications --json-output
```

---

## Part 3: 配置与运维

### 配置文件

`~/.dy/config.json`:

```bash
dy config show
dy config set api.proxy http://127.0.0.1:7897
dy config set api.timeout 60
dy config set playwright.headless true
dy config set default.download_dir ~/Videos
```

### 多账号

```bash
dy account list
dy account add work
dy account default work
dy login --account work
dy search "关键词" --account work
```

### 登录态维护
- Cookie 存储在 `~/.dy/cookies/`
- 过期后需重新 `dy login` 扫码
- 不同账号 Cookie 文件独立

### 注意事项
- 抖音签名算法 (a-bogus) 频繁更新，搜索/下载功能可能需要定期适配
- 创作者中心 UI 也会更新，发布功能可能需要调整选择器
- 批量操作建议加 2-5 秒延时，避免触发风控
- 所有命令支持 `--json-output` 输出机器可读格式
- 所有命令支持 `--account` 指定账号
