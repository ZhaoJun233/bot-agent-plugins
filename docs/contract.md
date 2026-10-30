# 插件目录与清单契约 (API 1)

简体中文 | [English](contract.en.md)

规范的索引（Index）对象严格包含 `SchemaVersion`（整数 1）与 `Plugins`（包含完整清单的数组，最多 1024 项）。JSON 键名使用帕斯卡命名法（PascalCase）。切勿在运行时清单中添加 `$schema`、描述性字段或嵌套的 `Compatibility` 对象；运行时会直接拒绝任何未知字段。独立的 [JSON Schemas](../schemas/manifest.schema.json) 自行声明其所使用的方言。

## 清单字段（Manifest fields）

| 字段 | 必填 | 含义与校验规则 |
| --- | --- | --- |
| Id | 是 | 1-80 个小写字母、数字、点号或连字符，必须以字母开头。禁止使用 `preset.` 前缀、连续点号、末尾点号或系统保留设备名。 |
| Version | 是 | 严格符合主版本.次版本.修订号（major.minor.patch）的语义化版本（SemVer），可带有可选的预发布标识，且受限于 API 1 宿主语法；不允许版本范围、`latest`、带前导零的数字标识符、构建元数据、连续连字符或预发布标识开头/结尾处的连字符。 |
| EntryAssembly | 是 | 安全的相对 DLL 路径，最长 240 字符。禁止路径穿越、绝对路径、反斜杠、系统保留设备名或别名。 |
| EntryType | 是 | 实现了 `IBotPlugin` 的公共具体类全限定名，必须具备公共无参构造函数；最长 512 字符。 |
| Sha256 | 是 | 锁定**整个 ZIP 压缩包字节**（而非单个 DLL）的 64 位十六进制哈希值；严禁使用占位符。 |
| DownloadUrl | 是 | 固定的 GitHub HTTPS Release 资产下载链接。Tag 与资产名称必须为 `Id-Version` 和 `Id-Version.zip`。不得包含凭据、URL 锚点（fragment）、查询参数或 `latest` 重定向。 |
| ApiVersion | 是 | 整数 1。 |
| TargetFramework | 否 | 必须为 `net8.0`；默认为 `net8.0`。 |
| MinimumHostVersion | 否 | `null` 或 2-4 段数字构成的版本号，与宿主程序集版本（assembly version）进行比对；并非商业推广或发布版本的 Tag。 |
| Permissions | 否 | 唯一的权限声明字符串数组，最多 64 项，符合正则 `^[a-z][a-z0-9.-]{0,79}$`。**仅供信息披露**，不作为安全隔离边界。 |
| Dependencies | 否 | 最多 64 个严格包含 `Id` 与 `Version` 的对象。两者均为固定值；ID 必须唯一，不可自引用；所依赖的插件版本必须存在于此目录中，且依赖图必须无环（acyclic）。运行时不会自动下载依赖项。 |
| Settings | 否 | 最多 128 个声明式设置项定义（详见下文）。不得包含可执行的校验器、脚本或 HTML。 |

缺省的可选数组视为空数组。目录 JSON 统一使用数组而非 `null`。本市场刻意制定了比运行时更为严格的发布规则：仅允许 GitHub 固定 Release 链接、无构建元数据的严格 SemVer、唯一的权限声明、规范化的程序集路径、合法类型的默认值以及无环的目录依赖图。在安装时，运行时的文件大小与解压安全检查依然具有最终决定权。清单序列化后的字符串长度最多为 32768 个字符。

## 设置项定义（Setting definitions）

必填字段：`Key`（以字母开头，后跟最多 79 个字母、数字、下划线、点号或连字符）、`Label`（非空文本，最长 200 字符）、`Type`（`string`、`boolean`、`number`、`secret` 或 `select`）。

可选字段：`DefaultValue`（字符串或 `null`，最长 4096 字符）、`Required`（布尔值，默认为 `false`）、`Choices`（最多 100 个唯一字符串组成的数组，或 `null`）。同一个插件内的 `Key` 必须唯一。布尔类型的默认值必须是字符串 `"true"` 或 `"false"`。数值类型的默认值必须是表示有限数值的字符串。`select` 类型要求 `Choices` 必须非空，且默认值必须为选项之一。`secret` 类型的默认值必须省略或设为 `null`。**严禁发布真实的密钥、密码或个人设置值。**

这些字段属于宿主通用设置界面的描述元数据。v1 版本的 `PluginContext` API 暴露了 `Services` 与 `EnvironmentInfo`；但这并不保证设置项会自动出现在其中。与宿主设置的深度集成由宿主负责，声明本身并不构成强制隔离的能力。

## 压缩包与生命周期（Archive and lifecycle）

压缩包上限：压缩后不超过 32 MiB，解压后不超过 128 MiB，总条目不超过 2048 个，单个文件不超过 32 MiB。本市场**仅允许包含插件自身的 `.dll` 文件**，严禁包含 `BotAgent.Core.dll`、原生安装器可执行文件、符号链接、源码文件或运行时脚本。示例 ZIP 仅包含一个编译好的 DLL。完整的清单文件独立存放，以避免产生自引用的压缩包哈希问题。

宿主处理流程：校验清单 → 下载受限大小的 ZIP → 校验完整 SHA256 哈希 → 暂存该不可变版本 → 保持社区插件为禁用状态 → 管理员手动启用并重启生效。升级、回滚与卸载均与宿主重启绑定；插件代码必须在关机（shutdown）信号触发时干净地停止。进程内执行的任意代码均可访问该进程的数据、凭据、文件系统和网络，不受 `Permissions` 限制。在信任清单前，请务必审查插件代码和发布者。

插件程序集的标识与元数据必须与清单一致。社区插件必须显式设置 `IsPreset = false`。SDK 编译期引用的 `BotAgent.Core` 必须在运行时解析为宿主自身拥有的真实程序集。

参见当前的真实[示例清单](../plugins/community.example.hello/1.0.0/manifest.json)。本仓库不提供任何伪造的可安装示例哈希。
