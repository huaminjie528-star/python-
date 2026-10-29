# DeepSeek 接入（v1.0.1）

1. 在 https://platform.deepseek.com/ 登录，创建自己的 API Key，并确认 API 余额可用。聊天网页账号本身不是 API Key。
2. 退出旧版应用，打开 v1.0.1 的 Little Cursor.app，在“模型设置”填写：

| 项目 | 内容 |
|---|---|
| 运行模式 | 真实大模型 · 工具调用 |
| API Base URL | `https://api.deepseek.com` |
| 模型名称 | `deepseek-flash` |
| API Key | 在 DeepSeek 平台创建的密钥 |

3. 保存设置并开始新会话，发送“请回复连接成功，不要调用工具”。正常回复后，再测试“读取 stats.py，解释 mean 的作用，不要修改文件”。

当前版本检测官方 DeepSeek 主机名后使用 `max_tokens`，并显式设置 `thinking.type=disabled`，先验证非思考模式下的工具循环。OpenAI 请求参数保持原样。不自动重试 429；额度不足需检查余额或配额，不能靠连续发送恢复。

Key 只留在后端内存，关闭应用后需要重新填写。切换服务商时也要换成对应服务商的 Key。不要发给别人或提交 GitHub。

2026-10-29 已完成模拟 DeepSeek 协议的多轮工具回灌测试；未使用个人 Key 调用 DeepSeek 服务，不宣称真实账户验收通过。

官方依据：[接入地址与模型名称](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[请求参数](https://api-docs.deepseek.com/api/create-chat-completion/)。
