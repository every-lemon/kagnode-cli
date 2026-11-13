# Repository map

| Area | Editable source | Purpose |
| --- | --- | --- |
| Commands and credentials | `main.go`, `browser_login.go`, `account_sync.go` | Account protocol, private storage and scriptable commands |
| Terminal UI | `tui.go`, `ecosystem.go` | Keyboard navigation, bounded output and reviewed setup wizard |
| Local manager | `assets/ecosystem.py`, `assets/installer.py` | Release verification and fixed project installer invocation |
| Installer protocol | `adapters/installer_protocol.py` | Vendored project interface validation; no native business rules |
| Core manager | `assets/core_manager.py`, `vendor/core-source/` | Separately reviewed signed UI/helper provenance |
| Tests | Go test files and `tests/` | Disposable mocked services and protocol fixtures |
| Packages | `packaging/`, `scripts/release.py` | Explicit source allowlist and reproducible named archives |
| Generated output | `dist/` | Ignored builds and package scratch |

`main.go` is the single version source. `packaging/source-files.json` is a reviewed source allowlist; refresh it when adding or removing tracked source. Runtime credentials, databases, caches and build scratch are excluded.

The retired fictional example files are listed in [the cleanup audit](REMOVED-EXAMPLES.md). Their user runtime data is preserved. Use Go formatting and the pinned Ruff checks through `scripts/format_source.py`; no browser-example generation remains.
