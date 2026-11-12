# Python 回声示例的两个真实版本

`PythonEcho-1.0.0/worker.py` 和 `PythonEcho-1.0.1/worker.py` 分别返回自己的版本号。输入只有 `text` 字符串，最多 200 字符；配置沿用 `prefix`，工具仅声明 `echo`。两个 worker 的实际源码与 ZIP 字节不同。初始化和关闭沿用现有 SDK 生命周期接口。

初始兼容基线为宿主 1.4.0、Python 3.11+，依赖模式为标准库。示例清单显式设置 `MinimumHostVersion=1.4.0`，协议探针独立核对，避免继承通用模板的默认最低版本。

打包使用固定公开宿主源码的 `src/BotAgent.Mcp/PythonWorkerSdk/botagent_worker.py` 原始字节，通过显式 `sdk` 参数注入；作者目录没有 SDK 副本。`.github/workflows/tooling.yml` 在两个可信宿主 checkout 完成后准备清单、打包、执行协议探针并上传候选产物。

协议探针验证两个版本的初始化、工具发现、合成回声、配置、参数边界、未声明工具拒绝、关闭和不同 worker 字节：

```sh
python tests/PythonExampleProbe/probe.py \
  --sdk artifacts/host-current/src/BotAgent.Mcp/PythonWorkerSdk/botagent_worker.py \
  artifacts/python-echo-1.0.0-release artifacts/python-echo-1.0.1-release
```

这些是生产者源码和待审候选。固定合并源码、完整清单与 ZIP 需经维护者批准、不可变 Release 和独立下载复检，再通过独立目录 PR 上架。进程隔离、空权限声明和 `read_only` 提示均不构成安全沙箱或工具授权；探针使用合成数据，不代表真实机器人业务验收。

The versioned workers expose their actual version in the synthetic echo result. The workflow packages the canonical host SDK bytes, then tests both ZIPs through the existing protocol. Source/artifact approval and catalog admission are separate; the process and readonly annotation do not provide a security sandbox or bypass host authorization.
