# Contributing and release checklist

1. Choose a unique non-preset plugin ID and a fixed SemVer version. Keep a public source repository under review. Describe requested permissions honestly; declarations do not sandbox code.
2. Use [the SDK guide](sdk/README.md). Build compiled net8.0 assemblies on CI/developer machines only. Test against an actual host Core DLL and exercise shutdown/cancellation with synthetic inputs.
3. Validate the [manifest contract](docs/contract.md), permissions, dependencies, typed settings and compatibility. Do not include real accounts, domains, messages, secrets or machine-specific paths in source or docs. GitHub source and release links are allowed.
4. Build a deterministic ZIP containing plugin assemblies only. For the bundled example, use the exact SDK pin, then run python tools/package.py. Full ZIP SHA256 is generated after packaging. Detached manifests avoid circular hashes.
5. For a new example version, update source metadata and plugin.json together, then run python tools/package.py --write-catalog. The script refuses to overwrite an existing ID/version with different bytes. The build descriptor plugin.json deliberately has no Sha256 or DownloadUrl and is **not installable**.
6. Run catalog validation, regression tests, the actual-host contract probe and CI. Review the staged diff and scan for private data before publishing.
7. After checks pass, create an immutable GitHub tag named Id-Version, and release assets Id-Version.zip, manifest.json and SHA256SUMS. Verify the downloaded ZIP hash against the index. Do not install GitHub-generated source archives. Never replace an existing release asset: bump Version instead.
8. Submit or merge the validated index/manifest PR only when the release asset exists and is verified. A maintainer may prepare index and draft release in parallel, but must not claim readiness before public asset verification. Future PRs must not modify an existing published manifest/hash.

The catalog may contain multiple versions of one plugin; each (Id,Version) pair is unique. Every dependency must pin another catalog entry, no cycles or self reference. This project does not auto-publish a release on a PR, so untrusted contributor code receives no write token. CI has read-only contents permission and action commits are pinned.
