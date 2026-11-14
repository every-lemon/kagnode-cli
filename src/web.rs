use crate::{
    auth, catalog, ha,
    store::{Session, Settings, Store},
};
use axum::{
    Form, Json, Router,
    extract::{ConnectInfo, DefaultBodyLimit, Path, State},
    http::{HeaderMap, StatusCode, header},
    middleware::{self, Next},
    response::{Html, IntoResponse, Redirect, Response},
    routing::{get, post},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{net::SocketAddr, sync::Arc};

#[derive(Clone)]
pub struct App {
    pub store: Store,
    pub origin: String,
    pub core: Arc<kagnode_core::Core>,
}
pub struct Error(StatusCode, String);
impl From<anyhow::Error> for Error {
    fn from(e: anyhow::Error) -> Self {
        Self(StatusCode::BAD_REQUEST, e.to_string())
    }
}
impl IntoResponse for Error {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"error":self.1}))).into_response()
    }
}
type Api<T> = Result<T, Error>;
fn cookie<'a>(h: &'a HeaderMap, name: &str) -> Option<&'a str> {
    h.get(header::COOKIE)?
        .to_str()
        .ok()?
        .split(';')
        .find_map(|p| {
            p.trim()
                .split_once('=')
                .filter(|(k, _)| *k == name)
                .map(|(_, v)| v)
        })
}
fn user(s: &App, h: &HeaderMap) -> Api<Session> {
    s.store
        .session(cookie(h, "kn_daemon").unwrap_or(""))?
        .ok_or(Error(
            StatusCode::UNAUTHORIZED,
            "Sign in as a local administrator".into(),
        ))
}
fn mutation(s: &App, h: &HeaderMap) -> Api<Session> {
    let u = user(s, h)?;
    if h.get("origin").and_then(|v| v.to_str().ok()) != Some(s.origin.as_str())
        || h.get("x-csrf-token").and_then(|v| v.to_str().ok()) != Some(u.csrf.as_str())
    {
        return Err(Error(
            StatusCode::FORBIDDEN,
            "Reload before submitting this change".into(),
        ));
    }
    if auth::now() - u.authenticated_at > 900 {
        return Err(Error(
            StatusCode::UNAUTHORIZED,
            "Sign in again before changing server settings".into(),
        ));
    }
    Ok(u)
}
pub fn router(app: App) -> Router {
    Router::new()
        .route("/healthz", get(health))
        .route("/login", get(login).post(login_post))
        .route("/logout", post(logout))
        .route("/assets/daemon.js", get(js))
        .route("/assets/daemon.css", get(css))
        .route("/kagnode-core/{version}/{file}", get(core_asset))
        .route("/api/v1/session", get(session))
        .route("/api/v1/logout", post(logout))
        .route("/api/v1/settings", get(settings).post(save_settings))
        .route("/api/v1/applications", get(applications))
        .route("/api/v1/applications/{id}/services", get(service_status))
        .route("/api/v1/applications/{id}/operations", get(service_history))
        .route("/api/v1/applications/{id}/service-plan", post(service_plan))
        .route(
            "/api/v1/applications/{id}/service-apply",
            post(service_apply),
        )
        .route("/api/v1/audit", get(audit))
        .route("/api/v1/ha/plan", post(ha_plan))
        .route("/api/v1/ha/configuration", get(ha_get).post(ha_save))
        .route("/", get(page))
        .route("/settings", get(page))
        .route("/audit", get(page))
        .route("/ha", get(page))
        .route("/servers/local/applications/{id}", get(application_page))
        .layer(DefaultBodyLimit::max(65536))
        .layer(middleware::from_fn(headers))
        .with_state(app)
}
async fn headers(request: axum::extract::Request, next: Next) -> Response {
    let mut response = next.run(request).await;
    let h = response.headers_mut();
    h.insert(header::CONTENT_SECURITY_POLICY,"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'".parse().unwrap());
    h.insert(header::CACHE_CONTROL, "no-store".parse().unwrap());
    h.insert(header::X_CONTENT_TYPE_OPTIONS, "nosniff".parse().unwrap());
    h.insert(header::REFERRER_POLICY, "same-origin".parse().unwrap());
    response
}
async fn health() -> Json<Value> {
    Json(json!({"ok":true,"product":"kagnode-daemon","version":env!("CARGO_PKG_VERSION")}))
}
async fn core_asset(
    State(s): State<App>,
    Path((version, file)): Path<(String, String)>,
) -> Response {
    match s.core.asset(&version, &file) {
        Ok(a) => ([(header::CONTENT_TYPE, a.content_type)], a.bytes).into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}
fn template(s: &App, name: &str, text: &[(&str, &str)], html: &[(&str, &str)]) -> String {
    s.core
        .template(name, text, html)
        .expect("canonical template parameters")
}
fn shell(s: &App, title: &str, u: Option<&Session>, body: &str) -> String {
    let esc = kagnode_core::escape;
    let head=s.core.head(json!({"authenticated":u.is_some(),"subject":u.map(|u|&u.email),"name":u.map(|u|&u.email),"home":"/","publicNavigation":false})).expect("valid Core context");
    let navigation = if u.is_some() {
        let nav = format!(
            "<div data-core-nav-root><button class=\"quick-search\" data-core-search-open aria-label=\"Quick search\"><span data-core-icon=\"search\"></span><span class=\"nav-label\">Quick search</span><kbd>Ctrl K</kbd></button><a href=\"/\" data-core-icon=\"home\">Overview</a><button data-core-nav-open=\"applications\"><span data-core-icon=\"server\"></span><span class=\"nav-label\">Applications</span></button><a href=\"/ha\" data-core-icon=\"shield\">High availability</a><a href=\"/audit\" data-core-icon=\"activity\">Activity</a><a href=\"/settings\" data-core-icon=\"settings\">Settings</a></div><div data-core-nav-folder=\"applications\" hidden><button data-core-nav-back><span data-core-icon=\"arrow-left\"></span><span class=\"nav-label\">Back to workspace</span></button>{}</div>",
            catalog::PRODUCTS
                .iter()
                .map(|p| format!(
                    "<a href=\"/servers/local/applications/{}\" data-core-icon=\"{}\">{}</a>",
                    p.id, p.icon, p.name
                ))
                .collect::<String>()
        );
        template(
            s,
            "sidebar",
            &[],
            &[
                (
                    "brand",
                    "<a href=\"/\" class=\"brand\"><strong>KagNode.</strong><span>Daemon</span></a>",
                ),
                ("navigation", &nav),
                ("footer", ""),
            ],
        )
    } else {
        String::new()
    };
    let account=u.map(|u| {
        let identity=format!("<strong>Administrator</strong><small>{}</small>",esc(&u.email));
        let actions="<a href=\"/settings\">Account and preferences</a><button id=\"sign-out\">Sign out</button>";
        format!("<button data-core-account-trigger aria-label=\"Open account menu\"><span data-core-icon=\"account\"></span></button>{}",template(s,"account-menu",&[],&[("identity",&identity),("actions",actions)]))
    }).unwrap_or_default();
    let content = if u.is_some() {
        format!(
            "{navigation}<div class=\"workspace\"><header class=\"topbar\"><span>KagNode. Daemon</span>{account}</header><main id=\"main\">{body}</main><footer><a href=\"https://github.com/every-lemon/kagnode-daemon\">Source and documentation</a></footer></div><div hidden data-core-search-source><a href=\"/\">Overview</a><a href=\"/ha\">High availability</a><a href=\"/settings\">Settings</a><a href=\"/audit\">Activity</a></div>"
        )
    } else {
        body.into()
    };
    format!(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{} · KagNode. Daemon</title>{head}<link rel=\"stylesheet\" href=\"/assets/daemon.css\"><script defer src=\"/assets/daemon.js\"></script></head><body>{content}</body></html>",
        esc(title)
    )
}
fn login_response(s: &App, message: &str) -> Response {
    let nonce = auth::random().expect("OS randomness");
    let form = format!(
        "<p role=\"status\">{}</p><form method=\"post\" action=\"/login\" data-core-login-progressive=\"on\"><input type=\"hidden\" name=\"_csrf\" value=\"{nonce}\"><label>Email<input type=\"email\" name=\"email\" autocomplete=\"username\" maxlength=\"254\" required></label><label>Password<input name=\"password\" type=\"password\" autocomplete=\"current-password\" maxlength=\"1024\" required></label><button class=\"button primary\">Sign in</button></form>",
        kagnode_core::escape(message)
    );
    let body = template(
        s,
        "login-frame",
        &[
            ("product", "KagNode. Daemon"),
            ("heading", "Sign in"),
            ("description", "Manage your KagNode servers."),
        ],
        &[("content", &form), ("provider", "")],
    );
    let mut response = Html(shell(s, "Sign in", None, &body)).into_response();
    response.headers_mut().insert(
        header::SET_COOKIE,
        format!(
            "kn_daemon_login={nonce}; HttpOnly; SameSite=Strict; Path=/; Max-Age=600{}",
            if s.origin.starts_with("https:") {
                "; Secure"
            } else {
                ""
            }
        )
        .parse()
        .unwrap(),
    );
    response
}
async fn login(State(s): State<App>) -> Response {
    login_response(&s, "")
}
#[derive(Deserialize)]
struct Login {
    email: String,
    password: String,
    #[serde(rename = "_csrf")]
    csrf: String,
}
async fn login_post(
    State(s): State<App>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    h: HeaderMap,
    Form(input): Form<Login>,
) -> Api<Response> {
    if h.get("origin").and_then(|v| v.to_str().ok()) != Some(s.origin.as_str())
        || input.csrf.len() != 64
        || cookie(&h, "kn_daemon_login") != Some(input.csrf.as_str())
    {
        return Err(Error(
            StatusCode::FORBIDDEN,
            "Reload the sign-in page".into(),
        ));
    }
    let store = s.store.clone();
    let result = tokio::task::spawn_blocking(move || {
        let password = zeroize::Zeroizing::new(input.password);
        store.login(&input.email, &password, &peer.ip().to_string())
    })
    .await
    .map_err(|_| anyhow::anyhow!("Sign-in unavailable"))?;
    match result {
        Ok(token) => {
            let mut r = Redirect::to("/").into_response();
            r.headers_mut().insert(
                header::SET_COOKIE,
                format!(
                    "kn_daemon={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{}",
                    if s.origin.starts_with("https:") {
                        "; Secure"
                    } else {
                        ""
                    }
                )
                .parse()
                .unwrap(),
            );
            Ok(r)
        }
        Err(_) => Ok(login_response(
            &s,
            "Sign-in failed or is temporarily limited. Check your details and try again.",
        )),
    }
}
async fn session(State(s): State<App>, h: HeaderMap) -> Api<Json<Value>> {
    Ok(Json(json!({"user":user(&s,&h)?})))
}
async fn logout(State(s): State<App>, h: HeaderMap) -> Api<Response> {
    mutation(&s, &h)?;
    s.store.logout(cookie(&h, "kn_daemon").unwrap_or(""))?;
    let mut r = StatusCode::NO_CONTENT.into_response();
    r.headers_mut().insert(
        header::SET_COOKIE,
        "kn_daemon=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
            .parse()
            .unwrap(),
    );
    Ok(r)
}
async fn settings(State(s): State<App>, h: HeaderMap) -> Api<Json<Settings>> {
    user(&s, &h)?;
    Ok(Json(s.store.settings()?))
}
async fn save_settings(
    State(s): State<App>,
    h: HeaderMap,
    Json(input): Json<Settings>,
) -> Api<Json<Settings>> {
    let u = mutation(&s, &h)?;
    Ok(Json(s.store.set_settings(&u.email, input)?))
}
async fn applications(State(s): State<App>, h: HeaderMap) -> Api<Json<Value>> {
    user(&s, &h)?;
    let root = s.store.managed_root();
    Ok(Json(
        json!({"server":"local","applications":catalog::PRODUCTS.iter().map(|p|json!({"product":p,"installed":catalog::installed(root,p),"url":format!("/servers/local/applications/{}",p.id),"management":"project-owned-adapter","native_actions_enabled":false})).collect::<Vec<_>>()}),
    ))
}
async fn audit(State(s): State<App>, h: HeaderMap) -> Api<Json<Value>> {
    user(&s, &h)?;
    Ok(Json(json!({"events":s.store.audit()?})))
}
async fn ha_plan(
    State(s): State<App>,
    h: HeaderMap,
    Json(input): Json<ha::Cluster>,
) -> Api<Json<Value>> {
    mutation(&s, &h)?;
    Ok(Json(input.plan()?))
}
async fn ha_get(State(s): State<App>, h: HeaderMap) -> Api<Json<Value>> {
    user(&s, &h)?;
    Ok(Json(match s.store.document("ha")? {
        Some((revision, value)) => json!({"revision":revision,"configuration":value}),
        None => json!({"revision":0,"configuration":null}),
    }))
}
#[derive(Deserialize)]
struct HaSave {
    revision: i64,
    configuration: ha::Cluster,
}
async fn ha_save(
    State(s): State<App>,
    h: HeaderMap,
    Json(input): Json<HaSave>,
) -> Api<Json<Value>> {
    let u = mutation(&s, &h)?;
    input.configuration.validate()?;
    Ok(Json(
        json!({"revision":s.store.save_document(&u.email,"ha",input.revision,&serde_json::to_value(input.configuration).map_err(anyhow::Error::from)?)?,"activated":false}),
    ))
}
async fn page(State(s): State<App>, h: HeaderMap) -> Response {
    let Ok(u) = user(&s, &h) else {
        return Redirect::to("/login").into_response();
    };
    Html(shell(&s,"Workspace",Some(&u),"<h1>Your KagNode workspace</h1><p id=\"page-status\" role=\"status\">Loading workspace…</p><section id=\"content\"></section>")).into_response()
}
async fn application_page(State(s): State<App>, h: HeaderMap, Path(id): Path<String>) -> Response {
    if catalog::product(&id).is_none() {
        return StatusCode::NOT_FOUND.into_response();
    }
    page(State(s), h).await
}
async fn js() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/javascript")],
        include_str!("../web/rust-daemon/app.js"),
    )
}
async fn css() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/css")],
        include_str!("../web/rust-daemon/app.css"),
    )
}

#[derive(Deserialize)]
struct ServicePlan {
    operation: crate::broker::Operation,
}
#[derive(Deserialize)]
struct ServiceApply {
    operation: crate::broker::Operation,
    expected_sha256: String,
    request_id: String,
}
async fn service_status(
    State(s): State<App>,
    h: HeaderMap,
    Path(id): Path<String>,
) -> Api<Json<Value>> {
    user(&s, &h)?;
    match crate::broker::request(crate::broker::Request::Status { product: id }).await {
        Ok(value) => Ok(Json(value)),
        Err(e) => Ok(Json(
            json!({"native_actions_enabled":false,"message":e.to_string()}),
        )),
    }
}
async fn service_plan(
    State(s): State<App>,
    h: HeaderMap,
    Path(id): Path<String>,
    Json(input): Json<ServicePlan>,
) -> Api<Json<Value>> {
    mutation(&s, &h)?;
    Ok(Json(
        crate::broker::request(crate::broker::Request::Plan {
            product: id,
            operation: input.operation,
        })
        .await?,
    ))
}
async fn service_apply(
    State(s): State<App>,
    h: HeaderMap,
    Path(id): Path<String>,
    Json(input): Json<ServiceApply>,
) -> Api<Json<Value>> {
    mutation(&s, &h)?;
    Ok(Json(
        crate::broker::request(crate::broker::Request::Apply {
            product: id,
            operation: input.operation,
            expected_sha256: input.expected_sha256,
            request_id: input.request_id,
        })
        .await?,
    ))
}

async fn service_history(
    State(s): State<App>,
    h: HeaderMap,
    Path(id): Path<String>,
) -> Api<Json<Value>> {
    user(&s, &h)?;
    Ok(Json(
        crate::broker::request(crate::broker::Request::History { product: id }).await?,
    ))
}
