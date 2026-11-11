/** KagNode Core local assets and Express adapter. AGPL-3.0-only. */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import http from "node:http";
const BUNDLE = {};
const TEMPLATES = {};
const cache = new Map();
const mimes = {
  js: "text/javascript; charset=utf-8",
  css: "text/css; charset=utf-8",
  svg: "image/svg+xml",
  woff2: "font/woff2",
};
const root = () => process.env.KAGNODE_CORE_ROOT || "/srv/kagnode/core";
const validApp = (v) => {
  if (!/^[a-z][a-z0-9-]{0,63}$/.test(v))
    throw Error("Invalid Core application ID");
  return v;
};
const protectedFile = (p) => {
  const s = fs.lstatSync(p);
  if (!s.isFile() || s.isSymbolicLink() || s.uid !== 0 || s.mode & 0o022)
    throw Error("Unprotected Core state");
  return s;
};
export function manifest(version = BUNDLE.version) {
  if (!/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/.test(version))
    throw Error("Invalid Core version");
  if (version === BUNDLE.version) return BUNDLE;
  const p = path.join(root(), "releases", version, "manifest.json"),
    stat = protectedFile(p),
    key = p + stat.mtimeMs;
  if (!cache.has(key)) {
    const value = JSON.parse(fs.readFileSync(p, "utf8"));
    if (value.version !== version || value.ui_api !== 1)
      throw Error("Incompatible Core");
    cache.clear();
    cache.set(key, value);
  }
  return cache.get(key);
}
export function active(app) {
  try {
    const p = path.join(root(), "apps", validApp(app), "state.json");
    protectedFile(p);
    return manifest(JSON.parse(fs.readFileSync(p, "utf8")).version);
  } catch {
    return BUNDLE;
  }
}
export function asset(uri) {
  const match = /^\/kagnode-core\/([a-zA-Z0-9.-]+)\/([a-zA-Z0-9_.-]+)$/.exec(
    uri,
  );
  if (!match) return null;
  try {
    const [, version, name] = match,
      value = manifest(version),
      item = value.files[name],
      type = mimes[name.split(".").at(-1)];
    if (!item || !type) return null;
    const p = path.join(root(), "releases", version, name);
    if (version !== BUNDLE.version) protectedFile(p);
    const data =
      version === BUNDLE.version
        ? Buffer.from(item.data, "base64")
        : fs.readFileSync(p);
    if (
      data.length !== item.size ||
      crypto.createHash("sha256").update(data).digest("hex") !== item.sha256
    )
      return null;
    return { data, type };
  } catch {
    return null;
  }
}
const escape = (v) =>
  String(v)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
export const iconSources = Object.freeze({ ...(BUNDLE.icon_sources || {}) });
export const iconLibrary = Object.keys(BUNDLE.icons || {})
  .sort()
  .map((name) => ({
    name,
    label: name.replaceAll("-", " ").replace(/^./, (c) => c.toUpperCase()),
  }));
export function icon(name) {
  const shape = Object.hasOwn(BUNDLE.icons || {}, name)
    ? BUNDLE.icons[name]
    : BUNDLE.icons.plan;
  return (
    '<svg class="ui-icon" data-core-icon-name="' +
    escape(name) +
    '"' +
    (name === "chevron" ? " data-disclosure-icon" : "") +
    ' width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    shape +
    "</svg>"
  );
}
export function inject(body, app = "kagnode", context = {}) {
  if (!/<head\b/i.test(body) || body.includes('name="kagnode-core"'))
    return body;
  const value = active(app),
    base = "/kagnode-core/" + value.version + "/",
    config = {
      authenticated: /data-authenticated=["']true["']/.test(body),
      issuer: "https://nebulacoder.com",
      ...context,
      version: value.version,
      base,
      app: validApp(app),
    };
  body = body
    .replace(
      /<script\b[^>]*src=["'][^"']*\/(?:kagnode-scroll|theme|preferences|controls|inputs)(?:\.[a-f0-9]{8,})?\.js(?:\?[^"']*)?["'][^>]*>\s*<\/script>/gi,
      "",
    )
    .replace(
      /<link\b[^>]*href=["'][^"']*\/(?:kagnode-scroll|inputs|controls)(?:\.[a-f0-9]{8,})?\.css(?:\?[^"']*)?["'][^>]*>/gi,
      "",
    );
  const tags =
    '<meta name="kagnode-core" content="' +
    escape(JSON.stringify(config)) +
    '"><script src="' +
    base +
    value.entrypoints.theme +
    '"></script><script defer src="' +
    base +
    value.entrypoints.script +
    '"></script>';
  return body
    .replace(/(<head\b[^>]*>)/i, "$1" + tags)
    .replace(
      /<\/head>/i,
      '<link rel="stylesheet" href="' +
        base +
        value.entrypoints.style +
        '"></head>',
    );
}
export function installCore(
  app,
  { appId = "kagnode", context = () => ({}) } = {},
) {
  app.use((q, r, next) => {
    if (q.path.startsWith("/kagnode-core/")) {
      if (!["GET", "HEAD"].includes(q.method)) return r.sendStatus(405);
      const result = asset(q.path);
      return result
        ? r
            .set({
              "Content-Type": result.type,
              "Cache-Control": "public, max-age=31536000, immutable",
              "X-Content-Type-Options": "nosniff",
            })
            .send(result.data)
        : r.sendStatus(404);
    }
    const send = r.send;
    r.send = function (body) {
      const contentType = this.get?.("Content-Type") || "";
      if (
        typeof body === "string" &&
        (!contentType || /^text\/html(?:;|$)/i.test(contentType)) &&
        /<head\b/i.test(body)
      ) {
        const c = context(q, r);
        body = inject(body, appId, c);
        this.set(
          "Cross-Origin-Opener-Policy",
          q.path === "/auth/appearance/authorize"
            ? "unsafe-none"
            : "same-origin-allow-popups",
        );
        const issuer = c.issuer || "https://nebulacoder.com";
        if (!/^https:\/\/[a-zA-Z0-9.-]+(?::\d+)?$/.test(issuer))
          throw Error("Core appearance issuer must be an HTTPS origin");
        let csp = String(
          this.get("Content-Security-Policy") || "default-src 'self'",
        );
        csp = /(?:^|;)\s*connect-src\b/.test(csp)
          ? csp.replace(/((?:^|;)\s*connect-src[^;]*)/, (m) =>
              m.split(/\s+/).includes(issuer) ? m : m + " " + issuer,
            )
          : csp + "; connect-src 'self' " + issuer;
        this.set("Content-Security-Policy", csp);
      }
      return send.call(this, body);
    };
    next();
  });
}
export function managerRequest(appId, action = "status", data = {}) {
  validApp(appId);
  if (!["status", "check", "apply", "rollback", "policy"].includes(action))
    throw Error("Unknown Core action");
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ ...data, action });
    const req = http.request(
      {
        socketPath: path.join(root(), "run", appId + ".sock"),
        path: "/",
        method: "POST",
        timeout: 45000,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        let size = 0;
        const chunks = [];
        res.on("data", (part) => {
          size += part.length;
          if (size > 65536) req.destroy(Error("Core response too large"));
          else chunks.push(part);
        });
        res.on("end", () => {
          try {
            const value = JSON.parse(Buffer.concat(chunks));
            res.statusCode < 400
              ? resolve(value)
              : reject(Error(value.error || "Core request failed"));
          } catch (e) {
            reject(e);
          }
        });
        res.on("error", reject);
      },
    );
    req.on("timeout", () => req.destroy(Error("Core manager timeout")));
    req.on("error", (e) => {
      if (action === "status" && ["ENOENT", "ECONNREFUSED"].includes(e.code))
        resolve({
          enabled: false,
          version: active(appId).version,
          message: "Enable Core management with KagNode CLI on this server.",
        });
      else reject(e);
    });
    req.end(body);
  });
}

/** Slots are trusted, already-escaped authorized host markup, never user input. */
export function renderTemplate(name, slots = {}) {
  if (!Object.hasOwn(TEMPLATES, name)) throw Error("Unknown Core template");
  return TEMPLATES[name].replace(/\{\{([a-z]+)\}\}/g, (_match, key) =>
    String(slots[key] || ""),
  );
}
