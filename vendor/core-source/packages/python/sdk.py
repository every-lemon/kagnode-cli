"""KagNode Core local assets and framework adapters. Never downloads on requests."""

import base64
import hashlib
import html
import http.client
import json
import os
from pathlib import Path
import re
import socket

BUNDLE = {}
TEMPLATES = {}
_cache = {}
MIMES = {
    "js": "text/javascript; charset=utf-8",
    "css": "text/css; charset=utf-8",
    "svg": "image/svg+xml",
    "woff2": "font/woff2",
}


def root():
    value = Path(os.environ.get("KAGNODE_CORE_ROOT", "/srv/kagnode/core"))
    if not value.is_absolute():
        raise ValueError("Core storage must be absolute")
    return value


def application(value):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
        raise ValueError("Invalid Core application ID")
    return value


def manifest(version=None):
    version = version or BUNDLE["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version):
        raise ValueError("Invalid Core version")
    if version == BUNDLE["version"]:
        return BUNDLE
    path = root() / "releases" / version / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Core version is unavailable")
    if path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
        raise ValueError("Core manifest must be protected")
    key = (str(path), path.stat().st_mtime_ns)
    if key not in _cache:
        value = json.loads(path.read_text())
        if value.get("version") != version or value.get("ui_api") != 1:
            raise ValueError("Incompatible Core manifest")
        _cache.clear()
        _cache[key] = value
    return _cache[key]


def active(app):
    try:
        path = root() / "apps" / application(app) / "state.json"
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise ValueError("Unsafe Core state")
        value = json.loads(path.read_text())
        candidate = manifest(value["version"])
        if candidate.get("ui_api") != 1:
            raise ValueError("Incompatible Core")
        return candidate
    except (OSError, ValueError, KeyError):
        return BUNDLE


def asset(uri):
    match = re.fullmatch(r"/kagnode-core/([a-zA-Z0-9.-]+)/([a-zA-Z0-9_.-]+)", uri)
    if not match:
        return None
    version, name = match.groups()
    try:
        value = manifest(version)
        item = value["files"][name]
        if name.rsplit(".", 1)[-1] not in MIMES:
            return None
        if version == BUNDLE["version"]:
            data = base64.b64decode(item["data"])
        else:
            path = root() / "releases" / version / name
            if path.is_symlink():
                return None
            data = path.read_bytes()
        if (
            len(data) != item["size"]
            or hashlib.sha256(data).hexdigest() != item["sha256"]
        ):
            return None
        return data, MIMES[name.rsplit(".", 1)[-1]]
    except (OSError, ValueError, KeyError):
        return None


def inject(body, app="kagnode", context=None):
    if "<head" not in body.lower() or 'name="kagnode-core"' in body:
        return body
    value = active(app)
    context = dict(context or {})
    context.setdefault(
        "authenticated", bool(re.search(r'data-authenticated=["\']true["\']', body))
    )
    context.update(
        version=value["version"],
        base="/kagnode-core/" + value["version"] + "/",
        app=application(app),
    )
    context.setdefault("issuer", "https://nebulacoder.com")
    # Public assets are local; retired standalone controllers must not compete.
    body = re.sub(
        r'<script\b[^>]*src=["\'][^"\']*/(?:kagnode-scroll|theme|preferences|controls|inputs)(?:\.[a-f0-9]{8,})?\.js(?:\?[^"\']*)?["\'][^>]*>\s*</script>',
        "",
        body,
        flags=re.I,
    )
    body = re.sub(
        r'<link\b[^>]*href=["\'][^"\']*/(?:kagnode-scroll|inputs|controls)(?:\.[a-f0-9]{8,})?\.css(?:\?[^"\']*)?["\'][^>]*>',
        "",
        body,
        flags=re.I,
    )
    base = context["base"]
    tags = (
        '<meta name="kagnode-core" content="'
        + html.escape(json.dumps(context, separators=(",", ":")), quote=True)
        + '">'
    )
    tags += '<script src="' + base + value["entrypoints"]["theme"] + '"></script>'
    tags += (
        '<script defer src="' + base + value["entrypoints"]["script"] + '"></script>'
    )
    body = re.sub(r"(<head\b[^>]*>)", lambda m: m[1] + tags, body, count=1, flags=re.I)
    return re.sub(
        r"</head>",
        '<link rel="stylesheet" href="'
        + base
        + value["entrypoints"]["style"]
        + '"></head>',
        body,
        count=1,
        flags=re.I,
    )


def manager_request(app, action="status", data=None):
    app = application(app)
    if action not in ("status", "check", "apply", "rollback", "policy"):
        raise ValueError("Unknown Core action")
    connection = http.client.HTTPConnection("localhost", timeout=45)
    try:
        connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.sock.settimeout(45)
        connection.sock.connect(str(root() / "run" / (app + ".sock")))
        connection.request(
            "POST",
            "/",
            json.dumps({**(data or {}), "action": action}),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("Core response too large")
        value = json.loads(raw)
        if response.status >= 400:
            raise ValueError(value.get("error", "Core request failed"))
        return value
    except OSError:
        if action == "status":
            return {
                "enabled": False,
                "version": active(app)["version"],
                "message": "Enable Core management with KagNode CLI on this server.",
            }
        raise ValueError("The local Core manager is unavailable")
    finally:
        connection.close()


def register_flask(app, app_id, context=None):
    from flask import request, Response

    @app.before_request
    def core_assets():
        if not request.path.startswith("/kagnode-core/"):
            return
        if request.method not in ("GET", "HEAD"):
            return Response("Method not allowed", 405)
        result = asset(request.path)
        if not result:
            return Response("Core asset unavailable", 404)
        data, mime = result
        response = Response(data, mimetype=mime)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.after_request
    def core_html(response):
        if response.status_code == 200 and response.mimetype == "text/html":
            response.direct_passthrough = False
            response.set_data(
                inject(
                    response.get_data(as_text=True),
                    app_id,
                    context() if callable(context) else context,
                )
            )
            response.headers.pop("ETag", None)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
            csp = response.headers.get("Content-Security-Policy", "default-src 'self'")
            issuer = (context() if callable(context) else context or {}).get(
                "issuer", "https://nebulacoder.com"
            )
            if not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::\d+)?", issuer):
                raise ValueError("Core appearance issuer must be an HTTPS origin")
            if re.search(r"(?:^|;)\s*connect-src\b", csp):
                csp = re.sub(
                    r"((?:^|;)\s*connect-src[^;]*)",
                    lambda m: m[1] + " " + issuer
                    if issuer not in m[1].split()
                    else m[1],
                    csp,
                )
            else:
                csp += "; connect-src 'self' " + issuer
            response.headers["Content-Security-Policy"] = csp
        return response


def register_flask_api(app, app_id, authenticated, administrator, write_guard=None):
    """Host supplies its local authentication/authorization and existing CSRF guard."""
    from flask import request, jsonify

    def execute(action):
        if not administrator():
            return jsonify(error="Local administrator access is required."), 403
        if request.method == "GET" and action != "status":
            return jsonify(error="Use POST for Core actions."), 405
        try:
            data = (
                request.get_json(silent=True) or {} if request.method == "POST" else {}
            )
            if not isinstance(data, dict):
                raise ValueError("Invalid Core request")
            return jsonify(manager_request(app_id, action, data))
        except (ValueError, OSError) as error:
            return jsonify(error=str(error)), 400

    def handler(action):
        if request.method == "POST" and write_guard:
            return write_guard(lambda: execute(action))()
        return execute(action)

    app.add_url_rule(
        "/api/v1/kagnode-core/<action>",
        endpoint="kagnode_core_api",
        view_func=authenticated(handler),
        methods=["GET", "POST"],
    )


def render_template(name, slots=None):
    """Slots are trusted, escaped authorized host markup, never raw user data."""
    if name not in TEMPLATES:
        raise ValueError("Unknown Core template")
    return re.sub(
        r"\{\{([a-z]+)\}\}", lambda m: str((slots or {}).get(m[1], "")), TEMPLATES[name]
    )


def icon(name):
    """Render a decorative, selected Core component glyph; never arbitrary SVG."""
    icons = BUNDLE.get("icons", {})
    key = name if name in icons else "plan"
    return (
        '<svg class="ui-icon" data-core-icon-name="'
        + html.escape(key, quote=True)
        + '" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
        + icons.get(key, "")
        + "</svg>"
    )
