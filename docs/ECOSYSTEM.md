# KagNode ecosystem manager

`kagnode setup` is a keyboard-only application wizard: arrows/Tab select, Enter
continues, Esc goes back. It never enables mouse reporting. `kagnode tui` also
provides `/setup` and `/apps`. Scriptable equivalents:

```sh
kagnode apps list
kagnode apps check passwords --channel preview
sudo kagnode apps --root /srv/kagnode install passwords --channel preview
sudo kagnode apps --root /srv/kagnode setup passwords --origin https://passwords.example.com
```

## Shared application root

Fresh managed installations use `/srv/kagnode/<app>/` with `releases/`, an atomic
`current` link, `config/`, `data/`, `logs/`, `backups/` and `downloads/`.
Choose a different absolute root with `--root` or `KAGNODE_ROOT`. Web applications
use `KAGNODE_ECOSYSTEM_ROOT` for the same value. Runtime users cannot modify their
release code. App-specific data stays private. OS packages, service definitions,
user identities, kernel state and system networking necessarily remain in their
normal system locations.

Existing installations are not moved or overwritten automatically. Source
packaging and native provisioners retain their existing compatibility paths.
A common source-download directory is not a migration of live databases, images,
mail storage or native service configuration.

## Available operations

| Application | Release check and verified source install | Managed service setup/update |
| --- | --- | --- |
| Passwords | Yes | Python virtual environment, loopback web service |
| Media | Yes | Node.js 24 web service; native codecs remain separate |
| Logos | Yes | Data-only artwork with loopback gallery server |
| CLI | Yes | Go source build; choose the resulting binary explicitly |
| Mail | Yes | Bound existing installation: guarded web-code updates |
| VPN | Yes | Bound existing installation: signed native updater |
| HTTP Boot | Yes | Bound existing installation: web console only; images separate |

Mail and VPN's original provisioners expect a dedicated supported host. Downloading
their source does not provision a mail/VPN server or resolve port, firewall and DNS
conflicts with other native services. Fresh native provisioning still uses those
projects' documented installers. Passwords, Media and Logos have managed web setup.

Existing native installations can use a narrow update adapter:

```sh
sudo kagnode apps bind-native mail --channel preview
sudo kagnode apps bind-native httpboot --channel preview
sudo kagnode apps bind-native vpn --channel preview
```

Binding recognizes only the documented native paths. Mail updates require unchanged
database/guard source; HTTP Boot updates require unchanged core, persistence,
snapshot and client-update source. Only listed web application files are replaced.
A change to those guards requires a separately reviewed native migration. VPN uses
its existing trusted release key, signed manifest and checksum-verified native
updater; packaging archives cannot bypass that signature requirement. No boot image
or Client media is rebuilt. Source and installed release versions can differ while
native qualification is pending.

### Consolidating existing native paths

```sh
sudo kagnode apps --root /srv/kagnode consolidate mail
sudo kagnode apps --root /srv/kagnode consolidate mail --apply
sudo kagnode apps --root /srv/kagnode consolidate mail --rollback
```

The first command previews exact paths. Apply requires the relevant services to be
stopped. It copies and inventories recognized application code, configuration and
data, retains original directories, and places compatibility links at old paths.
It refuses unknown/symlink layouts and insufficient space. A journal tracks partial
operations. Rollback retains subsequent writes for reconciliation; it does not
silently replace new data with an older snapshot. Test the preview and backup first.
This command is also available in the setup wizard. It has only fixture validation;
no live Mail, VPN, HTTP Boot or user saves were migrated for this release.

## One-click updates for managed services

Enable the panel for its actual local service account, then run the manager:

```sh
sudo kagnode apps enable-panel passwords --user kn-passwords
sudo kagnode apps serve
```

For persistence use `packaging/kagnode-updates.service`, adjusting the installed
CLI path and root. The service exposes **Unix sockets only**, one for each enabled
app. It checks the connecting process UID; application routes additionally require
an authenticated local administrator and existing CSRF protections. Applications
never receive a root shell or an arbitrary command/URL interface.

Open the app's local administration/settings page to check GitHub and review an
update. The release ID must still match the reviewed candidate. Downloads are
bounded, pinned to the intended GitHub repository, and checked against published
SHA-256 and sizes. These checks trust GitHub/repository release control; they are
not an independent signing system. VPN's native signature system is not replaced.

An update prepares code before stopping the old service, retains the old release,
and copies data/config while the managed service is stopped. Failed activation
keeps the data and backup and stops the failed service. It does not rewind a
possibly migrated database automatically. Inspect the journal and operation
record, then choose the appropriate recovery with a verified backup. Preview
channels are explicit; paused native/stable qualification is not promoted.

## Compatible Passwords engine

```sh
kagnode apps bitwarden --origin https://vault.example.com
sudo kagnode apps bitwarden --origin https://vault.example.com --apply
```

The first command previews the selected upstream stable release. The apply step
requires Docker/Compose, pulls the official image and pins its digest in
`passwords/bitwarden/compose.json`. It retains a separate private data directory,
starts with registration disabled and creates a private administrator token file.
It is a separate upstream web vault and does not make the KagNode Flask API speak
the Bitwarden protocol. Configure HTTPS before using client apps.
Existing local vaults and passwords are not converted. See the Passwords project
for HTTPS proxy, invitation, export/import and backup instructions.

The manager handles one application update at a time. Graceful shutdown waits for
an update; restart marks interrupted work and safely replaces stale owned sockets.
If backup fails before activation, the old service restarts. Failed activation stops
the candidate and records recovery as required rather than automatically rewinding
a database. Review `operation.json`, the retained release and its private backup.

## Verification boundaries

Unit tests use disposable directories and mocked service/process calls; they do
not install mail/network services, execute FFmpeg, build boot images or modify
live vaults. Test deployments and native migrations separately before production.
