use crate::{
    auth,
    store::{Profile, Store},
};
use anyhow::{Result, ensure};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    io::Write,
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    process::Command,
};

fn unit(profile: Profile, broker: bool, origin: &str) -> String {
    let mut s = if broker {
        "[Unit]\nDescription=KagNode restricted native service broker\nAfter=network.target\n[Service]\nType=simple\nUser=root\nExecStart=/usr/libexec/kagnode-daemon/kagnode broker --allowed-uid=@UID@\nRuntimeDirectory=kagnode-daemon\nRuntimeDirectoryMode=0755\nReadWritePaths=/run/kagnode-daemon /var/lib/kagnode-daemon /etc/kagnode/daemon\n".to_owned()
    } else {
        format!(
            "[Unit]\nDescription=KagNode Daemon\nAfter=network.target kagnode-daemon-broker.service\nRequires=kagnode-daemon-broker.service\n[Service]\nType=simple\nUser=kn-daemon\nGroup=kn-daemon\nExecStart=/usr/libexec/kagnode-daemon/kagnode --root /srv/kagnode/daemon/controller serve --origin {origin}\nReadWritePaths=/srv/kagnode/daemon/controller\n"
        )
    };
    s += "Restart=on-failure\nRestartSec=5\nUMask=0077\nPrivateTmp=true\nProtectHome=true\nNoNewPrivileges=true\n";
    if profile == Profile::Production {
        s += "ProtectSystem=strict\nProtectKernelTunables=true\nProtectKernelModules=true\nProtectControlGroups=true\nProtectKernelLogs=true\nRestrictSUIDSGID=true\nLockPersonality=true\nMemoryHigh=192M\nMemoryMax=256M\nTasksMax=64\nLogRateLimitIntervalSec=30s\nLogRateLimitBurst=200\n";
    }
    s += "[Install]\nWantedBy=multi-user.target\n";
    s
}
pub fn units(profile: Profile, origin: &str) -> BTreeMap<String, String> {
    let mut files = BTreeMap::from([
        (
            "kagnode-daemon.service".into(),
            unit(profile, false, origin),
        ),
        (
            "kagnode-daemon-broker.service".into(),
            unit(profile, true, origin),
        ),
    ]);
    if profile == Profile::Production {
        files.insert("kagnode-daemon-monitor.service".into(),"[Unit]\nDescription=KagNode Daemon local health inspection\nAfter=kagnode-daemon.service\n[Service]\nType=oneshot\nUser=kn-daemon\nExecStart=/usr/libexec/kagnode-daemon/kagnode health\nNoNewPrivileges=true\nProtectSystem=strict\nProtectHome=true\nPrivateTmp=true\nReadWritePaths=/srv/kagnode/daemon/controller\n".into());
        files.insert("kagnode-daemon-monitor.timer".into(),"[Unit]\nDescription=Check KagNode Daemon health\n[Timer]\nOnBootSec=2min\nOnUnitActiveSec=1min\nRandomizedDelaySec=10\n[Install]\nWantedBy=timers.target\n".into());
        files.insert("kagnode-daemon-backup.service".into(),"[Unit]\nDescription=Encrypted KagNode Daemon control database snapshot\nConditionPathExists=/etc/kagnode/daemon/backup-destination\n[Service]\nType=oneshot\nUser=root\nExecStart=/usr/libexec/kagnode-daemon/kagnode backup scheduled\nUMask=0077\nNoNewPrivileges=true\nProtectHome=true\nPrivateTmp=true\n".into());
        files.insert("kagnode-daemon-backup.timer".into(),"[Unit]\nDescription=Schedule KagNode Daemon backups after destination configuration\n[Timer]\nOnCalendar=*-*-* 03:30:00 UTC\nRandomizedDelaySec=15min\nPersistent=true\n[Install]\nWantedBy=timers.target\n".into());
    }
    files
}
pub fn plan(profile: Profile, web: bool, origin: &str) -> Result<Value> {
    ensure!(
        origin == "http://127.0.0.1:8750" || origin.starts_with("https://"),
        "Use a local or HTTPS dashboard origin"
    );
    let url = reqwest::Url::parse(origin)?;
    ensure!(
        url.path() == "/"
            && url.query().is_none()
            && url.fragment().is_none()
            && url.username().is_empty()
            && url.password().is_none()
            && !origin.chars().any(char::is_whitespace),
        "Configure an origin without paths, credentials or whitespace"
    );
    Ok(
        json!({"schema":1,"product":"kagnode-daemon","version":env!("CARGO_PKG_VERSION"),"profile":profile,"web":web,"origin":origin,"root":"/srv/kagnode/daemon","service_user":"kn-daemon","units":units(profile,origin).keys().collect::<Vec<_>>(),"unit_definitions":units(profile,origin),"production_backup":"scheduled only after a private destination is configured","existing_applications":"retained","existing_cli_migration":"blocked until compatibility is qualified","network_or_ha_activation":false}),
    )
}
fn checked(command: &str, args: &[&str]) -> Result<()> {
    ensure!(
        Command::new(command).args(args).status()?.success(),
        "Required installation operation failed: {command}"
    );
    Ok(())
}
fn new_file(path: &Path, bytes: &[u8], mode: u32) -> Result<()> {
    ensure!(
        !path.exists() && !path.is_symlink(),
        "An installation target already exists: {}",
        path.display()
    );
    std::fs::create_dir_all(path.parent().unwrap())?;
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(mode)
        .open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}
fn protected_ancestors(path: &Path) -> Result<()> {
    ensure!(
        path.is_absolute()
            && !path
                .components()
                .any(|p| matches!(p, std::path::Component::ParentDir)),
        "Use an absolute protected path"
    );
    for parent in path.ancestors().skip(1).filter(|p| p.exists()) {
        let m = parent.symlink_metadata()?;
        ensure!(
            m.is_dir() && !m.file_type().is_symlink() && m.uid() == 0 && m.mode() & 0o022 == 0,
            "Installation parents must be protected root-owned directories: {}",
            parent.display()
        );
    }
    Ok(())
}
pub fn apply(
    email: &str,
    password: &str,
    profile: Profile,
    web: bool,
    origin: &str,
) -> Result<Value> {
    ensure!(
        unsafe { libc::geteuid() } == 0,
        "Installation needs root privileges"
    );
    let reviewed = plan(profile, web, origin)?;
    let os = std::fs::read_to_string("/etc/os-release")?;
    ensure!(
        (os.lines().any(|l| l == "ID=ubuntu") && os.lines().any(|l| l == "VERSION_ID=\"24.04\""))
            || (os.lines().any(|l| l == "ID=debian")
                && os.lines().any(|l| l == "VERSION_ID=\"13\"")),
        "Native setup currently targets Ubuntu 24.04 and Debian 13"
    );
    let base = Path::new("/srv/kagnode/daemon");
    let exe = Path::new("/usr/libexec/kagnode-daemon/kagnode");
    // Complete the conflict audit before creating users, files or services.
    for path in [
        base,
        exe,
        Path::new("/usr/bin/kagnode"),
        Path::new("/var/lib/kagnode-daemon"),
        Path::new("/etc/kagnode/daemon"),
    ] {
        protected_ancestors(path)?;
        ensure!(
            !path.exists() && !path.is_symlink(),
            "Existing installation retained. Review compatible migration before replacing {}",
            path.display()
        );
    }
    for name in units(profile, origin).keys() {
        protected_ancestors(&Path::new("/etc/systemd/system").join(name))?;
        ensure!(
            !Path::new("/etc/systemd/system").join(name).exists(),
            "Existing service definition retained: {name}"
        );
    }
    ensure!(
        !Command::new("/usr/bin/id")
            .args(["-u", "kn-daemon"])
            .output()?
            .status
            .success(),
        "Reserved service account already exists; review its existing data before installation"
    );
    let source = std::env::current_exe()?.canonicalize()?;
    let metadata = source.metadata()?;
    ensure!(
        metadata.uid() == 0 && metadata.mode() & 0o022 == 0,
        "Run the verified root-owned installation candidate"
    );
    let _ = auth::email(email)?;
    let _ = auth::hash_password(password)?;
    std::fs::create_dir_all(base)?;
    std::fs::set_permissions(base, std::fs::Permissions::from_mode(0o755))?;
    let record = base.join("installation.json");
    let mut receipt = reviewed;
    receipt["state"] = json!("preparing");
    new_file(&record, &serde_json::to_vec_pretty(&receipt)?, 0o600)?;
    let result = (|| -> Result<Value> {
        checked(
            "/usr/sbin/useradd",
            &[
                "--system",
                "--user-group",
                "--home-dir",
                "/srv/kagnode/daemon/controller",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                "kn-daemon",
            ],
        )?;
        let user = String::from_utf8(
            Command::new("/usr/bin/id")
                .args(["-u", "kn-daemon"])
                .output()?
                .stdout,
        )?
        .trim()
        .parse::<u32>()?;
        let group = String::from_utf8(
            Command::new("/usr/bin/id")
                .args(["-g", "kn-daemon"])
                .output()?
                .stdout,
        )?
        .trim()
        .parse::<u32>()?;
        for p in ["/var/lib/kagnode-daemon", "/etc/kagnode/daemon"] {
            std::fs::create_dir_all(p)?;
            std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o700))?;
        }
        let state = base.join("controller");
        let store = Store::open(&state)?;
        store.init(email, password, profile, web)?;
        drop(store);
        for entry in std::iter::once(state.clone())
            .chain(std::fs::read_dir(&state)?.filter_map(|e| e.ok().map(|e| e.path())))
        {
            let c = std::ffi::CString::new(entry.as_os_str().as_encoded_bytes())?;
            ensure!(
                unsafe { libc::chown(c.as_ptr(), user, group) } == 0,
                "Cannot assign controller storage ownership"
            );
        }
        let bytes = std::fs::read(source)?;
        new_file(exe, &bytes, 0o755)?;
        std::os::unix::fs::symlink(exe, "/usr/bin/kagnode")?;
        let mut hashes = BTreeMap::new();
        for (name, text) in units(profile, origin) {
            let path = Path::new("/etc/systemd/system").join(&name);
            let text = text.replace("@UID@", &user.to_string());
            new_file(&path, text.as_bytes(), 0o644)?;
            hashes.insert(name, hex::encode(Sha256::digest(text.as_bytes())));
        }
        receipt["state"] = json!("installed");
        receipt["uid"] = json!(user);
        receipt["gid"] = json!(group);
        receipt["binary_sha256"] = json!(hex::encode(Sha256::digest(bytes)));
        receipt["unit_sha256"] = json!(hashes);
        std::fs::write(&record, serde_json::to_vec_pretty(&receipt)?)?;
        checked("/usr/bin/systemctl", &["daemon-reload"])?;
        checked(
            "/usr/bin/systemctl",
            &[
                "enable",
                "--now",
                "kagnode-daemon-broker.service",
                "kagnode-daemon.service",
            ],
        )?;
        if profile == Profile::Production {
            checked(
                "/usr/bin/systemctl",
                &[
                    "enable",
                    "--now",
                    "kagnode-daemon-monitor.timer",
                    "kagnode-daemon-backup.timer",
                ],
            )?;
        }
        receipt["state"] = json!("started");
        std::fs::write(&record, serde_json::to_vec_pretty(&receipt)?)?;
        Ok(receipt.clone())
    })();
    if let Err(error) = &result {
        receipt["state"] = json!("needs_recovery");
        receipt["error"] = json!(error.to_string());
        let _ = std::fs::write(record, serde_json::to_vec_pretty(&receipt)?);
    }
    result
}
pub fn configure_backup(destination: &Path) -> Result<Value> {
    ensure!(
        unsafe { libc::geteuid() } == 0,
        "Root must configure the private backup destination"
    );
    ensure!(
        destination.is_absolute()
            && !destination
                .components()
                .any(|p| matches!(p, std::path::Component::ParentDir))
            && !destination.starts_with("/etc/kagnode")
            && !destination.starts_with("/var/lib/kagnode-keys"),
        "Choose a backup directory separate from recovery keys and configuration"
    );
    for p in destination.ancestors().filter(|p| p.exists()) {
        ensure!(!p.is_symlink(), "Backup paths cannot traverse symlinks");
    }
    std::fs::create_dir_all(destination)?;
    let m = destination.metadata()?;
    ensure!(m.uid() == 0, "Backup destination must belong to root");
    ensure!(
        m.mode() & 0o077 == 0 || std::fs::read_dir(destination)?.next().is_none(),
        "Choose a private backup directory; existing shared directory permissions are retained"
    );
    std::fs::set_permissions(destination, std::fs::Permissions::from_mode(0o700))?;
    let path = PathBuf::from("/etc/kagnode/daemon/backup-destination");
    new_file(&path, destination.to_string_lossy().as_bytes(), 0o600)?;
    Ok(
        json!({"destination":destination,"scheduled_when_production_timer_enabled":true,"off_host_copy_configured":false}),
    )
}
