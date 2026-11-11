"""Actual compiled CLI browser shell, fictional profile issuer and private XDG data."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
name = {"value": "CLI profile fixture with a deliberately long display name"}


class Issuer(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path != "/api/cli/me":
            self.send_error(404)
            return
        raw = json.dumps(
            {"id": "fictional-cli-user", "name": name["value"], "photo": ""}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)


server = ThreadingHTTPServer(("127.0.0.1", 0), Issuer)
threading.Thread(target=server.serve_forever, daemon=True).start()
process = None
try:
    with tempfile.TemporaryDirectory(prefix="kagnode-cli-browser-") as temporary:
        scratch = Path(temporary)
        binary = scratch / "kagnode"
        subprocess.run(["go", "build", "-o", str(binary), "."], cwd=ROOT, check=True)
        env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(scratch / "config"),
            "XDG_DATA_HOME": str(scratch / "data"),
            "KAGNODE_CORE_ROOT": str(scratch / "core"),
        }
        account = scratch / "config/kagnode/cli/account.json"
        account.parent.mkdir(parents=True, mode=0o700)
        account.write_text(
            json.dumps(
                {
                    "base": f"http://127.0.0.1:{server.server_port}",
                    "access_token": "fictional-fixture",
                    "refresh_token": "fictional-fixture",
                    "expires": int(time.time()) + 3600,
                    "name": name["value"],
                    "profile_updated": int(time.time()),
                    "id": "fictional-cli-user",
                    "offline_demo_access": True,
                }
            )
        )
        account.chmod(0o600)
        subprocess.run(
            [str(binary), "demo", "install"], env=env, check=True, capture_output=True
        )
        process = subprocess.Popen(
            [str(binary), "demo", "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        state = scratch / "data/kagnode/cli/server.json"
        for _ in range(100):
            if state.exists():
                break
            if process.poll() is not None:
                raise RuntimeError("Owned CLI fixture exited")
            time.sleep(0.1)
        info = json.loads(state.read_text())
        base = info["url"]
        with sync_playwright() as playwright:
            engine = os.environ.get("KAGNODE_BROWSER_ENGINE", "chromium")
            executable = os.environ.get("KAGNODE_BROWSER_EXECUTABLE")
            browser = getattr(playwright, engine).launch(
                **({"executable_path": executable} if executable else {})
            )
            for width in [390, 820, 1440]:
                name["value"] = (
                    "CLI profile fixture with a deliberately long display name"
                )
                cached = json.loads(account.read_text())
                cached.update(name=name["value"], profile_updated=int(time.time()))
                account.write_text(json.dumps(cached))
                account.chmod(0o600)
                context = browser.new_context(
                    viewport={"width": width, "height": 1000}, reduced_motion="reduce"
                )
                page = context.new_page()
                failures = []
                page.on("pageerror", lambda error: failures.append(str(error)))

                def request(route):
                    if route.request.url.startswith(base + "/"):
                        return route.continue_()
                    failures.append("Unexpected external request")
                    route.abort()

                context.route("**/*", request)
                response = page.goto(base + "/?key=" + info["key"])
                assert response.status == 200
                page.wait_for_function(
                    "() => document.documentElement.dataset.coreReady==='true' && !!window.KagNodeAccounts"
                )
                assert page.evaluate("KagNodeCore.version") == "5.0.0"
                page.wait_for_function(
                    "() => document.querySelector('#account-menu [data-kn-account-name]')?.textContent.includes('deliberately')"
                )
                controls = page.locator("[data-core-account-trigger]")
                assert controls.count() == 1
                trigger = controls.first
                assert trigger.evaluate("n=>n.getBoundingClientRect().width") <= 40
                assert len(trigger.inner_text().strip()) <= 4
                trigger.click()
                menu = page.locator("#account-menu")
                menu.wait_for(state="visible")
                assert (
                    menu.locator("[data-kn-account-name]").inner_text() == name["value"]
                )
                assert menu.evaluate(
                    "n=>{const b=n.getBoundingClientRect();return b.x>=0&&b.right<=innerWidth}"
                )
                page.keyboard.press("Escape")
                assert menu.is_hidden()
                assert trigger.evaluate("n=>document.activeElement===n")
                trigger.click()
                name["value"] = "Updated synced CLI fixture"
                page.evaluate(
                    """async()=>{const r=await fetch('/api/kagnode-account',{method:'POST',headers:{'Content-Type':'application/json','X-KagNode-Action':'profile'},body:JSON.stringify({action:'refresh'})});if(!r.ok)throw Error('Fixture refresh failed');await KagNodeAccounts.refresh()}"""
                )
                page.wait_for_function(
                    "() => document.querySelector('#account-menu [data-kn-account-name]').textContent==='Updated synced CLI fixture'"
                )
                page.mouse.click(2, 800)
                menu.wait_for(state="hidden")
                for path in ["/demos/vps", "/demos/console", "/demos/workspace/q1"]:
                    assert page.goto(base + path).status == 200
                    page.wait_for_function("() => !!window.KagNodeCore")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth+1"
                    )
                assert not failures, failures
                context.close()
            browser.close()
            print(
                json.dumps(
                    {
                        "engine": engine,
                        "core": "5.0.0",
                        "layouts": [390, 820, 1440],
                        "compiledCli": True,
                        "profileRefresh": True,
                        "canonicalAccountMenu": True,
                        "externalRequests": 0,
                        "fictionalRoutesPerLayout": 3,
                    }
                )
            )
finally:
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    server.shutdown()
    server.server_close()
