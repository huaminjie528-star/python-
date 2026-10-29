# DeepSeek 接入（v1.0.2）

1. 在 https://platform.deepseek.com/ 登录，创建自己的 API Key，并确认 API 余额可用。聊天网页账号本身不是 API Key。
2. 退出旧版应用，打开 v1.0.2 的 Little Cursor.app，在“模型设置”填写：

| 项目 | 内容 |
|---|---|
| 运行模式 | 真实大模型 · 工具调用 |
| API Base URL | `https://api.deepseek.com` |
| 模型名称 | `deepseek-flash` |
| API Key | 在 DeepSeek 平台创建的密钥 |

3. 保存设置并开始新会话，发送“请回复连接成功，不要调用工具”。正常回复后，再测试“读取 stats.py，解释 mean 的作用，不要修改文件”。

当前版本检测官方 DeepSeek 主机名后使用 `max_tokens`，并显式设置 `thinking.type=disabled`，先验证非思考模式下的工具循环。OpenAI 请求参数保持原样。不自动重试 429；额度不足需检查余额或配额，不能靠连续发送恢复。

Key 只留在后端内存，关闭应用后需要重新填写。切换服务商时也要换成对应服务商的 Key。不要发给别人或提交 GitHub。

2026-10-29 已完成模拟 DeepSeek 协议的多轮工具回灌测试，并在修正服务地址后用用户配置的 Key 得到真实的“连接成功”回复。真实模型文件操作尚未验收。

v1.0.2 增加 DNS、连接拒绝、TLS/证书、超时、连接重置的分类提示，每次请求重新读取系统代理配置，避免长期缓存旧代理。24 项自动测试通过。网络超时可能发生在服务端已经接受请求之后，因此不自动重发付费请求。

如果遇到网络错误，先保持当前配置，检查网络或代理软件是否稳定。网络检测时本机启用了 `127.0.0.1:17890` 系统代理，公共 HTTPS 探测当时成功；这不证明过去每次失败都由代理造成。请以新版本显示的具体网络原因继续定位，不要关闭 TLS 证书验证。重启应用会清除内存中的 Key，需要重新填写。

官方依据：[接入地址与模型名称](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[请求参数](https://api-docs.deepseek.com/api/create-chat-completion/)。
