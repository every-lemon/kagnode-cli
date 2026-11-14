//! Framework-independent, locally served UI. Host authorization stays in the host.
use base64::Engine;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::{Read, Write},
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
#[derive(Clone)]
pub struct Core {
    root: PathBuf,
    app: String,
    fallback: Value,
}
#[derive(Debug)]
pub struct Asset {
    pub bytes: Vec<u8>,
    pub content_type: &'static str,
    pub version: String,
}
fn identifier(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && s.as_bytes()[0].is_ascii_lowercase()
        && s.bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}
fn version(s: &str) -> bool {
    let (base, beta) = s
        .split_once("-beta.")
        .map_or((s, None), |(b, n)| (b, Some(n)));
    let p: Vec<_> = base.split('.').collect();
    p.len() == 3
        && p[0] == "5"
        && p[1] == "0"
        && !p[2].is_empty()
        && p[2].len() <= 8
        && p[2].bytes().all(|b| b.is_ascii_digit())
        && beta.is_none_or(|n| {
            !n.is_empty()
                && !n.starts_with('0')
                && n.len() <= 8
                && n.bytes().all(|b| b.is_ascii_digit())
        })
}

fn file(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 120
        && !s.starts_with('.')
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
}
fn protected(path: &Path) -> Result<()> {
    if !path.is_absolute()
        || path.components().any(|p| {
            matches!(
                p,
                std::path::Component::ParentDir | std::path::Component::CurDir
            )
        })
    {
        return Err("Unsafe Core path".into());
    }
    for ancestor in path.ancestors().skip(1) {
        let meta = std::fs::symlink_metadata(ancestor)?;
        if !meta.is_dir()
            || meta.file_type().is_symlink()
            || meta.uid() != 0
            || (meta.mode() & 0o022 != 0
                && !(ancestor == Path::new("/tmp") && meta.mode() & 0o1000 != 0))
        {
            return Err("Core ancestor is not protected".into());
        }
    }
    let meta = std::fs::symlink_metadata(path)?;
    if meta.file_type().is_symlink() || meta.uid() != 0 || meta.mode() & 0o022 != 0 {
        return Err("Core path is not protected".into());
    }
    Ok(())
}
fn read_bound(path: &Path, max: usize) -> Result<Vec<u8>> {
    let meta = std::fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.len() > max as u64 {
        return Err("Invalid Core file".into());
    }
    protected(path)?;
    let mut bytes = Vec::new();
    std::fs::File::open(path)?
        .take(max as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > max {
        return Err("Oversized Core file".into());
    }
    Ok(bytes)
}
pub fn escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
impl Core {
    pub fn new(root: impl Into<PathBuf>, application: &str) -> Result<Self> {
        if !identifier(application) {
            return Err("Invalid Core application ID".into());
        }
        let root = root.into();
        if !root.is_absolute() {
            return Err("Core storage must be absolute".into());
        }
        let fallback: Value = serde_json::from_str(include_str!("../fallback/bundle.json"))?;
        if fallback["ui_api"] != 1 || !version(fallback["version"].as_str().unwrap_or("")) {
            return Err("Incompatible fallback bundle".into());
        }
        Ok(Self {
            root,
            app: application.into(),
            fallback,
        })
    }
    pub fn baseline(&self) -> &str {
        self.fallback["version"].as_str().unwrap()
    }
    fn manifest(&self, requested: &str) -> Result<Value> {
        if !version(requested) {
            return Err("Invalid Core version".into());
        }
        if requested == self.baseline() {
            return Ok(self.fallback.clone());
        }
        protected(&self.root)?;
        protected(&self.root.join("releases"))?;
        let dir = self.root.join("releases").join(requested);
        protected(&dir)?;
        let value: Value =
            serde_json::from_slice(&read_bound(&dir.join("manifest.json"), 512 * 1024)?)?;
        if value["version"] != requested
            || value["ui_api"] != 1
            || value["files"].as_object().is_none_or(|f| f.len() > 32)
        {
            return Err("Incompatible Core manifest".into());
        }
        Ok(value)
    }
    pub fn active(&self) -> Value {
        let read = || -> Result<Value> {
            protected(&self.root)?;
            let apps = self.root.join("apps");
            protected(&apps)?;
            let app = apps.join(&self.app);
            protected(&app)?;
            let state: Value =
                serde_json::from_slice(&read_bound(&app.join("state.json"), 128 * 1024)?)?;
            self.manifest(state["version"].as_str().ok_or("Missing Core version")?)
        };
        read().unwrap_or_else(|_| self.fallback.clone())
    }
    pub fn asset(&self, requested: &str, name: &str) -> Result<Asset> {
        if !file(name) {
            return Err("Invalid asset name".into());
        }
        let content_type = match name.rsplit('.').next() {
            Some("js") => "text/javascript; charset=utf-8",
            Some("css") => "text/css; charset=utf-8",
            Some("svg") => "image/svg+xml",
            Some("woff2") => "font/woff2",
            _ => return Err("Unsupported Core asset".into()),
        };
        let manifest = self.manifest(requested)?;
        let item = &manifest["files"][name];
        let size = item["size"].as_u64().ok_or("Unknown Core asset")?;
        if size > 512 * 1024 {
            return Err("Oversized Core asset".into());
        }
        let bytes = if requested == self.baseline() {
            base64::engine::general_purpose::STANDARD
                .decode(item["data"].as_str().ok_or("Missing fallback data")?)?
        } else {
            read_bound(
                &self.root.join("releases").join(requested).join(name),
                512 * 1024,
            )?
        };
        let sha = format!("{:x}", Sha256::digest(&bytes));
        if bytes.len() as u64 != size || item["sha256"] != sha {
            return Err("Core asset checksum mismatch".into());
        }
        Ok(Asset {
            bytes,
            content_type,
            version: requested.into(),
        })
    }
    pub fn head(&self, context: Value) -> Result<String> {
        let manifest = self.active();
        let version = manifest["version"].as_str().ok_or("Missing Core version")?;
        let mut context = context.as_object().cloned().unwrap_or_default();
        context.insert("version".into(), json!(version));
        context.insert("base".into(), json!(format!("/kagnode-core/{version}/")));
        context.insert("app".into(), json!(self.app));
        let issuer = context
            .get("issuer")
            .and_then(Value::as_str)
            .unwrap_or("https://nebulacoder.com");
        if !https_origin(issuer) {
            return Err("Use a trusted HTTPS appearance issuer".into());
        }
        let entries = &manifest["entrypoints"];
        let entry = |key: &str| -> Result<&str> {
            let name = entries[key].as_str().ok_or("Missing Core entrypoint")?;
            if !file(name) || manifest["files"][name].is_null() {
                return Err("Invalid Core entrypoint".into());
            }
            Ok(name)
        };
        Ok(format!(
            "<meta name=\"kagnode-core\" content=\"{}\"><script src=\"/kagnode-core/{version}/{}\"></script><link rel=\"stylesheet\" href=\"/kagnode-core/{version}/{}\"><script defer src=\"/kagnode-core/{version}/{}\"></script>",
            escape(&Value::Object(context).to_string()),
            entry("theme")?,
            entry("style")?,
            entry("script")?
        ))
    }
    /// Canonical markup. Text is escaped; only host-authored fragments belong in `html`.
    pub fn template(
        &self,
        name: &str,
        text: &[(&str, &str)],
        html: &[(&str, &str)],
    ) -> Result<String> {
        let templates: Value = serde_json::from_str(include_str!("../fallback/templates.json"))?;
        let source = templates[name].as_str().ok_or("Unknown Core template")?;
        let mut result = String::new();
        let mut remaining = source;
        while let Some((before, rest)) = remaining.split_once("{{") {
            result.push_str(before);
            let (key, after) = rest.split_once("}}").ok_or("Invalid Core template")?;
            if let Some((_, value)) = text.iter().find(|(k, _)| *k == key) {
                result.push_str(&escape(value));
            } else if let Some((_, value)) = html.iter().find(|(k, _)| *k == key) {
                result.push_str(value);
            } else {
                return Err("Missing Core template parameter".into());
            }
            remaining = after;
        }
        result.push_str(remaining);
        Ok(result)
    }
    pub fn manager_request(&self, action: &str, parameters: Value) -> Result<Value> {
        if !matches!(
            action,
            "status" | "summary" | "check" | "apply" | "rollback" | "policy"
        ) {
            return Err("Unknown Core action".into());
        }
        protected(&self.root)?;
        protected(&self.root.join("run"))?;
        let socket = self.root.join("run").join(format!("{}.sock", self.app));
        let mut stream = std::os::unix::net::UnixStream::connect(socket)?;
        stream.set_read_timeout(Some(std::time::Duration::from_secs(45)))?;
        stream.set_write_timeout(Some(std::time::Duration::from_secs(5)))?;
        let mut payload = parameters
            .as_object()
            .cloned()
            .ok_or("Core parameters must be an object")?;
        payload.insert("action".into(), json!(action));
        let body = serde_json::to_vec(&payload)?;
        if body.len() > 4096 {
            return Err("Oversized Core request".into());
        }
        let head = format!(
            "POST / HTTP/1.0\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        stream.write_all(head.as_bytes())?;
        stream.write_all(&body)?;
        let mut response = Vec::new();
        stream.take(73729).read_to_end(&mut response)?;
        if response.len() > 73728 {
            return Err("Oversized Core response".into());
        }
        parse_response(&response)
    }
}
fn https_origin(value: &str) -> bool {
    let Some(authority) = value.strip_prefix("https://") else {
        return false;
    };
    let authority = authority.strip_suffix('/').unwrap_or(authority);
    if authority.is_empty()
        || authority.len() > 300
        || authority.contains(['/', '?', '#', '@', '\\'])
        || authority
            .chars()
            .any(|c| c.is_whitespace() || c.is_control())
    {
        return false;
    }
    let (host, port) = if let Some(ipv6) = authority.strip_prefix('[') {
        let Some((ip, rest)) = ipv6.split_once(']') else {
            return false;
        };
        if ip.parse::<std::net::Ipv6Addr>().is_err() {
            return false;
        }
        (
            ip,
            if rest.is_empty() {
                None
            } else {
                let Some(port) = rest.strip_prefix(':') else {
                    return false;
                };
                Some(port)
            },
        )
    } else {
        let (host, port) = authority
            .split_once(':')
            .map_or((authority, None), |(h, p)| (h, Some(p)));
        if !host.split('.').all(|label| {
            !label.is_empty()
                && label.len() <= 63
                && !label.starts_with('-')
                && !label.ends_with('-')
                && label
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'-')
        }) {
            return false;
        }
        (host, port)
    };
    !host.is_empty()
        && port.is_none_or(|p| {
            !p.is_empty()
                && p.bytes().all(|c| c.is_ascii_digit())
                && p.parse::<u16>().is_ok_and(|n| n > 0)
        })
}
fn parse_response(response: &[u8]) -> Result<Value> {
    let boundary = response
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .ok_or("Invalid Core HTTP response")?;
    if boundary > 8192 {
        return Err("Oversized Core headers".into());
    }
    let headers = std::str::from_utf8(&response[..boundary])?;
    let status = headers
        .lines()
        .next()
        .and_then(|s| s.split_whitespace().nth(1))
        .and_then(|s| s.parse::<u16>().ok())
        .ok_or("Missing Core status")?;
    let lengths = headers
        .lines()
        .filter_map(|s| s.split_once(':'))
        .filter(|(k, _)| k.eq_ignore_ascii_case("content-length"))
        .map(|(_, v)| v.trim().parse::<usize>())
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if lengths.len() != 1
        || lengths[0] > 65536
        || headers
            .lines()
            .any(|s| s.to_ascii_lowercase().starts_with("transfer-encoding:"))
    {
        return Err("Invalid Core HTTP framing".into());
    }
    let body = &response[boundary + 4..];
    if body.len() != lengths[0] {
        return Err("Incomplete Core response".into());
    }
    let value: Value = serde_json::from_slice(body)?;
    if status != 200 {
        return Err("The local Core manager refused this operation".into());
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn manager_http_framing_is_bounded_and_unambiguous() {
        let body = b"{\"enabled\":true}";
        let mut valid =
            format!("HTTP/1.0 200 OK\r\nContent-Length: {}\r\n\r\n", body.len()).into_bytes();
        valid.extend(body);
        assert_eq!(parse_response(&valid).unwrap()["enabled"], true);
        for invalid in [
            b"HTTP/1.0 200 OK\r\n\r\n{}".as_slice(),
            b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
            b"HTTP/1.0 200 OK\r\nContent-Length: 3\r\n\r\n{}",
            b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}",
            b"HTTP/1.0 403 Forbidden\r\nContent-Length: 2\r\n\r\n{}",
        ] {
            assert!(parse_response(invalid).is_err());
        }
    }
    #[test]
    fn canonical_templates_escape_text_without_replacing_host_fragments() {
        let c = Core::new("/nonexistent/core", "proxy-manager").unwrap();
        let markup = c
            .template(
                "login-frame",
                &[
                    ("product", "<unsafe>"),
                    ("heading", "Sign in"),
                    ("description", "{{content}}"),
                ],
                &[("content", "<form></form>"), ("provider", "")],
            )
            .unwrap();
        assert!(markup.contains("&lt;unsafe&gt;"));
        assert!(markup.contains("<form></form>"));
        assert!(markup.contains("{{content}}"));
        assert!(!markup.contains("<unsafe>"));
        assert!(c.template("login-frame", &[], &[]).is_err());
        assert!(version("5.0.10-beta.1"));
        assert!(!version("5.0.10-beta.01"));
    }
    #[test]
    fn fallback_is_local_and_checked() {
        let core = Core::new("/nonexistent/core", "proxy-manager").unwrap();
        let m = core.active();
        for (name, _) in m["files"].as_object().unwrap() {
            assert!(core.asset(core.baseline(), name).is_ok());
        }
        let head=core.head(json!({"authenticated":false,"issuer":"https://nebulacoder.com","subject":"<unsafe>"})).unwrap();
        assert!(head.contains("/kagnode-core/"));
        assert!(!head.contains("<unsafe>"));
        assert!(!head.contains("githubusercontent"));
    }
    #[test]
    fn unsafe_ids_paths_and_other_release_lines_rejected() {
        assert!(Core::new("relative", "proxy-manager").is_err());
        assert!(Core::new("/tmp/core", "../other").is_err());
        let c = Core::new("/nonexistent", "proxy-manager").unwrap();
        for v in ["../5.0.8", "5.1.0", "5.0.8-alpha", "5.0"] {
            assert!(c.asset(v, "core.js").is_err());
        }
        for name in ["../manifest.json", "ca.key", ".hidden.js", "core.js/map"] {
            assert!(c.asset(c.baseline(), name).is_err());
        }
    }
    #[test]
    fn missing_state_falls_back_without_network() {
        let c = Core::new("/nonexistent", "proxy-manager").unwrap();
        assert_eq!(c.active(), c.fallback);
    }
    #[test]
    fn appearance_issuer_is_an_https_origin() {
        for value in [
            "https://nebulacoder.com",
            "https://accounts.example:9443/",
            "https://[::1]:9443",
        ] {
            assert!(https_origin(value), "{value}");
        }
        for value in [
            "http://nebulacoder.com",
            "https://user@host",
            "https://host/path",
            "https://host?x",
            "https://host#x",
            "https://host:0",
            "https://host:65536",
            "https://host:abc",
            "https://host\\evil",
            "https://host\t",
            "https://a..example",
            "https://<unsafe>",
        ] {
            assert!(!https_origin(value), "{value}");
        }
    }
    #[test]
    fn writable_ancestors_and_symlinked_cache_are_rejected() {
        let dir = tempfile::tempdir().unwrap();
        let data = dir.path().join("data");
        std::fs::create_dir(&data).unwrap();
        let link = dir.path().join("link");
        std::os::unix::fs::symlink(&data, &link).unwrap();
        assert!(protected(&link).is_err());
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(dir.path(), std::fs::Permissions::from_mode(0o777)).unwrap();
        assert!(protected(&data).is_err());
    }
}
