# Catalog and manifest contract (API 1)

The canonical index is an object with exactly SchemaVersion (integer 1) and Plugins (array of complete manifests, maximum 1024). JSON keys are PascalCase. Do not add $schema, descriptive fields or a nested Compatibility object to runtime manifests; the runtime rejects unknown fields. The standalone [JSON schemas](../schemas/manifest.schema.json) identify their own dialect.

## Manifest fields

| Field | Required | Meaning / validation |
| --- | --- | --- |
| Id | yes | 1-80 lower-case letters, digits, dots or hyphens, starts with a letter. No preset. prefix, doubled/trailing dot, or reserved device name. |
| Version | yes | Exact SemVer major.minor.patch with optional prerelease; no range, latest, leading-zero numeric identifier or build metadata. |
| EntryAssembly | yes | Safe relative DLL path, maximum 240 characters. No traversal, rooted path, backslash, reserved device name or alias. |
| EntryType | yes | Fully qualified public concrete IBotPlugin implementation with a public parameterless constructor; maximum 512 characters. |
| Sha256 | yes | 64 hex characters pinning the **entire ZIP bytes**, not just a DLL; non-placeholder. |
| DownloadUrl | yes | Fixed GitHub HTTPS release asset. Tag and asset must be Id-Version and Id-Version.zip. No credentials, fragment, query string or latest redirect. |
| ApiVersion | yes | Integer 1. |
| TargetFramework | no | Exactly net8.0; default net8.0. |
| MinimumHostVersion | no | Null or 2-4 numeric components, compared with the host assembly version; not a marketing/release tag. |
| Permissions | no | Array of unique declaration strings, at most 64, pattern [a-z][a-z0-9.-]{0,79}. **Disclosure only**, not a security boundary. |
| Dependencies | no | At most 64 objects containing exactly Id and Version. Both are fixed; IDs unique, no self reference; dependency releases must exist in this catalog and the graph must be acyclic. Runtime does not automatically download dependencies. |
| Settings | no | At most 128 declarative setting definitions, below. No executable validators, scripts or HTML. |

Missing optional arrays mean empty. Catalog JSON uses arrays rather than null. This marketplace deliberately imposes narrower publishing rules than the runtime: only GitHub fixed-release links, strict SemVer without build metadata, unique permissions, normalized assembly paths, valid typed defaults and an acyclic catalog dependency graph. Runtime byte-size and extraction checks remain authoritative at installation. A manifest is at most 32768 serialized characters.

## Setting definitions

Required fields: Key (letter followed by up to 79 letters, digits, underscore, dot or hyphen), Label (nonblank, at most 200 characters), Type (string, boolean, number, secret or select).

Optional fields: DefaultValue (string or null, at most 4096 characters), Required (boolean, default false), Choices (array of at most 100 unique strings, or null). Keys must be unique within a plugin. Boolean defaults are the strings true or false. Numeric defaults must be finite numbers expressed as strings. Select requires nonempty Choices and any default must be one of them. Secret defaults must be omitted or null. **Never publish real secrets or personal settings values.**

These are descriptors for the host's generic settings UI. The v1 PluginContext API exposes Services and EnvironmentInfo; it does not promise that settings automatically appear in either. Integration with host settings is a host-side responsibility, not a claim that declarations enforce isolation.

## Archive and lifecycle

Archives are at most 32 MiB compressed, 128 MiB expanded, 2048 entries, and 32 MiB per file. This marketplace permits **only plugin .dll files**, never BotAgent.Core.dll, native installer executables, symlinks, source files or runtime scripts. The example ZIP contains exactly one compiled DLL. The complete manifest is detached to avoid a self-referential archive hash.

Host behavior: validate → download bounded ZIP → verify full SHA256 → stage an immutable version → leave community plugin disabled → operator enables and restarts. Upgrade, rollback and uninstall are restart-bound; plugin code must stop cleanly on shutdown. In-process arbitrary code may access the process's data, credentials, filesystem and network regardless of Permissions. Review both code and publisher before trusting the manifest.

Plugin assembly identity/metadata must agree with the manifest. Community plugins must set IsPreset=false. The SDK's compile-time BotAgent.Core reference must resolve to the real host-owned assembly at runtime.

See the current real [example manifest](../plugins/community.example.hello/1.0.0/manifest.json). No fake installable sample hash is provided.
