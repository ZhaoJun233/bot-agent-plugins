# BotAgent plugin marketplace

A public, version-pinned catalog of reviewed community plugins for [BotAgent](https://github.com/ZhaoJun233/bot-agent). This is a separate repository, not a mirror of the host's history.

**Plugins execute arbitrary .NET code in the host process. They are not sandboxed.** A checksum authenticates bytes relative to a trusted catalog; it does not prove that code is safe. Only install reviewed publishers and keep backups. Permission declarations are disclosures, **not enforceable capability isolation**. New community plugins are disabled by default; installation, upgrade, rollback and removal are staged for a host restart. Installation must not compile source or run install scripts.

## Catalog and releases

- [Index](index.json): { "SchemaVersion": 1, "Plugins": [manifest] }.
- [Manifest schema](schemas/manifest.schema.json) and [index schema](schemas/index.schema.json): JSON Schema draft 2020-12.
- [Exact contract](docs/contract.md), [security policy](SECURITY.md), and [contribution process](CONTRIBUTING.md).
- [Hello example](examples/HelloPlugin/HelloPlugin.cs): deliberately inert lifecycle plugin; no messages, files, network, timers or service access. Its [manifest](plugins/community.example.hello/1.0.0/manifest.json) contains the real ZIP SHA256, not a placeholder.

Release tag: **community.example.hello-1.0.0**. Asset: **community.example.hello-1.0.0.zip**. It contains only **HelloPlugin.dll**. The detached manifest and checksum file are release metadata, not runtime scripts. GitHub also generates source archives; **do not install those**.

A host must fetch this index explicitly from a trusted HTTPS location, validate the selected manifest and full archive SHA256, stage the immutable version, then require operator enablement and restart. This repository does not deploy or turn on any plugin on a running bot. A host with package-loader support is required; the older public host snapshot used by CI proves API compatibility only, not marketplace availability.

## Build and verify locally

Use the exact .NET SDK in [global.json](global.json), the .NET 8 runtime, Python 3.13, and the pinned validation dependency. These are **maintainer tools**, never runtime installation steps.

~~~sh
python -m pip install -r tools/requirements.txt
dotnet build examples/HelloPlugin/HelloPlugin.csproj -c Release
python tools/package.py
python tools/validate.py --archive artifacts/release/community.example.hello-1.0.0.zip
python -m unittest discover -s tools -p 'test_*.py'
dotnet run --project tests/ContractProbe -c Release -- sdk/BotAgent.PluginApi/bin/Release/net8.0/BotAgent.Core.dll examples/HelloPlugin/bin/Release/net8.0/HelloPlugin.dll
~~~

[CI](.github/workflows/validate.yml) also builds the template and probes against an actual public BotAgent.Core build at a pinned public commit. It compares rebuilt ZIP bytes with the catalog hash; it never rewrites a catalog pin. No token is needed to build. The compile-time [SDK shim](sdk/README.md) is not the host implementation and must never be placed in a plugin ZIP.

## Author a plugin

Copy [the template](templates/PluginTemplate/Plugin.cs) and its [project file](templates/PluginTemplate/PluginTemplate.csproj), choose a unique non-preset ID, implement IBotPlugin, and set IsPreset to false. Read the [SDK guide](sdk/README.md). Package only reviewed compiled plugin assemblies, publish a fixed release tag and immutable asset, then submit the complete manifest and index change by PR. Settings are declarative metadata; secrets never belong in public defaults. Dependencies are exact pins, not auto-install instructions.

License: MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
