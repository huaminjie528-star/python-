# 构建和发布

本次环境：macOS 15.5、arm64、Python 3.9.6、pywebview 6.1、PyInstaller 6.16.0。依赖的准确版本见 `requirements-lock.txt`。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
bash scripts/build_macos.sh
```

产物为 `dist/Little Cursor.app` 和 `release/LittleCursor-1.0.0-macOS.dmg`。后者供 Release 下载。DMG 采用压缩 UDZO 格式，包含完整 app bundle。打开磁盘映像后把应用拖到应用程序目录即可，不需要在目标电脑运行 pip。

应用资源从 `sys._MEIPASS` 读取。首次启动复制示例到用户 Application Support 目录，后续修改只发生在用户工作区。Key 不进入包和设置文件，日志保存在用户数据目录，发布包不包含开发时的日志。

PyInstaller 生成本地 ad-hoc 签名，不含 Apple Developer ID，也未公证。下载到其他电脑后可能受到 Gatekeeper 限制；正式分发需要自己的开发者证书、codesign 和 notarytool 流程。本次只声明本机可打开，不声明经过其他电脑或 Windows/Linux 验收。

GitHub Actions 中 `check.yml` 执行测试。`release.yml` 在推送版本 tag 时构建 DMG，保存为名为 `LittleCursor-macOS-CI-unverified` 的 Actions 构建产物。通过本机验收后再手动附加到 Release，工作流不自动覆盖已发布的验收包。若构建环境缺少软件包或受限，应查 Actions 日志，不要把空 Release 当成安装包完成。

发布材料包括源码、`report.md`、`docs/trace.md`、截图和安装包。真实课堂演示仍须使用自己的 Key 与任意新文件完成老师现场需求。
