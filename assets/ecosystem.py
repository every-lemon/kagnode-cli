#!/usr/bin/env python3
"""KagNode's local installation and release manager. No shell execution.

GitHub source releases are pinned by release ID and their published SHA-256.
VPN native updates remain with its signed updater. Native provisioning is never
an incidental side effect of downloading an application release.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import http.client
import json
import datetime
import platform
import random
from zoneinfo import ZoneInfo
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import signal
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

RELEASE_PUBLIC_KEY = b"-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAuJzR4gg2djgIrWTepTgtJsPnlbvhUYz/mwO7ubtl8l4=\n-----END PUBLIC KEY-----\n"

CATALOG = {
    "proxy-manager": {
        "name": "KagNode. PM",
        "repo": "kagnode-pm",
        "kind": "native",
        "port": 9443,
    },
    "passwords": {
        "name": "KagNode Passwords",
        "repo": "kagnode-passwords",
        "kind": "python",
        "port": 8810,
    },
    "mail": {
        "name": "KagNode Mail",
        "repo": "kagnode-mail",
        "kind": "native",
        "port": 8811,
    },
    "vpn": {
        "name": "KagNode VPN",
        "repo": "kagnode-vpn",
        "kind": "signed-native",
        "port": 8812,
    },
    "httpboot": {
        "name": "KagNode HTTP Boot",
        "repo": "kagnode-httpboot",
        "kind": "native",
        "port": 8813,
    },
    "media": {
        "name": "KagNode Media",
        "repo": "kagnode-media",
        "kind": "node",
        "port": 8814,
    },
    "logos": {
        "name": "KagNode Logos",
        "repo": "kagnode-logos",
        "kind": "static",
        "port": None,
    },
    "entropy": {
        "name": "KagNode Entropy",
        "repo": "kagnode-entropy",
        "kind": "rust",
        "port": 8817,
    },
    "core": {
        "name": "KagNode Core",
        "repo": "kagnode-core",
        "kind": "signed-ui",
        "port": None,
    },
    "cli": {
        "name": "KagNode CLI",
        "repo": "kagnode-cli",
        "kind": "binary",
        "port": None,
    },
}
# Strictly code-only web updates. Core/schema/provisioning source must match.
NATIVE_PROFILES = {
    "vpn": {
        "code": "/opt/kagnode/vpn",
        "guards": ["release-key.pem", "VERSION"],
        "payload": [],
        "services": [],
    },
    "mail": {
        "code": "/opt/kagnode/mail",
        "guards": ["kagnode/db.py", "kagnode/guard.py"],
        "payload": ["kagnode"],
        "services": ["kagnode-web.service", "kagnode-guard.service"],
    },
    "httpboot": {
        "code": "/opt/kagnode/httpboot/source",
        "guards": [
            "httpboot/server_v2.py",
            "httpboot/persistence_v2.py",
            "httpboot/snapshot_store.py",
            "httpboot/client_updates.py",
        ],
        "payload": [
            "httpboot/server_console.py",
            "httpboot/server_web.py",
            "httpboot/server_web_assets.py",
            "httpboot/account_sync.py",
            "httpboot/ecosystem_updates.py",
        ],
        "services": ["kagnode-httpboot-web.service"],
    },
}

LIMIT = 512 * 1024 * 1024
CLI_LINK = Path("/usr/local/bin/kagnode")


def patch_version(value):
    match = re.fullmatch(r"5\.0\.(\d+)(?:-beta\.([1-9]\d*))?", str(value))
    if not match:
        return None
    patch, beta = match.groups()
    return (int(patch), 1 if beta is None else 0, int(beta or 0))


class ManagerError(Exception):
    pass


class MetadataError(ManagerError):
    def __init__(self, path):
        self.filename = Path(path).name
        super().__init__(
            "Invalid local metadata in "
            + self.filename
            + ". Review or restore this file before continuing."
        )


def atomic(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(json.dumps(value, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def lock_handle(path, *, create=False, privileged=False):
    """Open control files without blocking on pipes or modifying foreign inodes."""
    flags = (
        os.O_NOFOLLOW
        | os.O_NONBLOCK
        | (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except (FileNotFoundError, PermissionError):
        raise
    except OSError:
        raise MetadataError(path) from None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise MetadataError(path)
        if privileged and (info.st_uid != 0 or info.st_mode & 0o022):
            raise MetadataError(path)
        if create and privileged:
            os.fchmod(descriptor, 0o600)
        yield descriptor
    finally:
        os.close(descriptor)


def validate_metadata(path, value):
    if value is None and path.name == "candidate.json":
        return
    if not isinstance(value, dict):
        raise MetadataError(path)
    if path.name not in (
        "state.json",
        "candidate.json",
        "operation.json",
        "manager.json",
        "setup-operation.json",
    ):
        return
    for field in ("active", "needs_recovery", "changed", "prerelease"):
        if field in value and type(value[field]) is not bool:
            raise MetadataError(path)
    for field in (
        "version",
        "tag",
        "origin",
        "repository",
        "url",
        "message",
        "recovery",
    ):
        if field in value and (
            not isinstance(value[field], str) or len(value[field]) > 65536
        ):
            raise MetadataError(path)
    if "channel" in value and value["channel"] not in ("stable", "beta", "preview"):
        raise MetadataError(path)
    if "adapter" in value and value["adapter"] not in ("managed", "native-web"):
        raise MetadataError(path)
    for field, length in (("source_commit", 40), ("sha256", 64)):
        if field in value and (
            not isinstance(value[field], str)
            or not re.fullmatch("[a-f0-9]{" + str(length) + "}", value[field])
        ):
            raise MetadataError(path)
    for field in ("release_id", "size", "checked", "updated", "installed_at"):
        if field in value and (type(value[field]) is not int or value[field] < 0):
            raise MetadataError(path)
    if "port" in value and (
        type(value["port"]) is not int or not 1024 <= value["port"] <= 65535
    ):
        raise MetadataError(path)
    if "native_binding" in value:
        binding = value["native_binding"]
        if (
            not isinstance(binding, dict)
            or not isinstance(binding.get("profile"), str)
            or binding["profile"] not in NATIVE_PROFILES
        ):
            raise MetadataError(path)
        guards = binding.get("guards")
        if not isinstance(guards, dict) or set(guards) != set(
            NATIVE_PROFILES[binding["profile"]]["guards"]
        ):
            raise MetadataError(path)
        if any(
            not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            for digest in guards.values()
        ):
            raise MetadataError(path)
    if (
        path.name == "operation.json"
        and "phase" in value
        and value["phase"]
        not in (
            "queued",
            "checking",
            "downloading",
            "preparing",
            "complete",
            "failed",
            "interrupted",
        )
    ):
        raise MetadataError(path)
    if path.name == "setup-operation.json":
        if value.get("state") not in ("running", "completed", "needs_recovery"):
            raise MetadataError(path)
    if path.name == "manager.json":
        panels = value.get("panels", {})
        if not isinstance(panels, dict):
            raise MetadataError(path)
        for name, account in panels.items():
            if (
                name not in CATALOG
                or not isinstance(account, dict)
                or any(
                    type(account.get(field)) is not int or account[field] < 0
                    for field in ("uid", "gid")
                )
            ):
                raise MetadataError(path)


def read(path, default=None):
    path = Path(path)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise MetadataError(path)
            result[key] = value
        return result

    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return default
    except PermissionError:
        raise
    except OSError:
        raise MetadataError(path) from None
    try:
        stream = None
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                raise MetadataError(path)
            stream = os.fdopen(descriptor, "rb")
            with stream:
                data = stream.read(1024 * 1024 + 1)
        finally:
            if stream is None:
                os.close(descriptor)
        if len(data) > 1024 * 1024:
            raise MetadataError(path)

        def invalid_constant(_):
            raise MetadataError(path)

        value = json.loads(
            data, object_pairs_hook=unique, parse_constant=invalid_constant
        )
        validate_metadata(path, value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise MetadataError(path) from None


def https_url(url, repo=None):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ManagerError("Release downloads must use HTTPS without credentials.")
    allowed = {
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
    if parsed.hostname not in allowed or parsed.port not in (None, 443):
        raise ManagerError("Release host is not in the GitHub allowlist.")
    if repo and (
        parsed.hostname != "github.com"
        or not parsed.path.startswith(f"/every-lemon/{repo}/releases/download/")
    ):
        raise ManagerError("Release asset belongs to a different repository.")
    return url


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request(url, limit=2_000_000):
    https_url(url)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KagNode-CLI-Ecosystem",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.build_opener(Redirects()).open(req, timeout=30) as response:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ManagerError("GitHub response exceeds the size limit.")
            return data
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise ManagerError(
                "GitHub rate limit or permission error. Wait before checking again."
            ) from error
        raise ManagerError(f"GitHub returned HTTP {error.code}.") from error


def source_archive(archive, destination):
    """Reject paths/links/devices/duplicates before extracting any member."""
    with tarfile.open(archive, "r:gz") as bundle:
        members, names, total, top = [], set(), 0, None
        for member in bundle:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or not path.parts
                or any(ord(c) < 32 for c in member.name)
            ):
                raise ManagerError("Unsafe archive path.")
            if not (member.isfile() or member.isdir()) or member.name in names:
                raise ManagerError(
                    "Archive contains links, special files, or duplicate paths."
                )
            names.add(member.name)
            top = top or path.parts[0]
            if top != path.parts[0]:
                raise ManagerError("Archive must have a single top-level directory.")
            total += member.size
            if total > LIMIT * 2 or len(names) > 25000:
                raise ManagerError("Expanded archive exceeds installation limits.")
            if len(path.parts) > 1:
                members.append((member, Path(*path.parts[1:])))
        for member, rel in members:
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            if member.isdir():
                target.mkdir(exist_ok=True, mode=0o755)
            else:
                with bundle.extractfile(member) as source, target.open("xb") as dest:
                    shutil.copyfileobj(source, dest)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
        for directory, _, _ in os.walk(destination):
            Path(directory).chmod(0o755)


def validate_root(root, privileged=False):
    path = Path(root)
    if (
        not path.is_absolute()
        or str(path) != os.path.normpath(str(path))
        or len(path.parts) < 3
        or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path))
    ):
        raise ManagerError("Use an absolute dedicated root such as /srv/kagnode.")
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ManagerError("The installation root must not pass through symlinks.")
        if (
            parent.exists()
            and privileged
            and (parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022)
        ):
            raise ManagerError(
                "Installation root and ancestors must be root-owned and not group/world writable."
            )
    return path


class Manager:
    def __init__(self, root, require_root=True, system_root=None):
        self.root = validate_root(root, require_root)
        self.require_root = require_root
        # Production roots share native installations. Tests may explicitly
        # scope that host-wide lock beneath a disposable filesystem root.
        self.system_root = Path("/") if require_root else system_root

    def project(self, name):
        name = {"authenticator": "passwords", "pm": "proxy-manager"}.get(name, name)
        if name not in CATALOG:
            raise ManagerError("Unknown application. Use apps list.")
        path = self.root / name
        if path.is_symlink():
            raise ManagerError("Application directory must not be a symlink.")
        if (
            self.require_root
            and path.exists()
            and (path.stat().st_uid != 0 or path.stat().st_mode & 0o022)
        ):
            raise ManagerError(
                "Application root must be owned by root and not writable by application accounts."
            )
        for child in (
            "state.json",
            "candidate.json",
            "operation.json",
            "activation.json",
            "migration.json",
            "setup-operation.json",
            ".lock",
            "config",
            "releases",
            "downloads",
            "backups",
        ):
            target = path / child
            if target.is_symlink():
                raise ManagerError("Managed paths cannot be symlinks: " + child)

        return name, path

    def migration_marker(self, name):
        if self.system_root is None or name not in NATIVE_PROFILES:
            return None
        marker = (
            Path(self.system_root)
            / "var/lib/kagnode-migrations"
            / ("ecosystem-" + name + ".active.json")
        )
        if marker.is_symlink():
            raise ManagerError("Migration recovery marker must not be a symlink.")
        return marker

    def migration_pending(self, path):
        if (path / "migration.json").exists():
            return True
        marker = self.migration_marker(path.name)
        if marker is None:
            return False
        if marker.exists():
            return True
        # Also recognize journals created before shared recovery markers existed.
        journal = marker.with_name("ecosystem-" + path.name + ".json")
        if not journal.exists():
            return False
        try:
            from consolidate import load_journal, validate_journal

            previous = load_journal(journal)
            if not isinstance(previous, dict) or previous.get("status") not in (
                "complete",
                "rolled-back",
            ):
                return True
            records = previous.get("records")
            if not isinstance(records, list) or not records:
                return True
            completed = (
                ("complete",)
                if previous["status"] == "complete"
                else ("planned", "ready", "rolled-back")
            )
            if any(
                not isinstance(row, dict) or row.get("stage") not in completed
                for row in records
            ):
                return True
            destination = previous.get("destination")
            if not isinstance(destination, str):
                return True
            validate_root(
                Path(self.system_root) / destination.lstrip("/"), self.require_root
            )
            args = argparse.Namespace(
                project=path.name,
                destination=Path(destination),
                apply=False,
                rollback=False,
            )

            def local(raw):
                target = Path(self.system_root) / raw.lstrip("/")
                for parent in target.parents:
                    if parent == Path(self.system_root):
                        break
                    if parent.is_symlink():
                        raise ManagerError(
                            "Migration path must not pass through a symlink."
                        )
                return target

            validate_journal(previous, args, Path(self.system_root), local)
            return False
        except (OSError, ValueError, RuntimeError, ManagerError, ImportError):
            return True

    @contextlib.contextmanager
    def native_lock(self, name):
        if self.system_root is None or name not in NATIVE_PROFILES:
            yield
            return
        directory = validate_root(
            Path(self.system_root) / "var/lib/kagnode-migrations", self.require_root
        )
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = directory / ("ecosystem-" + name + ".lock")
        if lock_path.exists():
            validate_root(lock_path, self.require_root)
        with lock_handle(
            lock_path, create=True, privileged=self.require_root
        ) as descriptor:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ManagerError(
                    "Another operation is already using this native installation."
                )
            yield

    @contextlib.contextmanager
    def lock(self, name):
        if self.require_root and os.geteuid() != 0:
            raise ManagerError(
                "Run installation changes with sudo; checking releases does not need sudo."
            )
        name, path = self.project(name)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o755)
        path.mkdir(exist_ok=True, mode=0o755)
        self.root.chmod(0o755)
        path.chmod(0o755)
        with (
            self.native_lock(name),
            lock_handle(
                path / ".lock", create=True, privileged=self.require_root
            ) as descriptor,
        ):
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ManagerError(
                    "Another operation is already running for this application."
                )
            yield path

    def operation_running(self, path):
        locks = [path / ".lock"]
        marker = self.migration_marker(path.name)
        if marker is not None:
            locks.append(marker.with_name("ecosystem-" + path.name + ".lock"))
        for lock_path in locks:
            try:
                with lock_handle(lock_path, privileged=self.require_root) as descriptor:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        return True
            except FileNotFoundError:
                continue
        return False

    def status(self, name):
        name, path = self.project(name)
        metadata = {}
        errors = []
        try:
            for filename, fallback in (
                ("state.json", {}),
                ("operation.json", {}),
                ("candidate.json", None),
                ("setup-operation.json", {}),
            ):
                try:
                    metadata[filename] = read(path / filename, fallback)
                except MetadataError as error:
                    metadata[filename] = fallback
                    errors.append({"file": error.filename, "message": str(error)})
            state = metadata["state.json"]
            try:
                in_progress = self.operation_running(path)
            except MetadataError as error:
                in_progress = False
                errors.append({"file": error.filename, "message": str(error)})
            recovery = bool(
                errors
                or state.get("needs_recovery")
                or metadata["setup-operation.json"].get("state")
                in ("running", "needs_recovery")
                or (
                    (
                        (path / "activation.json").exists()
                        or self.migration_pending(path)
                    )
                    and not in_progress
                )
            )
        except PermissionError:
            return {
                "id": name,
                **CATALOG[name],
                "root": str(path),
                "message": "Use sudo to inspect this installation's private status.",
                "can_apply": False,
            }
        try:
            update_policy = self.update_policy(name)
        except (MetadataError, ManagerError, ValueError):
            update_policy = {
                "channel": "stable",
                "mode": "manual",
                "revision": 0,
                "unavailable": True,
            }
            recovery = True
        setup = metadata["setup-operation.json"]
        project_owned = setup.get("state") == "completed" and not state.get(
            "native_binding"
        )
        binding = (
            setup.get("result", {}).get("binding")
            if isinstance(setup.get("result"), dict)
            else None
        )
        return {
            "id": name,
            **CATALOG[name],
            "root": str(path),
            "manager_command": "kagnode core status APP" if name == "core" else None,
            "needs_recovery": recovery,
            "in_progress": in_progress,
            "metadata_errors": errors,
            "recovery": (
                "Review or restore damaged metadata; checking releases again can replace a damaged candidate cache."
                if errors
                else "An update or migration needs recovery review. Check activation.json, migration.json, operation.json and retained backups before continuing."
                if recovery
                else None
            ),
            "installed": state.get("version"),
            "active": state.get("active", False),
            "channel": update_policy["channel"],
            "update_policy": update_policy,
            "operation": metadata["operation.json"],
            "service_setup": metadata["setup-operation.json"],
            "runtime_binding": binding,
            "runtime_update_requires_review": project_owned,
            "update_blocked_reason": "Project-owned runtime updates require its reviewed update interface; changing downloaded source cannot update this running service."
            if project_owned
            else "Native runtime updates require a verified project update adapter; the running service is retained."
            if CATALOG[name]["kind"] in ("native", "signed-native")
            and not state.get("native_binding")
            else None,
            "candidate": metadata["candidate.json"],
            "adapter": state.get("adapter", "managed"),
            "can_apply": name != "core"
            and not project_owned
            and not recovery
            and not in_progress
            and (
                CATALOG[name]["kind"] not in ("native", "signed-native")
                or bool(state.get("native_binding"))
            ),
        }

    def check(self, name, channel=None):
        name, path = self.project(name)
        if name == "core":
            return {
                "id": name,
                **CATALOG[name],
                "can_apply": False,
                "message": "Core uses its signed manager, not application source installation. Use kagnode core bind APP --user USER --lock-file DECLARATION, then core status APP, core check APP and core apply APP for verified UI patches.",
            }
        try:
            state = read(path / "state.json", {})
        except PermissionError:
            raise ManagerError(
                "Use sudo to check releases for this managed installation."
            )
        policy = self.update_policy(name)
        channel = channel or policy["channel"]
        if channel == "preview":
            channel = "beta"
        if channel not in ("stable", "beta", "preview"):
            raise ManagerError("Choose Stable or Beta.")
        repo = CATALOG[name]["repo"]
        if name == "vpn" and state.get("native_binding"):
            return self.check_vpn(path, channel)
        releases = json.loads(
            request(
                f"https://api.github.com/repos/every-lemon/{repo}/releases?per_page=50"
            )
        )
        if not isinstance(releases, list):
            raise ManagerError("Invalid GitHub release listing.")
        candidate = None
        for release in releases:
            if release.get("draft") or (
                release.get("prerelease") and channel not in ("beta", "preview")
            ):
                continue
            assets = {a["name"]: a for a in release.get("assets", [])}
            if "release-manifest.json" not in assets:
                continue
            manifest_asset = assets["release-manifest.json"]
            manifest = json.loads(
                request(https_url(manifest_asset["browser_download_url"], repo))
            )
            if (
                manifest.get("schema") != 1
                or manifest.get("repository") != f"every-lemon/{repo}"
                or not re.fullmatch(r"[a-f0-9]{40}", manifest.get("source_commit", ""))
            ):
                raise ManagerError("Release manifest identity is invalid.")
            installed_version = patch_version(state.get("version"))
            release_version = patch_version(manifest.get("version"))
            if (
                installed_version
                and release_version
                and release_version < installed_version
            ):
                continue
            verified = False
            signature_asset = assets.get("release-manifest.sig")
            if signature_asset:
                signature = request(
                    https_url(signature_asset["browser_download_url"], repo), limit=1024
                )
                # Verification uses the original signed bytes, not a re-encoded object.
                raw_manifest = request(
                    https_url(manifest_asset["browser_download_url"], repo)
                )
                if json.loads(raw_manifest) != manifest:
                    raise ManagerError("Release manifest changed while checking")
                self.verify_release(raw_manifest, signature)
                verified = True
            matches = [
                n
                for n in manifest.get("assets", {})
                if n.startswith(repo + "_") and n.endswith("_source.tar.gz")
            ]
            if name == "proxy-manager":
                arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
                matches = [
                    n
                    for n in manifest.get("assets", {})
                    if arch
                    and n.startswith("kagnode-pm_")
                    and n.endswith(f"_linux_{arch}.tar.gz")
                ]
            if name == "logos":
                matches = [
                    n
                    for n in manifest.get("assets", {})
                    if n.startswith(repo + "_")
                    and n.endswith(("_source.tar.gz", "_artwork.tar.gz"))
                ]
            if len(matches) != 1:
                continue
            asset_name = matches[0]
            asset = manifest["assets"][asset_name]
            if (
                asset_name not in assets
                or not re.fullmatch(r"[a-f0-9]{64}", asset.get("sha256", ""))
                or type(asset.get("size")) is not int
                or not 0 < asset["size"] <= LIMIT
            ):
                raise ManagerError("Invalid source asset checksum or size.")
            candidate = {
                "signature_verified": verified,
                "automatic_update": manifest.get("automatic_update")
                if verified
                else None,
                "repository": manifest["repository"],
                "release_id": release["id"],
                "tag": release["tag_name"],
                "version": manifest["version"],
                "source_commit": manifest["source_commit"],
                "channel": channel,
                "prerelease": release["prerelease"],
                "checked": int(time.time()),
                "url": https_url(assets[asset_name]["browser_download_url"], repo),
                "sha256": asset["sha256"],
                "size": asset["size"],
                "changed": state.get("source_commit") != manifest["source_commit"],
            }
            break
        if path.exists() and os.access(path, os.W_OK):
            atomic(path / "candidate.json", candidate)
        return candidate or {
            "available": False,
            "channel": channel,
            "message": "No compatible release in this channel. Beta releases require an explicit Beta selection.",
        }

    def update_policy(self, name):
        _, path = self.project(name)
        value = read(path / "update-policy.json", None)
        if value is None:
            state = read(path / "state.json", {})
            return {
                "schema": 1,
                "revision": 0,
                "channel": "beta"
                if state.get("channel") == "preview"
                else state.get("channel", "stable"),
                "mode": "manual",
                "window": {"start": "03:00", "end": "04:00", "timezone": "UTC"},
            }
        self.validate_policy(value)
        return value

    @staticmethod
    def validate_policy(value):
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "revision", "channel", "mode", "window"}
            or value["schema"] != 1
            or type(value["revision"]) is not int
            or value["revision"] < 0
            or value["channel"] not in ("stable", "beta")
            or value["mode"] not in ("manual", "auto")
        ):
            raise ManagerError("Invalid update policy")
        window = value["window"]
        if not isinstance(window, dict) or set(window) != {"start", "end", "timezone"}:
            raise ManagerError("Invalid maintenance window")
        for key in ("start", "end"):
            if not isinstance(window[key], str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", window[key]
            ):
                raise ManagerError("Use HH:MM maintenance times")
        if window["start"] == window["end"]:
            raise ManagerError("Maintenance window must have a duration")
        try:
            ZoneInfo(window["timezone"])
        except (ValueError, KeyError, TypeError):
            raise ManagerError("Use an IANA timezone") from None

    def policy(self, name, channel, mode, window, revision):
        with self.lock(name) as path:
            previous = self.update_policy(name)
            if type(revision) is not int or previous["revision"] != revision:
                raise ManagerError("Update policy changed; reload before saving")
            value = {
                "schema": 1,
                "revision": revision + 1,
                "channel": channel,
                "mode": mode,
                "window": window,
            }
            self.validate_policy(value)
            atomic(path / "update-policy.json", value)
            atomic(path / "candidate.json", None)
            return value

    @staticmethod
    def in_window(policy, now=None):
        value = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(
            ZoneInfo(policy["window"]["timezone"])
        )
        current = value.strftime("%H:%M")
        start = policy["window"]["start"]
        end = policy["window"]["end"]
        return (
            start <= current < end if start < end else current >= start or current < end
        )

    @staticmethod
    def automatic_eligible(state, candidate):
        # A signed release must explicitly qualify this exact installed version.
        contract = candidate.get("automatic_update")
        return bool(
            candidate.get("signature_verified")
            and isinstance(contract, dict)
            and contract.get("schema") == 1
            and isinstance(contract.get("from_versions"), list)
            and state.get("version") in contract["from_versions"]
            and contract.get("data_compatibility") == "backward-compatible"
            and contract.get("scope") in ("application", "native-runtime")
            and contract.get("requires_engine_change") is False
            and contract.get("requires_hardware_build") is False
            and re.fullmatch(
                r"5\.0\.\d+(?:-beta\.[1-9]\d*)?", candidate.get("version", "")
            )
        )

    @staticmethod
    def verify_release(raw, signature):
        public_key = RELEASE_PUBLIC_KEY
        with tempfile.TemporaryDirectory(
            prefix="kagnode-release-signature-"
        ) as temporary:
            root = Path(temporary)
            (root / "key.pem").write_bytes(public_key)
            (root / "manifest").write_bytes(raw)
            (root / "signature").write_bytes(signature)
            checked = subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-rawin",
                    "-pubin",
                    "-inkey",
                    str(root / "key.pem"),
                    "-in",
                    str(root / "manifest"),
                    "-sigfile",
                    str(root / "signature"),
                ],
                capture_output=True,
                timeout=15,
            )
            if checked.returncode:
                raise ManagerError("Release signature verification failed")

    def cycle(self):
        for name in CATALOG:
            if name == "core":
                continue
            _, path = self.project(name)
            if not (path / "state.json").is_file():
                continue
            try:
                policy = self.update_policy(name)
                if policy["mode"] != "auto" or self.operation_running(path):
                    continue
                status = self.status(name)
                if status.get("needs_recovery") or not status.get("can_apply"):
                    continue
                schedule = read(path / "automatic-check.json", {})
                candidate = read(path / "candidate.json", {}) or {}
                if time.time() >= schedule.get("next_check", 0):
                    candidate = self.check(name, policy["channel"])
                    atomic(
                        path / "automatic-check.json",
                        {
                            "next_check": int(time.time())
                            + 21600
                            + random.randrange(900)
                        },
                    )
                if not self.in_window(policy) or not candidate.get("changed"):
                    continue
                attempted = read(path / "automatic-attempt.json", {})
                if attempted.get("release_id") == candidate.get("release_id"):
                    continue
                if not self.automatic_eligible(
                    read(path / "state.json", {}), candidate
                ):
                    self.operation(
                        path,
                        "review-required",
                        "This release lacks signed unattended-upgrade qualification; current service retained",
                    )
                    continue
                atomic(
                    path / "automatic-attempt.json",
                    {
                        "release_id": candidate["release_id"],
                        "started": int(time.time()),
                        "phase": "starting",
                    },
                )
                self.install(
                    name, policy["channel"], candidate["release_id"], automatic=True
                )
                atomic(
                    path / "automatic-attempt.json",
                    {
                        "release_id": candidate["release_id"],
                        "completed": int(time.time()),
                        "phase": "complete",
                    },
                )
            except (ManagerError, OSError, ValueError) as error:
                if not self.operation_running(path):
                    self.operation(path, "failed", str(error))

    def operation(self, path, phase, message, **extra):
        value = {
            "phase": phase,
            "message": message,
            "updated": int(time.time()),
            **extra,
        }
        atomic(path / "operation.json", value)
        print(json.dumps(value), flush=True)

    def begin_activation(self, path, candidate, adapter):
        # Persist before any service/code mutation. A killed process or failed
        # metadata write must not make a partially applied release look safe.
        atomic(
            path / "activation.json",
            {
                "adapter": adapter,
                "version": candidate["version"],
                "source_commit": candidate.get("source_commit"),
                "started": int(time.time()),
            },
        )
        self.sync_directory(path)

    @staticmethod
    def sync_directory(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def finish_activation(self, path):
        self.sync_directory(path)
        (path / "activation.json").unlink(missing_ok=True)
        self.sync_directory(path)

    def require_recovered(
        self, path, state, allow_migration=False, allow_setup_recovery=False
    ):
        read(path / "operation.json", {})
        read(path / "candidate.json", None)
        if (
            state.get("needs_recovery")
            or (
                not allow_setup_recovery
                and read(path / "setup-operation.json", {}).get("state")
                in ("running", "needs_recovery")
            )
            or (path / "activation.json").exists()
            or (not allow_migration and self.migration_pending(path))
        ):
            raise ManagerError(
                "This installation needs recovery review before another update or activation. Inspect activation.json, migration.json, operation.json and the retained backup."
            )

    def install(self, name, channel=None, release_id=None, *, automatic=False):
        name, path = self.project(name)
        if name == "core":
            raise ManagerError(
                "Use kagnode core install/adopt to verify signed Core manifests; source installation is not UI activation."
            )
        with self.lock(name):
            existing = read(path / "state.json", {})
            self.require_recovered(path, existing)
            setup = read(path / "setup-operation.json", {})
            if setup.get("state") == "completed" and not existing.get("native_binding"):
                raise ManagerError(
                    "This runtime is owned by its project installer. Source/current replacement is not a runtime update. Use the project's reviewed update interface when available; existing runtime and data were retained."
                )
            candidate = self.check(name, channel)
            if not candidate.get("release_id"):
                raise ManagerError(candidate["message"])
            if automatic:
                policy = self.update_policy(name)
                if (
                    policy["mode"] != "auto"
                    or not self.in_window(policy)
                    or not self.automatic_eligible(existing, candidate)
                ):
                    raise ManagerError(
                        "Automatic update is outside policy, incompatible or lacks signed unattended-upgrade qualification"
                    )
            if release_id is not None and candidate["release_id"] != release_id:
                raise ManagerError(
                    "The release changed since review. Check again before installing."
                )
            if name == "vpn" and existing.get("native_binding"):
                return self.update_vpn(path, candidate, existing)
            if existing.get("source_commit") == candidate["source_commit"]:
                return {"message": "Already installed", **self.status(name)}
            if (
                existing.get("active")
                and not existing.get("native_binding")
                and CATALOG[name]["kind"]
                in (
                    "native",
                    "signed-native",
                )
            ):
                raise ManagerError(
                    "Native service updates must use their verified native adapter."
                )
            if (path / "data").is_symlink() or (path / "logs").is_symlink():
                raise ManagerError(
                    "Application data must remain within its managed directory."
                )
            for folder in (
                "releases",
                "config",
                "data",
                "logs",
                "backups",
                "downloads",
            ):
                (path / folder).mkdir(
                    mode=0o700 if folder in ("config", "data", "backups") else 0o755,
                    exist_ok=True,
                )
                if folder in ("releases", "downloads"):
                    (path / folder).chmod(0o755)
            if shutil.disk_usage(path).free < candidate["size"] * 4 + 1024**3:
                raise ManagerError(
                    "Not enough free space for this release and its rollback copy."
                )
            release = (
                path
                / "releases"
                / (candidate["source_commit"] + "-" + os.urandom(4).hex())
            )
            download = path / "downloads" / (candidate["sha256"] + ".tar.gz")
            try:
                self.operation(
                    path, "downloading", "Downloading the reviewed GitHub release"
                )
                data = request(candidate["url"], LIMIT)
                if (
                    len(data) != candidate["size"]
                    or hashlib.sha256(data).hexdigest() != candidate["sha256"]
                ):
                    raise ManagerError("Source download failed SHA-256 verification.")
                download.write_bytes(data)
                del data
                if release.exists():
                    raise ManagerError(
                        "A previous staging directory exists; inspect it before retrying."
                    )
                release.mkdir(mode=0o755)
                source_archive(download, release)
                self.operation(
                    path,
                    "preparing",
                    "Preparing the application in its own release directory",
                )
                self.prepare(name, path, release)
                if existing.get("native_binding"):
                    self.begin_activation(path, candidate, "native-web")
                    self.apply_native(name, path, release, existing)
                    atomic(
                        path / "state.json",
                        {
                            **existing,
                            **candidate,
                            "active": True,
                            "installed_at": int(time.time()),
                        },
                    )
                    self.operation(
                        path,
                        "complete",
                        "Compatible native web application updated; system configuration retained",
                    )
                    self.finish_activation(path)
                    return self.status(name)
                old = (
                    (path / "current").resolve()
                    if (path / "current").is_symlink()
                    else None
                )
                if (path / "current").exists() and old is None:
                    raise ManagerError(
                        "Existing current directory is not managed. Nothing was replaced."
                    )
                active = existing.get("active", False)
                activated = False
                self.begin_activation(path, candidate, "managed")
                try:
                    if active:
                        self.service(name, "stop")
                    self.backup(path)
                    target = path / ".current-next"
                    target.unlink(missing_ok=True)
                    target.symlink_to(release.relative_to(path))
                    os.replace(target, path / "current")
                    activated = True
                    atomic(
                        path / "state.json",
                        {
                            **existing,
                            **candidate,
                            "active": active,
                            "previous": str(old) if old else None,
                            "installed_at": int(time.time()),
                        },
                    )
                    if active:
                        self.service(name, "start")
                        self.healthy(name)
                except Exception:
                    # Never restore a database automatically after a new version may
                    # have accepted writes. Keep both data backup and new release.
                    if active:
                        self.service(name, "stop", check=False)
                        if not activated:
                            # A failed backup cannot have changed code or data.
                            self.service(name, "start")
                        else:
                            atomic(
                                path / "state.json",
                                {
                                    **read(path / "state.json", {}),
                                    "active": False,
                                    "needs_recovery": True,
                                },
                            )
                    if not activated:
                        self.finish_activation(path)
                    raise
                self.operation(
                    path,
                    "complete",
                    "Release installed"
                    + (
                        " and service is running"
                        if active
                        else "; setup is available in the CLI"
                    ),
                )
                self.finish_activation(path)
                return self.status(name)
            except Exception as error:
                self.operation(
                    path,
                    "failed",
                    str(error),
                    recovery="Previous release and pre-update data backup are retained. No database was automatically restored.",
                )
                raise

    def native_root(self, name):
        path = Path(NATIVE_PROFILES[name]["code"])
        if path.is_symlink():
            expected = self.root / name / "runtime"
            if path.resolve() != expected.resolve() or expected.is_symlink():
                raise ManagerError(
                    "Native compatibility link points outside this application's managed runtime."
                )
            path = expected
        return validate_root(path, True)

    def check_vpn(self, path, channel):
        profile = NATIVE_PROFILES["vpn"]
        native = self.native_root("vpn")
        current = (native / "VERSION").read_text().strip()
        releases = json.loads(
            request(
                "https://api.github.com/repos/every-lemon/kagnode-vpn/releases?per_page=100"
            )
        )

        def version(value):
            match = re.fullmatch(
                r"v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?", value
            )
            if not match:
                raise ManagerError("Invalid native VPN release version.")
            return (
                *map(int, match.group(1, 2, 3)),
                {"alpha": 0, "beta": 1, "rc": 2, None: 3}[match[4]],
                int(match[5] or 0),
            )

        choices = []
        for release in releases:
            if (
                release.get("draft")
                or (release.get("prerelease") and channel not in ("beta", "preview"))
                or not re.fullmatch(
                    r"v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?",
                    release.get("tag_name", ""),
                )
            ):
                continue
            assets = {
                a["name"]: a["browser_download_url"] for a in release.get("assets", [])
            }
            if all(
                name in assets
                for name in ("manifest.json", "manifest.sig", "update.sh")
            ):
                choices.append((version(release["tag_name"]), release, assets))
        if not choices:
            raise ManagerError("No signed VPN release is available in this channel.")
        _, release, assets = max(choices, key=lambda value: value[0])
        manifest = request(https_url(assets["manifest.json"], "kagnode-vpn"), 65536)
        signature = request(https_url(assets["manifest.sig"], "kagnode-vpn"), 4096)
        with tempfile.TemporaryDirectory(prefix="vpn-verify-") as scratch:
            scratch = Path(scratch)
            (scratch / "manifest").write_bytes(manifest)
            (scratch / "signature").write_bytes(signature)
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(native / "release-key.pem"),
                    "-rawin",
                    "-in",
                    str(scratch / "manifest"),
                    "-sigfile",
                    str(scratch / "signature"),
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
        content = json.loads(manifest)
        asset = content.get("assets", {}).get("update.sh", {})
        if (
            content.get("schema") != 1
            or content.get("version") != release["tag_name"][1:]
            or content.get("platform") != "ubuntu-24.04-amd64"
            or not re.fullmatch(r"[a-f0-9]{64}", asset.get("sha256", ""))
            or type(asset.get("size")) is not int
            or not 0 < asset["size"] < 8 * 1024**2
        ):
            raise ManagerError("Signed VPN release metadata is invalid.")
        candidate = {
            "release_id": release["id"],
            "version": content["version"],
            "tag": release["tag_name"],
            "channel": channel,
            "prerelease": release["prerelease"],
            "sha256": asset["sha256"],
            "size": asset["size"],
            "url": https_url(assets["update.sh"], "kagnode-vpn"),
            "signature": "verified",
            "changed": version(content["version"]) > version(current),
            "checked": int(time.time()),
        }
        atomic(path / "candidate.json", candidate)
        return candidate

    def update_vpn(self, path, candidate, state):
        if not candidate.get("changed"):
            return {
                "message": "VPN is already at this release or newer.",
                **self.status("vpn"),
            }
        self.operation(path, "downloading", "Downloading signed VPN update")
        data = request(candidate["url"], 8 * 1024**2)
        if (
            len(data) != candidate["size"]
            or hashlib.sha256(data).hexdigest() != candidate["sha256"]
        ):
            raise ManagerError("Signed VPN payload failed checksum verification.")
        download = path / "downloads"
        download.mkdir(mode=0o700, exist_ok=True)
        script = download / (candidate["sha256"] + ".sh")
        script.write_bytes(data)
        script.chmod(0o600)
        self.operation(path, "preparing", "Applying the verified native VPN updater")
        log = path / "native-update.log"
        self.begin_activation(path, candidate, "signed-native")
        with log.open("a") as output:
            os.chmod(log, 0o600)
            subprocess.run(
                ["/bin/bash", str(script)]
                + (["--prerelease"] if candidate["prerelease"] else []),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                check=True,
                timeout=1800,
            )
        actual = (Path(NATIVE_PROFILES["vpn"]["code"]) / "VERSION").read_text().strip()
        if actual != candidate["version"]:
            raise ManagerError(
                "The native updater did not report the expected installed version."
            )
        atomic(
            path / "state.json",
            {**state, "version": actual, "channel": candidate["channel"]},
        )
        self.operation(path, "complete", "Signed VPN update completed")
        self.finish_activation(path)
        return self.status("vpn")

    def bind_native(self, name, channel="stable"):
        """Bind known existing installations; do not relocate private data."""
        if name not in NATIVE_PROFILES:
            raise ManagerError("This application has no native web update adapter.")
        profile = NATIVE_PROFILES[name]
        with self.lock(name) as path:
            current = read(path / "state.json", {})
            self.require_recovered(path, current)
            if current.get("native_binding"):
                raise ManagerError("Native installation already bound.")
            native = self.native_root(name)
            if not native.is_dir() or any(
                not (native / field).is_file() for field in profile["guards"]
            ):
                raise ManagerError(
                    "The expected native installation was not found. No code or data was changed."
                )
            guards = {
                field: hashlib.sha256((native / field).read_bytes()).hexdigest()
                for field in profile["guards"]
            }
            atomic(
                path / "state.json",
                {
                    "version": "existing-native",
                    "channel": channel,
                    "active": True,
                    "native_binding": {"profile": name, "guards": guards},
                    "adapter": "native-web",
                },
            )
            return self.status(name)

    def apply_native(self, name, path, release, state):
        profile = NATIVE_PROFILES.get(name)
        binding = state.get("native_binding", {})
        if (
            not profile
            or not isinstance(binding, dict)
            or binding.get("profile") != name
        ):
            raise ManagerError("Unrecognized native update binding.")
        if not isinstance(binding.get("guards"), dict) or set(binding["guards"]) != set(
            profile["guards"]
        ):
            raise ManagerError(
                "Native guard inventory is incomplete or changed; recovery review is required."
            )
        native = self.native_root(name)
        for field, digest in binding["guards"].items():
            if (
                not (native / field).is_file()
                or not (release / field).is_file()
                or hashlib.sha256((native / field).read_bytes()).hexdigest() != digest
                or hashlib.sha256((release / field).read_bytes()).hexdigest() != digest
            ):
                raise ManagerError(
                    "Native schema/provisioning guard changed: "
                    + field
                    + ". A reviewed migration is required."
                )
        backup = (
            path
            / "backups"
            / ("native-" + time.strftime("%Y%m%dT%H%M%S") + "-" + os.urandom(3).hex())
        )
        backup.mkdir(parents=True, mode=0o700)
        active = [
            unit
            for unit in profile["services"]
            if subprocess.run(
                ["systemctl", "is-active", "--quiet", unit], check=False
            ).returncode
            == 0
        ]
        changed = []
        try:
            for unit in active:
                subprocess.run(["systemctl", "stop", unit], check=True, timeout=60)
            for relative in profile["payload"]:
                source, target = release / relative, native / relative
                if not source.exists():
                    raise ManagerError("Native release payload missing: " + relative)
                if target.is_symlink():
                    raise ManagerError(
                        "Native payload path is a symlink; review its layout first."
                    )
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                if target.is_dir():
                    shutil.copytree(target, saved, symlinks=True)
                elif target.exists():
                    shutil.copy2(target, saved)
                staging = target.with_name(target.name + ".kagnode-next")
                if staging.exists() or staging.is_symlink():
                    raise ManagerError("A previous native staging path needs review.")
                if source.is_dir():
                    shutil.copytree(source, staging)
                else:
                    shutil.copy2(source, staging)
                old = target.with_name(target.name + ".kagnode-old")
                if old.exists() or old.is_symlink():
                    raise ManagerError("A retained native rollback path needs review.")
                if target.exists():
                    target.rename(old)
                changed.append((target, old, staging))
                staging.rename(target)
            for unit in active:
                subprocess.run(["systemctl", "start", unit], check=True, timeout=60)
                subprocess.run(["systemctl", "is-active", "--quiet", unit], check=True)
            # Only obsolete code copies are removed; the verified backup stays.
            for target, old, staging in changed:
                if old.is_dir():
                    shutil.rmtree(old)
                else:
                    old.unlink(missing_ok=True)
        except Exception:
            for unit in active:
                subprocess.run(["systemctl", "stop", unit], check=False, timeout=60)
            for target, old, staging in reversed(changed):
                if target.exists():
                    failed = target.with_name(
                        target.name + ".kagnode-failed-" + os.urandom(3).hex()
                    )
                    target.rename(failed)
                if old.exists():
                    old.rename(target)
            for unit in active:
                subprocess.run(["systemctl", "start", unit], check=False, timeout=60)
            raise

    def user(self, name):
        username = "kn-" + name
        try:
            return pwd.getpwnam(username)
        except KeyError:
            subprocess.run(
                [
                    "/usr/sbin/useradd",
                    "--system",
                    "--no-create-home",
                    "--home-dir",
                    str(self.root / name),
                    "--shell",
                    "/usr/sbin/nologin",
                    username,
                ],
                check=True,
            )
            return pwd.getpwnam(username)

    def prepare(self, name, path, release):
        kind = CATALOG[name]["kind"]
        # Fresh application source is inert. Dependency installs, runtime users,
        # configuration and service setup belong to the reviewed project adapter.
        # Retain the existing bounded preparation for already active managed
        # upgrades and the explicitly requested CLI source build.
        if kind != "binary" and not read(path / "state.json", {}).get("active"):
            return
        if kind not in ("python", "node", "binary"):
            return
        user = self.user(name)
        for base, directories, files in os.walk(release):
            os.chown(base, user.pw_uid, user.pw_gid)
            for filename in files:
                os.chown(Path(base) / filename, user.pw_uid, user.pw_gid)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(release),
            "PYTHONDONTWRITEBYTECODE": "1",
            "npm_config_cache": str(path / "downloads" / "npm"),
        }

        def run(args):
            subprocess.run(
                args,
                cwd=release,
                env=env,
                user=user.pw_uid,
                group=user.pw_gid,
                extra_groups=[],
                check=True,
                timeout=900,
                stdin=subprocess.DEVNULL,
            )

        try:
            if kind == "python":
                run([sys.executable, "-m", "venv", str(release / ".venv")])
                run(
                    [
                        str(release / ".venv/bin/pip"),
                        "install",
                        "--disable-pip-version-check",
                        "-r",
                        "requirements.txt",
                    ]
                )
            elif kind == "node":
                node = shutil.which("node")
                if not node or not subprocess.check_output(
                    [node, "--version"], text=True
                ).startswith("v24."):
                    raise ManagerError(
                        "Node.js 24 is required. Install it before configuring Media."
                    )
                cache = path / "downloads/npm"
                cache.mkdir(exist_ok=True)
                os.chown(cache, user.pw_uid, user.pw_gid)
                run([shutil.which("npm") or "/usr/bin/npm", "ci", "--ignore-scripts"])
                run([shutil.which("npm") or "/usr/bin/npm", "run", "build"])
            else:
                go = shutil.which("go")
                if not go:
                    raise ManagerError(
                        "Go is required for this source installation; prebuilt CLI downloads are also available."
                    )
                run([go, "build", "-trimpath", "-o", "kagnode", "."])
        finally:
            # Application code becomes immutable to the runtime account.
            for base, directories, files in os.walk(release):
                os.chown(base, 0, 0)
                os.chmod(base, 0o755)
                for filename in files:
                    target = Path(base) / filename
                    if not target.is_symlink():
                        os.chown(target, 0, 0)
                        target.chmod(0o755 if target.stat().st_mode & 0o111 else 0o644)

    def backup(self, path):
        size = sum(
            file.stat().st_size
            for folder in ("data", "config")
            for file in (path / folder).rglob("*")
            if file.is_file() and not file.is_symlink()
        )
        if shutil.disk_usage(path).free < size + 512 * 1024**2:
            raise ManagerError(
                "Not enough free space for a complete pre-update data backup."
            )
        if not any((path / "data").iterdir()) and not any((path / "config").iterdir()):
            return
        target = (
            path
            / "backups"
            / (time.strftime("%Y%m%dT%H%M%S") + "-" + os.urandom(3).hex())
        )
        target.mkdir(mode=0o700)
        for folder in ("data", "config"):
            shutil.copytree(path / folder, target / folder, symlinks=True)
        inventory = []
        for folder in ("data", "config"):
            for original in [path / folder, *sorted((path / folder).rglob("*"))]:
                destination = target / original.relative_to(path)
                info = original.lstat()
                if self.require_root:
                    os.lchown(destination, info.st_uid, info.st_gid)
                if original.is_symlink():
                    if os.readlink(original) != os.readlink(destination):
                        raise ManagerError("Backup symlink verification failed")
                    inventory.append(
                        {
                            "path": str(original.relative_to(path)),
                            "link": os.readlink(original),
                        }
                    )
                elif original.is_file():
                    checksum = hashlib.sha256(original.read_bytes()).hexdigest()
                    if checksum != hashlib.sha256(destination.read_bytes()).hexdigest():
                        raise ManagerError("Backup content verification failed")
                    inventory.append(
                        {
                            "path": str(original.relative_to(path)),
                            "sha256": checksum,
                            "uid": info.st_uid,
                            "gid": info.st_gid,
                            "mode": stat.S_IMODE(info.st_mode),
                        }
                    )
        atomic(
            target / "inventory.json",
            {"schema": 1, "verified": True, "files": inventory},
        )
        atomic(target / "state.json", read(path / "state.json", {}))

    def service(self, name, action, check=True):
        units = ["kagnode-" + name + ".service"]
        worker = Path("/etc/systemd/system/kagnode-media-worker.service")
        if name == "media" and worker.exists():
            if action == "stop":
                units.insert(0, worker.name)
            else:
                units.append(worker.name)
        for unit in units:
            subprocess.run(["systemctl", action, unit], check=check, timeout=60)

    def healthy(self, name):
        port = read(self.root / name / "state.json", {}).get(
            "port", CATALOG[name]["port"]
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                connection.request("GET", "/healthz" if name == "media" else "/")
                response = connection.getresponse()
                if 200 <= response.status < 400:
                    return
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(1)
        raise ManagerError(
            "Service did not return a healthy HTTP response. Inspect its journal; backup retained."
        )

    def setup(self, name, origin, port=None):
        _, path = self.project(name)
        self.require_recovered(path, read(path / "state.json", {}))
        raise ManagerError(
            "Legacy inferred service setup was retired. Use apps plan PROJECT --mode native|application|adopt, review the project-owned plan, then apps apply PROJECT --plan FILE."
        )

    def activate_cli(self):
        """Opt-in PATH activation; never replace a package-owned executable."""
        with self.lock("cli") as path:
            self.require_recovered(path, read(path / "state.json", {}))
            current = path / "current"
            binary = current / "kagnode"
            if (
                not current.is_symlink()
                or not current.resolve().is_relative_to(path / "releases")
                or not binary.is_file()
                or binary.is_symlink()
                or not os.access(binary, os.X_OK)
            ):
                raise ManagerError(
                    "Install a verified CLI release before activating it."
                )
            destination = CLI_LINK
            validate_root(destination.parent, self.require_root)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            if destination.is_symlink() and os.readlink(destination) == str(binary):
                return {
                    "message": "The managed CLI is already active.",
                    "executable": str(destination),
                }
            if destination.exists() or destination.is_symlink():
                raise ManagerError(
                    "An existing /usr/local/bin/kagnode was retained. Review its installation before activation."
                )
            destination.symlink_to(binary)
            return {
                "message": "The managed CLI is on PATH; future updates switch its current release.",
                "executable": str(destination),
            }


def bitwarden_setup(root, origin, image, port=8816, apply=False):
    """Pinned upstream engine, isolated data; no automatic legacy-vault conversion."""
    root = validate_root(root, apply)
    Manager(root, apply).project("passwords")
    if apply and os.geteuid() != 0:
        raise ManagerError("Use sudo for engine installation.")
    if apply and (root / "passwords/bitwarden").exists():
        raise ManagerError(
            "Existing engine configuration retained. Use its documented backup/update workflow."
        )
    if not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?", origin):
        raise ManagerError("Bitwarden server needs its own HTTPS origin.")
    if image is None:
        latest = json.loads(
            request(
                "https://api.github.com/repos/dani-garcia/vaultwarden/releases/latest"
            )
        )
        tag = latest.get("tag_name", "")
        if (
            latest.get("draft")
            or latest.get("prerelease")
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", tag)
        ):
            raise ManagerError("No valid stable Vaultwarden release was found.")
        if not apply:
            return {
                "directory": str(root / "passwords/bitwarden"),
                "version": tag,
                "message": "With --apply, pull the official stable image and pin its immutable digest. Existing vaults remain unchanged.",
            }
        subprocess.run(
            ["docker", "pull", "vaultwarden/server:" + tag], check=True, timeout=600
        )
        digests = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "image",
                    "inspect",
                    "vaultwarden/server:" + tag,
                    "--format",
                    "{{json .RepoDigests}}",
                ],
                text=True,
            )
        )
        image = next(
            (
                digest
                for digest in digests
                if re.fullmatch(r"vaultwarden/server@sha256:[a-f0-9]{64}", digest)
            ),
            "",
        )
    if not re.fullmatch(r"vaultwarden/server@sha256:[a-f0-9]{64}", image):
        raise ManagerError(
            "Pin the official vaultwarden/server image by SHA-256 digest, not latest."
        )
    if not 1024 <= port <= 65535:
        raise ManagerError("Invalid port.")
    base = root / "passwords" / "bitwarden"
    compose = {
        "services": {
            "vaultwarden": {
                "image": image,
                "restart": "unless-stopped",
                "ports": [f"127.0.0.1:{port}:80"],
                "volumes": ["./data:/data"],
                "environment": {
                    "DOMAIN": origin,
                    "SIGNUPS_ALLOWED": "false",
                    "INVITATIONS_ALLOWED": "false",
                    "SHOW_PASSWORD_HINT": "false",
                },
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "logging": {
                    "driver": "json-file",
                    "options": {"max-size": "10m", "max-file": "3"},
                },
            }
        }
    }
    if not apply:
        return {
            "directory": str(base),
            "compose": compose,
            "message": "Review with --apply to install. Configure admin invitation privately; registration is disabled.",
        }
    if os.geteuid() != 0:
        raise ManagerError("Use sudo for engine installation.")
    if base.exists():
        raise ManagerError(
            "Existing engine configuration retained. Use its documented backup/update workflow."
        )
    base.mkdir(parents=True, mode=0o700)
    (base / "data").mkdir(mode=0o700)
    import secrets

    token = secrets.token_urlsafe(48)
    secret_file = base / "admin.env"
    secret_file.write_text("ADMIN_TOKEN=" + token + "\n")
    secret_file.chmod(0o600)
    compose["services"]["vaultwarden"]["env_file"] = ["./admin.env"]
    atomic(base / "compose.json", compose)
    subprocess.run(
        ["docker", "compose", "-f", str(base / "compose.json"), "pull"],
        check=True,
        timeout=600,
    )
    subprocess.run(
        ["docker", "compose", "-f", str(base / "compose.json"), "up", "-d"],
        check=True,
        timeout=120,
    )
    return {
        "server": origin,
        "proxy": f"http://127.0.0.1:{port}",
        "directory": str(base),
        "message": "Engine started. Configure HTTPS, open /admin using the private admin.env token, and invite accounts before client sign-in. Existing KagNode vault was not modified.",
    }


def enable_panel(manager, name, username):
    name, path = manager.project(name)
    with manager.lock(name):
        account = pwd.getpwnam(username)
        configured = read(manager.root / "manager.json", {"panels": {}})
        configured.setdefault("panels", {})[name] = {
            "uid": account.pw_uid,
            "gid": account.pw_gid,
        }
        atomic(manager.root / "manager.json", configured)
    return {
        "message": "Panel authorized. Start kagnode apps serve as root, or install its systemd service.",
        "socket": str(manager.root / "run" / (name + ".sock")),
        "application_user": username,
    }


def serve(manager, stop_event=None):
    """One daemon owns the socket directory; graceful shutdown finishes writes."""
    if os.geteuid() != 0:
        raise ManagerError("The local update manager must run as root.")
    manager.root.mkdir(parents=True, exist_ok=True, mode=0o755)
    for field in ("manager.json", ".manager.lock"):
        if (manager.root / field).is_symlink():
            raise ManagerError("Unsafe manager configuration path.")
    with lock_handle(
        manager.root / ".manager.lock", create=True, privileged=manager.require_root
    ) as descriptor:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ManagerError("The update manager is already running.") from error
        return serve_locked(manager, stop_event)


def serve_locked(manager, stop_event=None):
    from http.server import BaseHTTPRequestHandler

    if os.geteuid() != 0:
        raise ManagerError("The local update manager must run as root.")
    config = read(manager.root / "manager.json", {"panels": {}})
    run = manager.root / "run"
    run.mkdir(mode=0o755, exist_ok=True)
    if run.is_symlink() or run.stat().st_uid != 0 or run.stat().st_mode & 0o022:
        raise ManagerError("Unsafe socket directory.")
    run.chmod(0o755)
    active = set()
    jobs_lock = threading.Lock()
    servers = []
    workers = []
    stop_event = stop_event or threading.Event()

    def factory(project, account):
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(5)
                super().setup()

            def log_message(self, *args):
                pass

            def do_POST(self):
                self.connection.settimeout(5)
                status, value = 200, {}
                try:
                    _, uid, _ = struct.unpack(
                        "3i",
                        self.connection.getsockopt(
                            socket.SOL_SOCKET, socket.SO_PEERCRED, 12
                        ),
                    )
                    if uid not in (0, account["uid"]):
                        raise ManagerError(
                            "This process is not authorized for that application."
                        )
                    length = int(self.headers.get("Content-Length", "0"))
                    if (
                        self.path != "/"
                        or self.headers.get("Transfer-Encoding")
                        or not 0 < length <= 4096
                    ):
                        raise ManagerError("Invalid update request.")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict) or data.get("action") not in (
                        "state",
                        "check",
                        "apply",
                        "policy",
                    ):
                        raise ManagerError("Unknown update action.")
                    if data["action"] == "state":
                        value = {"enabled": True, **manager.status(project)}
                    elif data["action"] == "policy":
                        value = manager.policy(
                            project,
                            data.get("channel"),
                            data.get("mode"),
                            data.get("window"),
                            data.get("revision"),
                        )
                    else:
                        with jobs_lock:
                            if active:
                                raise ManagerError(
                                    "An application update is running. Refresh its status before starting another."
                                )
                            if data["action"] == "check":
                                value = {
                                    "enabled": True,
                                    "candidate": manager.check(project),
                                }
                            else:
                                candidate = (
                                    read(manager.root / project / "candidate.json", {})
                                    or {}
                                )
                                if (
                                    type(data.get("release_id")) is not int
                                    or candidate.get("release_id") != data["release_id"]
                                    or not candidate.get("changed")
                                ):
                                    raise ManagerError(
                                        "Check for updates and review the current release first."
                                    )
                                state = read(manager.root / project / "state.json", {})
                                if not state.get("version"):
                                    raise ManagerError(
                                        "Install this application through the CLI before enabling panel updates."
                                    )
                                if CATALOG[project]["kind"] in (
                                    "native",
                                    "signed-native",
                                ) and not state.get("native_binding"):
                                    raise ManagerError(
                                        "Native updates require the project's verified updater. This panel can check releases; it will not bypass native validation."
                                    )
                                manager.require_recovered(manager.root / project, state)
                                manager.operation(
                                    manager.root / project,
                                    "queued",
                                    "Reviewed update queued",
                                )
                                active.add(project)

                                def work():
                                    try:
                                        manager.install(
                                            project,
                                            candidate["channel"],
                                            data["release_id"],
                                        )
                                    except Exception as error:
                                        manager.operation(
                                            manager.root / project, "failed", str(error)
                                        )
                                    finally:
                                        with jobs_lock:
                                            active.discard(project)

                                worker = threading.Thread(target=work)
                                workers.append(worker)
                                worker.start()
                                status, value = (
                                    202,
                                    {
                                        "queued": True,
                                        "message": "Update started. Keep this page open to follow progress.",
                                    },
                                )
                except (ManagerError, OSError, ValueError, KeyError) as error:
                    status, value = 400, {"error": str(error)}
                encoded = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    handlers = {}
    try:
        for name, account in config.get("panels", {}).items():
            manager.project(name)
            if any(
                type(account.get(field)) is not int or account[field] < 0
                for field in ("uid", "gid")
            ):
                raise ManagerError("Invalid panel account configuration.")
            try:
                previous = read(manager.root / name / "operation.json", {})
            except MetadataError:
                # Keep the daemon available for diagnostic status. Never replace
                # a damaged progress record with a misleading restart result.
                previous = {}
            if previous.get("phase") in (
                "queued",
                "downloading",
                "preparing",
            ) and not manager.operation_running(manager.root / name):
                manager.operation(
                    manager.root / name,
                    "interrupted",
                    "The manager restarted during an operation. Review the retained release and backup before retrying.",
                )
            path = run / (name + ".sock")
            if path.is_symlink() or (
                path.exists() and not stat.S_ISSOCK(path.stat().st_mode)
            ):
                raise ManagerError("Unexpected file at the manager socket path.")
            # The exclusive process lock proves no other manager owns this socket.
            path.unlink(missing_ok=True)
            server = Server(str(path), factory(name, account))
            os.chown(path, 0, account["gid"])
            path.chmod(0o660)
            servers.append((server, path))
            threading.Thread(target=server.serve_forever, daemon=True).start()
        if not servers:
            raise ManagerError("Enable at least one application panel first.")
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, lambda *_: stop_event.set())
        print(
            "KagNode update manager is listening on local application sockets.",
            flush=True,
        )

        def scheduler():
            while not stop_event.is_set():
                with jobs_lock:
                    if not active:
                        active.add("automatic-cycle")
                        try:
                            manager.cycle()
                        finally:
                            active.discard("automatic-cycle")
                stop_event.wait(60)

        scheduler_thread = threading.Thread(target=scheduler)
        scheduler_thread.start()
        stop_event.wait()
        scheduler_thread.join()
    finally:
        for server, path in servers:
            server.shutdown()
            server.server_close()
            path.unlink(missing_ok=True)
        for worker in workers:
            worker.join()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=os.environ.get("KAGNODE_ROOT", "/srv/kagnode")
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("serve")
    sub.add_parser("activate-cli")
    migrate = sub.add_parser("consolidate")
    migrate.add_argument("project", choices=["mail", "vpn", "httpboot"])
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--rollback", action="store_true")
    native = sub.add_parser("bind-native")
    native.add_argument("project", choices=list(NATIVE_PROFILES))
    native.add_argument(
        "--channel", choices=["stable", "beta", "preview"], default=None
    )
    policy = sub.add_parser("policy")
    policy.add_argument("project", choices=list(CATALOG) + ["pm", "authenticator"])
    policy.add_argument("--channel", choices=["stable", "beta"])
    policy.add_argument("--mode", choices=["manual", "auto"])
    policy.add_argument("--start", default="03:00")
    policy.add_argument("--end", default="04:00")
    policy.add_argument("--timezone", default="UTC")
    policy.add_argument("--revision", type=int)
    panel = sub.add_parser("enable-panel")
    panel.add_argument("project", choices=list(CATALOG) + ["pm", "authenticator"])
    panel.add_argument("--user", required=True)
    for command in ("status", "check", "install", "update"):
        p = sub.add_parser(command)
        p.add_argument("project", choices=list(CATALOG) + ["authenticator", "pm"])
        if command != "status":
            p.add_argument(
                "--channel", choices=["stable", "beta", "preview"], default=None
            )
        if command in ("install", "update"):
            p.add_argument("--release-id", type=int)
    for command in ("plan", "apply", "health", "recover", "installer-status"):
        p = sub.add_parser(command)
        p.add_argument("project", choices=list(CATALOG) + ["pm", "authenticator"])
        p.add_argument(
            "--mode", choices=["native", "application", "adopt"], default="application"
        )
        p.add_argument(
            "--config",
            help="Private JSON configuration file; secret fields are file references",
        )
        p.add_argument("--plan", help="Private reviewed plan file for apply/recover")
        p.add_argument("--save-plan", help="New file inside a private directory")
        p.add_argument(
            "--recover",
            action="store_true",
            help="Review project-owned recovery instead of fresh setup",
        )
    p = sub.add_parser("setup")
    p.add_argument("project", choices=list(CATALOG) + ["pm", "authenticator"])
    p.add_argument("--origin", required=True)
    p.add_argument("--port", type=int)
    p = sub.add_parser("bitwarden")
    p.add_argument("--origin", required=True)
    p.add_argument(
        "--image",
        help="Optional official image digest; without it, resolve the latest stable upstream image",
    )
    p.add_argument("--port", type=int, default=8816)
    p.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    manager = Manager(
        args.root,
        args.command
        not in ("list", "status", "check", "plan", "health", "installer-status"),
        system_root=Path("/"),
    )
    if args.command == "list":
        result = [manager.status(name) for name in CATALOG]
    elif args.command == "consolidate":
        command = [
            sys.executable,
            str(Path(__file__).with_name("consolidate.py")),
            args.project,
            "--destination",
            str(manager.root),
        ]
        if args.apply:
            command.append("--apply")
        if args.rollback:
            command.append("--rollback")
        subprocess.run(command, check=True)
        return
    elif args.command == "bind-native":
        result = manager.bind_native(args.project, args.channel)
    elif args.command == "serve":
        return serve(manager)
    elif args.command == "activate-cli":
        result = manager.activate_cli()
    elif args.command == "enable-panel":
        result = enable_panel(manager, args.project, args.user)
    elif args.command == "policy":
        if args.channel is None and args.mode is None:
            result = manager.update_policy(args.project)
        elif args.channel is None or args.mode is None or args.revision is None:
            raise ManagerError("Choose channel, mode and the reviewed policy revision")
        else:
            result = manager.policy(
                args.project,
                args.channel,
                args.mode,
                {"start": args.start, "end": args.end, "timezone": args.timezone},
                args.revision,
            )
    elif args.command == "status":
        result = manager.status(args.project)
    elif args.command == "check":
        result = manager.check(args.project, args.channel)
    elif args.command in ("install", "update"):
        result = manager.install(args.project, args.channel, args.release_id)
    elif args.command in ("plan", "apply", "health", "recover", "installer-status"):
        from installer import operate

        result = operate(
            manager,
            args.project,
            "status" if args.command == "installer-status" else args.command,
            args.mode,
            args.config,
            args.plan,
            args.save_plan,
            args.recover,
        )
    elif args.command == "setup":
        result = manager.setup(args.project, args.origin, args.port)
    else:
        result = bitwarden_setup(
            args.root, args.origin, args.image, args.port, args.apply
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ManagerError, OSError, ValueError, subprocess.SubprocessError) as error:
        print("KagNode: " + str(error), file=sys.stderr)
        sys.exit(1)
