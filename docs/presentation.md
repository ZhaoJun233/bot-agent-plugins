# 中文市场展示契约 v1（M1）

## 独立展示，不扩大执行权限

[技术目录](../index.json) 与 [技术清单 Schema](../schemas/manifest.schema.json) 保持原样、严格拒绝未知字段。[展示目录](../presentation.json) 是与技术目录同级、可选的非执行性文件，由 [展示 Schema](../schemas/presentation.schema.json) 和 [语义校验器](../tools/validate_presentation.py) 联合验证。禁止把展示字段塞进旧 manifest；展示文案、源码链接、审核声明均不得改变宿主执行权限。

结构为 `SchemaVersion: 1`、`Entries: [{Id, Version, PackageSha256, Metadata}]`，磁盘 JSON 全部采用 PascalCase，宿主 API 用 camelCase。单文档最多 2 MiB、2048 条记录，重复属性、重复 ID+版本或未知属性拒绝。文本有长度上限，不接受空白描述。

`Metadata` 包含 Name、Summary、Description、Category、Tags、Author、Repository、License、Usage、Configuration、Compatibility、Changelog、Maintenance、PermissionNotes、RiskNotice、Runtime、SourceKind、Review。中文名称、介绍、用法、配置、兼容性、更新和风险说明为首要内容；标识符与技术版本保留原值。仓库链接限无用户信息的 GitHub HTTPS 仓库地址，不渲染任意 HTML。

## 身份与来源

- `Runtime`: builtin / dotnet / python；`SourceKind`: builtin / official / community。Python 是预留的展示词汇，不表示当前目录或宿主能够安装运行 Python。当前技术清单只接受 .NET 包。
- **内置**：Runtime 与 SourceKind 均为 builtin，PackageSha256 为 null。只有实际宿主预设注册表中的 ID+版本才会投影到 builtinPlugins，展示目录不能创建内置能力。无 manifest、下载、安装、升级、回滚或卸载操作；版本随宿主走。
- **外部包**：必须精确匹配技术目录的 ID、Version、Sha256。展示信息不能替换下载地址或其他执行字段。无法匹配时不附加该条展示信息。
- 首批恰好八项内置 + 一个 Hello 示例，不为凑数量制造空包。内置的开关与设置仍走现有宿主页面，不改回复策略或设置存储。

## 审核不是永久勋章

`Review` 必填 Status、Version、Sha256，分别绑定该条的确切版本和包哈希。Status 为 unreviewed 或 reviewed。reviewed 还要求 Reviewer、RFC3339 ReviewedAt、40/64 位十六进制 SourceRevision；说明 Notes 可选。升级到其他版本或替换字节不能继承审核状态。内置能力显示“随宿主提供”，禁止伪装成独立审核包。

首批所有记录均为 unreviewed。Hello 发布资产的 SHA256 与目录一致，只证明字节与可信目录相符，**不证明插件安全**。本阶段不实现审核人身份认证、签名、风险数据库或撤销强制执行。即使未来存在完整审核声明，也不是沙箱承诺；.NET 插件在宿主进程内运行，权限表仅为披露。

## 兼容与失败语义

旧宿主继续读取原技术目录，忽略展示文件。新宿主可读取同级展示文件：不可用或解析失败时显示提示并回退旧技术展示，本机内置能力仍可展示。宿主响应保留原来 manifest 必需的 plugins 数组，新增独立的 builtinPlugins；没有把假 manifest 填入 plugins。安装/升级/卸载的原始安全门、默认禁用和结果回执语义均不改变。当前完整宿主支持暂存后的热应用；兼容宿主可能返回待重启。任何阶段的暂存、失败或超时都不应被展示层改写成成功。

发布侧 CI 对缺字段、重复身份、包哈希漂移、继承旧审核、内置伪包、伪造 Python 支持、非中文简介等反例报错。宿主消费外部输入时还必须独立做边界与身份校验，不能把 CI 当信任边界。

## 范围

M1 提供统一中文目录与真实内置投影，不完成 M2–M6：仓库预览/导入、多插件多版本选择、持久审核/撤销执行、作者全流程以及 Python 进程隔离均另行实现。展示侧链接只供查看，不自动拉取、执行或发布代码。
