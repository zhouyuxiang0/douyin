# 视频发布与核验

发布与核验统一通过已安装的 Google Chrome 启动。若启动失败，先运行 `python -m dy_cli.utils.browser` 检查 Chrome，无需下载专用 Chromium。

视频发布优先使用 `dy publish`。独立图片是正式封面输入：横封面建议4:3，竖封面建议3:4，可以使用不同构图；不要把从视频截帧当作必经步骤。按主题与品牌分别设计清楚的标题、主体和留白，先展示实际图片，再按用户已确认的发布方案执行。平台会裁切比例不符的输入，必须查看输出的两种预览；CLI 不会擅自生成图、重写封面字或替换成AI推荐封面。

## 一次上传，检查后提交

```bash
dy publish --title '已确认标题' --content-file description.txt --video final.mp4 \
  --tags 心理学 --tags 科普 --visibility 公开 --expected-account '账号昵称' \
  --thumbnail-horizontal cover-4x3.png --thumbnail-vertical cover-3x4.png \
  --receipt publication.json --review --json-output
```

`--review` 在上传、填写、选择真实话题和设置双封面后等待 stdin。读取 `publication.json` 与 `publication.assets/` 内的完整表单及横竖封面截图，检查主体/标题是否被裁切、内容是否正确，然后输入 `publish` 继续同一次上传；输入 `save` 或其他文字则暂存，不提交。无需用户重复批准已明确批准且没有变化的内容；如果封面、文案或设置有实质变化，先展示变更并对齐。

仅准备草稿：将 `--review` 换成 `--prepare-only`。此模式会上传到抖音并保存草稿，区别于完全本地的 `--dry-run`。它会验证同页恢复及全新会话恢复，把包含身份信息的会话单独保存在 `~/.dy/publish-sessions/`，不会将 Cookie 或签名媒体URL写入发布凭据。继续用：

```bash
dy publish --resume publication.json --review --json-output
```

续发使用原凭据的文件摘要、文案、话题及设置，拒绝覆盖参数。原文件变化、账号不符、草稿不能恢复均停止。

封面保存可能异步完成：点击“完成”后，主表单图片可见或加载完成仍可能对应旧默认图。先记录编辑前的图片身份，等待两个封面各自更新并持续稳定，再冻结预览基线；不同的独立输入不应仍共用同一默认图。随后保留预览后变化检测，不能删除校验或直接接受变化。该等待已内置发布引擎：先确认两张图片均已脱离编辑前的地址、完成检测并连续稳定，再记录首次预览；后续直接运行已同步的 CLI，不依赖单期临时补丁。遇到 `cover_changed` 先核对提交标记、实际预览和保存状态；只有确认未提交且没有可恢复草稿，才重新上传。

## 输入与边界

- `--thumbnail-horizontal` 与 `--thumbnail-vertical` 分别指定独立图片。`--thumbnail` 是两者共用的回退图片；指定的横/竖图片优先。
- `--content-file` 完整读取正文。编辑器中将段落空白归一为空格，避免平台把换行序列化成额外 `*`；字句不改。
- `--tags` 从建议列表选择准确名称，并验证真实话题元素；无准确选项时停止，不替换相似话题。
- `--visibility` 显式设置并回读；`--save-permission keep|allow|deny` 默认为沿用表单现值。当前视频流程只支持立即发布，传入 `--schedule` 会明确失败，绝不会降级为立即发布。
- 此路径不添加活动、位置、合集、商品、外链、额外音乐、声明或跨平台同步。用户要求这些额外设置时先实现/验证对应控件，不宣称已经支持。
- 封面编辑器的“生成参考图”输入框不是“上传封面”输入框。CLI按带上传说明的区域定位；完成后等待主表单两张图片生效。
- 图文仍使用旧路径，双封面/凭据/续发保证仅适用于视频。不要把图文旧返回值作为已发布证据。

## 结果及重试

凭据区分 `prepared`、`submitting`、`reviewing`、`published`、`submitted_unverified` 和 `verification_failed`。提交前先持久化 `submit_attempted`；任何超时或崩溃后都不自动重发。同一凭据有进程锁，作品列表已有相同标题和全文也会阻止重复投稿。

```bash
dy publish-verify publication.json --timeout 90 --check-pages --json-output
```

核验只读查询作品列表，但会更新本地凭据。校验作品ID、账号、标题全文、真实话题、可见范围、视频时长（有本地 ffprobe 时）及双封面字段。`published` 需要明确审核通过状态及所有上述核验通过；没有作品ID、HTTP成功而业务失败、作品仍审核中都不能报已发布。截图证明提交时的视觉效果，API里的封面字段存在性不证明视觉质量，必须结合预览检查。`--check-pages` 另外读取管理页与公开页，核对全文、账号、时长及播放器时间推进，并保存页面截图；`page_verification.status=verified` 才代表这些页面检查通过。登录墙、超时或播放器未推进会返回部分验证，不重复发布。它不代表整片听审或移动端观感验收。

只有确认 `published` 后，且用户确实要求归档，才进入[归档流程](archiving.md)。
