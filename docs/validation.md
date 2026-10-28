# 本机验收记录

日期：2026-10-28。环境：macOS 15.5 / Apple Silicon / Python 3.9.6。

- `python3 -m unittest discover -s tests -v`：16 项通过，运行耗时 1.678 秒。包含本地模拟模型 HTTP 服务与真实 MCP 子进程。因执行环境限制，本地监听测试在获准的非沙箱进程运行。
- `node --check ui/app.js`：通过。
- `python3 scripts/collect_trace.py`：真实执行，输出 `docs/trace.md`。
- `bash scripts/build_macos.sh`：完成 `.app` 和 `.dmg`。
- hdiutil 挂载 DMG，校验通过，内部为 `Little Cursor.app`。
- 从 DMG 复制应用后打开，原生窗口与三栏界面显示正常。
- 安装版示例：空列表测试失败（exit 1），批准 diff 后 4 项测试通过（exit 0）。
- 安装版重复替换：old 出现两次，错误可见，补读和扩大上下文后替换成功。
- 安装版 MCP：`mcp__course__describe_project` 返回验收清单，界面标明“外部 MCP”。
- 安装版中断：sleep 命令运行后点击中断，exit -9、reason cancelled，之后结束任务。

未验证：个人真实模型 Key、现场随机题、其他电脑安装、Apple Developer ID 签名/公证、Windows/Linux。开发过程尚不满足七天跨度和十五次真实提交要求。
