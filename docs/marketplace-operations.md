# 市场维护手册

本流程面向单维护者。目录收录、CI 校验、人工审核、资产发布和宿主运行是不同证据；绿色工作流不能替代插件代码审核。正式 feed 只收录已发布且独立下载核验过的包，不能先合并占位下载地址。

## 一次性 bootstrap 与保护配置

1. 固定 bootstrap PR 的 base/head，完成生成器、原生测试、旧版及当前真实宿主 ABI 检查，并由维护者审核准确提交。bootstrap 同时引入工具和初始规范目录，是唯一的一次性混合变更；后续 PR 必须按下面三类分开。
2. 合并 bootstrap 后配置 main：要求 PR，必需状态为 GitHub Actions 的 `marketplace-gate`，要求基于最新 base；禁止强推和删除。要求他人批准的数量为 0，不要求单维护者无法满足的第二人审批。
3. 创建 `marketplace-review` environment，指定维护者为 required reviewer，允许 self-review，不允许管理员绕过该 gate。记录设置的 API 回读结果；文档和 YAML 不代表配置已经生效。
4. Actions 默认 token 保持 read。允许 GitHub Actions 创建 PR 的仓库开关也允许其提交 approve review；本工具仅创建/更新 PR，从不调用 approve、merge API。只有治理准备 job 获得 contents/pull-requests/issues/actions write，最终 gate job 仅有 statuses write。
5. 为新 Release 启用不可变发布。已有 Hello 1.0.0 不重新上传、不移动 tag，以原固定 SHA256 核验。不可变设置不追溯证明旧 Release 不可变。

## 三类 PR 和准确候选审核

| 路由 | 可改内容 | 校验 |
| --- | --- | --- |
| contributor | 规范投稿和对应生成目录 | 可信 base 校验器读取候选数据，不运行投稿代码 |
| maintainer | 审核、治理、内置资料及其生成结果 | 同上，额外比较历史撤销记录和治理时间 |
| tooling | 工具、schema、模板、示例源代码、文档、工作流 | 独立原生 CI；只读权限，无持久化凭据；仍需人工 gate |

工具和目录数据不能混在长期 PR 中。PR 校验器、路由及 workflow 均来自可信 base；tooling job 才运行候选代码。所有带鉴权的 checkout 在候选代码之前完成，凭据不保留。

每次审核从当前 main 显式 dispatch `maintainer-review.yml`，输入 `pr_number`、`base_sha`、`candidate_sha`。不要依赖机器人创建 PR 后自动触发的事件。准备 job 校验 PR 的实时 base/head；人工 environment gate 通过后，独立、无 checkout 的 job 再查一次，并只给准确 candidate SHA 写 `marketplace-gate`。候选或 base 变化须重新 dispatch 和批准。

合并前在已固定的可信 base checkout 中执行以下只读检查，然后以同一 head 合并；任何非零退出都停止合并：

~~~sh
python tools/marketplace_gate.py premerge --repository OWNER/REPO --pr NUMBER --base-sha FULL_BASE_SHA --candidate-sha FULL_HEAD_SHA
~~~

它重新核对 PR、Actions 写入的成功 gate，以及本次变更的治理时间。GitHub 的成功状态本身没有 24 小时自动失效机制，因此该合并前检查是维护步骤，不能仅凭网页上早前的绿灯合并。bootstrap 使用固定差异与人工审批，不宣称已有尚未安装的 gate。

## 源码、产物和目录发布

1. 独立源码 PR 合并得到 S；从 S 构建，并为构建输入、完整清单、ZIP、canonical SDK 记录 SHA256。显式传入打包输入/清单/输出，旧回归资产与新候选分目录存放。
2. 维护者审核固定 S 和产物 H；tag 指向 S，以固定文件名发布 Release。草稿可修复，公开后不替换同版本资产、不移动 tag；有误则停止目录发布并另发新版本。
3. 在独立目录下载刚发布的资产，核对完整清单与 ZIP 的哈希、大小和结构。目录 PR 此时仍保持未合并。
4. 添加 canonical submission、维护者 review 和生成目录，形成候选 C；`sourceRevision` 指向 S，不指向包含其自身证据的 C。review 绑定 ID、版本、源提交和 ZIP 哈希。C 的审核和 gate 另行记录。
5. 下载验证和 C 的候选检查通过后才合并目录。生成器会直接广告所有未被 withdrawn/revoked 的投稿，没有 pending 发布状态。

Hello 1.0.0 的既有资产保持原样。Python 示例发布在本市场仓库；未完成真实 Release 与下载核验时 Python feed 为空。跨仓库规则以合成契约测试验证，不宣称已经完成真实外部作者演练。

## 治理刷新和失败处理

- 每天 UTC 01:00（北京时间 09:00）读取默认分支的远端治理 feed。发布满 72 小时，创建或更新唯一分支 `automation/governance-refresh` 的同一个待审 PR；仅改 `governance/ledger.json` 和 `governance.json` 的 `generatedAt`，其余字节不变。
- 先核对分支和 PR 的归属及差异。无法确认归属、有额外改动或默认分支变化时停止，保留现场；不 force push、不覆盖用户改动。已 squash 合并且核验为该流程产生的分支可以复用。
- 候选未超过 24 小时则保持同一 SHA，不重复 dispatch；超过 24 小时则生成新 SHA、重跑验证、重新人工批准。过期批准不能被沿用。
- 远端超过 120 小时未刷新、HTTP 失败、解析失败和源数据不一致分别记录状态；仅状态变化时在同一运营 issue 中提醒，恢复时通知。准备了本地 PR 不等于远端已经发布，不能因此停止告警。
- 不自动 approve、merge 或撤销正常示例包。真实演练要保留创建 PR、显式 dispatch、候选检查与最终远端下载的记录。撤销测试使用隔离合成治理源；目录修复不能删除历史 tombstone，包回滚不能自动逆转用户数据。

## 原生检查与验收记录

运行 `python tools/generate_catalog.py --check`、`python -m unittest discover -s tools -p 'test_*.py'`，构建 Hello 和模板，执行工作流中的两代真实宿主 ABI 探针。固定包另用 `tools/verify_release.py` 对比发布前和独立下载副本，不能把同一文件传两次当成网络发布证明。

交付记录逐项写明：源码/目录提交、SDK 与包哈希、用户批准、真实 Release URL、Windows/Linux 原生命令和退出码、合成/真实范围及未通过项。仓库设置、治理演练、宿主界面和生命周期各有独立证据；不得由目录单测推断整个市场验收完成。
