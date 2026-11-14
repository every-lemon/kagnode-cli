//! Root-only service enrollment and bounded, replay-safe systemd operations.
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    os::unix::fs::{MetadataExt, PermissionsExt},
    path::{Path, PathBuf},
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
    process::Command,
};

const POLICY: &str = "/etc/kagnode/daemon/managed-services.json";
pub const SOCKET: &str = "/run/kagnode-daemon/broker.sock";
#[derive(Clone, Copy, Debug, Serialize, Deserialize, clap::ValueEnum)]
#[serde(rename_all = "lowercase")]
pub enum Operation {
    Start,
    Stop,
    Restart,
}
impl Operation {
    fn text(self) -> &'static str {
        match self {
            Self::Start => "start",
            Self::Stop => "stop",
            Self::Restart => "restart",
        }
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub units: BTreeMap<String, BTreeMap<String, String>>,
}
#[derive(Serialize, Deserialize, Default)]
#[serde(deny_unknown_fields)]
pub struct Registry {
    pub products: BTreeMap<String, Binding>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    History {
        product: String,
    },
    Status {
        product: String,
    },
    Plan {
        product: String,
        operation: Operation,
    },
    Apply {
        product: String,
        operation: Operation,
        expected_sha256: String,
        request_id: String,
    },
    Resolve {
        request_id: String,
        product: String,
        inspection_sha256: String,
        reason: String,
    },
}
fn sha(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}
fn identifier(s: &str) -> bool {
    s.len() == 32 && s.bytes().all(|b| b.is_ascii_hexdigit())
}
fn permitted(product: &str, unit: &str) -> bool {
    let Some(p) = crate::catalog::product(product) else {
        return false;
    };
    if p.units.contains(&unit) {
        return true;
    }
    match p.id {
        "passwords" => ["authentactor.service", "kagnode-authenticator.service"].contains(&unit),
        "vpn" => [
            "vpn-control.service",
            "vpn-management.service",
            "vpn-downloads.service",
            "vpn-watchdog.service",
        ]
        .contains(&unit),
        "mail" => [
            "kagnode-web.service",
            "kagnode-guard.service",
            "postfix.service",
            "dovecot.service",
        ]
        .contains(&unit),
        _ => false,
    }
}
fn protected_file(path: &Path) -> Result<Vec<u8>> {
    let m = path.symlink_metadata()?;
    ensure!(
        m.is_file()
            && !m.file_type().is_symlink()
            && m.uid() == 0
            && m.mode() & 0o022 == 0
            && m.len() <= 1024 * 1024,
        "Service policy inputs must be protected root-owned files"
    );
    for p in path.ancestors().skip(1) {
        let m = p.symlink_metadata()?;
        ensure!(
            m.is_dir() && !m.file_type().is_symlink() && m.uid() == 0 && m.mode() & 0o022 == 0,
            "Unsafe service policy directory"
        );
    }
    Ok(std::fs::read(path)?)
}
fn registry() -> Result<Registry> {
    Ok(serde_json::from_slice(&protected_file(Path::new(POLICY))?)?)
}
async fn systemctl(args: &[&str]) -> Result<String> {
    let mut command = Command::new("/usr/bin/systemctl");
    command
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LANG", "C")
        .args(args)
        .kill_on_drop(true);
    let output = tokio::time::timeout(Duration::from_secs(90), command.output())
        .await
        .map_err(|_| {
            anyhow::anyhow!("Systemd operation timed out; inspect native state before retrying")
        })??;
    ensure!(
        output.stdout.len() + output.stderr.len() <= 65536,
        "Systemd response exceeded its bound"
    );
    ensure!(
        output.status.success(),
        "Systemd operation failed; inspect the service journal"
    );
    Ok(String::from_utf8(output.stdout)?.trim().to_owned())
}
pub async fn enroll(product: &str, unit: &str) -> Result<Value> {
    ensure!(
        unsafe { libc::geteuid() } == 0,
        "Root must review and enroll native services"
    );
    ensure!(
        permitted(product, unit),
        "This unit is not an approved service for that product"
    );
    let id = crate::catalog::product(product).unwrap().id;
    let fragment = systemctl(&["show", unit, "--property=FragmentPath", "--value"]).await?;
    ensure!(!fragment.is_empty(), "The unit has no installed fragment");
    let dropins = systemctl(&["show", unit, "--property=DropInPaths", "--value"]).await?;
    let mut files = BTreeMap::new();
    for p in std::iter::once(fragment.as_str()).chain(dropins.split_whitespace()) {
        let path = Path::new(p).canonicalize()?;
        ensure!(
            path.starts_with("/etc/systemd/system") || path.starts_with("/usr/lib/systemd/system"),
            "Only installed system service definitions can be enrolled"
        );
        files.insert(
            path.to_string_lossy().into_owned(),
            sha(&protected_file(&path)?),
        );
    }
    let file = Path::new(POLICY);
    let mut data = if file.exists() {
        registry()?
    } else {
        Registry::default()
    };
    data.products
        .entry(id.into())
        .or_insert(Binding {
            units: BTreeMap::new(),
        })
        .units
        .insert(unit.into(), files);
    std::fs::create_dir_all(file.parent().unwrap())?;
    std::fs::set_permissions(
        file.parent().unwrap(),
        std::fs::Permissions::from_mode(0o700),
    )?;
    let temporary = file.with_extension("next");
    let mut options = std::fs::OpenOptions::new();
    use std::os::unix::fs::OpenOptionsExt;
    let mut stream = options
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temporary)?;
    use std::io::Write;
    stream.write_all(&serde_json::to_vec_pretty(&data)?)?;
    stream.sync_all()?;
    std::fs::rename(temporary, file)?;
    Ok(json!({"product":id,"enrolled_unit":unit,"running_state_changed":false}))
}
fn binding(product: &str) -> Result<Binding> {
    let id = crate::catalog::product(product)
        .ok_or_else(|| anyhow::anyhow!("Unknown application"))?
        .id;
    let mut registry = registry()?;
    let binding = registry.products.remove(id).ok_or_else(|| {
        anyhow::anyhow!(
            "A root administrator must enroll the existing service before Daemon can control it"
        )
    })?;
    ensure!(
        !binding.units.is_empty() && binding.units.len() <= 12,
        "Invalid service binding"
    );
    for (unit, files) in &binding.units {
        ensure!(
            permitted(id, unit) && !files.is_empty(),
            "Service binding is outside the product allowlist"
        );
        for (path, expected) in files {
            ensure!(
                sha(&protected_file(Path::new(path))?) == *expected,
                "A service definition changed; root must review its enrollment again"
            );
        }
    }
    Ok(binding)
}
async fn plan(product: &str, operation: Operation) -> Result<Value> {
    let binding = binding(product)?;
    let mut states = BTreeMap::new();
    for unit in binding.units.keys() {
        let fragment = systemctl(&["show", unit, "--property=FragmentPath", "--value"]).await?;
        ensure!(!fragment.is_empty(), "Enrolled service disappeared");
        let canonical = Path::new(&fragment).canonicalize()?;
        ensure!(
            binding.units[unit].contains_key(canonical.to_string_lossy().as_ref()),
            "Systemd loaded a different service fragment"
        );
        let dropins = systemctl(&["show", unit, "--property=DropInPaths", "--value"]).await?;
        let observed: std::collections::BTreeSet<_> = std::iter::once(fragment.as_str())
            .chain(dropins.split_whitespace())
            .map(|p| {
                Path::new(p)
                    .canonicalize()
                    .map(|p| p.to_string_lossy().into_owned())
            })
            .collect::<std::io::Result<_>>()?;
        ensure!(
            observed == binding.units[unit].keys().cloned().collect(),
            "Systemd override files changed; root must review enrollment"
        );
        states.insert(
            unit.clone(),
            systemctl(&["show", unit, "--property=ActiveState", "--value"]).await?,
        );
    }
    let mut value = json!({"schema":1,"product":crate::catalog::product(product).unwrap().id,"operation":operation,"units":binding.units,"states":states,"effect":"Changes native service availability; configuration and user data are retained"});
    value["sha256"] = json!(sha(&serde_json::to_vec(&value)?));
    Ok(value)
}
async fn handle(db: &mut rusqlite::Connection, request: Request, peer: u32) -> Result<Value> {
    match request {
        Request::History { product } => {
            ensure!(
                crate::catalog::product(&product).is_some(),
                "Unknown application"
            );
            let mut q=db.prepare("SELECT id,state,result,at FROM operations WHERE product=?1 ORDER BY at DESC LIMIT 100")?;
            let rows = q
                .query_map([&product], |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, String>(1)?,
                        r.get::<_, String>(2)?,
                        r.get::<_, i64>(3)?,
                    ))
                })?
                .collect::<rusqlite::Result<Vec<_>>>()?;
            Ok(
                json!({"operations":rows.into_iter().map(|(id,state,result,at)|json!({"id":id,"state":state,"result":serde_json::from_str::<Value>(&result).unwrap_or(Value::Null),"at":at})).collect::<Vec<_>>()}),
            )
        }
        Request::Status { product } => {
            let mut p = plan(&product, Operation::Start).await?;
            p["native_actions_enabled"] = json!(true);
            p["pending"] = json!(db.query_row(
                "SELECT count(*) FROM operations WHERE state IN ('running','uncertain')",
                [],
                |r| r.get::<_, i64>(0)
            )?);
            Ok(p)
        }
        Request::Plan { product, operation } => plan(&product, operation).await,
        Request::Apply {
            product,
            operation,
            expected_sha256,
            request_id,
        } => {
            ensure!(
                identifier(&request_id) && expected_sha256.len() == 64,
                "Invalid operation identity"
            );
            let payload =
                json!({"product":product,"operation":operation,"expected":expected_sha256});
            let digest = sha(&serde_json::to_vec(&payload)?);
            use rusqlite::OptionalExtension;
            if let Some((old, state, result)) = db
                .query_row(
                    "SELECT digest,state,result FROM operations WHERE id=?1",
                    [&request_id],
                    |r| {
                        Ok((
                            r.get::<_, String>(0)?,
                            r.get::<_, String>(1)?,
                            r.get::<_, String>(2)?,
                        ))
                    },
                )
                .optional()?
            {
                ensure!(
                    old == digest,
                    "Operation identity was already used for another request"
                );
                return Ok(
                    json!({"id":request_id,"state":state,"result":serde_json::from_str::<Value>(&result)?}),
                );
            }
            ensure!(
                db.query_row(
                    "SELECT count(*) FROM operations WHERE state IN ('running','uncertain')",
                    [],
                    |r| r.get::<_, i64>(0)
                )? == 0,
                "An interrupted native operation needs inspection before another change"
            );
            let reviewed = plan(&product, operation).await?;
            ensure!(
                reviewed["sha256"] == expected_sha256,
                "Service state or definitions changed; review a fresh plan"
            );
            db.execute("INSERT INTO operations(id,digest,state,result,at,peer,product) VALUES(?1,?2,'running','null',?3,?4,?5)",rusqlite::params![request_id,digest,crate::auth::now(),peer,product])?;
            let result = async {
                let units: Vec<_> = reviewed["units"]
                    .as_object()
                    .unwrap()
                    .keys()
                    .map(String::as_str)
                    .collect();
                let mut args = vec![operation.text(), "--"];
                args.extend(units.iter().copied());
                systemctl(&args).await?;
                let observed = plan(&product, operation).await?;
                let desired = match operation {
                    Operation::Stop => "inactive",
                    _ => "active",
                };
                ensure!(
                    observed["states"]
                        .as_object()
                        .unwrap()
                        .values()
                        .all(|v| v == desired),
                    "Service did not reach the expected state; inspect before recovery"
                );
                Ok::<_, anyhow::Error>(observed)
            }
            .await;
            let (state, value) = match result {
                Ok(v) => ("completed", v),
                Err(e) => (
                    "uncertain",
                    json!({"error":e.to_string(),"requires_inspection":true}),
                ),
            };
            db.execute(
                "UPDATE operations SET state=?1,result=?2 WHERE id=?3",
                rusqlite::params![state, serde_json::to_string(&value)?, request_id],
            )?;
            Ok(json!({"id":request_id,"state":state,"result":value}))
        }
        Request::Resolve {
            request_id,
            product,
            inspection_sha256,
            reason,
        } => {
            ensure!(
                peer == 0,
                "Only root can resolve uncertain native operations"
            );
            ensure!(
                identifier(&request_id)
                    && reason.len() >= 12
                    && reason.len() <= 500
                    && !reason.chars().any(char::is_control),
                "Provide the operation identity and a useful inspection reason"
            );
            let current = plan(&product, Operation::Start).await?;
            ensure!(
                current["sha256"] == inspection_sha256,
                "Inspection changed; inspect services again"
            );
            for unit in current["units"].as_object().unwrap().keys() {
                let job = systemctl(&["show", unit, "--property=Job", "--value"]).await?;
                ensure!(
                    job.is_empty(),
                    "Systemd still has a pending job for this service"
                );
            }
            ensure!(db.execute("UPDATE operations SET state='resolved',result=?1 WHERE id=?2 AND state='uncertain'",rusqlite::params![serde_json::to_string(&json!({"inspection":current,"reason":reason}))?,request_id])?==1,"No matching uncertain operation exists");
            Ok(json!({"id":request_id,"state":"resolved","native_state_changed":false}))
        }
    }
}
pub async fn serve(root: &Path, allowed_uid: u32) -> Result<()> {
    ensure!(
        unsafe { libc::geteuid() } == 0,
        "The service broker must run as root"
    );
    for p in root.ancestors().filter(|p| p.exists()) {
        ensure!(
            !p.is_symlink() && p.metadata()?.uid() == 0,
            "Unsafe broker state directory"
        );
    }
    std::fs::create_dir_all(root)?;
    std::fs::set_permissions(root, std::fs::Permissions::from_mode(0o700))?;
    let path = root.join("broker.sqlite");
    ensure!(!path.is_symlink(), "Unsafe broker database");
    let mut db = rusqlite::Connection::open(&path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    db.execute_batch("PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,digest TEXT NOT NULL,state TEXT NOT NULL,result TEXT NOT NULL,at INTEGER NOT NULL,peer INTEGER NOT NULL,product TEXT NOT NULL);UPDATE operations SET state='uncertain' WHERE state='running';")?;
    let socket = PathBuf::from(SOCKET);
    std::fs::create_dir_all(socket.parent().unwrap())?;
    std::fs::set_permissions(
        socket.parent().unwrap(),
        std::fs::Permissions::from_mode(0o755),
    )?;
    if socket.exists() {
        ensure!(
            UnixStream::connect(&socket).await.is_err(),
            "Broker is already running"
        );
        ensure!(!socket.is_symlink(), "Unsafe broker socket");
        std::fs::remove_file(&socket)?;
    }
    let listener = UnixListener::bind(&socket)?;
    std::fs::set_permissions(&socket, std::fs::Permissions::from_mode(0o600))?;
    let c = std::ffi::CString::new(socket.as_os_str().as_encoded_bytes())?;
    ensure!(
        unsafe { libc::chown(c.as_ptr(), allowed_uid, !0) } == 0,
        "Cannot assign broker socket peer ownership"
    );
    loop {
        let (stream, _) = listener.accept().await?;
        let uid = stream.peer_cred()?.uid();
        if uid != 0 && uid != allowed_uid {
            continue;
        }
        let mut reader = BufReader::new(stream);
        let mut line = String::new();
        let read = tokio::time::timeout(
            Duration::from_secs(5),
            (&mut reader).take(16385).read_line(&mut line),
        )
        .await;
        let result = match read {
            Ok(Ok(_)) if line.len() <= 16384 => match serde_json::from_str::<Request>(&line) {
                Ok(request) => handle(&mut db, request, uid).await,
                Err(_) => Err(anyhow::anyhow!("Invalid broker request")),
            },
            _ => Err(anyhow::anyhow!("Broker request exceeded its bound")),
        };
        let value = match result {
            Ok(v) => json!({"ok":true,"value":v}),
            Err(e) => json!({"ok":false,"error":e.to_string()}),
        };
        let mut stream = reader.into_inner();
        let bytes = serde_json::to_vec(&value)?;
        let _ = stream.write_all(&bytes).await;
        let _ = stream.shutdown().await;
    }
}
pub async fn request(value: Request) -> Result<Value> {
    let mut stream = UnixStream::connect(SOCKET).await.map_err(|_| {
        anyhow::anyhow!("The privileged service broker is not enabled on this installation")
    })?;
    let mut bytes = serde_json::to_vec(&value)?;
    bytes.push(b'\n');
    stream.write_all(&bytes).await?;
    let mut response = Vec::new();
    tokio::time::timeout(
        Duration::from_secs(100),
        stream.take(262145).read_to_end(&mut response),
    )
    .await??;
    ensure!(
        response.len() <= 262144,
        "Broker response exceeded its bound"
    );
    let v: Value = serde_json::from_slice(&response)?;
    ensure!(
        v["ok"] == true,
        "{}",
        v["error"].as_str().unwrap_or("Broker request failed")
    );
    Ok(v["value"].clone())
}
