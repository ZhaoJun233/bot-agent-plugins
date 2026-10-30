# 贡献与发布清单

[English](CONTRIBUTING.md) | 简体中文

1. 选择一个唯一的、不带 `preset.` 前缀的插件 ID，以及一个固定的语义化版本（SemVer）。保持公开源码仓库处于可审查状态。诚实描述所申请的权限；权限声明并不能对代码提供沙箱保护。
2. 参考 [SDK 指南](sdk/README.zh-CN.md)。仅在 CI 或开发者本机上构建已编译的 `net8.0` 程序集。针对真实的宿主 Core DLL 进行测试，并使用合成测试数据验证关机与取消信号的响应。
3. 校验[清单契约](docs/contract.zh-CN.md)、权限声明、依赖关系、强类型设置项以及兼容性。源码与文档中严禁包含真实的账号、域名、群聊消息、密钥凭据或特定机器的绝对路径。允许使用 GitHub 源码与 Release 链接。
4. 构建确定性的 ZIP 压缩包，且其中仅包含插件自身的程序集。对于内置示例，请使用精确锁定的 SDK 版本，然后运行 `python tools/package.py`。打包完成后会自动生成整个 ZIP 的 SHA256 校验和。清单文件分离存储以避免自引用循环哈希。
5. 如需发布新的示例版本，请同步更新源码元数据与 `plugin.json`，然后运行 `python tools/package.py --write-catalog`。若同名 ID/Version 已存在且字节不同，脚本会直接拒绝覆盖。构建描述文件 `plugin.json` 刻意不含 `Sha256` 与 `DownloadUrl`，因此**不可直接用于安装**。
6. 在发布前，运行目录校验工具、回归测试、真实宿主契约探针以及 CI 检查。审查暂存区中的差异（diff），并在发布前扫描是否存在私有或敏感数据。
7. 所有检查通过后，创建名为 `Id-Version` 的不可变 GitHub Tag，并上传 Release 资产文件：`Id-Version.zip`、`manifest.json` 与 `SHA256SUMS`。下载并校验 ZIP 文件的哈希是否与索引中的记录完全一致。切勿安装 GitHub 自动生成的源码包（Source code）。绝不要替换已发布的 Release 资产：若有变动必须递增 Version。
8. 仅当 Release 资产已存在且验证无误后，方可提交或合并校验通过的 index/manifest PR。维护者可以并行准备索引与 Draft Release，但在公开资产验证完成前，不得声明已准备就绪。后续的 PR 绝不能修改已发布的清单与哈希。

目录中可以包含同一插件的多个不同版本；每个 `(Id, Version)` 二元组必须唯一。每一个依赖项都必须锁定目录中的另一项有效条目，严禁循环依赖或自引用。本项目不会在 PR 中自动发布 Release，因此不可信的贡献者代码不会获得任何写权限 Token。CI 拥有只读的内容权限，且 GitHub Actions 均已锁定具体 commit。
