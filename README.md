<p align="center"><img src="assets/kagnode-wordmark.svg" width="440" alt="KagNode."></p>

# KagNode. Daemon

## Overview

An administrator workspace for KagNode applications, with a shared Core dashboard and a Rust terminal interface. The repository was renamed from `kagnode-cli`; existing releases, account credentials, native data and the `kagnode` command remain compatible.

## Release status

The released **5.0.2** compatibility CLI remains available. The **5.0.3 Rust Daemon candidate** adds local administration, Core presentation, terminal folder navigation, reviewed native service operations, encrypted control-database backups and fresh-install profiles. Qualification and migration work is tracked in [the Rust migration matrix](docs/RUST-MIGRATION.md).

The Rust candidate does not replace an existing CLI installation until compatibility is qualified. Remote node management, live networking, automatic HA and Core Server Offloading remain gated. Saving a cluster declaration is not HA activation. Existing application runtimes and data stay in place.

## Features

- Rust administrator sessions, Argon2 credentials, CSRF protection, revision conflicts and audit history.
- Canonical Core login, sidebar, folder navigation, search, account controls and preferences.
- Keyboard/mouse terminal browsing and scriptable JSON inspection.
- Root-enrolled service bindings, reviewed definition/state hashes, request idempotency and uncertain-operation recovery.
- Fresh Light/Production install profiles; optional web dashboard with private local administration retained.
- Consistent encrypted Daemon database snapshots with restore checks; application data retains separate backup ownership.
- Typed HA declarations and fail-closed promotion preconditions; live cluster activation remains unqualified.
- Retained compatibility CLI source and existing account/installer/update flows during staged Rust replacement.

## Requirements

The Rust candidate requires Rust 1.88 or newer to build. Native setup targets Ubuntu 24.04 and Debian 13; Linux amd64/arm64 qualification is recorded separately. The new Rust server/terminal runtime does not require Node.js, Go or Python. Browser UI remains HTML/CSS/JavaScript. Existing third-party engines keep their own dependencies.

The retained 5.0.2 compatibility CLI uses Go and Python management helpers, as documented in its release. It stays available until each Rust replacement passes parity and upgrade checks.

## Installation and downloads

Download from [GitHub Releases](https://github.com/every-lemon/kagnode-daemon/releases). Verify `SHA256SUMS` before extracting or installing a package.

| Payload                   | Formats                                      | Support                                     |
| ------------------------- | -------------------------------------------- | ------------------------------------------- |
| Complete source / artwork | `.tar.xz`, `.tar.gz`, `.zip`                 | Named top-level directory; manual setup     |
| Source                    | `.deb`                                       | Source only; does not provision a service   |
| Source                    | `.rpm`                                       | Rocky Linux 10 source payload; manual build |
| Linux CLI binaries        | `.deb`, `.rpm`, `.tar.xz`, `.tar.gz`, `.zip` | amd64 and arm64                             |

Linux arm64 binaries are cross-built; disposable package lifecycle checks run on amd64. Physical/native service qualification remains separate.

Source packages install under `/usr/share/kagnode/`; they do not replace an existing application, migrate data, start services or configure networking. CLI binary packages install /usr/bin/kagnode. See [package details](docs/PACKAGING.md).

## Usage

```sh
kagnode login
kagnode whoami
kagnode setup
kagnode apps list
kagnode apps plan mail --mode native --config /root/mail-config.json --save-plan /root/mail-plan.json
kagnode apps apply mail --plan /root/mail-plan.json
```

See [reviewed application setup](docs/INSTALLERS.md) and [account sign-in](docs/ACCOUNT-SYNC.md) for prerequisites and recovery.

## Configuration and storage

The [KagNode Core manager](docs/CORE.md) verifies signed UI releases and reviewed adapters. This terminal application has no browser-demo server.

Account credentials remain under the user-scoped KagNode XDG configuration directory (0600). Applications share `/srv/kagnode` for releases, configuration and manager state; native projects retain their declared native data locations. Old example data in the XDG data directory is retained but no longer distributed or served.

## Security

Use HTTPS and least-privilege accounts for hosted services. Keep secrets and user data out of Git. Managed application/native-service capabilities are qualified separately; installing the CLI does not qualify or automatically deploy them. See [security guidance](docs/SECURITY.md).

## Development and testing

```sh
go test ./...
go vet ./...
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/tui_pty.py
python3 scripts/repository_check.py
python3 scripts/format_source.py --check
python3 scripts/release.py --output dist/packages
```

Install the formatting dependencies from `requirements-format.txt`. Package building additionally needs `dpkg-deb`, `rpmbuild`, XZ support and, for CLI binaries, Go. Read [the repository map](docs/STRUCTURE.md) before editing generated files.

## Documentation

- [Ecosystem setup, update adapters and current limitations](docs/ECOSYSTEM.md)

- [Repository structure](docs/STRUCTURE.md)
- [Historical operations](docs/OPERATIONS.md)
- [Packages and release process](docs/PACKAGING.md)
- [Verification and limits](docs/VERIFICATION.md)
- [KagNode Account linking](docs/ACCOUNT-SYNC.md)
- [Changelog](CHANGELOG.md)

## Licensing

See [LICENSE](LICENSE) and retained third-party notices. KagNode artwork retains its separate permission and brand policy; the application uses AGPL-3.0-only.
