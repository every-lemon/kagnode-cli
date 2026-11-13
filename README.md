<p align="center"><img src="assets/kagnode-wordmark.svg" width="440" alt="KagNode."></p>

# KagNode CLI

## Overview

A keyboard-only Linux application manager and KagNode Account client. Review real project-owned installation plans before changing your system.

## Release status

**5.0.1** is the coordinated stable CLI release, replacing fictional examples with real application setup and browser PKCE sign-in.

Stable scope covers the CLI and tested installer orchestration. Each project declares its supported operating systems and setup modes; native services and hardware retain separate verification boundaries. See [verification](docs/VERIFICATION.md) and [changelog](CHANGELOG.md).

## Features

- Keyboard-only application setup wizard and a shared installation root.
- GitHub release checks, verified source installs and local admin-panel update manager.
- Optional digest-pinned Vaultwarden engine setup for KagNode Passwords.

- Login with KagNode through the shared account sign-in and approval journey.
- Browser authorization with a private loopback return, PKCE and validated fresh proof; explicit headless fallback.
- Project-owned dependency, configuration, review, health and recovery interfaces.
- Entropy and signed Core catalog entries. Retired demo commands explain their removal; existing user data remains.

Optional KagNode Account linking syncs your display name and photo after explicit approval. Your local application administrator can disable it. Local sign-in and permissions stay independent.

## Requirements

Linux amd64 or arm64. Account sign-in uses the compiled binary. Application/Core management also requires Python 3.10+ and the system tools declared by the selected project. Building from source requires Go as specified by go.mod; packaged binaries do not require Go or Node.js.

## Installation and downloads

Download from [GitHub Releases](https://github.com/every-lemon/kagnode-cli/releases). Verify `SHA256SUMS` before extracting or installing a package.

| Payload | Formats | Support |
| --- | --- | --- |
| Complete source / artwork | `.tar.xz`, `.tar.gz`, `.zip` | Named top-level directory; manual setup |
| Source | `.deb` | Source only; does not provision a service |
| Source | `.rpm` | Rocky Linux 10 source payload; manual build |
| Linux CLI binaries | `.deb`, `.rpm`, `.tar.xz`, `.tar.gz`, `.zip` | amd64 and arm64 |



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
