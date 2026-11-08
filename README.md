<p align="center"><img src="assets/kagnode-wordmark.svg" width="440" alt="KagNode."></p>

# KagNode CLI

## Overview

Linux terminal and browser tools for KagNode account sign-in and explicitly fictional cloud examples.

## Release status

Product source: **1.2.0-beta.1**. Packaging preview: **1.2.0-beta.1.packaging.14**.

Packaging prereleases do not change the latest stable release or establish new hardware or service compatibility. See [verification](docs/VERIFICATION.md) and [changelog](CHANGELOG.md).

## Features

- Keyboard-only application setup wizard and a shared installation root.
- GitHub release checks, verified source installs and local admin-panel update manager.
- Optional digest-pinned Vaultwarden engine setup for KagNode Passwords.

- Browser-assisted account sign-in.
- Interactive terminal interface and local browser examples.
- Fictional product workflows; no live provisioning, inference or billing API.

Optional KagNode Account linking syncs your display name and photo after explicit approval. Your local application administrator can disable it. Local sign-in and permissions stay independent.

## Requirements

Linux amd64 or arm64. Building from source requires Go as specified by go.mod; packaged binaries do not require Go or Node.js.

## Installation and downloads

Download from [GitHub Releases](https://github.com/every-lemon/kagnode-cli/releases). Verify `SHA256SUMS` before extracting or installing a package.

| Payload | Formats | Support |
| --- | --- | --- |
| Complete source / artwork | `.tar.xz`, `.tar.gz`, `.zip` | Named top-level directory; manual setup |
| Source preview | `.deb` | Source only; does not provision a service |
| Source preview | `.rpm` | Rocky Linux 10 packaging preview; native services unverified |
| Linux CLI binaries | `.deb`, preview `.rpm`, `.tar.xz`, `.tar.gz`, `.zip` | amd64 and arm64 |



Source packages install under `/usr/share/kagnode/`; they do not replace an existing application, migrate data, start services or configure networking. CLI binary packages install /usr/bin/kagnode. See [package details](docs/PACKAGING.md).

## Usage

```sh
kagnode login
kagnode whoami
kagnode demo install
kagnode demo start
```

See [operations and existing setup instructions](docs/OPERATIONS.md) for the full workflow and its prerequisites.

## Configuration and storage

Shared presentation uses [KagNode Core](docs/CORE.md), with a pinned local fallback and reviewed server adapters. Compatible stable UI patches have a separate local-administrator policy.

Account credentials stay under the user-scoped KagNode XDG configuration directory; local demo data stays in its separate XDG data directory.

## Security

Use HTTPS and least-privilege accounts for hosted services. Keep secrets and user data out of Git. Preview packages are for inspection and controlled testing; native service and hardware claims remain limited to recorded verification. See [security guidance](docs/SECURITY.md).

## Development and testing

```sh
go test ./...
go vet ./...
python3 scripts/repository_check.py
python3 scripts/format_source.py --check
python3 scripts/release.py --output dist/packages
```

Install the formatting dependencies from `requirements-format.txt`. Package building additionally needs `dpkg-deb`, `rpmbuild`, XZ support and, for CLI binaries, Go. Read [the repository map](docs/STRUCTURE.md) before editing generated files.

## Documentation

- [Ecosystem setup, update adapters and current limitations](docs/ECOSYSTEM.md)

- [Repository structure](docs/STRUCTURE.md)
- [Operations](docs/OPERATIONS.md)
- [Packages and release process](docs/PACKAGING.md)
- [Verification and limits](docs/VERIFICATION.md)
- [KagNode Account linking](docs/ACCOUNT-SYNC.md)
- [Changelog](CHANGELOG.md)

## Licensing

See [LICENSE](LICENSE) and retained third-party notices. KagNode artwork retains its separate permission and brand policy; the application uses AGPL-3.0-only.
