# dy-cli 使用指南

安装和环境准备统一见 [README](../README.md#windows-安装)。以下示例在 `dy` 命令可用后执行。

## 命令详解

### 搜索

```bash
dy search "AI创业"                        # 综合搜索
dy search "咖啡" --sort 最多点赞          # 按点赞排序
dy search "春招" --time 一天内            # 限制时间
dy search "科技" --type video             # 仅视频
dy search "风景" --type atlas             # 仅图文
dy search "科技" --count 50              # 返回 50 条
dy search "科技" --type user             # 搜索用户
dy search "科技" -o results.csv          # 导出 (.json/.csv/.yaml)
dy search "科技" --json-output           # JSON 输出
```

### 短索引

搜索结果会自动缓存，后续命令可直接用序号代替 aweme_id：

```bash
dy search "美食"
dy read 1                                # 查看第 1 条详情 (等价 dy detail 1)
dy detail 1 --comments                   # 详情 + 评论
dy dl 1                                  # 下载第 1 条
dy like 1                                # 点赞第 1 条
```

### 下载

```bash
dy download https://v.douyin.com/xxxxx/   # 分享链接
dy download 1234567890                     # 视频 ID
dy download URL --music                    # 同时下载 BGM
dy download URL -o ~/Videos/douyin         # 指定目录
dy download URL --json-output              # 仅输出链接
dy download URL --list-quality             # 列出可用画质
dy download URL -q 720                     # 指定画质 (auto/best/worst/2160/1440/1080/720/540)
```

`-q auto`（默认）使用平台默认地址，与旧版行为一致；指定分辨率不存在时报错并列出可选项；同一分辨率取码率最高的档位。

### 发布

使用本定制版的[发布与核验指南](../references/publishing.md)。视频需要独立双封面或通用封面；定时发布尚不支持，结果未知时不得重发。

### 热榜

```bash
dy trending                              # 显示 Top 50
dy trending --count 20                   # 显示 Top 20
dy trending --watch                      # 每 5 分钟刷新
dy trending --json-output                # JSON 输出
```

### 直播

```bash
dy live list                             # 列出推荐直播间
dy live list --count 10                  # 指定数量
dy live info ROOM_ID                     # 直播间信息
dy live record ROOM_ID                   # 录制直播 (需要 ffmpeg)
dy live record ROOM_ID --quality HD1     # 指定画质
dy live record ROOM_ID -o live.mp4       # 指定输出文件
```

### 互动

```bash
dy like AWEME_ID                         # 点赞
dy favorite AWEME_ID                     # 收藏
dy comment AWEME_ID -c "写得好!"         # 评论
dy follow SEC_USER_ID                    # 关注
dy comments AWEME_ID                     # 查看评论
dy comments AWEME_ID --count 50          # 更多评论
```

### 用户

```bash
dy me                                    # 我的信息
dy profile SEC_USER_ID                   # 用户主页
dy profile SEC_USER_ID --posts           # 含作品列表
```

### 数据看板

```bash
dy analytics                             # 数据看板
dy analytics --csv data.csv              # 导出 CSV
dy notifications                         # 通知消息
```

### 多账号

```bash
dy account list                          # 列出账号
dy account add work                      # 添加并登录
dy account default work                  # 设为默认
dy account remove work                   # 删除
dy login --account work                  # 指定账号登录
```

### 配置

```bash
dy config show                           # 查看全部
dy config set api.proxy http://...       # 设置代理
dy config set api.timeout 60             # 请求超时
dy config set playwright.headless true   # 无头模式
dy config set default.download_dir ~/Vid # 下载目录
dy config get api.proxy                  # 获取单项
dy config reset                          # 重置默认
```

---

## 命令别名

| 别名 | 完整命令 |
|------|---------|
| `dy pub` | `dy publish` |
| `dy s` | `dy search` |
| `dy dl` | `dy download` |
| `dy t` | `dy trending` |
| `dy r` / `dy read` | `dy detail` |
| `dy fav` | `dy favorite` |
| `dy noti` | `dy notifications` |
| `dy stat` | `dy status` |
| `dy acc` | `dy account` |
| `dy cfg` | `dy config` |

---

## 引擎说明

| 引擎 | 功能 | 速度 |
|------|------|------|
| **API** | 搜索、下载、评论、热榜、直播、用户 | ⚡ 快 |
| **Playwright** | 发布、登录、数据看板、通知 | 🐢 较慢 (需浏览器) |

命令自动选择最优引擎，无需手动指定。

---

## 常见问题

### Q: 搜索返回空结果?
可能是签名算法问题。尝试先登录：
```bash
dy login
dy search "关键词"
```

### Q: 发布失败?
1. 确保已登录: `dy status`
2. Cookie 过期需重新登录: `dy login`
3. 抖音创作者中心 UI 可能更新，需要更新脚本

### Q: 如何设置代理?
```bash
dy config set api.proxy http://127.0.0.1:7897
```

### Q: 直播录制需要什么?
安装 ffmpeg:
```bash
brew install ffmpeg       # macOS
apt install ffmpeg         # Ubuntu
```
