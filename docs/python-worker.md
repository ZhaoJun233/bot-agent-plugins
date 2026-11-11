# Python 工作进程作者指南 / Python worker author guide

这是 M5 本地实现说明，不表示已发布 ZIP、已配置 GitHub 保护或已通过真实部署验收。所有演示输入均为合成数据。

## 运行时边界 / Runtime boundary

- 现有 .NET `ApiVersion:1` 清单保持严格不变，不能带 `Runtime`。
- Python 使用独立的 [API 2 schema](<../schemas/python-manifest.schema.json>)，不允许 `EntryAssembly`、`EntryType`、`TargetFramework`（包括 null）。公共 ID、固定版本、完整 ZIP SHA256、下载地址、设置与权限规则保留。
- `Runtime` 必须显式为 `Kind:python`、`ProtocolVersion:1`、`EntryPoint` 相对 `.py` 路径、`MinimumPythonVersion:3.11`、`DependencyMode:stdlib-only`、非空 `Tools`。Python 最低版本只能写 `3.<minor>`，minor 为 11..99，不接受 pip 风格范围或前导零；实际解释器须是 major 3 且 minor 不低于声明。
- 工具名只允许 `[A-Za-z0-9_-]{1,64}`，区分大小写、去重、最多 64 个。不声明不是全部授权；SDK 发现的额外工具与 read-only 提示不能提升权限。
- 本期仅支持标准库，不支持 requirements、pip、venv 或预装第三方依赖模式。宿主/预览/CI 不会安装依赖。尚未配置合格解释器时，必须报告不可用，而不是兼容。
- **独立进程不是安全沙箱。** 代码仍可能访问服务账户可访问的文件、网络和操作系统资源。只安装受信任代码；需要强隔离时由运营者配置容器、账户与 OS 策略。SDK/主机授权与进程边界不能证明 Python 源码没有自行调用系统 API。

## 一个规范来源，两条技术 feed / One author source, separate feeds

[规范投稿 schema](<../schemas/submission.schema.json>) 中 `manifest` 按 `ApiVersion` 判别，`metadata.Runtime` 必须一致。作者无权提交 Review/Governance。

`python tools/generate_catalog.py` 从 `submissions/<id>/<version>.json` 生成：

| Runtime | Technical feed | Presentation | Immutable descriptor |
| --- | --- | --- | --- |
| .NET | `index.json` + `repository.json` | `presentation.json` | `plugins/<id>/<version>/manifest.json` |
| Python | `python-repository.json` | `python-presentation.json` | `python-plugins/<id>/<version>/manifest.json` |

Python feed 文档最多 2 MiB、256 个 ID、每个 ID 128 个版本、总计 1024 个候选；每份清单最多 64 KiB。依赖图验证使用迭代算法，接受预算内的长链并拒绝环。

Python feed 唯一根格式为 `{"SchemaVersion":2,"Plugins":[{"Id":"...","Versions":["API 2 manifests"]}]}`。不要创建 python-index 或 Releases 风格旁路。现有 .NET 消费者永远不会收到 Python 清单。当前每条 feed 的依赖图独立闭合；禁止跨运行时依赖和同一 ID 的运行时迁移，迁移须选择新 ID。

维护者 Review 仍单独绑定 exact id/version/SHA/source commit、审核人声明及证据链接；JSON 人名不是身份认证。共享 `governance.json` 支持 Python tuple：deprecated 提示、withdrawn 下架非安全吊销、revoked 终态持久保存，即使广告消失。归档清单仍保留不可变。

## 作者流程 / Author workflow

1. 从 [投稿模板](<../templates/PythonWorker/submission.template.json>) 与 [echo 示例](<../examples/PythonEcho/worker.py>) 开始。模板 preparation SHA 不是发布哈希，不能直接成为广告。选择非 preset ID、固定版本、公开源码提交。
2. 使用宿主**同一次候选版本**的 canonical SDK `src/BotAgent.Mcp/PythonWorkerSdk/botagent_worker.py`；不要复制一份到作者源码树长期维护。显式 `--sdk` 指向该文件，打包工具原样加入 ZIP 根，并在复制后计算整个 ZIP 哈希。维护者须核对 SDK 来源/提交；路径参数本身不是来源认证。
3. 只打包 `.py`、`.json`、`.txt`、`.md` 被动资源。禁止 native 模块、DLL、wheel、环境目录和依赖安装元数据。ZIP 验证只检查数据布局/UTF-8/大小/路径/哈希，**不分析或执行导入，也不能证明标准库声明属实**。隐藏的第三方 import 可能在启动时失败，须人工源代码审核与受控运行测试。
4. 在本地、明确受信任的测试环境运行示例/合约探针。PR 校验只读数据，不运行这些步骤。

```sh
python tools/package.py --input examples/PythonEcho --manifest templates/PythonWorker/submission.template.json --sdk /trusted/host/src/BotAgent.Mcp/PythonWorkerSdk/botagent_worker.py --output artifacts/python-stage
# 将 artifacts/python-stage/manifest.json 的完整真实清单放入新的规范投稿 manifest。
python tools/generate_catalog.py
python tools/generate_catalog.py --check
python tools/package.py --input examples/PythonEcho --manifest submissions/community.example.python-echo/1.0.0.json --sdk /trusted/host/src/BotAgent.Mcp/PythonWorkerSdk/botagent_worker.py --output artifacts/python-stage --check-catalog
python tools/verify_release.py --manifest artifacts/python-stage/manifest.json --before artifacts/python-stage/community.example.python-echo-1.0.0.zip
```

目录/参数示例中的 `/trusted/host` 是运营者明确选择的源码位置，不由工具下载。SDK 改变意味着 ZIP 哈希改变，已发布相同版本不得替换；必须新版本。`verify_release --after` 可比较运营者提供的下载后副本，但用同一本地文件不能证明已公开上传或不可变发布。

打包 CLI 入口是 `tools/package.py`；`tools/package_python.py` 只是库。维护者还可主动运行以下原生回显探针（会执行已审核的示例代码，严禁加入贡献者 CI）：

```sh
python tools/probe_python_example.py --archive artifacts/python-stage/community.example.python-echo-1.0.0.zip --manifest artifacts/python-stage/manifest.json --sdk-sha256 <audited-sdk-sha256>
```

探针核对整个 ZIP 与 SDK 哈希，用合成 initialize/tools-list/echo/error/shutdown 五帧验证六项断言；不代替真实宿主导入/启用测试，不证明 OS 隔离或远端发布。

## SDK contract

`from botagent_worker import Plugin`，`@plugin.tool(name=...,description=...,input_schema=...,read_only=True)` 注册 `def tool(arguments, context)`；`context.configuration` 和 `context.capabilities` 由宿主传入。`@plugin.on_load` / `@plugin.on_unload` 定义生命周期，最后 `plugin.run()`。stdio NDJSON JSON-RPC 2.0 protocol 1：initialize、tools/list、tools/call、shutdown。stdout 专用于协议，不打印调试或密钥。未知结果不得重放；进程异常、超时与关闭由宿主隔离处理。

## 运营者设置 / Operator setup

运营者预先安装 Python 3.11+（major 3），为宿主配置显式可信解释器路径。宿主可以探测**解释器本身**的版本，不能为了准备度检查执行包入口。不要从模型参数选择解释器、命令行、任意环境变量或 pip 源。配置/secret 仅通过受控协议传入，不写入日志或 ToString。宿主 UI 设置名以集成宿主实现为准，本市场不自动发现/下载/配置解释器。

## CI trust and evidence

贡献者 job 从 PR base commit 加载校验器/schema/dependencies；candidate 只是只读数据，read-only token、无提交脚本/构建/包运行、无工作流/审核/治理修改权限。Python 生成文件通过相同边界。独立维护者环境审核不等于已配置 GitHub required reviewers/rulesets；请参阅 [M4 信任边界](<m4-market.md>)。首次增加校验器的 bootstrap PR 不能伪装成普通数据 PR。

原生命令：先构建受信任 Hello 示例与 `artifacts/release`（继承测试前置），再运行 `python -m unittest discover -s tools -p "test_*.py"`。Python 边界共享 [fixture](<../tests/fixtures/python-contract.json>)，不包含真实账号、对话、下载或 token。发布、真实公开宿主矩阵、GitHub 保护均需独立外部证据；本任务未执行。
