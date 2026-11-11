# Contributing and release checklist

English | [简体中文](CONTRIBUTING.md)

## Contributor lane: data only

1. Start from the [SDK and reusable template](sdk/README.en.md). Choose a unique non-preset ID, a fixed SemVer and a public source revision. Develop/build locally; the marketplace PR must **not** change or execute source, scripts, workflows or dependencies.
2. Build assemblies on your own machine and package with the generic offline CLI. Supply a full technical manifest (or submission JSON) using `--manifest`; `--input` accepts any prebuilt assembly directory. The build descriptor in the Hello example is not an installable manifest. Do not include host Core, credentials or private data.

   ~~~sh
   python tools/package.py --manifest submissions/community.example.hello/1.0.0.json --input examples/HelloPlugin/bin/Release/net8.0 --output artifacts/staging --check-catalog
   ~~~

   For a genuinely new version, initially omit `--check-catalog`, copy the resulting full ZIP hash into its new canonical submission, then verify again. Never change an existing submitted ID/version manifest or overwrite a versioned ZIP. Direct `--write-catalog` is removed.
3. Submit exactly `submissions/<id>/<version>.json`, matching [the submission schema](schemas/submission.schema.json): `schemaVersion: 1`, `manifest`, `metadata`. Descriptions are required in Chinese, with optional English. Metadata cannot contain `Review` or `Governance`. The canonical submission owns both technical and presentation data.
4. Run `python tools/generate_catalog.py` and `python tools/generate_catalog.py --check`. Commit the canonical submission and generated index/repository/presentation/archival manifests only. The generator neither downloads nor executes anything. See [M4 trust boundaries](docs/m4-market.md).
5. Contributor CI uses the trusted PR-base validator, schemas and requirements; candidate checkout is only bounded JSON/data. A contributor cannot edit reviews, governance, builtins, validator, workflows or arbitrary files. There are no plugin builds, downloads or execution and the token is read-only. A green check is syntax/integrity evidence, **not human approval or proof of safety**.

## Protected maintainer lane

6. A human reviews the source at its exact commit, permissions, dependencies, cancellation/shutdown and the fixed ZIP. Keep synthetic evidence. Run compatibility checks on the pinned public host revisions in [the matrix](docs/m4-market.md#compatibility-matrix); the generic ContractProbe executes plugin code and is never run in contributor CI.
7. Add a separate `reviews/<id>/<version>.json` matching [the review schema](schemas/review.schema.json): exact ID/version/hash, source commit, reviewer, UTC review time, HTTPS evidence and notes. Regenerate presentation. The human name and evidence links are declarations, not identity authentication. Only protected repository history plus a configured human approval gate authorizes a review.
8. Follow the [operations runbook](docs/marketplace-operations.md): require the sole maintainer in the environment and allow self-review. Dispatch the default-branch workflow with PR number, exact base SHA and exact candidate SHA. Trusted routing separates contributor data, maintainer data and tooling. Recheck identity before writing the candidate gate and immediately before merge; remote settings require separate verification.
9. Publication is a separate, explicitly authorized maintainer operation. After approval, fixed tag `Id-Version` and fixed `Id-Version.zip`, detached manifest and SHA256SUMS are immutable. Use [the offline verifier](tools/verify_release.py) before publication and against a separately obtained post-publication ZIP; it checks full hash, paths, layout and bounded PE headers, not safety or compatibility. No automatic upload/download/publishing is implemented in either lane.

   ~~~sh
   python tools/verify_release.py --manifest submissions/community.example.hello/1.0.0.json --before artifacts/staging/community.example.hello-1.0.0.zip --after artifacts/downloaded/community.example.hello-1.0.0.zip
   ~~~

10. Publish the generated catalogs only after the fixed asset is available and checked. Do not install GitHub source archives. The present M4 change is local implementation/testing only; it has not published anything or verified live GitHub protections.

## Governance

Maintainers edit [the ledger](governance/ledger.json), never the generated feed by hand. The [governance schema](schemas/governance.schema.json) defines `deprecated` (warn; keep advertised), `withdrawn` (delist; not a security revocation), and `revoked` (terminal security tombstone). Regenerate all feeds; revoked tuples survive loss of advertisement and may never be removed or demoted. Keep historical manifests. The host applies its own persisted security state; this repository does not mutate installations.

## Python workers (M5)

See the [Python author/runtime guide](<docs/python-worker.md>) for the strict API 2 discriminant, separate Python feed, canonical host SDK packaging, operator-provisioned interpreter, stdlib-only limitations, and secretless data-only review lane. Process isolation is not a sandbox; no pip or candidate package execution occurs during validation.
