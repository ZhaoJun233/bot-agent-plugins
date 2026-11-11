# 贡献与发布清单

简体中文 | [English](CONTRIBUTING.en.md)

## 作者：只提交数据

1. 使用 [SDK 与可复用模板](sdk/README.md)，选择非 preset 的唯一 ID、固定 SemVer、公开源代码提交。作者自行构建；市场 PR 不执行也不接纳作者脚本、工作流或构建代码。
2. 使用通用 [离线打包工具](tools/package.py)：`--manifest` 指向完整技术清单或规范投稿 JSON；`--input` 指向任意预编译 DLL 目录；`--output` 是暂存目录。固定 ZIP 字节顺序、时间和格式，生成完整 SHA256、清单和 SHA256SUMS。不包含宿主 Core，不执行 DLL。同一版本的既有 ZIP 不得覆盖。
3. 唯一投稿来源是 `submissions/<id>/<version>.json`，遵守 [投稿 schema](schemas/submission.schema.json)：`schemaVersion:1`、`manifest`、`metadata`。中文展示必填、英文可选；禁止自带 Review/Governance。新版本先打包、把真实哈希写入新投稿再检查；既有版本技术清单不可更改。
4. 运行以下命令，提交规范投稿与生成文件。不再使用 `--write-catalog`。

~~~sh
python tools/generate_catalog.py
python tools/generate_catalog.py --check
python tools/package.py --manifest submissions/community.example.hello/1.0.0.json --input examples/HelloPlugin/bin/Release/net8.0 --output artifacts/staging --check-catalog
~~~

5. 投稿 CI 从可信 PR base 读取验证器、schema 和依赖；候选 checkout 只按有界数据读取。只读 token，不运行投稿脚本/构建/插件、不下载插件。作者不能修改 reviews、governance、内置展示、验证器、schema、工作流或任意额外文件。通过仅说明结构和完整性，不等于审核或安全证明。

## 维护者：单维护者审核与固定资产

6. 人工核对准确源 commit、版本、权限、依赖、ZIP 哈希与合成测试证据。执行兼容性探针会运行插件，必须在独立受保护的维护者环境进行，不能放入作者 CI。固定公开宿主矩阵与当前缺口见 [M4 说明](docs/m4-market.md)。
7. 单独添加 `reviews/<id>/<version>.json`：[审核 schema](schemas/review.schema.json) 绑定 ID、版本、ZIP SHA256、40 位源 commit、审核者、UTC 时间、HTTPS 证据与说明。作者投稿不拥有审核。JSON 中的人名不是身份认证；可信仓库历史和受保护的人工授权才是信任来源。
8. 按[维护手册](docs/marketplace-operations.md)配置单维护者 environment、PR 与准确候选 gate，允许 self-review。默认分支的[维护者工作流](.github/workflows/maintainer-review.yml)接受 PR 号、base SHA 和 candidate SHA。工具、投稿、维护者数据分开检查；状态写入前及合并前重新核对准确候选。设置是否已生效必须单独回读验证。
9. 固定源码提交 S，审核构建产物 H 后发布指向 S 的 tag；独立下载验证后再合并目录 C。固定 tag `Id-Version`，资产 `Id-Version.zip`、manifest、SHA256SUMS 禁止覆盖；变更必须升版本。用[固定资产校验器](tools/verify_release.py)核对发布前 ZIP 与独立获取的发布后副本；工具本身不联网、不上传、不执行。未提供发布后副本时明确不能声称已验证发布。

~~~sh
python tools/verify_release.py --manifest submissions/community.example.hello/1.0.0.json --before artifacts/staging/community.example.hello-1.0.0.zip --after artifacts/downloaded/community.example.hello-1.0.0.zip
~~~

10. 只有固定公开资产存在、哈希与布局已复核后，才允许在另行授权下发布生成目录。不要使用 GitHub 源码压缩包作为插件。不把声明权限当作沙箱；插件是受信任进程内代码。

## 治理

维护者编辑 [治理账本](governance/ledger.json)，生成根目录治理 feed，不手改生成文件。[治理 schema](schemas/governance.schema.json) 中 deprecated 只警告、withdrawn 下架但不是安全吊销、revoked 是终态安全墓碑。撤下广告不删除历史清单；revoked 元组必须永久保留，不得删除或降级。宿主自行保存安全状态，本仓库不会修改安装。

## Python 工作进程（M5）

请阅读 [Python 作者与运行时指南](<docs/python-worker.md>)：严格 API 2 判别、独立 Python feed、canonical 宿主 SDK 打包、运营者预配置解释器、仅标准库与无密钥数据校验流程。进程隔离不是沙箱；校验不执行 pip 或投稿包。
