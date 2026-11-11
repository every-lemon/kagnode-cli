#!/usr/bin/env python3
"""Build hashed demo assets. Source remains available; no runtime Node dependency."""

import hashlib, json, os, re, subprocess, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "assets"
built = source / "built"
built.mkdir(exist_ok=True)
manifest = {}
import importlib.util

spec = importlib.util.spec_from_file_location(
    "core_sdk", root / "vendor/core-source/packages/python/sdk.py"
)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
core.BUNDLE = json.loads((source / "core-bundle.json").read_text())
core.TEMPLATES = json.loads(
    (root / "vendor/core-source/packages/templates.json").read_text()
)
account_menu = core.render_template(
    "account-menu",
    {
        "identity": "<strong data-kn-account-name>CLI account</strong><small>Local CLI examples</small>",
        "actions": '<section data-kn-scroll-settings></section><section class="kn-account-settings" data-kn-account-settings></section>',
    },
)
account_control = (
    '<div class="kn-cli-profile"><button type="button" class="icon-button" '
    'data-core-account-trigger aria-label="Account and preferences" aria-expanded="false">'
    '<span class="kn-profile-avatar" data-kn-account-avatar>A</span></button>'
    + account_menu
    + "</div>"
)
# Retain only the current generated local fallback. Runtime releases are separate.
for stale in source.glob("kn-core-*"):
    if stale.name.removeprefix("kn-core-") not in core.BUNDLE["files"]:
        stale.unlink()
for name, item in core.BUNDLE["files"].items():
    import base64

    (source / ("kn-core-" + name)).write_bytes(base64.b64decode(item["data"]))

with tempfile.TemporaryDirectory(prefix="kagnode-cli-web-") as scratch:
    for file in sorted(source.iterdir()):
        if file.suffix not in (".css", ".js"):
            continue
        if file.name.startswith("kn-core-"):
            # Preserve signed Core bytes and hashes; do not minify them a second time.
            (built / file.name).write_bytes(file.read_bytes())
            manifest["/" + file.name] = "/built/" + file.name
            continue
        out = Path(scratch) / file.name
        subprocess.run(
            [
                os.environ.get("ESBUILD", "esbuild"),
                str(file),
                "--minify",
                "--target=es2020",
                "--charset=utf8",
                "--legal-comments=inline",
                "--banner:"
                + file.suffix[1:]
                + "=/*! KagNode. CLI | Source retained in project repository. */",
                "--outfile=" + str(out),
            ],
            check=True,
            capture_output=True,
        )
        data = out.read_bytes()
        name = file.stem + "." + hashlib.sha256(data).hexdigest()[:16] + file.suffix
        (built / name).write_bytes(data)
        manifest["/" + file.name] = "/built/" + name
    for name in core.BUNDLE["files"]:
        mapped = manifest.get("/kn-core-" + name, "/kn-core-" + name)
        manifest["/kagnode-core/" + core.BUNDLE["version"] + "/" + name] = mapped
    for file in sorted(source.glob("*.html")):
        text = file.read_text().replace("<div data-cli-account></div>", account_control)
        text = core.inject(text, "cli")
        if file.name.startswith("frame-"):
            # Sandboxed fictional frames have an opaque origin and inline-only CSP.
            # Embed Core at build time rather than granting the frame network access.
            import base64, html

            bundle = core.BUNDLE
            entries = bundle["entrypoints"]
            text = re.sub(
                r'<script[^>]+src="/kagnode-core/[^"]+"[^>]*></script>', "", text
            )
            text = re.sub(r'<link[^>]+href="/kagnode-core/[^"]+"[^>]*>', "", text)
            css = base64.b64decode(bundle["files"][entries["style"]]["data"]).decode()
            js = (
                base64.b64decode(bundle["files"][entries["theme"]]["data"]).decode()
                + "\n"
                + base64.b64decode(bundle["files"][entries["script"]]["data"]).decode()
            )
            mark = "data:image/svg+xml;base64," + bundle["files"]["mark.svg"]["data"]

            def frame_config(match):
                context = json.loads(html.unescape(match[1]))
                context["mark"] = mark
                return (
                    '<meta name="kagnode-core" content="'
                    + html.escape(json.dumps(context), quote=True)
                    + '">'
                )

            text = re.sub(
                r'<meta name="kagnode-core" content="([^"]*)">', frame_config, text
            )
            text = text.replace("</head>", "<style>" + css + "</style></head>").replace(
                "</body>", "<script>" + js + "</script></body>"
            )
        for old, new in manifest.items():
            if old.startswith("/kagnode-core/"):
                continue
            text = text.replace('"' + old + '"', '"' + new + '"')

        def inline(match):
            tag, attributes, code = match.groups()
            suffix = ".js" if tag == "script" else ".css"
            if (
                not code.strip()
                or tag == "script"
                and re.search(
                    r"type=[\"\'](?:application/[^\"\']*json|importmap)", attributes
                )
            ):
                return match.group(0)
            out = subprocess.run(
                [
                    os.environ.get("ESBUILD", "esbuild"),
                    "--minify",
                    "--target=es2020",
                    "--charset=utf8",
                    "--loader=" + suffix[1:],
                ],
                input=code,
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            return "<" + tag + attributes + ">" + out + "</" + tag + ">"

        text = re.sub(r"<(script|style)([^>]*)>(.*?)</\1>", inline, text, flags=re.S)
        (built / file.name).write_text(re.sub(r">\s+<", "><", text))
        manifest["/" + file.name] = "/built/" + file.name
for file in built.iterdir():
    if "/built/" + file.name not in manifest.values():
        file.unlink()
(source / "ui-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Built", len(manifest), "minified demo assets and pages without source maps.")
