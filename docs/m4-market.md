# M4 MARKET: canonical catalog, review and governance

## Data ownership and reproducibility

- [Canonical submissions](../submissions/community.example.hello/1.0.0.json) own the technical manifest plus bilingual presentation metadata. Review and governance are deliberately not submission fields.
- [Builtin presentation input](../catalog/builtins.json) is maintainer-owned. [Review records](../schemas/review.schema.json) bind the exact ID/version/ZIP hash/source commit/human/evidence. A reviewer string is not an authenticated identity; branch history and a separately configured human gate authorize changes.
- [The generator](../tools/generate_catalog.py) reads only bounded local data and trusted schemas. No wall clock, network, package build or plugin execution. Sorted canonical inputs, stable JSON UTF-8/LF and explicit ledger timestamp produce byte-identical output. `--check` rejects missing/stale outputs. It emits [legacy index](../index.json), [multi-version repository](../repository.json), [presentation](../presentation.json), [governance feed](../governance.json), and immutable per-version [archive manifests](../plugins/community.example.hello/1.0.0/manifest.json).
- Duplicate JSON keys, nonfinite numbers, links, path/identity mismatch, unknown fields, oversize documents and immutable technical-manifest changes fail. Canonical JSON is limited to 2 MiB/document and 1024 submissions; the candidate checkout is bounded to 32 MiB and 10000 filesystem entries, with checkout internals pruned.
- Delisted versions retain their archive manifests. Dependents of a missing/delisted required pin are also hidden. An empty advertised repository is valid.

## Governance DTO and transitions

[Ledger input](../governance/ledger.json) and [generated feed](../governance.json) use exactly:

~~~json
{
  "schemaVersion": 1,
  "generatedAt": "2026-11-06T00:00:00Z",
  "entries": []
}
~~~

Each entry has exactly `id`, `version`, lowercase 64-character `sha256`, `status`, nonblank `reason` (1..500), and UTC `updatedAt`. Timestamps use `Z`, optionally 1..7 fractional digits. Entries are unique by the complete tuple; maximum 1024 live feed entries and 2 MiB. `updatedAt <= generatedAt`; timestamps cannot roll back against trusted base history.

| State | Advertisement | Security meaning | Transition policy |
| --- | --- | --- | --- |
| deprecated | Retained | Warning, not security denial | Maintainer can change/remove |
| withdrawn | Removed | Delisting, not revocation | Maintainer can restore |
| revoked | Removed | Security tombstone | Must persist forever; cannot delete/demote |

The contributor lane cannot change the ledger or feed. The maintainer lane compares candidate history against both trusted base ledger and base feed, so deleting an advertisement or rewriting both candidate files cannot clear an old revocation. The host teammate owns persistent enforcement/global hash behavior; the feed schema was coordinated with that implementation. No host source changes occur here.

## CI threat boundary

[Contributor workflow](../.github/workflows/validate.yml): `pull_request_target`, pinned checkout/setup actions, `contents: read`, no persisted checkout credentials, no submodules/LFS, no user expressions interpolated into shell programs. Validator, schemas and pip requirements come from the exact trusted PR base. Candidate head is data only. [Validator](../tools/validate_pr.py) neither imports candidate modules nor starts processes nor performs network operations. The GitHub infrastructure checks out data and installs trusted validator dependencies; that is not candidate package execution.

The contributor allowlist covers canonical submissions and generated index/repository/presentation/archive manifests only. Reviews, governance, builtin inputs, schemas, validators, workflows and arbitrary source are denied. A changed or injected candidate script cannot replace the trusted validator.

[Maintainer workflow](../.github/workflows/maintainer-review.yml) binds the PR number, exact base and exact candidate SHA to the owner-reviewed `marketplace-review` environment. Trusted routing distinguishes contributor data, maintainer data and source/tooling. Data stays passive; source/tooling receives separate native tests with read-only permission and no exposed credential. Only the independent, no-checkout final job has status-write permission. It rechecks the PR before writing `marketplace-gate` on the candidate SHA. A default-branch workflow run alone cannot approve a candidate.

**External configuration:** require PRs and the unified gate, disallow force pushes/deletion, require the sole maintainer in the environment, and allow self-review. This is explicitly a single-maintainer workflow, not independent two-person review. Bootstrap must be reviewed and merged before enabling these protections. Configuration and live exercises require their own evidence; local YAML/tests cannot prove remote settings. See the [operations runbook](marketplace-operations.md).

## Fixed artifacts and packaging

[Generic packager](../tools/package.py) takes a full manifest or canonical submission and any prebuilt DLL directory. It never builds/executes input. It preserves the existing ZIP_STORED format, fixed 2026-01-01 timestamp and sorted relative paths, excludes host Core, bounds size/count and refuses replacement of an existing versioned ZIP with different bytes. It writes detached manifest and SHA256SUMS. Native Hello still matches the inherited SHA256 `01dccbf848c9c9fbd5797e47a86339b79a4963eb585fc8157ff74768145c50cb`.

[Offline pre/post verifier](../tools/verify_release.py) verifies full immutable manifest hash and safe ZIP layout for one or both supplied copies. It does not obtain the post-publication copy or prove that a remote asset exists; PE-header/layout validation is not a managed-code audit or compatibility proof. Publication is an intentionally manual, separately authorized operation after protected human review and asset checks. There is no live end-to-end publication claim.

## Compatibility matrix

[Generic native probe](../tests/ContractProbe/Program.cs) accepts `<host-core.dll> <plugin.dll> [<entry-type> <id> <version>]`. It executes initialization/shutdown and therefore belongs only in a reviewed maintainer environment. Native tests use synthetic/inert plugins and an empty service provider.

| Fixed public host revision | Framework | Current M4 evidence |
| --- | --- | --- |
| c37c818a16a1b489c3a4d5f2c6d7a9dce42776e7 | net8.0 historical baseline | Inherited documentation only; not rerun against an actual public-host DLL in this worktree |
| dd181696afadc7a298eebda736e788f529f60b76 | net10.0 public dev baseline | Matrix is pinned but actual-host compatibility remains unverified |
| Local reference-only SDK, not a public host | net8.0 | Native Hello and generic template assignability/metadata/init/shutdown passed; not a substitute for either host row |

Obtain/build the two fixed public host revisions in an explicitly authorized maintainer environment, retain exact commit/binary hashes, then run each applicable plugin against the actual host Core/runtime. Do not report the matrix complete from the SDK-shim smoke. No off-limits host/main/#151 checkout was touched.

## Native synthetic evidence

Run from the market worktree (Python 3.13.12; .NET SDK 10.0.101):

~~~sh
python tools/generate_catalog.py --check
python -m unittest discover -s tools -p "test_*.py"
dotnet build examples/HelloPlugin/HelloPlugin.csproj -c Release
python tools/package.py --output artifacts/m4-fixed --check-catalog
python tools/verify_release.py --manifest submissions/community.example.hello/1.0.0.json --before artifacts/m4-fixed/community.example.hello-1.0.0.zip --after artifacts/m4-fixed/community.example.hello-1.0.0.zip
dotnet run --project tests/ContractProbe -c Release -- sdk/BotAgent.PluginApi/bin/Release/net8.0/BotAgent.Core.dll examples/HelloPlugin/bin/Release/net8.0/HelloPlugin.dll
~~~

The last verifier command exercises both local code paths using the same local file; it is **not a downloaded/publication observation**. [Catalog tests](../tools/test_catalog.py) use independent temporary base/candidate trees and include script execution denial, protected edits, forged review fields, terminal revocation, absent tombstones, schema bounds and deterministic regeneration. [Release tests](../tools/test_release.py) use synthetic PE-prefix bytes only and cover generic packaging, pre/post tampering and overwrite denial. Final native run: 100 tests in 16.612s, OK with no skips; generator check reported 5 documents; pre/post local verifier and git diff whitespace checks passed. Hello and template builds reported 0 warnings/0 errors and both lifecycle probes passed against the SDK shim. Initial template build without BotAgentCorePath failed as designed, then passed with the explicit shim reference. The generalized packager reproduced the exact inherited ZIP hash. Final counts/results are also recorded in the implementation handoff; these are implementer tests, not independent acceptance or live GitHub configuration evidence.
