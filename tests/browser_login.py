"""Native CLI browser-return protocol; fictional local issuer, no real accounts."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit, urlencode
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class Issuer(BaseHTTPRequestHandler):
    attempt = {}
    denied = False
    token_used = False
    cancel_count = 0

    def log_message(self, *args):
        pass

    def respond(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/oauth/authorize?"):
            raw = b'<form action="/approve" method="post"><button>Approve sign-in</button></form>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.startswith("/api/v1/account-sync/profile?"):
            assert parse_qs(urlsplit(self.path).query)["client_id"] == [
                "kagnode-cli-profile"
            ]
            assert self.headers.get("Authorization") == "Bearer access"
            self.respond({"subject": "fixture-subject", "name": "Fixture display"})
        else:
            self.send_error(404)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/approve":
            query = {
                "state": self.attempt["state"],
                "iss": self.origin,
                ("error" if self.denied else "code"): (
                    "access_denied" if self.denied else "single-code"
                ),
            }
            self.send_response(303)
            self.send_header(
                "Location", self.attempt["redirect_uri"] + "?" + urlencode(query)
            )
            self.end_headers()
            return
        data = json.loads(raw)
        if self.path.endswith("/browser/start"):
            type(self).attempt = data
            assert (
                data["client_id"] == "kagnode-cli-profile"
                and data["code_challenge_method"] == "S256"
            )
            self.respond(
                {
                    "request_id": "fixture",
                    "authorization_uri": self.origin
                    + "/oauth/authorize?request=fixture",
                    "expires_in": 600,
                }
            )
        elif self.path.endswith("/token"):
            assert not self.token_used and data["code"] == "single-code"
            assert (
                base64.urlsafe_b64encode(
                    hashlib.sha256(data["code_verifier"].encode()).digest()
                )
                .decode()
                .rstrip("=")
                == self.attempt["code_challenge"]
            )
            type(self).token_used = True
            now = int(time.time())
            self.respond(
                {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": 300,
                    "authorization": {
                        "issuer": self.origin,
                        "subject": "fixture-subject",
                        "client_id": "kagnode-cli-profile",
                        "installation": self.attempt["installation"],
                        "purpose": "sign_in",
                        "nonce": self.attempt["nonce"],
                        "issued_at": now,
                        "approved_at": now,
                        "auth_time": now,
                        "expires_at": now + 120,
                    },
                }
            )
        elif self.path.endswith("/browser/cancel"):
            type(self).cancel_count += 1
            self.respond({})
        else:
            self.send_error(404)


with tempfile.TemporaryDirectory(prefix="kagnode-browser-login-") as temporary:
    folder = Path(temporary)
    binary = folder / "kagnode"
    subprocess.run(["go", "build", "-o", str(binary), "."], cwd=ROOT, check=True)
    opener = folder / "xdg-open"
    opener.write_text(
        '#!/usr/bin/python3\nimport os,sys\nfrom pathlib import Path\nPath(os.environ["KAGNODE_TEST_URL"]).write_text(sys.argv[1])\n'
    )
    opener.chmod(0o755)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Issuer)
    Issuer.origin = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as playwright:
        engine = os.environ.get("KAGNODE_BROWSER_ENGINE", "chromium")
        options = {}
        if engine == "chromium" and os.environ.get("CHROME"):
            options["executable_path"] = os.environ["CHROME"]
        if engine == "webkit" and os.environ.get("WEBKIT"):
            options["executable_path"] = os.environ["WEBKIT"]
        browser = getattr(playwright, engine).launch(**options)
        for denied in (False, True):
            Issuer.denied = denied
            Issuer.token_used = False
            urlfile = folder / "url"
            urlfile.unlink(missing_ok=True)
            config = folder / ("denied" if denied else "success")
            config.mkdir()
            env = {
                **os.environ,
                "XDG_CONFIG_HOME": str(config),
                "PATH": str(folder) + os.pathsep + os.environ["PATH"],
                "KAGNODE_TEST_URL": str(urlfile),
            }
            process = subprocess.Popen(
                [str(binary), "login", "--server", Issuer.origin],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 10
                while not urlfile.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert urlfile.exists(), "browser was not opened"
                page = browser.new_page()
                page.goto(urlfile.read_text())
                page.get_by_role("button", name="Approve sign-in").click()
                page.wait_for_url("**/auth/kagnode/complete")
                assert urlsplit(page.url).query == ""
                out, err = process.communicate(timeout=10)
                assert (process.returncode == 0) == (not denied), (out, err)
                account = config / "kagnode/cli/account.json"
                assert account.exists() == (not denied)
                if account.exists():
                    value = json.loads(account.read_text())
                    assert (
                        value["id"] == "fixture-subject"
                        and value["protocol"] == "account-sync"
                    )
                    assert account.stat().st_mode & 0o777 == 0o600
                assert Issuer.token_used == (not denied)
                assert "single-code" not in out + err and "refresh" not in out + err
                page.close()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        before_cancel = Issuer.cancel_count
        urlfile = folder / "cancel-url"
        config = folder / "cancelled"
        config.mkdir()
        env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(config),
            "PATH": str(folder) + os.pathsep + os.environ["PATH"],
            "KAGNODE_TEST_URL": str(urlfile),
        }
        process = subprocess.Popen(
            [str(binary), "login", "--server", Issuer.origin],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 10
            while not urlfile.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert urlfile.exists(), "cancelled browser initiation missing"
            process.terminate()
            out, err = process.communicate(timeout=10)
            assert process.returncode != 0 and "cancelled" in err
            assert Issuer.cancel_count == before_cancel + 1
            assert not (config / "kagnode/cli/account.json").exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        browser.close()
    server.shutdown()
    server.server_close()
print(
    "PASS native CLI browser PKCE return: success, denial, cancellation, private credential persistence; "
    + engine
)
