# Rust migration and verification matrix

All product versions remain on 5.0.x. The current public 5.0.2 packages preserve the compatibility CLI. Rust 5.0.3 is a staged candidate until the following gates pass.

| Component              | Current implementation                                                                                       | Remaining qualification                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Local admin/auth       | Rust Argon2, hashed revocable sessions, CSRF, private SQLite                                                 | Optional KagNode linking and application-specific user adapters                          |
| Dashboard              | Rust/Axum with canonical Core templates and local assets                                                     | Full application adapters and remote-node roles                     |
| Terminal               | Rust/Ratatui folder browsing, search, keyboard and optional mouse                                            | Interactive configuration/action parity                                            |
| Native lifecycle       | Rust root broker, root-enrolled fixed units, reviewed hashes, idempotency and uncertainty journal            | Remote-node enrollment and per-product recovery qualification                                        |
| Install profiles       | Rust guarded fresh install, optional loopback dashboard, concrete Production hardening/monitor/backup timers | Debian native lifecycle and legacy migration                                      |
| Backups                | Rust consistent SQLite snapshot, authenticated encryption, restore/integrity checks, separate recovery key   | Retention/off-host handling and application-specific backup adapters               |
| HA                     | Typed declarations and safety preconditions; activation is blocked                                           | Pacemaker/Corosync/DRBD, fencing, witness, VLAN and per-app recovery qualification |
| Netctl                 | Separate Rust inspection, rendering and IPAM project                                                         | Agent integration and safe native network transaction adapters                     |
| Shared Core management | Released signed UI patch mechanism retained                                                                  | Rust manager parity and optional pinned GitHub delivery                            |
| Application migration  | Existing PM/Entropy Rust retained; other runtimes stay intact                                                | VPN, Passwords, Media, Mail and HTTP Boot compatible Rust replacements             |

Preserve existing database schemas, account/vault encryption, identity grants, package identities and native installation roots. Do not substitute downloaded source for an upgrade of a project-owned runtime. Do not rebuild HTTP Boot images, execute Media transcoding or resume hardware qualification as part of source migration.

Native activation on existing machines remains a later reviewed phase. Public Core UI patches are deployed separately without changing application policies or restarting native services.

## Isolated qualification — 2026-11-14

The Rust 5.0.3 candidate was installed on an owned Ubuntu 24.04 disposable VM in Production mode. Native checks passed fresh-install conflict protection, private health access, hardened services/timers, allowlisted start/stop/restart, duplicate request replay, changed unit rejection and unprivileged peer refusal. An intentionally failed operation remained uncertain across broker restart; a fresh root inspection resolved it without another service operation. Encrypted control-database snapshots passed a separate restore/integrity check. Existing PM traffic was not restarted.

Chromium and WebKit passed the real VM dashboard on desktop and mobile: progressive login, folder entry/back, settings, HA declarations, application status, activity and sign-out/session revocation. These results cover the tested candidate and fixture, not live host migration, remote control, actual cluster failover or every supported platform. Subsequent hardening retains unit regressions and must pass CI before merge.
