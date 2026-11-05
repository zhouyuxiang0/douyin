# AI 工具调用 dy

先按 [Windows 安装说明](../README.md#windows-安装)安装定制版 CLI，重启 AI 工具以刷新 PATH。任何能执行本机终端命令的助手都可以调用 `dy`；不需要改写知识视频制作技能或增加 MCP 服务。

操作约定见 [SKILL.md](../SKILL.md)。需要发布时再读取[发布指南](../references/publishing.md)，归档依照[项目保留约定](../references/archiving.md)。在命令中使用 `--json-output` 获取[结构化结果](../SCHEMA.md)。

只在用户授权范围内执行发布、互动或文件清理。安装验证仅检查命令版本、帮助和本机 Chrome，扫码登录由用户完成；不要用真实投稿或互动测试安装是否成功。

使用源码 ZIP 安装时，AI 可以直接调用 `.venv\Scripts\dy.exe`，不依赖虚拟环境是否已在当前终端激活。用户级 uv 安装则先通过 `Get-Command dy` 核对路径。
