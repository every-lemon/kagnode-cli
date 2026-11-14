use anyhow::{Result, ensure};
use clap::{Parser, Subcommand};
use kagnode_daemon::{
    catalog,
    store::{Profile, Store},
    web::{self, App},
};
use serde_json::json;
use std::{
    net::SocketAddr,
    os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt},
    path::PathBuf,
    sync::Arc,
};
#[derive(Parser)]
#[command(
    name = "kagnode",
    version,
    about = "KagNode. Daemon — manage your open-source workspace"
)]
struct Args {
    #[arg(
        long,
        global = true,
        default_value = "/srv/kagnode/daemon/controller",
        env = "KAGNODE_DAEMON_ROOT"
    )]
    root: PathBuf,
    #[command(subcommand)]
    command: Option<Command>,
}
#[derive(Subcommand)]
enum Command {
    Init {
        #[arg(long)]
        email: String,
        #[arg(long)]
        password_file: PathBuf,
        #[arg(long, value_enum, default_value = "light")]
        profile: Profile,
        #[arg(long)]
        web: bool,
    },
    Serve {
        #[arg(long, default_value = "127.0.0.1:8750")]
        listen: SocketAddr,
        #[arg(long, default_value = "http://127.0.0.1:8750")]
        origin: String,
    },
    Status {
        #[arg(long)]
        json: bool,
    },
    Settings {
        #[command(subcommand)]
        command: Setting,
    },
    Ha {
        #[command(subcommand)]
        command: Ha,
    },
    Tui {
        #[arg(long)]
        no_mouse: bool,
    },
    Install {
        #[arg(long)]
        email: Option<String>,
        #[arg(long)]
        password_file: Option<PathBuf>,
        #[arg(long, value_enum, default_value = "light")]
        profile: Profile,
        #[arg(long, conflicts_with = "no_web")]
        web: bool,
        #[arg(long)]
        no_web: bool,
        #[arg(long)]
        yes: bool,
        #[arg(long)]
        print_plan: bool,
        #[arg(long, default_value = "http://127.0.0.1:8750")]
        origin: String,
    },
    Health,
    Backup {
        #[command(subcommand)]
        command: Backup,
    },
    Broker {
        #[arg(long, default_value = "/var/lib/kagnode-daemon")]
        state: PathBuf,
        #[arg(long)]
        allowed_uid: u32,
    },
    Services {
        #[command(subcommand)]
        command: Services,
    },
}
#[derive(Subcommand)]
enum Backup {
    Configure {
        #[arg(long)]
        directory: PathBuf,
    },
    Create {
        #[arg(long)]
        directory: PathBuf,
        #[arg(long, default_value = "/var/lib/kagnode-keys/daemon-backup.key")]
        key: PathBuf,
    },
    Validate {
        #[arg(long)]
        file: PathBuf,
        #[arg(long)]
        key: PathBuf,
        #[arg(long)]
        work: PathBuf,
    },
    Scheduled,
}
#[derive(Subcommand)]
enum Services {
    Enroll {
        #[arg(long)]
        product: String,
        #[arg(long)]
        unit: String,
    },
    Plan {
        #[arg(long)]
        product: String,
        #[arg(long, value_enum)]
        operation: kagnode_daemon::broker::Operation,
    },
    Apply {
        #[arg(long)]
        product: String,
        #[arg(long, value_enum)]
        operation: kagnode_daemon::broker::Operation,
        #[arg(long)]
        expected_sha256: String,
        #[arg(long)]
        request_id: String,
    },
    Resolve {
        #[arg(long)]
        product: String,
        #[arg(long)]
        request_id: String,
        #[arg(long)]
        inspection_sha256: String,
        #[arg(long)]
        reason: String,
    },
}
#[derive(Subcommand)]
enum Setting {
    Show,
    Web {
        #[arg(value_parser=["on","off"])]
        value: String,
    },
}
#[derive(Subcommand)]
enum Ha {
    Plan {
        #[arg(long)]
        file: PathBuf,
    },
}
fn private_file(path: &std::path::Path) -> Result<zeroize::Zeroizing<String>> {
    let m = path.symlink_metadata()?;
    ensure!(
        m.is_file()
            && !m.file_type().is_symlink()
            && m.nlink() == 1
            && m.uid() == unsafe { libc::geteuid() }
            && m.mode() & 0o077 == 0
            && m.len() <= 4096,
        "Password file must be a private, owned regular file"
    );
    Ok(zeroize::Zeroizing::new(
        std::fs::read_to_string(path)?
            .trim_end_matches(['\r', '\n'])
            .to_owned(),
    ))
}
fn prompt(message: &str) -> Result<String> {
    use std::io::{BufRead, Write};
    let mut tty = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/tty")?;
    tty.write_all(message.as_bytes())?;
    tty.flush()?;
    let mut line = String::new();
    std::io::BufReader::new(tty).read_line(&mut line)?;
    ensure!(line.len() <= 4096, "Input too long");
    Ok(line.trim().to_owned())
}
#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    if let Some(Command::Install {
        email,
        password_file,
        profile,
        web,
        no_web,
        yes,
        print_plan,
        origin,
    }) = &args.command
    {
        let web = if *web {
            true
        } else if *no_web || *print_plan {
            false
        } else {
            prompt("Install the web dashboard? [y/N] ")?.eq_ignore_ascii_case("y")
        };
        let plan = kagnode_daemon::install::plan(*profile, web, origin)?;
        println!("{}", serde_json::to_string_pretty(&plan)?);
        if *print_plan {
            return Ok(());
        }
        let email = if let Some(v) = email {
            v.clone()
        } else {
            prompt("Administrator email: ")?
        };
        let password = if let Some(path) = password_file {
            private_file(path)?
        } else {
            let first =
                zeroize::Zeroizing::new(rpassword::prompt_password("Administrator password: ")?);
            let second = zeroize::Zeroizing::new(rpassword::prompt_password("Confirm password: ")?);
            ensure!(*first == *second, "Passwords do not match");
            first
        };
        ensure!(
            *yes || prompt("Install the reviewed configuration? [y/N] ")?.eq_ignore_ascii_case("y"),
            "Installation cancelled before provisioning"
        );
        println!(
            "{}",
            serde_json::to_string_pretty(&kagnode_daemon::install::apply(
                &email, &password, *profile, web, origin
            )?)?
        );
        return Ok(());
    }
    if let Some(Command::Backup { command }) = &args.command {
        use kagnode_daemon::backup;
        let value = match command {
            Backup::Configure { directory } => {
                kagnode_daemon::install::configure_backup(directory)?
            }
            Backup::Create { directory, key } => backup::create(&args.root, directory, key)?,
            Backup::Validate { file, key, work } => backup::validate(file, key, work)?,
            Backup::Scheduled => {
                let config = std::path::Path::new("/etc/kagnode/daemon/backup-destination");
                let m = config.symlink_metadata()?;
                ensure!(
                    m.uid() == 0
                        && m.mode() & 0o077 == 0
                        && !m.file_type().is_symlink()
                        && m.len() <= 4096,
                    "Unsafe backup destination configuration"
                );
                let directory = PathBuf::from(std::fs::read_to_string(config)?.trim());
                backup::create(
                    &args.root,
                    &directory,
                    std::path::Path::new("/var/lib/kagnode-keys/daemon-backup.key"),
                )?
            }
        };
        println!("{}", serde_json::to_string_pretty(&value)?);
        return Ok(());
    }
    if let Some(Command::Broker { state, allowed_uid }) = &args.command {
        return kagnode_daemon::broker::serve(state, *allowed_uid).await;
    }
    if let Some(Command::Services { command }) = &args.command {
        use kagnode_daemon::broker::{self, Request};
        let value = match command {
            Services::Enroll { product, unit } => broker::enroll(product, unit).await?,
            Services::Plan { product, operation } => {
                broker::request(Request::Plan {
                    product: product.clone(),
                    operation: *operation,
                })
                .await?
            }
            Services::Apply {
                product,
                operation,
                expected_sha256,
                request_id,
            } => {
                broker::request(Request::Apply {
                    product: product.clone(),
                    operation: *operation,
                    expected_sha256: expected_sha256.clone(),
                    request_id: request_id.clone(),
                })
                .await?
            }
            Services::Resolve {
                product,
                request_id,
                inspection_sha256,
                reason,
            } => {
                broker::request(Request::Resolve {
                    product: product.clone(),
                    request_id: request_id.clone(),
                    inspection_sha256: inspection_sha256.clone(),
                    reason: reason.clone(),
                })
                .await?
            }
        };
        println!("{}", serde_json::to_string_pretty(&value)?);
        return Ok(());
    }
    // Use the runtime owner for its database, even from a root terminal; avoid
    // creating root-owned SQLite journal files that strand the service account.
    if unsafe { libc::geteuid() } == 0 && args.root.exists() {
        let m = args.root.symlink_metadata()?;
        ensure!(!m.file_type().is_symlink(), "Unsafe state directory");
        if m.uid() != 0 {
            ensure!(
                unsafe { libc::setgroups(0, std::ptr::null()) } == 0
                    && unsafe { libc::setgid(m.gid()) } == 0
                    && unsafe { libc::setuid(m.uid()) } == 0,
                "Cannot enter the runtime account"
            );
        }
    }
    let store = Store::open(&args.root)?;
    match args.command {
        Some(Command::Init {
            email,
            password_file,
            profile,
            web,
        }) => {
            store.init(&email, &private_file(&password_file)?, profile, web)?;
            println!(
                "Local administrator initialized. Existing application data was not modified."
            );
        }
        Some(Command::Status { json: _ }) => {
            let settings = store.settings()?;
            let root = store.managed_root();
            println!(
                "{}",
                serde_json::to_string_pretty(
                    &json!({"product":"KagNode. Daemon","version":env!("CARGO_PKG_VERSION"),"settings":settings,"applications":catalog::PRODUCTS.iter().map(|p|json!({"product":p,"installed":catalog::installed(root,p)})).collect::<Vec<_>>()})
                )?
            );
        }
        Some(Command::Settings {
            command: Setting::Show,
        }) => println!("{}", serde_json::to_string_pretty(&store.settings()?)?),
        Some(Command::Settings {
            command: Setting::Web { value },
        }) => {
            let mut s = store.settings()?;
            s.web_enabled = value == "on";
            store.set_settings("local-terminal", s)?;
            println!(
                "Dashboard preference saved. Enabling takes effect when the Daemon starts; disabling closes its HTTP listener."
            );
        }
        Some(Command::Ha {
            command: Ha::Plan { file },
        }) => {
            ensure!(
                std::fs::metadata(&file)?.len() <= 65536,
                "Cluster declaration is too large"
            );
            let c: kagnode_daemon::ha::Cluster = serde_json::from_slice(&std::fs::read(file)?)?;
            println!("{}", serde_json::to_string_pretty(&c.plan()?)?);
        }
        Some(Command::Serve { listen, origin }) => {
            ensure!(
                listen.ip().is_loopback(),
                "Bind the dashboard to loopback and configure a trusted HTTPS reverse proxy for remote access"
            );
            ensure!(
                origin.starts_with("https://") || origin == format!("http://{listen}"),
                "Use HTTPS for a remote dashboard origin"
            );
            let url = reqwest::Url::parse(&origin)?;
            ensure!(
                url.path() == "/"
                    && url.query().is_none()
                    && url.fragment().is_none()
                    && url.username().is_empty()
                    && url.password().is_none(),
                "Configure an origin without a path, query or credentials"
            );
            let app = App {
                store: store.clone(),
                origin: origin.trim_end_matches('/').to_owned(),
                core: Arc::new(
                    kagnode_core::Core::new("/srv/kagnode/core", "daemon")
                        .map_err(|e| anyhow::anyhow!(e.to_string()))?,
                ),
            };
            let run = store.root.join("run");
            std::fs::create_dir_all(&run)?;
            std::fs::set_permissions(&run, std::fs::Permissions::from_mode(0o700))?;
            let socket = run.join("daemon.sock");
            if socket.exists() {
                ensure!(
                    std::os::unix::net::UnixStream::connect(&socket).is_err(),
                    "Daemon is already running"
                );
                ensure!(
                    socket.symlink_metadata()?.file_type().is_socket(),
                    "Unexpected socket path"
                );
                std::fs::remove_file(&socket)?;
            }
            let listener = tokio::net::UnixListener::bind(&socket)?;
            std::fs::set_permissions(&socket, std::fs::Permissions::from_mode(0o600))?;
            let local = web::router(app.clone());
            let task = tokio::spawn(async move { axum::serve(listener, local).await });
            if store.settings()?.web_enabled {
                let listener = tokio::net::TcpListener::bind(listen).await?;
                println!("Daemon dashboard listening on {listen}; origin {origin}");
                axum::serve(
                    listener,
                    web::router(app).into_make_service_with_connect_info::<SocketAddr>(),
                )
                .with_graceful_shutdown(async move {
                    loop {
                        if !store.settings().is_ok_and(|s| s.web_enabled) {
                            break;
                        }
                        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                    }
                })
                .await?;
            } else {
                println!("Daemon running with dashboard disabled; private local socket available");
            }
            tokio::signal::ctrl_c().await?;
            task.abort();
            std::fs::remove_file(socket)?;
        }
        Some(Command::Health) => {
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            let mut socket =
                tokio::net::UnixStream::connect(store.root.join("run/daemon.sock")).await?;
            socket
                .write_all(b"GET /healthz HTTP/1.0\r\nHost: localhost\r\n\r\n")
                .await?;
            let mut reply = String::new();
            tokio::time::timeout(
                std::time::Duration::from_secs(5),
                socket.take(16384).read_to_string(&mut reply),
            )
            .await??;
            ensure!(
                reply.starts_with("HTTP/1.0 200") || reply.starts_with("HTTP/1.1 200"),
                "Daemon health check failed"
            );
            println!("Daemon local health is OK");
        }
        Some(
            Command::Broker { .. }
            | Command::Services { .. }
            | Command::Install { .. }
            | Command::Backup { .. },
        ) => unreachable!(),
        Some(Command::Tui { no_mouse }) => kagnode_daemon::tui::run(&store, !no_mouse)?,
        None => kagnode_daemon::tui::run(&store, true)?,
    }
    Ok(())
}
