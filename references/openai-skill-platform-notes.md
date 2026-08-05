# OpenAI Skill 平台说明（2026-08 核验）

- Skill 是带 `SKILL.md` 的版本化文件包，可包含脚本、参考资料和资产。
- `SKILL.md` 必须包含 YAML front matter 的 `name` 与 `description`。
- ChatGPT/Codex 先读取名称和描述，匹配后再加载完整指令，因此描述必须清晰限定触发范围。
- `agents/openai.yaml` 可配置显示信息、隐式调用策略和工具依赖。
- API ZIP 上传要求一个顶层目录；官方限制包括 50 MB ZIP、500 个文件、单文件解压后不超过 25 MB。
- ChatGPT Skills 页面支持从电脑上传；可用性取决于账号和工作区设置。

官方资料：
- https://learn.chatgpt.com/docs/build-skills
- https://help.openai.com/en/articles/20001066-skills-in-chatgpt
- https://developers.openai.com/api/docs/guides/tools-skills
