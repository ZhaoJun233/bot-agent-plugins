# Minimal compile-time SDK and template

English | [简体中文](README.zh-CN.md)

[PluginApi.cs](BotAgent.PluginApi/PluginApi.cs) declares only the existing public IBotPlugin, PluginCategory and PluginContext contract. It is not a replacement runtime and exposes no other host internals. Its assembly identity is BotAgent.Core, Version=1.0.0.0, Culture=neutral, PublicKeyToken=null.

The contract is from the public [BotAgent API snapshot](https://github.com/ZhaoJun233/bot-agent/blob/c37c818a16a1b489c3a4d5f2c6d7a9dce42776e7/src/BotAgent.Core/Domain/Plugins/IBotPlugin.cs) and [PluginContext](https://github.com/ZhaoJun233/bot-agent/blob/c37c818a16a1b489c3a4d5f2c6d7a9dce42776e7/src/BotAgent.Core/Domain/Plugins/PluginContext.cs). MIT attribution is preserved in [NOTICE](../NOTICE) and [LICENSE](../LICENSE). No private host repository or history is needed.

Build the example from the repository root:

~~~sh
dotnet build examples/HelloPlugin/HelloPlugin.csproj -c Release
~~~

Build the [template](../templates/PluginTemplate/PluginTemplate.csproj) with an **absolute path** to your host-owned Core DLL (or the built compile-time shim). Replace the placeholder path on your machine:

~~~sh
dotnet build templates/PluginTemplate/PluginTemplate.csproj -c Release -p:BotAgentCorePath=/absolute/path/to/BotAgent.Core.dll
~~~

Do not copy BotAgent.Core.dll into plugin output or release archives. Both sample projects disable runtime copying of this reference, and the package validator rejects it. Do not add a runtime NuGet restore or source compilation step to your installer. Build on a development machine or CI only.

A plugin must have a public parameterless entry constructor, stable Id and fixed Version, IsPreset=false, and a safe asynchronous lifecycle. Keep constructors side-effect free. Cancellation and shutdown should release resources. The included example deliberately performs no host service lookup and sends no messages.

Before publishing, run [ContractProbe](../tests/ContractProbe/Program.cs) against an actual host Core DLL, not only this shim. It verifies assignability, metadata and initialize/shutdown behavior. CI repeats this against the pinned public host snapshot; this catches accidental divergence in the reference API. The probe does not prove arbitrary third-party plugins are safe or compatible with every host build.
