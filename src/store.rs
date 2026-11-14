use crate::auth;
use anyhow::{Result, ensure};
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use std::{
    os::unix::fs::{MetadataExt, PermissionsExt},
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};

#[derive(Clone)]
pub struct Store {
    pub root: PathBuf,
    db: Arc<Mutex<Connection>>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
#[serde(rename_all = "lowercase")]
pub enum Profile {
    Light,
    Production,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Settings {
    pub revision: u64,
    pub profile: Profile,
    pub web_enabled: bool,
    pub offloading: bool,
}
#[derive(Clone, Serialize)]
pub struct Session {
    pub email: String,
    pub csrf: String,
    pub authenticated_at: i64,
}
#[derive(Serialize)]
pub struct Audit {
    pub id: i64,
    pub at: i64,
    pub actor: String,
    pub action: String,
    pub detail: String,
}
impl Store {
    pub fn open(root: &Path) -> Result<Self> {
        ensure!(
            root.is_absolute()
                && !root
                    .components()
                    .any(|p| matches!(p, std::path::Component::ParentDir)),
            "Use an absolute private state directory"
        );
        for ancestor in root.ancestors().filter(|p| p.exists()) {
            let m = ancestor.symlink_metadata()?;
            ensure!(
                m.is_dir()
                    && !m.file_type().is_symlink()
                    && (m.uid() == 0 || m.uid() == unsafe { libc::geteuid() })
                    && (m.mode() & 0o022 == 0
                        || (ancestor == Path::new("/tmp") && m.mode() & 0o1000 != 0)),
                "State directories must have protected ownership and permissions"
            );
        }
        if root.exists() && !root.join("daemon.sqlite").exists() {
            ensure!(
                std::fs::read_dir(root)?.next().is_none(),
                "Existing non-Daemon files retained; choose an empty private state directory"
            );
        }
        std::fs::create_dir_all(root)?;
        let info = root.symlink_metadata()?;
        ensure!(
            info.uid() == unsafe { libc::geteuid() },
            "State directory has another owner"
        );
        std::fs::set_permissions(root, std::fs::Permissions::from_mode(0o700))?;
        let path = root.join("daemon.sqlite");
        ensure!(!path.is_symlink(), "Database cannot be a symlink");
        if path.exists() {
            let m = path.symlink_metadata()?;
            ensure!(
                m.is_file() && m.nlink() == 1 && m.uid() == info.uid(),
                "Unsafe database file"
            );
        }
        let db = Connection::open(&path)?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
        db.busy_timeout(std::time::Duration::from_secs(5))?;
        db.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admins(email TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, email TEXT NOT NULL REFERENCES admins(email), csrf TEXT NOT NULL, authenticated_at INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at INTEGER NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(identity TEXT PRIMARY KEY, start INTEGER NOT NULL, count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS documents(kind TEXT PRIMARY KEY, revision INTEGER NOT NULL, value TEXT NOT NULL);")?;
        Ok(Self {
            root: root.into(),
            db: Arc::new(Mutex::new(db)),
        })
    }
    fn db(&self) -> Result<std::sync::MutexGuard<'_, Connection>> {
        self.db
            .lock()
            .map_err(|_| anyhow::anyhow!("Database unavailable"))
    }
    pub fn managed_root(&self) -> &Path {
        if self.root.file_name().is_some_and(|n| n == "controller") {
            self.root
                .parent()
                .and_then(Path::parent)
                .unwrap_or(&self.root)
        } else {
            self.root.parent().unwrap_or(&self.root)
        }
    }
    pub fn init(&self, email: &str, password: &str, profile: Profile, web: bool) -> Result<()> {
        let email = auth::email(email)?;
        let hash = auth::hash_password(password)?;
        let mut db = self.db()?;
        let tx = db.transaction()?;
        ensure!(
            tx.query_row("SELECT COUNT(*) FROM admins", [], |r| r.get::<_, i64>(0))? == 0,
            "Existing administrators retained; initialization cannot reset accounts"
        );
        tx.execute("INSERT INTO admins VALUES(?1,?2)", params![email, hash])?;
        tx.execute(
            "INSERT INTO settings VALUES(1,?1)",
            [serde_json::to_string(&Settings {
                revision: 1,
                profile,
                web_enabled: web,
                offloading: false,
            })?],
        )?;
        tx.execute("INSERT INTO audit(at,actor,action,detail) VALUES(?1,?2,'initialize','Created local administrator and installation policy')", params![auth::now(),email])?;
        tx.commit()?;
        Ok(())
    }
    pub fn settings(&self) -> Result<Settings> {
        Ok(serde_json::from_str(&self.db()?.query_row(
            "SELECT value FROM settings WHERE id=1",
            [],
            |r| r.get::<_, String>(0),
        )?)?)
    }
    pub fn set_settings(&self, actor: &str, next: Settings) -> Result<Settings> {
        ensure!(
            !next.offloading,
            "UI offloading requires a verified compatible release declaration before activation"
        );
        let mut db = self.db()?;
        let tx = db.transaction()?;
        let old: Settings = serde_json::from_str(&tx.query_row(
            "SELECT value FROM settings WHERE id=1",
            [],
            |r| r.get::<_, String>(0),
        )?)?;
        ensure!(
            old.profile == next.profile,
            "Changing installation profile requires a reviewed provisioning plan"
        );
        ensure!(
            old.revision == next.revision,
            "Settings changed; reload before saving"
        );
        let value = Settings {
            revision: old.revision + 1,
            ..next
        };
        tx.execute(
            "UPDATE settings SET value=?1 WHERE id=1",
            [serde_json::to_string(&value)?],
        )?;
        tx.execute("INSERT INTO audit(at,actor,action,detail) VALUES(?1,?2,'settings','Updated installation preferences; listener changes require service restart')", params![auth::now(),actor])?;
        tx.commit()?;
        Ok(value)
    }
    pub fn login(&self, email: &str, password: &str, peer: &str) -> Result<String> {
        let identity = auth::digest(peer);
        let email = auth::email(email)?;
        let hash = {
            let db = self.db()?;
            db.execute("INSERT INTO attempts(identity,start,count) VALUES(?1,?2,1) ON CONFLICT(identity) DO UPDATE SET start=CASE WHEN start<?3 THEN ?2 ELSE start END,count=CASE WHEN start<?3 THEN 1 ELSE count+1 END", params![identity,auth::now(),auth::now()-300])?;
            let count: i64 = db.query_row(
                "SELECT count FROM attempts WHERE identity=?1",
                [&identity],
                |r| r.get(0),
            )?;
            ensure!(count <= 12, "Too many sign-in attempts; wait five minutes");
            db.query_row(
                "SELECT password_hash FROM admins WHERE email=?1",
                [&email],
                |r| r.get::<_, String>(0),
            )
            .optional()?
        };
        let dummy = "$argon2id$v=19$m=19456,t=2,p=1$YWJjZGVmZ2hpamtsbW5vcA$LVpD9X5K/RWgyqzbMvnOjVApq+S+ZJ+8sAc7vPgXlZI";
        let valid = auth::verify(password, hash.as_deref().unwrap_or(dummy));
        ensure!(hash.is_some() && valid, "Email or password is incorrect");
        let token = auth::random()?;
        let csrf = auth::random()?;
        let db = self.db()?;
        db.execute("DELETE FROM sessions WHERE expires<?1", [auth::now()])?;
        db.execute(
            "INSERT INTO sessions VALUES(?1,?2,?3,?4,?5)",
            params![
                auth::digest(&token),
                email,
                csrf,
                auth::now(),
                auth::now() + 3600 * 8
            ],
        )?;
        db.execute("DELETE FROM attempts WHERE identity=?1", [&identity])?;
        Ok(token)
    }
    pub fn session(&self, token: &str) -> Result<Option<Session>> {
        ensure!(token.len() <= 128, "Invalid session");
        Ok(self.db()?.query_row("SELECT email,csrf,authenticated_at FROM sessions WHERE token_hash=?1 AND expires>?2", params![auth::digest(token),auth::now()], |r| Ok(Session { email:r.get(0)?,csrf:r.get(1)?,authenticated_at:r.get(2)? })).optional()?)
    }
    pub fn logout(&self, token: &str) -> Result<()> {
        self.db()?.execute(
            "DELETE FROM sessions WHERE token_hash=?1",
            [auth::digest(token)],
        )?;
        Ok(())
    }
    pub fn audit(&self) -> Result<Vec<Audit>> {
        let db = self.db()?;
        let mut q =
            db.prepare("SELECT id,at,actor,action,detail FROM audit ORDER BY id DESC LIMIT 100")?;
        Ok(q.query_map([], |r| {
            Ok(Audit {
                id: r.get(0)?,
                at: r.get(1)?,
                actor: r.get(2)?,
                action: r.get(3)?,
                detail: r.get(4)?,
            })
        })?
        .collect::<rusqlite::Result<_>>()?)
    }
    pub fn document(&self, kind: &str) -> Result<Option<(i64, serde_json::Value)>> {
        let row = self
            .db()?
            .query_row(
                "SELECT revision,value FROM documents WHERE kind=?1",
                [kind],
                |r| Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?)),
            )
            .optional()?;
        row.map(|(revision, raw)| Ok((revision, serde_json::from_str(&raw)?)))
            .transpose()
    }
    pub fn save_document(
        &self,
        actor: &str,
        kind: &str,
        revision: i64,
        value: &serde_json::Value,
    ) -> Result<i64> {
        let raw = serde_json::to_string(value)?;
        ensure!(raw.len() <= 65536, "Configuration is too large");
        let mut db = self.db()?;
        let tx = db.transaction()?;
        let current = tx
            .query_row(
                "SELECT revision FROM documents WHERE kind=?1",
                [kind],
                |r| r.get::<_, i64>(0),
            )
            .optional()?
            .unwrap_or(0);
        ensure!(
            revision == current,
            "Configuration changed; reload before saving"
        );
        tx.execute("INSERT INTO documents VALUES(?1,?2,?3) ON CONFLICT(kind) DO UPDATE SET revision=excluded.revision,value=excluded.value", params![kind,current+1,raw])?;
        tx.execute(
            "INSERT INTO audit(at,actor,action,detail) VALUES(?1,?2,'configuration',?3)",
            params![auth::now(), actor, kind],
        )?;
        tx.commit()?;
        Ok(current + 1)
    }
}
