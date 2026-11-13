# Reviewed KagNode Core manager

`kagnode core` invokes the separately reviewed Core manager with fixed repository, signature, checksum, locking, compatibility and rollback protections. It does not automatically install backend helpers. Core is listed in the real application catalog, but `apps install core` refuses to substitute a source download for signed UI activation.

`assets/core-manager-manifest.json` pins the bundled helper and its corresponding readable source under `vendor/core-source/`. Review helper updates separately from compatible UI patches. Use `kagnode core --help` and the [canonical operations guide](https://github.com/every-lemon/kagnode-core/blob/main/docs/OPERATIONS.md).

CLI 5.0.1 removes the fictional browser examples and their server. No Core browser assets are needed by the keyboard-only TUI. Existing application bindings, pinned fallbacks and runtime data remain untouched by upgrading the CLI package. Each real application's reviewed lock governs its Core baseline and patch policy.
