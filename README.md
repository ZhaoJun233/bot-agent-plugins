# BotAgent 插件市场

简体中文 | [English](README.en.md)

面向 [BotAgent](https://github.com/ZhaoJun233/bot-agent) 的公开、版本锁定的社区已审核插件目录。这是一个独立的仓库，并非宿主提交历史的镜像。

**插件在宿主进程内执行任意 .NET 代码，未运行在沙箱中。** 校验和仅用于向受信任的目录证实文件字节完整性，并不能证明代码本身是安全的。请仅安装经过审查的发布者发布的插件，并做好数据备份。权限声明仅供**信息披露**，**并非可强制执行的能力隔离边界**。新安装的社区插件默认处于禁用状态；其安装、升级、回滚与卸载均在宿主重启时生效。安装过程严禁编译源码或执行安装脚本。

## 目录与发布规范

- [索引文件](index.json)：`{ "SchemaVersion": 1, "Plugins": [manifest] }`。
- [清单 Schema](schemas/manifest.schema.json) 与 [索引 Schema](schemas/index.schema.json)：基于 JSON Schema draft 2020-12。
- [契约规范](docs/contract.md)、[安全与隐私策略](SECURITY.md) 以及 [贡献与发布流程](CONTRIBUTING.md)。
- [Hello 示例插件](examples/HelloPlugin/HelloPlugin.cs)：故意设计为无副作用的纯生命周期示例；不收发消息、不读写文件、不发起网络请求、不启动定时器，也不访问任何宿主服务。其[清单文件](plugins/community.example.hello/1.0.0/manifest.json)包含真实的 ZIP SHA256 校验和，而非占位符。

发布 Tag：**community.example.hello-1.0.0**。发布资产（Asset）：**community.example.hello-1.0.0.zip**。其中仅包含 **HelloPlugin.dll**。分离的清单与校验和文件属于发布元数据，并非运行时脚本。GitHub 也会自动生成源码压缩包（Source code）；**切勿安装这些源码包**。

宿主必须显式通过受信任的 HTTPS 地址拉取此索引，校验所选清单以及整个压缩包的 SHA256，暂存该不可变版本，之后由管理员手动启用并重启宿主生效。本仓库不会向正在运行的机器人部署或启用任何插件。宿主需具备插件包加载器（package-loader）支持；CI 中使用的较旧公开宿主快照仅用于验证 API 兼容性，并不代表所有宿主版本均已内置插件市场界面。

## 本地构建与验证

请使用 [global.json](global.json) 中指定的精确 .NET SDK、.NET 8 运行时、Python 3.13 以及版本锁定的验证依赖。这些均为**维护者工具**，绝非运行时的安装步骤。

~~~sh
python -m pip install -r tools/requirements.txt
dotnet build examples/HelloPlugin/HelloPlugin.csproj -c Release
python tools/package.py
python tools/validate.py --archive artifacts/release/community.example.hello-1.0.0.zip
python -m unittest discover -s tools -p 'test_*.py'
dotnet run --project tests/ContractProbe -c Release -- sdk/BotAgent.PluginApi/bin/Release/net8.0/BotAgent.Core.dll examples/HelloPlugin/bin/Release/net8.0/HelloPlugin.dll
~~~

[CI](.github/workflows/validate.yml) 还会构建插件模板，并针对锁定公开 commit 的真实公开 BotAgent.Core 构建进行探针测试。CI 会比对重新构建出的 ZIP 字节哈希与目录中的哈希，绝不会重写目录中已锁定的哈希值。构建过程无需任何 Token。编译期 [SDK 垫片](sdk/README.md)并非宿主实现，**严禁**打包进插件的 ZIP 压缩包中。

## 开发新插件

复制[模板代码](templates/PluginTemplate/Plugin.cs)及其[项目工程文件](templates/PluginTemplate/PluginTemplate.csproj)，选择一个非 preset 前缀的唯一 ID，实现 `IBotPlugin` 接口，并将 `IsPreset` 设为 `false`。详细信息请阅读 [SDK 指南](sdk/README.md)。打包时仅可包含经过审查的已编译插件程序集，发布固定的 Release Tag 与不可变资产，随后通过 PR 提交完整的清单与 index.json 变更。设置项属于声明式元数据；严禁在公开默认值中包含密钥与敏感信息。依赖项必须固定具体版本，而非自动安装指令。

开源许可证：MIT。详见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
