# Security and privacy

English | [简体中文](SECURITY.md)

Plugins run in process with full .NET code trust. **There is no sandbox.** Permissions are descriptive declarations, not access control. SHA256 detects changed bytes only when the index/manifest is independently trusted. HTTPS and a public source link do not establish publisher trust.

Review source and build provenance, pin a specific catalog revision when practical, inspect the full manifest, keep rollback copies, and enable only the intended plugin. A new community plugin is disabled by default and activation requires a restart. Never enable code merely because it appears in a catalog. This project does not perform production deployment.

Only compiled plugin assemblies belong in installable ZIPs. Never include a host Core DLL, source, secrets, chat logs, member profiles, personal identifiers, install hooks, build scripts or post-install commands. The checked-in maintainer tools run only during development/CI and are not distributed in plugin ZIPs.

Report vulnerabilities using GitHub's private vulnerability reporting if available. Do not post sensitive material to a public issue. If private reporting is unavailable, open a minimal issue requesting a private channel without disclosing exploit secrets, private messages or personal data. Public reproductions must use synthetic data only.
