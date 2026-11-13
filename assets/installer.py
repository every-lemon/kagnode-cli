"""Invoke fixed project-owned installers from an installed, verified release."""

from __future__ import annotations
import hashlib
import os
from pathlib import Path
import secrets
import signal
import threading
import stat
import subprocess
import sys
import tempfile
from installer_protocol import canonical, plan_digest, ProtocolError, load_json


def private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or info.st_uid != os.geteuid()
            or info.st_size > 65536
        ):
            raise ProtocolError(
                "Configuration/review file must be a private regular file owned by current user"
            )
        return load_json(os.read(fd, 65537))
    finally:
        os.close(fd)


def adapter_path(manager, name, path):
    from ecosystem import read

    state = read(path / "state.json", {})
    manager.require_recovered(path, state, allow_setup_recovery=True)
    current = path / "current"
    if not current.is_symlink():
        raise ProtocolError("Install a verified source release first")
    release = current.resolve(strict=True)
    if not release.is_relative_to(path / "releases"):
        raise ProtocolError("Installer source is outside verified releases")
    adapter = release / "scripts/kagnode-installer.py"
    if not adapter.is_file() or adapter.is_symlink():
        raise ProtocolError(
            "This release has no typed installer. Update to a release advertising installer schema 1; no setup was performed"
        )
    for entry in [release, *adapter.relative_to(release).parents]:
        if not entry.is_absolute():
            entry = release / entry
        if entry.is_symlink():
            raise ProtocolError("Installer paths must not contain symlinks")
    info = adapter.stat()
    if manager.require_root and (info.st_uid != 0 or info.st_mode & 0o022):
        raise ProtocolError(
            "Installer code must be protected from local application accounts"
        )
    return adapter


def invoke(adapter, action, request):
    with tempfile.TemporaryDirectory(prefix="kagnode-setup-") as temporary:
        folder = Path(temporary)
        folder.chmod(0o700)
        incoming, outgoing = folder / "request.json", folder / "result.json"
        incoming.write_bytes(canonical(request))
        incoming.chmod(0o600)
        # Only the reviewed project interface is executable; no shell, hooks,
        # command supplied by configuration, or fallback install guesses.
        command = [
            sys.executable,
            str(adapter),
            action,
            "--request",
            str(incoming),
            "--output",
            str(outgoing),
        ]
        child = subprocess.Popen(command, stdin=sys.stdin)
        handlers = {}

        def interrupted(*_):
            raise InterruptedError("Installer operation cancelled")

        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                handlers[sig] = signal.signal(sig, interrupted)
        try:
            code = child.wait(timeout=1800 if action in ("apply", "recover") else 120)
            if code:
                raise ProtocolError(
                    "The project installer failed; inspect its private recovery log"
                )
        except (BaseException,) as error:
            # Keep the application/native locks until the owning wrapper has
            # finished its cancellation cleanup and all direct children reap.
            for sig in handlers:
                signal.signal(sig, signal.SIG_IGN)
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            if isinstance(
                error, (InterruptedError, KeyboardInterrupt, subprocess.TimeoutExpired)
            ):
                raise ProtocolError(
                    "Installer cancelled or timed out; review recovery before retrying"
                ) from None
            raise
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        result = private_json(outgoing)
        if (
            not isinstance(result, dict)
            or result.get("schema") != 1
            or result.get("project") != request["project"]
            or result.get("operation_id") != request["operation_id"]
        ):
            raise ProtocolError(
                "Installer returned an invalid or unrelated operation result"
            )
        return result


def operate(
    manager,
    name,
    action,
    mode="application",
    configuration=None,
    review_file=None,
    save_plan=None,
    recovery=False,
):
    name, path = manager.project(name)
    if name in ("core", "cli"):
        raise ProtocolError(
            "Use the dedicated signed Core manager, CLI activation, no native service installer applies"
        )
    config = private_json(configuration) if configuration else {}
    if not isinstance(config, dict):
        raise ProtocolError("Configuration must be a JSON object")
    with manager.lock(name):
        adapter = adapter_path(manager, name, path)
        from ecosystem import read

        pending = read(path / "setup-operation.json", {})
        if action == "apply" and pending.get("state") in ("running", "needs_recovery"):
            raise ProtocolError(
                "Previous setup needs reviewed recovery before another apply"
            )
        request = {
            "schema": 1,
            "project": name,
            "operation_id": secrets.token_hex(16),
            "root": str(manager.root),
            "mode": mode,
            "configuration": config,
            "intent": "recover" if recovery else "setup",
        }
        if recovery:
            original = pending.get("request")
            if pending.get("state") not in (
                "running",
                "needs_recovery",
            ) or not isinstance(original, dict):
                raise ProtocolError(
                    "No operation-owned incomplete setup is available for recovery"
                )
            request = {
                **original,
                "intent": "recover",
                "configuration": config
                if configuration
                else original.get("configuration", {}),
            }
            request.pop("review", None)
        identity = {
            "path": str(adapter),
            "sha256": hashlib.sha256(adapter.read_bytes()).hexdigest(),
        }
        if action in ("apply", "recover"):
            if not review_file:
                raise ProtocolError("An explicitly reviewed --plan file is required")
            approved = private_json(review_file)
            if approved.get("request", {}).get("project") != name or approved.get(
                "request", {}
            ).get("root") != str(manager.root):
                raise ProtocolError("Review belongs to another project/root")
            if approved.get("adapter") != identity:
                raise ProtocolError(
                    "Installer source changed; review the new release plan"
                )
            request = approved["request"]
            if (action == "recover") != (request.get("intent", "setup") == "recover"):
                raise ProtocolError(
                    "Review intent does not match setup/recovery; create a fresh plan with --recover"
                )
            plan = approved.get("plan", {})
            if plan.get("plan_sha256") != plan_digest(plan):
                raise ProtocolError("Review plan checksum is invalid")
            request["review"] = {"plan_sha256": plan["plan_sha256"]}
            # Fresh plan immediately before apply rejects configuration/platform
            # drift. Project adapter repeats this validation at its boundary.
            fresh = invoke(adapter, "plan", request)
            if plan_digest(fresh) != plan["plan_sha256"]:
                raise ProtocolError("The installation plan changed; review it again")
            if (
                not fresh.get("supported")
                or fresh.get("ready_for_apply") is False
                or (fresh.get("manual_steps") and not fresh.get("interactive"))
            ):
                raise ProtocolError(
                    "Unsupported capability or remaining manual steps prevent automatic setup"
                )
            if fresh.get("interactive") and not (
                sys.stdin.isatty() and sys.stdout.isatty()
            ):
                raise ProtocolError(
                    "This project needs a real terminal. Run sudo kagnode setup for the reviewed interactive installer"
                )
            journal = path / "setup-operation.json"
            manager.operation(path, "preparing", "Project-owned setup in progress")
            from ecosystem import atomic

            atomic(
                journal,
                {
                    "state": "running",
                    "request": request,
                    "plan_sha256": plan["plan_sha256"],
                },
            )
            try:
                result = invoke(adapter, action, request)
                if (
                    result.get("state") != "completed"
                    or result.get("health", {}).get("ok") is not True
                ):
                    raise ProtocolError(
                        "Setup did not establish healthy operation; use reviewed recovery"
                    )
                health = invoke(adapter, "health", request)
                if health.get("health", {}).get("ok") is not True:
                    raise ProtocolError(
                        "Post-setup health check failed; use reviewed recovery"
                    )
                atomic(
                    journal, {"state": "completed", "result": result, "health": health}
                )
                manager.operation(
                    path,
                    "complete",
                    "Project-owned setup completed and health verified",
                )
            except Exception:
                atomic(
                    journal,
                    {
                        "state": "needs_recovery",
                        "request": request,
                        "plan_sha256": plan["plan_sha256"],
                    },
                )
                manager.operation(
                    path, "failed", "Project-owned setup needs reviewed recovery"
                )
                raise
            return result
        result = invoke(adapter, action, request)
        if action == "plan":
            if result.get("plan_sha256") != plan_digest(result):
                raise ProtocolError("Installer plan checksum is invalid")
            if save_plan:
                from installer_protocol import write_result

                write_result(
                    save_plan, {"request": request, "plan": result, "adapter": identity}
                )
        return result
