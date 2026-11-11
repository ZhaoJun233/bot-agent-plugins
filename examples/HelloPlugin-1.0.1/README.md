# Hello 1.0.1 source candidate

This version changes only the assembly and plugin version from 1.0.0 to 1.0.1. It remains inert: no messages, network, files, timers or service access. The separate directory preserves the original 1.0.0 sources and deterministic package.

Source availability does not mean this version has been released or admitted to the catalog. Follow the source → reviewed artifact → immutable Release → independent download → catalog sequence in [the operations guide](../../docs/marketplace-operations.md).

Build and package with explicit paths; the packager's defaults still select 1.0.0:

~~~sh
dotnet build examples/HelloPlugin-1.0.1/HelloPlugin.csproj -c Release
python -c "import json; from pathlib import Path; p=Path('artifacts/hello-1.0.1-input.json'); p.parent.mkdir(exist_ok=True); m=json.loads(Path('submissions/community.example.hello/1.0.0.json').read_text(encoding='utf-8'))['manifest']; m.update(json.loads(Path('examples/HelloPlugin-1.0.1/plugin.json').read_text(encoding='utf-8'))); pin=m['Id']+'-'+m['Version']; m['DownloadUrl']='https://github.com/ZhaoJun233/bot-agent-plugins/releases/download/'+pin+'/'+pin+'.zip'; p.write_text(json.dumps(m),encoding='utf-8')"
python tools/package.py --input examples/HelloPlugin-1.0.1/bin/Release/net8.0 --manifest artifacts/hello-1.0.1-input.json --output artifacts/hello-1.0.1-release
~~~

The temporary input uses the existing complete manifest as a template. The packager recomputes its SHA256 from the new ZIP; publish only the resulting output manifest, ZIP and checksums after review. Never publish the temporary input or use it as a canonical submission.

Run the real-host contract probe with the explicit entry type, ID and version:

~~~sh
dotnet run --project tests/ContractProbe -c Release -- /path/to/actual/BotAgent.Core.dll examples/HelloPlugin-1.0.1/bin/Release/net8.0/HelloPlugin.dll Marketplace.Examples.HelloPlugin community.example.hello 1.0.1
~~~

For a net10.0 host, build the probe with -p:ProbeTargetFramework=net10.0 and execute its net10.0 DLL with those same five arguments. No SDK shim or host DLL may be included in the ZIP.
