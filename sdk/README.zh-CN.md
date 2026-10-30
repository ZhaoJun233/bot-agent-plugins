# 编译期最小 SDK 与模板

[English](README.md) | 简体中文

[PluginApi.cs](BotAgent.PluginApi/PluginApi.cs) 仅声明现有的公开 `IBotPlugin`、`PluginCategory` 与 `PluginContext` 契约。它并非可替代的运行时，亦不暴露任何宿主内部实现。其程序集标识为 `BotAgent.Core, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null`。

该契约源自公开的 [BotAgent API 快照](https://github.com/ZhaoJun233/bot-agent/blob/c37c818a16a1b489c3a4d5f2c6d7a9dce42776e7/src/BotAgent.Core/Domain/Plugins/IBotPlugin.cs) 以及 [PluginContext](https://github.com/ZhaoJun233/bot-agent/blob/c37c818a16a1b489c3a4d5f2c6d7a9dce42776e7/src/BotAgent.Core/Domain/Plugins/PluginContext.cs)。MIT 开源归属已在 [NOTICE](../NOTICE) 与 [LICENSE](../LICENSE) 中完整保留。无需访问宿主私有仓库或提交历史即可进行开发。

从仓库根目录构建示例插件：

~~~sh
dotnet build examples/HelloPlugin/HelloPlugin.csproj -c Release
~~~

使用宿主自身拥有的 Core DLL（或编译出的编译期垫片）的**绝对路径**构建[模板工程](../templates/PluginTemplate/PluginTemplate.csproj)。请将以下占位路径替换为你本机的实际路径：

~~~sh
dotnet build templates/PluginTemplate/PluginTemplate.csproj -c Release -p:BotAgentCorePath=/absolute/path/to/BotAgent.Core.dll
~~~

**严禁**将 `BotAgent.Core.dll` 复制到插件输出目录或发布压缩包中。两个示例工程均已禁用此引用的运行时本地复制（CopyLocal），且包校验工具会显式拒绝包含该 DLL 的压缩包。切勿在安装流程中引入运行时 NuGet 还原或源码编译步骤。所有构建均应仅在开发机或 CI 环境中完成。

插件必须具备公共无参入口构造函数、稳定的 Id 与固定的 Version，设置 `IsPreset = false`，并具备安全的异步生命周期。构造函数应保持无副作用。取消信号（Cancellation）与关机信号（Shutdown）触发时必须释放所占用的资源。内置的示例插件特意未进行任何宿主服务查找，亦不发送任何消息。

在发布前，请使用真实宿主的 Core DLL（而非仅使用垫片程序集）运行[契约探针（ContractProbe）](../tests/ContractProbe/Program.cs)。探针会验证类型可赋值性、元数据以及初始化/关机行为。CI 会针对锁定的公开宿主快照重复此项测试，以防参考 API 发生意外分歧。探针测试并不能证明任意第三方插件代码是安全的，或能与每一个宿主构建完全兼容。
