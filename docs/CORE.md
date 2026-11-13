# Reviewed KagNode Core manager

`kagnode core` invokes the separately reviewed Core manager with fixed repository, signature, checksum, locking, compatibility and rollback protections. It does not automatically install backend helpers. Core is listed in the real application catalog, but `apps install core` refuses to substitute a source download for signed UI activation.

`assets/core-manager-manifest.json` pins the bundled helper and its corresponding readable source under `vendor/core-source/`. Review helper updates separately from compatible UI patches. Use `kagnode core --help` and the [canonical operations guide](https://github.com/every-lemon/kagnode-core/blob/main/docs/OPERATIONS.md).

CLI 5.0.1 removes the fictional browser examples and their server. No Core browser assets are needed by the keyboard-only TUI. Existing application bindings, pinned fallbacks and runtime data remain untouched by upgrading the CLI package. Each real application's reviewed lock governs its Core baseline and patch policy.

## Reviewing a helper update

Maintain source and runtime authority separately. After reviewing a published Core release, download its full signed package set and run:

```sh
python3 scripts/bundle_core_manager.py /path/to/reviewed-core-release --core-source /path/to/kagnode-core-checkout
```

The build step verifies the existing pinned public key, full manifest signature, every signed package checksum, canonical source archive, Python wheel bytes and committed Core Git source. It updates only this CLI source tree and its manager-only provenance. It does not install a runtime helper, change application bindings, enable automatic backend upgrades or restart any service. The UI manifest alone cannot authorize a helper import.

The reviewed 5.0.6 helper keeps manager protocol 1 and adds a sanitized `summary` query plus an independent summaries policy (`core policy APP --summaries on|off`). Automatic UI activation notices are emitted only by the trusted background update cycle. Manual application and rollback cannot claim to be automatic events. Installing this CLI source/package does not restart an existing manager; its running helper remains a separate administrator-reviewed operation.
