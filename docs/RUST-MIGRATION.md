# Rust migration and verification matrix

All product versions remain on 5.0.x. The current public 5.0.2 packages preserve the compatibility CLI. Rust 5.0.3 is a staged candidate until the following gates pass.

| Component              | Current implementation                                                                                       | Remaining qualification                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Local admin/auth       | Rust Argon2, hashed revocable sessions, CSRF, private SQLite                                                 | Native/browser account flows and optional KagNode linking                          |
| Dashboard              | Rust/Axum with canonical Core templates and local assets                                                     | Full application adapters, remote-node roles and browser audit                     |
| Terminal               | Rust/Ratatui folder browsing, search, keyboard and optional mouse                                            | Interactive configuration/action parity                                            |
| Native lifecycle       | Rust root broker, root-enrolled fixed units, reviewed hashes, idempotency and uncertainty journal            | Disposable native permission/recovery tests                                        |
| Install profiles       | Rust guarded fresh install, optional loopback dashboard, concrete Production hardening/monitor/backup timers | Native install lifecycle and legacy migration                                      |
| Backups                | Rust consistent SQLite snapshot, authenticated encryption, restore/integrity checks, separate recovery key   | Native scheduling/retention and application-specific backup adapters               |
| HA                     | Typed declarations and safety preconditions; activation is blocked                                           | Pacemaker/Corosync/DRBD, fencing, witness, VLAN and per-app recovery qualification |
| Netctl                 | Separate Rust inspection, rendering and IPAM project                                                         | Agent integration and safe native network transaction adapters                     |
| Shared Core management | Released signed UI patch mechanism retained                                                                  | Rust manager parity and optional pinned GitHub delivery                            |
| Application migration  | Existing PM/Entropy Rust retained; other runtimes stay intact                                                | VPN, Passwords, Media, Mail and HTTP Boot compatible Rust replacements             |

Preserve existing database schemas, account/vault encryption, identity grants, package identities and native installation roots. Do not substitute downloaded source for an upgrade of a project-owned runtime. Do not rebuild HTTP Boot images, execute Media transcoding or resume hardware qualification as part of source migration.

Native activation on existing machines remains a later reviewed phase. Public Core UI patches are deployed separately without changing application policies or restarting native services.
