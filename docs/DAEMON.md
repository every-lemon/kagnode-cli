# Rust Daemon candidate

Build with `cargo build --release --locked`. The binary is `kagnode`.

## Local administration

Create a private password file (0600) and initialize an empty private state directory:

```sh
kagnode --root /srv/kagnode/daemon/controller init --email admin@example.invalid --password-file /path/to/private-password --web
kagnode serve
kagnode status --json
kagnode settings show
kagnode settings web off
```

The optional HTTP dashboard binds IPv4 loopback by default. Configure a trusted HTTPS reverse proxy before remote access and set the exact `--origin`. Disabling the dashboard leaves application services untouched. A private local health socket remains. Local administrators are distinct from KagNode Account identities and ordinary application users.

## Fresh native setup

`kagnode install --print-plan --profile production --web` prints the proposed owned files and units. Interactive setup reads from the controlling terminal, including when launched by a pipe. Noninteractive setup requires explicit email/password-file, web choice and `--yes`.

Existing CLI binaries, state directories, units and reserved service users block fresh installation rather than being overwritten. Partial installation writes a recovery receipt. Do not delete retained data to bypass a conflict; compatible migration is a separate qualification gate.

Production installs concrete service hardening plus health and backup timers. Scheduled backups remain conditional until root configures a private destination with `kagnode backup configure --directory /private/backup-directory`. Backup scope is the Daemon control database; it is not a substitute for application-native backup/export.

## Native service enrollment

Only root can enroll a fixed known product unit. The broker records installed unit fragments and drop-in hashes. Files or loaded overrides that change require re-enrollment. No arbitrary shell command or arbitrary unit name is accepted.

```sh
sudo kagnode services enroll --product pm --unit kagnode-proxy-controller.service
sudo kagnode services plan --product pm --operation restart
```

Apply requires the exact reviewed hash and a unique 32-hex request ID. Repeated matching requests return their original result. Interrupted/failed operations become uncertain and block further changes. Root must inspect actual systemd state and use the explicit resolve operation with a fresh inspection hash and reason. Resolution never changes native state or restores a database.

## Encrypted backups

Recovery keys default outside application state and backup payloads at `/var/lib/kagnode-keys/daemon-backup.key`. Keep a separate secure recovery-key copy. Encrypted snapshots use authenticated encryption, consistent SQLite backup and a non-destructive restore/integrity check. Validation temporary files and their SQLite sidecars are removed. Native application state and enrollment keys have separate backup adapters and qualification requirements.

## HA declarations

`kagnode ha plan --file cluster.json` validates identities, failure domains, VLAN IDs, virtual IPs and selected applications. It reports unresolved networking, quorum, storage, fencing and adapter checks. Neither the terminal nor the browser can bypass those checks by submitting a boolean. Current source has no live HA activation operation.
