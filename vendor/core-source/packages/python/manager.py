"""Local, signed, UI-only Core patch manager. No application hooks or restarts."""

from __future__ import annotations
import argparse
import base64
import contextlib
import fcntl
import hashlib
import http.server
import json
import logging
import os
from pathlib import Path, PurePosixPath
import pwd
import random
import re
import shutil
import signal
import socket
import socketserver
import stat
import struct
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request

PUBLIC_KEY = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAuJzR4gg2djgIrWTepTgtJsPnlbvhUYz/mwO7ubtl8l4=\n-----END PUBLIC KEY-----\n"
REPOSITORY = "every-lemon/kagnode-core"
LIMIT = 64 * 1024 * 1024


class OperationBusy(ValueError):
    """A manual or background Core mutation already holds the operation lock."""


@contextlib.contextmanager
def _lock_descriptor(path):
    """Open a stable regular control without waiting on a corrupted FIFO."""

    def validate(info):
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o022
        ):
            raise ValueError("Unsafe Core lock")

    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
    if before is not None:
        validate(before)
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        0o600,
    )
    try:
        current = os.fstat(descriptor)
        validate(current)
        if before is not None and (before.st_dev, before.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise ValueError("Core lock changed while opening")
        yield descriptor
    finally:
        os.close(descriptor)


def version(value):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise ValueError("Only stable Core patch versions can be activated")
    return tuple(map(int, match.groups()))


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".core-", delete=False, mode="w"
    ) as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
        name = stream.name
    os.chmod(name, 0o644)
    os.replace(name, path)


def read(path, default=None):
    try:
        if path.is_symlink():
            raise ValueError("Core state cannot be a symlink")
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


class TrustedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.hostname
            not in {
                "api.github.com",
                "github.com",
                "release-assets.githubusercontent.com",
                "objects.githubusercontent.com",
            }
        ):
            raise ValueError("Untrusted Core download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, maximum=2_000_000):
    p = urllib.parse.urlsplit(url)
    if (
        p.scheme != "https"
        or p.username
        or p.password
        or p.port not in (None, 443)
        or p.hostname
        not in {
            "api.github.com",
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }
    ):
        raise ValueError("Core downloads must use approved GitHub HTTPS hosts")
    if p.hostname == "github.com" and not p.path.startswith(
        "/" + REPOSITORY + "/releases/"
    ):
        raise ValueError("Core download has the wrong repository")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KagNode-Core-Manager/1",
            "Accept": (
                "application/vnd.github+json"
                if p.hostname == "api.github.com"
                else "application/octet-stream"
            ),
        },
    )
    with urllib.request.build_opener(TrustedRedirect()).open(
        request, timeout=30
    ) as response:
        final = urllib.parse.urlsplit(response.url)
        if final.scheme != "https" or final.hostname not in {
            "api.github.com",
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }:
            raise ValueError("Untrusted Core download redirect")
        data = response.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("Core download exceeds its size limit")
        return data


def verify_signature(data, signature, public_key=PUBLIC_KEY):
    with tempfile.TemporaryDirectory(prefix="kagnode-core-signature-") as directory:
        d = Path(directory)
        (d / "key.pem").write_text(public_key)
        (d / "manifest").write_bytes(data)
        (d / "signature").write_bytes(signature)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(d / "key.pem"),
                "-rawin",
                "-in",
                str(d / "manifest"),
                "-sigfile",
                str(d / "signature"),
            ],
            capture_output=True,
            timeout=10,
        )
        if result.returncode:
            raise ValueError("Core release signature verification failed")


def validate_summary(value):
    if not isinstance(value, dict) or set(value) != {"title", "items"}:
        raise ValueError("Invalid public Core summary")

    def text(item, maximum):
        return (
            isinstance(item, str)
            and 1 <= len(item) <= maximum
            and not any(ord(c) < 32 or c in "<>" for c in item)
        )

    if (
        not text(value["title"], 120)
        or not isinstance(value["items"], list)
        or not 1 <= len(value["items"]) <= 8
        or not all(text(item, 240) for item in value["items"])
    ):
        raise ValueError("Invalid public Core summary")
    return {"title": value["title"], "items": list(value["items"])}


def validate_manifest(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid Core manifest")
    version(value.get("version"))
    if (
        value.get("schema") != 1
        or value.get("repository") != REPOSITORY
        or value.get("kind") != "ui"
        or value.get("ui_api") != 1
        or value.get("adapter_api") != 1
    ):
        raise ValueError(
            "Core UI contract is incompatible; update the application with review"
        )
    if not re.fullmatch(r"[a-f0-9]{40}", value.get("source_commit", "")):
        raise ValueError("Core source provenance is invalid")
    files = value.get("files")
    if not isinstance(files, dict) or not 1 <= len(files) <= 100:
        raise ValueError("Invalid Core asset inventory")
    for name, item in files.items():
        if not isinstance(item, dict):
            raise ValueError("Invalid Core asset metadata")
        if (
            not re.fullmatch(r"[a-zA-Z0-9_.-]+\.(js|css|svg|woff2)", name)
            or not re.fullmatch(r"[a-f0-9]{64}", item.get("sha256", ""))
            or type(item.get("size")) is not int
            or not 0 < item["size"] <= 16 * 1024 * 1024
        ):
            raise ValueError("Invalid Core asset")
    if sum(v["size"] for v in files.values()) > LIMIT:
        raise ValueError("Core assets exceed size limit")
    if any(name not in files for name in value.get("entrypoints", {}).values()) or set(
        value.get("entrypoints", {})
    ) != {"theme", "script", "style"}:
        raise ValueError("Core entrypoints are incomplete")
    if "user_summary" in value:
        validate_summary(value["user_summary"])
    return value


def application_lock(path, app):
    """Read reviewed application metadata; it never supplies download locations."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Application Core declaration cannot be a symlink")
    with os.fdopen(
        os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb"
    ) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Application Core declaration must be a regular file")
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError("Application Core declaration is too large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Application Core declaration must be an object")
    baseline = value.get("baseline")
    parsed = version(baseline)
    version(value.get("adapter"))
    if (
        type(value.get("schema")) is not int
        or value["schema"] != 1
        or value.get("repository") != REPOSITORY
        or value.get("application", app) != app
        or type(value.get("ui_api")) is not int
        or value["ui_api"] != 1
        or value.get("patch_range") != f"{parsed[0]}.{parsed[1]}.x"
        or type(value.get("automatic_ui_patches")) is not bool
        or value.get("backend_updates") != "reviewed"
        or not re.fullmatch(r"[a-f0-9]{40}", str(value.get("source_commit", "")))
        or not re.fullmatch(
            r"[a-f0-9]{64}", str(value.get("fallback_manifest_sha256", ""))
        )
    ):
        raise ValueError("Invalid or incompatible application Core declaration")
    return value, hashlib.sha256(raw).hexdigest()


class Manager:
    def __init__(self, root="/srv/kagnode/core", trusted=True):
        self.root = Path(root)
        self.trusted = trusted
        if not self.root.is_absolute() or any(c in str(self.root) for c in "\n\r\x00"):
            raise ValueError("Core root must be an absolute path")
        if trusted:
            for p in [self.root, *self.root.parents]:
                if p.is_symlink() or (
                    p.exists() and (p.stat().st_uid != 0 or p.stat().st_mode & 0o022)
                ):
                    raise ValueError(
                        "Core root and ancestors must be protected and root-owned"
                    )

    def app(self, name):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
            raise ValueError("Invalid application")
        path = self.root / "apps" / name
        if path.is_symlink():
            raise ValueError("Application state cannot be a symlink")
        return path

    def ensure(self):
        if self.trusted and os.geteuid() != 0:
            raise ValueError("Use sudo for Core management")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o755)
        self.root.chmod(0o755)
        for child in ("apps", "releases", "run"):
            p = self.root / child
            if p.is_symlink():
                raise ValueError("Core managed directories cannot be symlinks")
            p.mkdir(exist_ok=True, mode=0o755)
            p.chmod(0o755)

    @contextlib.contextmanager
    def lock(self):
        self.ensure()
        with _lock_descriptor(self.root / ".operation.lock") as descriptor:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OperationBusy("Another Core operation is running")
            yield

    def bind(self, name, username, baseline=None, lock_file=None):
        with self.lock():
            self.app(name)
            if (baseline is None) == (lock_file is None):
                raise ValueError(
                    "Choose an explicit baseline or application declaration"
                )
            declaration, declaration_sha = (
                application_lock(lock_file, name)
                if lock_file is not None
                else (None, None)
            )
            baseline = declaration["baseline"] if declaration else baseline
            version(baseline)
            account = pwd.getpwnam(username)
            path = self.app(name)
            if (path / "state.json").exists():
                raise ValueError(
                    "Existing Core binding retained; review an adopt operation for application upgrades"
                )
            path.mkdir(exist_ok=True, mode=0o755)
            path.chmod(0o755)
            state = {
                "version": baseline,
                "baseline": baseline,
                "adapter": declaration["adapter"] if declaration else baseline,
                "automatic": declaration["automatic_ui_patches"]
                if declaration
                else True,
                "uid": account.pw_uid,
                "gid": account.pw_gid,
                "previous": None,
                "last_check": 0,
            }
            if declaration:
                state.update(
                    declaration_sha256=declaration_sha,
                    source_commit=declaration["source_commit"],
                    fallback_manifest_sha256=declaration["fallback_manifest_sha256"],
                )
            atomic(path / "state.json", state)
            return self.status(name)

    def state(self, name):
        value = read(self.app(name) / "state.json")
        if not value:
            raise ValueError("Bind this application before using Core management")
        version(value["version"])
        return value

    def status(self, name):
        # The lock, not a timestamp or a reusable PID, proves whether a writer
        # is still alive. Nested status calls inside a mutation simply skip.
        if (not self.trusted or os.geteuid() == 0) and read(
            self.app(name) / "operation.json", {}
        ).get("phase") == "downloading":
            try:
                with self.lock():
                    self._recover_operation(name)
            except OperationBusy:
                pass
        state = self.state(name)
        result = {
            "enabled": True,
            **{k: v for k, v in state.items() if k not in ("uid", "gid")},
            "summaries": state.get("summaries", True),
            "capabilities": {"update_summaries": True, "automatic_ui_patches": True},
            "candidate": read(self.app(name) / "candidate.json"),
            "operation": read(self.app(name) / "operation.json", {}),
        }
        if result["operation"].get("phase") == "interrupted":
            result["message"] = result["operation"]["message"]
        elif (
            self.trusted
            and os.geteuid() != 0
            and result["operation"].get("phase") == "downloading"
        ):
            result["operation"] = {
                **result["operation"],
                "phase": "verification-required",
                "message": "Run privileged Core status to verify whether this recorded operation is still active.",
            }
        return result

    def _cleanup_staging(self):
        """Only remove our marked scratch while holding the global lock."""
        for path in (self.root / "releases").glob(".stage-*"):
            marker = path / ".kagnode-stage.json"
            if path.is_symlink() or not path.is_dir() or marker.is_symlink():
                continue
            try:
                owned = read(marker)
            except (OSError, ValueError):
                continue
            if owned == {"schema": 1, "kind": "ui-cache", "root": str(self.root)}:
                shutil.rmtree(path)

    def _recover_operation(self, name):
        """Reconcile an abandoned journal; never activate or rewrite UI state."""
        operation = self.app(name) / "operation.json"
        pending = read(operation, {})
        if pending.get("phase") != "downloading":
            return
        state = self.state(name)
        complete = False
        adoption_committed = pending.get("action") != "adopt" or (
            state.get("baseline") == pending.get("version")
            and state.get("declaration_sha256") == pending.get("declaration_sha256")
        )
        if pending.get("version") == state["version"] and adoption_committed:
            try:
                self._cached_version(state["version"])
                complete = True
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                pass
        self._cleanup_staging()
        if complete:
            candidate_path = self.app(name) / "candidate.json"
            candidate = read(candidate_path)
            if candidate and candidate.get("version") == state["version"]:
                atomic(candidate_path, {**candidate, "changed": False})
        atomic(
            operation,
            {
                **pending,
                "phase": "complete" if complete else "interrupted",
                "recovered": True,
                "recovered_at": int(time.time()),
                "message": "Current Core UI verified after an interrupted operation. Services were not restarted."
                if complete
                else "Core update was interrupted. Current UI is retained; check for updates and retry, or repeat the reviewed baseline adoption.",
            },
        )

    def recover_pending(self):
        try:
            with self.lock():
                for path in (self.root / "apps").glob("*/state.json"):
                    self._recover_operation(path.parent.name)
                self._cleanup_staging()
        except OperationBusy:
            # An independently started updater owns its journal and scratch.
            pass

    def check(self, name):
        with self.lock():
            return self._check(name)

    def _check(self, name):
        self._recover_operation(name)
        state = self.state(name)
        releases = json.loads(
            fetch(
                "https://api.github.com/repos/" + REPOSITORY + "/releases?per_page=50"
            )
        )
        choices = []
        for release in releases:
            if release.get("draft") or release.get("prerelease"):
                continue
            try:
                tag = release["tag_name"].removeprefix("v")
                parsed = version(tag)
            except (ValueError, KeyError):
                continue
            if parsed[:2] != version(state["baseline"])[:2] or parsed < version(
                state["version"]
            ):
                continue
            assets = {item["name"]: item for item in release.get("assets", [])}
            if not {"core-manifest.json", "core-manifest.sig"} <= assets.keys():
                continue
            choices.append((parsed, release))
        candidate = None
        for _, release in sorted(choices, key=lambda x: x[0], reverse=True):
            candidate = self._release_candidate(release)
            candidate["changed"] = candidate["version"] != state["version"]
            break
        atomic(self.app(name) / "candidate.json", candidate)
        atomic(
            self.app(name) / "state.json",
            {**state, "last_check": int(time.time()), "last_error": ""},
        )
        return self.status(name)

    def _release_candidate(self, release):
        if release.get("draft") or release.get("prerelease"):
            raise ValueError("Only published stable Core releases can be reviewed")
        assets = {item["name"]: item for item in release.get("assets", [])}
        if not {"core-manifest.json", "core-manifest.sig"} <= assets.keys():
            raise ValueError("Core release has no signed manifest")
        raw = fetch(assets["core-manifest.json"]["browser_download_url"])
        signature = fetch(assets["core-manifest.sig"]["browser_download_url"], 1024)
        verify_signature(raw, signature)
        manifest = validate_manifest(json.loads(raw))
        if release["tag_name"] != "v" + manifest["version"]:
            raise ValueError("Core tag and manifest differ")
        archive = manifest.get("archive", {})
        if (
            archive.get("name") not in assets
            or not re.fullmatch(r"[a-f0-9]{64}", archive.get("sha256", ""))
            or type(archive.get("size")) is not int
            or not 0 < archive["size"] <= LIMIT
        ):
            raise ValueError("Invalid signed Core archive")
        candidate = {
            "version": manifest["version"],
            "release_id": release["id"],
            "manifest": manifest,
            "signature": base64.b64encode(signature).decode(),
            "raw": base64.b64encode(raw).decode(),
            "url": assets[archive["name"]]["browser_download_url"],
            "changed": True,
        }
        return candidate

    def _resolve_version(self, requested):
        version(requested)
        release = json.loads(
            fetch(
                "https://api.github.com/repos/"
                + REPOSITORY
                + "/releases/tags/v"
                + requested
            )
        )
        if release.get("tag_name") != "v" + requested:
            raise ValueError("Core release tag does not match the reviewed baseline")
        return self._release_candidate(release)

    def _cached_version(self, requested):
        version(requested)
        target = self.root / "releases" / requested
        if target.is_symlink():
            raise ValueError("Unsafe Core release directory")
        raw = (target / "core-manifest.json").read_bytes()
        verify_signature(raw, (target / "core-manifest.sig").read_bytes())
        manifest = validate_manifest(json.loads(raw))
        if (
            manifest["version"] != requested
            or read(target / "manifest.json") != manifest
        ):
            raise ValueError("Cached Core manifest does not match its signed version")
        self.validate_cache(target, manifest)
        return manifest

    def _ensure_version(self, requested):
        if (self.root / "releases" / requested).exists():
            return self._cached_version(requested)
        return self._cache(self._resolve_version(requested))

    def install(self, name, release_id=None, *, automatic=False):
        with self.lock():
            status = self._check(name)
            candidate = status["candidate"]
            if not candidate:
                return status
            if release_id is not None and (
                type(release_id) is not int or candidate["release_id"] != release_id
            ):
                raise ValueError("The reviewed Core release changed; check again")
            state = self.state(name)
            if automatic and not state.get("automatic", True):
                raise ValueError("Automatic Core patches are paused")
            if version(candidate["version"])[:2] != version(state["baseline"])[:2]:
                raise ValueError(
                    "Backend or minor/major upgrades require application review"
                )
            operation = self.app(name) / "operation.json"
            atomic(
                operation,
                {
                    "phase": "downloading",
                    "action": "apply",
                    "version": candidate["version"],
                    "at": int(time.time()),
                },
            )
            try:
                self._cache(candidate)
                atomic(
                    self.app(name) / "state.json",
                    {
                        **state,
                        "version": candidate["version"],
                        "previous": state["version"]
                        if candidate["changed"]
                        else state.get("previous"),
                        "last_error": "",
                        "activation": (
                            {
                                "id": hashlib.sha256(
                                    (
                                        name
                                        + ":"
                                        + candidate["version"]
                                        + ":"
                                        + str(time.time_ns())
                                    ).encode()
                                ).hexdigest(),
                                "version": candidate["version"],
                                "automatic": True,
                            }
                            if automatic and candidate["changed"]
                            else None
                        )
                        if candidate["changed"]
                        else state.get("activation"),
                        "updated": int(time.time()),
                    },
                )
                atomic(
                    self.app(name) / "candidate.json", {**candidate, "changed": False}
                )
                atomic(
                    operation,
                    {
                        "phase": "complete",
                        "version": candidate["version"],
                        "at": int(time.time()),
                        "message": "Core UI assets activated. Services were not restarted."
                        if candidate["changed"]
                        else "Current Core UI verified and cached. Active version is unchanged.",
                    },
                )
            except Exception as error:
                atomic(
                    operation,
                    {"phase": "failed", "at": int(time.time()), "message": str(error)},
                )
                raise
            return self.status(name)

    def _cache(self, candidate):
        target = self.root / "releases" / candidate["version"]
        raw = base64.b64decode(candidate["raw"])
        verify_signature(raw, base64.b64decode(candidate["signature"]))
        manifest = validate_manifest(json.loads(raw))
        if manifest["version"] != candidate["version"]:
            raise ValueError("Core candidate and signed manifest differ")
        if target.exists():
            if self._cached_version(candidate["version"]) != manifest:
                raise ValueError(
                    "Cached Core release differs from the reviewed manifest"
                )
        else:
            if shutil.disk_usage(self.root).free < LIMIT * 3:
                raise ValueError("Not enough space for Core staging and rollback")
            data = fetch(candidate["url"], LIMIT)
            expected = manifest["archive"]
            if (
                len(data) != expected["size"]
                or hashlib.sha256(data).hexdigest() != expected["sha256"]
            ):
                raise ValueError("Core archive checksum failed")
            with tempfile.TemporaryDirectory(
                dir=self.root / "releases", prefix=".stage-"
            ) as temp:
                stage = Path(temp)
                atomic(
                    stage / ".kagnode-stage.json",
                    {"schema": 1, "kind": "ui-cache", "root": str(self.root)},
                )
                archive = stage / "download.tar.gz"
                archive.write_bytes(data)
                seen = set()
                with tarfile.open(archive) as bundle:
                    for entry in bundle:
                        name_path = PurePosixPath(entry.name)
                        if (
                            name_path.is_absolute()
                            or ".." in name_path.parts
                            or len(name_path.parts) != 2
                            or name_path.parts[0]
                            != "kagnode-core-" + candidate["version"]
                            or not entry.isfile()
                        ):
                            raise ValueError("Unsafe Core archive path or file type")
                        filename = name_path.name
                        if filename in seen or filename not in manifest["files"]:
                            raise ValueError(
                                "Unexpected or duplicate Core archive entry"
                            )
                        seen.add(filename)
                        expected_file = manifest["files"][filename]
                        if entry.size != expected_file["size"]:
                            raise ValueError("Core file size mismatch")
                        blob = bundle.extractfile(entry).read()
                        if hashlib.sha256(blob).hexdigest() != expected_file["sha256"]:
                            raise ValueError("Core asset checksum failed")
                        (stage / filename).write_bytes(blob)
                        (stage / filename).chmod(0o644)
                if seen != set(manifest["files"]):
                    raise ValueError("Core archive is incomplete")
                archive.unlink()
                atomic(stage / "manifest.json", manifest)
                (stage / "core-manifest.json").write_bytes(raw)
                (stage / "core-manifest.sig").write_bytes(
                    base64.b64decode(candidate["signature"])
                )
                stage.chmod(0o755)
                (stage / ".kagnode-stage.json").unlink()
                os.rename(stage, target)
        self.validate_cache(target, manifest)
        return manifest

    def validate_cache(self, target, manifest):
        if target.is_symlink():
            raise ValueError("Unsafe Core release directory")
        for filename, item in manifest["files"].items():
            path = target / filename
            if (
                path.is_symlink()
                or not path.is_file()
                or path.stat().st_size != item["size"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
            ):
                raise ValueError("Installed Core asset integrity failed")

    def summary(self, name):
        with self.lock():
            return self._summary(name)

    def _summary(self, name):
        state = self.state(name)
        event = state.get("activation")
        empty = {"available": True, "notice": None}
        if (
            not state.get("summaries", True)
            or not isinstance(event, dict)
            or event.get("automatic") is not True
            or event.get("version") != state["version"]
            or not re.fullmatch(r"[a-f0-9]{64}", str(event.get("id", "")))
        ):
            return empty
        operation = read(self.app(name) / "operation.json", {})
        if (
            operation.get("phase") != "complete"
            or operation.get("version") != state["version"]
        ):
            return empty
        manifest = self._cached_version(state["version"])
        if "user_summary" not in manifest:
            return empty
        return {
            "available": True,
            "notice": {
                "id": event["id"],
                "version": state["version"],
                **validate_summary(manifest["user_summary"]),
            },
        }

    def policy(self, name, automatic=None, summaries=None):
        if automatic is None and summaries is None:
            raise ValueError("Choose an update policy")
        updates = {}
        for key, value in (("automatic", automatic), ("summaries", summaries)):
            if value is not None:
                if type(value) is not bool:
                    raise ValueError("Core policies must be true or false")
                updates[key] = value
        with self.lock():
            atomic(self.app(name) / "state.json", {**self.state(name), **updates})
        return self.status(name)

    def adopt(self, name, lock_file, expected_baseline):
        """Root-reviewed application upgrade; deliberately unavailable over sockets."""
        with self.lock():
            self._recover_operation(name)
            state = self.state(name)
            version(expected_baseline)
            if state["baseline"] != expected_baseline:
                raise ValueError(
                    "The Core baseline changed; reload and review the application upgrade"
                )
            declaration, digest = application_lock(lock_file, name)
            operation = self.app(name) / "operation.json"
            atomic(
                operation,
                {
                    "phase": "downloading",
                    "action": "adopt",
                    "declaration_sha256": digest,
                    "version": declaration["baseline"],
                    "at": int(time.time()),
                    "message": "Verifying current and reviewed Core UI bundles",
                },
            )
            try:
                try:
                    self._ensure_version(state["version"])
                except Exception as error:
                    raise ValueError(
                        "Cannot retain current Core UI for rollback. Run check/apply on the current patch line first: "
                        + str(error)
                    ) from error
                baseline = self._ensure_version(declaration["baseline"])
                if baseline["source_commit"] != declaration["source_commit"]:
                    raise ValueError(
                        "Application Core source does not match the signed release"
                    )
                _, current_digest = application_lock(lock_file, name)
                if current_digest != digest:
                    raise ValueError(
                        "Application Core declaration changed during review; retry the upgrade"
                    )
                keep_current = version(state["version"])[:2] == version(
                    declaration["baseline"]
                )[:2] and version(state["version"]) >= version(declaration["baseline"])
                selected = state["version"] if keep_current else declaration["baseline"]
                atomic(
                    self.app(name) / "state.json",
                    {
                        **state,
                        "version": selected,
                        "baseline": declaration["baseline"],
                        "adapter": declaration["adapter"],
                        "previous": state["version"]
                        if selected != state["version"]
                        else state.get("previous"),
                        "previous_baseline": state["baseline"],
                        "automatic": state["automatic"]
                        and declaration["automatic_ui_patches"],
                        "declaration_sha256": digest,
                        "source_commit": declaration["source_commit"],
                        "fallback_manifest_sha256": declaration[
                            "fallback_manifest_sha256"
                        ],
                        "last_error": "",
                        "updated": int(time.time()),
                    },
                )
                atomic(self.app(name) / "candidate.json", None)
                atomic(
                    operation,
                    {
                        "phase": "complete",
                        "version": selected,
                        "at": int(time.time()),
                        "message": "Reviewed application Core baseline adopted. Previous UI retained; services were not restarted.",
                    },
                )
            except Exception as error:
                atomic(
                    operation,
                    {"phase": "failed", "at": int(time.time()), "message": str(error)},
                )
                raise
            return self.status(name)

    def rollback(self, name):
        with self.lock():
            state = self.state(name)
            previous = state.get("previous")
            if not previous:
                raise ValueError("No previous Core version is recorded")
            version(previous)
            target = self.root / "releases" / previous
            if previous != state["baseline"] or target.exists():
                self._cached_version(previous)
            atomic(
                self.app(name) / "state.json",
                {
                    **state,
                    "version": previous,
                    "previous": state["version"],
                    "automatic": False,
                    "last_error": "",
                    "updated": int(time.time()),
                },
            )
            atomic(self.app(name) / "candidate.json", None)
            atomic(
                self.app(name) / "operation.json",
                {
                    "phase": "complete",
                    "version": previous,
                    "at": int(time.time()),
                    "message": "Previous Core UI restored. Automatic updates are paused.",
                },
            )
        return self.status(name)

    def cycle(self):
        for path in (self.root / "apps").glob("*/state.json"):
            name = path.parent.name
            try:
                result = self.check(name)
                if result["automatic"] and (result.get("candidate") or {}).get(
                    "changed"
                ):
                    self.install(
                        name, result["candidate"]["release_id"], automatic=True
                    )
            except OperationBusy:
                # Contention is expected: the manual operation owns this state.
                continue
            except Exception as error:
                try:
                    with self.lock():
                        state = self.state(name)
                        atomic(
                            path,
                            {
                                **state,
                                "last_error": str(error),
                                "last_check": int(time.time()),
                            },
                        )
                except OperationBusy:
                    # A new operation started after the failed check. Leave its
                    # state untouched and retry at the next scheduled cycle.
                    continue
                except (OSError, ValueError):
                    logging.warning("Core update error could not be recorded safely")
                    continue


def serve(manager, stop=None):
    manager.ensure()
    stop = stop or threading.Event()
    with _lock_descriptor(manager.root / ".daemon.lock") as descriptor:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _serve_locked(manager, stop)


def _serve_locked(manager, stop):
    manager.recover_pending()
    servers = []

    def factory(name, account):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                self.connection.settimeout(45)
                code = 200
                try:
                    _, uid, _ = struct.unpack(
                        "3i",
                        self.connection.getsockopt(
                            socket.SOL_SOCKET, socket.SO_PEERCRED, 12
                        ),
                    )
                    if uid not in (0, account["uid"]):
                        raise PermissionError(
                            "This application process is not authorized"
                        )
                    length = int(self.headers.get("Content-Length", "0"))
                    if (
                        self.path != "/"
                        or self.headers.get("Transfer-Encoding")
                        or not 0 < length <= 4096
                    ):
                        raise ValueError("Invalid Core manager request")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError("Core manager requests must be JSON objects")
                    action = data.get("action")
                    if action == "status":
                        result = manager.status(name)
                    elif action == "summary":
                        result = manager.summary(name)
                    elif action == "check":
                        result = manager.check(name)
                    elif action == "apply":
                        result = manager.install(name, data.get("release_id"))
                    elif action == "policy":
                        result = manager.policy(
                            name, data.get("automatic"), data.get("summaries")
                        )
                    elif action == "rollback":
                        result = manager.rollback(name)
                    else:
                        raise ValueError("Unknown Core manager action")
                except PermissionError as error:
                    code, result = 403, {"error": str(error)}
                except (
                    ValueError,
                    OSError,
                    KeyError,
                    subprocess.SubprocessError,
                ) as error:
                    code, result = 400, {"error": str(error)}
                raw = json.dumps(result).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return Handler

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = False

    try:
        for p in (manager.root / "apps").glob("*/state.json"):
            name = p.parent.name
            account = manager.state(name)
            address = manager.root / "run" / (name + ".sock")
            if address.exists():
                import stat

                if (
                    address.is_symlink()
                    or address.stat().st_uid != 0
                    or not stat.S_ISSOCK(address.stat().st_mode)
                ):
                    raise ValueError("Unsafe Core socket")
                address.unlink()
            server = Server(str(address), factory(name, account))
            os.chown(address, 0, account["gid"])
            address.chmod(0o660)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append((server, address))

        def scheduler():
            while not stop.is_set():
                manager.cycle()
                stop.wait(21600 + random.randrange(900))

        thread = threading.Thread(target=scheduler, daemon=False)
        thread.start()
        old = {}
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                old[sig] = signal.signal(sig, lambda *_: stop.set())
        stop.wait()
        for sig, handler in old.items():
            signal.signal(sig, handler)
    finally:
        stop.set()
        for server, address in servers:
            server.shutdown()
            server.server_close()
            address.unlink(missing_ok=True)
        if "thread" in locals():
            thread.join(timeout=180)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root", default=os.environ.get("KAGNODE_CORE_ROOT", "/srv/kagnode/core")
    )
    s = p.add_subparsers(dest="command", required=True)
    s.add_parser("serve")
    b = s.add_parser("bind")
    b.add_argument("app")
    b.add_argument("--user", required=True)
    choice = b.add_mutually_exclusive_group(required=True)
    choice.add_argument("--baseline")
    choice.add_argument("--lock-file", type=Path)
    adopt = s.add_parser("adopt")
    adopt.add_argument("app")
    adopt.add_argument("--lock-file", type=Path, required=True)
    adopt.add_argument("--expected-baseline", required=True)
    for operation in ("status", "check", "apply", "rollback", "policy"):
        a = s.add_parser(operation)
        a.add_argument("app")
        if operation == "policy":
            a.add_argument("--automatic", choices=("on", "off"))
            a.add_argument("--summaries", choices=("on", "off"))
        if operation == "apply":
            a.add_argument("--release-id", type=int)
    args = p.parse_args()
    manager = Manager(args.root)
    if args.command == "serve":
        return serve(manager)
    if args.command == "bind":
        result = manager.bind(args.app, args.user, args.baseline, args.lock_file)
    elif args.command == "adopt":
        result = manager.adopt(args.app, args.lock_file, args.expected_baseline)
    elif args.command == "status":
        result = manager.status(args.app)
    elif args.command == "check":
        result = manager.check(args.app)
    elif args.command == "apply":
        result = manager.install(args.app, args.release_id)
    elif args.command == "rollback":
        result = manager.rollback(args.app)
    else:
        result = manager.policy(
            args.app,
            None if args.automatic is None else args.automatic == "on",
            None if args.summaries is None else args.summaries == "on",
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit("KagNode Core: " + str(error))
