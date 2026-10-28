# 发布交接

2026-10-28 已发布到用户指定的公开仓库：

- [源码](https://github.com/huaminjie528-star/python-)
- [v1.0.0 Release](https://github.com/huaminjie528-star/python-/releases/tag/v1.0.0)
- [macOS Apple Silicon 安装包](https://github.com/huaminjie528-star/python-/releases/download/v1.0.0/LittleCursor-1.0.0-macOS.dmg)
- [离线操作采样演示](https://github.com/huaminjie528-star/python-/releases/download/v1.0.0/demo.mp4)
- [校验值](https://github.com/huaminjie528-star/python-/releases/download/v1.0.0/SHA256SUMS.txt)

Release 指向代码提交 `c8afabe6e731df1d860da1764c76fe355eaa2ab4`，不是空 tag。GitHub 返回附件均为 uploaded，大小与 SHA-256 与本地一致：

```text
05ba92d0e8f1df8d191c17b995d0a1d142bbc00a79cc18fff69d475b67030b01  LittleCursor-1.0.0-macOS.dmg
c17196e27a8d04a9d40e8e656da46b112c5dc10c8e2ebfbb4b2c51119bfd2c33  demo.mp4
```

[源码提交的 GitHub Actions 测试](https://github.com/huaminjie528-star/python-/actions/runs/40672683566)已通过。标签触发的重复打包任务已主动取消，以保留经过本机安装验收的附件，不让 CI 覆盖它；这不代表该构建失败，也不代表云端包已经验收。

提交前还需要本人完成：

1. 在应用的“模型设置”中配置自己的 Key、服务地址和支持工具调用的模型，用陌生项目完成一次真实模型验收。
2. 按课堂要求练习五分钟现场随机题，建议补录本人讲解的真实模型演示。现有视频是明确标注的离线采样回放。
3. 继续做真实迭代并提交，满足 ≥15 次 commit、跨度 ≥7 天。当前记录只有实际发生的提交，没有伪造日期或凑数。

跨机分发还需要考虑 macOS Gatekeeper。当前包未做 Apple Developer ID 签名或公证，只验证过本机 Apple Silicon。
