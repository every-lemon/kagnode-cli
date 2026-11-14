//! Consistent SQLite snapshots, authenticated encryption and non-destructive checks.
use anyhow::{Result, ensure};
use ring::aead;
use rusqlite::{Connection, OpenFlags};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::{Read, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
};
const AAD: &[u8] = b"KagNode Daemon backup v1";
const LIMIT: u64 = 64 * 1024 * 1024;
struct Plaintext(PathBuf);
impl Drop for Plaintext {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
        for suffix in ["-wal", "-shm", "-journal"] {
            let mut sidecar = self.0.as_os_str().to_os_string();
            sidecar.push(suffix);
            let _ = std::fs::remove_file(PathBuf::from(sidecar));
        }
    }
}
fn private_directory(path: &Path) -> Result<()> {
    ensure!(
        path.is_absolute()
            && !path
                .components()
                .any(|p| matches!(p, std::path::Component::ParentDir)),
        "Use an absolute private backup directory without parent traversal"
    );
    for p in path.ancestors().filter(|p| p.exists()) {
        let m = p.symlink_metadata()?;
        ensure!(
            m.is_dir()
                && !m.file_type().is_symlink()
                && (m.uid() == 0 || m.uid() == unsafe { libc::geteuid() }),
            "Unsafe backup directory ancestor"
        );
    }
    std::fs::create_dir_all(path)?;
    let m = path.metadata()?;
    ensure!(
        m.uid() == unsafe { libc::geteuid() },
        "Backup directory has another owner"
    );
    ensure!(
        m.mode() & 0o077 == 0 || std::fs::read_dir(path)?.next().is_none(),
        "Do not change permissions of an existing shared directory"
    );
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700))?;
    Ok(())
}
fn read_key(path: &Path, create: bool) -> Result<zeroize::Zeroizing<Vec<u8>>> {
    ensure!(path.is_absolute(), "Use an absolute recovery-key path");
    if create && !path.exists() {
        private_directory(path.parent().unwrap())?;
        let mut bytes = zeroize::Zeroizing::new(vec![0u8; 32]);
        getrandom::fill(&mut bytes).map_err(|_| anyhow::anyhow!("OS randomness unavailable"))?;
        match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(path)
        {
            Ok(mut f) => {
                f.write_all(&bytes)?;
                f.sync_all()?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(e) => return Err(e.into()),
        }
    }
    let m = path.symlink_metadata()?;
    ensure!(
        m.is_file()
            && !m.file_type().is_symlink()
            && m.nlink() == 1
            && m.uid() == unsafe { libc::geteuid() }
            && m.mode() & 0o077 == 0
            && m.len() == 32,
        "Recovery key must be an owned private 32-byte file"
    );
    Ok(zeroize::Zeroizing::new(std::fs::read(path)?))
}
fn aead(key: &[u8]) -> Result<aead::LessSafeKey> {
    Ok(aead::LessSafeKey::new(
        aead::UnboundKey::new(&aead::AES_256_GCM, key)
            .map_err(|_| anyhow::anyhow!("Invalid recovery key"))?,
    ))
}
pub fn create(state: &Path, destination: &Path, key_path: &Path) -> Result<Value> {
    ensure!(
        !key_path.starts_with(destination) && !key_path.starts_with(state),
        "Keep the recovery key outside state and backup payloads"
    );
    private_directory(destination)?;
    let source = state.join("daemon.sqlite");
    let m = source.symlink_metadata()?;
    ensure!(
        m.is_file() && !m.file_type().is_symlink() && m.nlink() == 1 && m.len() <= LIMIT,
        "Unsafe or oversized Daemon database"
    );
    let token = crate::auth::random()?;
    let temporary = Plaintext(destination.join(format!(".snapshot-{token}")));
    std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temporary.0)?;
    let db = Connection::open_with_flags(source, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    db.backup("main", &temporary.0, None)?;
    let check = Connection::open_with_flags(&temporary.0, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    ensure!(
        check.query_row("PRAGMA integrity_check", [], |r| r.get::<_, String>(0))? == "ok",
        "SQLite snapshot failed integrity checking"
    );
    drop(check);
    ensure!(
        std::fs::metadata(&temporary.0)?.len() <= LIMIT,
        "Snapshot exceeds the encryption memory bound"
    );
    let mut bytes = zeroize::Zeroizing::new(std::fs::read(&temporary.0)?);
    let clear_hash = hex::encode(Sha256::digest(&bytes));
    let key = read_key(key_path, true)?;
    let mut nonce = [0u8; 12];
    getrandom::fill(&mut nonce).map_err(|_| anyhow::anyhow!("OS randomness unavailable"))?;
    aead(&key)?
        .seal_in_place_append_tag(
            aead::Nonce::assume_unique_for_key(nonce),
            aead::Aad::from(AAD),
            &mut *bytes,
        )
        .map_err(|_| anyhow::anyhow!("Backup encryption failed"))?;
    let stamp = chrono::Utc::now().format("%Y-%m-%d-%H-%M");
    let output = destination.join(format!(
        "KagNode Daemon-{}-{stamp}-{}.kndb",
        env!("CARGO_PKG_VERSION"),
        &token[..8]
    ));
    let mut f = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&output)?;
    f.write_all(b"KNDB1")?;
    f.write_all(&nonce)?;
    f.write_all(&bytes)?;
    f.sync_all()?;
    let verified = validate(&output, key_path, destination)?;
    ensure!(
        verified["snapshot_sha256"] == clear_hash,
        "Restored snapshot differs from the consistent original"
    );
    let result = json!({"file":output,"encrypted":true,"bytes":std::fs::metadata(&output)?.len(),"restore_checked":true,"snapshot_sha256":clear_hash,"scope":"Daemon control database only; applications and runtime identity keys require their own backup adapters","key_included":false});
    let receipt = output.with_extension("verified.json");
    let mut r = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(receipt)?;
    r.write_all(&serde_json::to_vec_pretty(&result)?)?;
    r.sync_all()?;
    Ok(result)
}
pub fn validate(file: &Path, key_path: &Path, private_work: &Path) -> Result<Value> {
    private_directory(private_work)?;
    let m = file.symlink_metadata()?;
    ensure!(
        m.is_file()
            && !m.file_type().is_symlink()
            && m.nlink() == 1
            && m.len() <= LIMIT + 64
            && m.len() > 33,
        "Unsafe or oversized encrypted backup"
    );
    let mut raw = zeroize::Zeroizing::new(Vec::new());
    std::fs::File::open(file)?
        .take(LIMIT + 65)
        .read_to_end(&mut raw)?;
    ensure!(&raw[..5] == b"KNDB1", "Unsupported backup format");
    let nonce: [u8; 12] = raw[5..17].try_into()?;
    let key = read_key(key_path, false)?;
    let clear = aead(&key)?
        .open_in_place(
            aead::Nonce::assume_unique_for_key(nonce),
            aead::Aad::from(AAD),
            &mut raw[17..],
        )
        .map_err(|_| anyhow::anyhow!("Backup authentication failed"))?;
    let hash = hex::encode(Sha256::digest(&*clear));
    let temporary =
        Plaintext(private_work.join(format!(".restore-check-{}", crate::auth::random()?)));
    let mut f = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temporary.0)?;
    f.write_all(clear)?;
    f.sync_all()?;
    let db = Connection::open_with_flags(&temporary.0, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    ensure!(
        db.query_row("PRAGMA integrity_check", [], |r| r.get::<_, String>(0))? == "ok",
        "Restored snapshot failed SQLite integrity checks"
    );
    let admins = db.query_row("SELECT count(*) FROM admins", [], |r| r.get::<_, i64>(0))?;
    ensure!(admins > 0, "Snapshot has no Daemon administrator");
    for table in ["settings", "sessions", "audit", "documents"] {
        ensure!(
            db.query_row(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?1",
                [table],
                |r| r.get::<_, i64>(0)
            )? == 1,
            "Snapshot is missing required Daemon tables"
        );
    }
    Ok(
        json!({"validated":true,"snapshot_sha256":hash,"sqlite_integrity":"ok","live_database_changed":false}),
    )
}
