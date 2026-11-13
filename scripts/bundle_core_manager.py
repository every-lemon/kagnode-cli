#!/usr/bin/env python3
"""Explicit reviewed helper import from an independently signed Core release.

This is a maintainer build step. It never touches runtime bindings or services.
The UI manifest cannot authorize a backend helper upgrade.
"""

from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bundle(folder, core_source):
    folder = Path(folder)
    spec = importlib.util.spec_from_file_location(
        "reviewed_core_manager", ROOT / "assets/core_manager.py"
    )
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    key = (ROOT / "vendor/core-source/assets/release-public.pem").read_bytes()
    if key.strip() != manager.PUBLIC_KEY.encode().strip():
        raise ValueError("The committed helper and pinned release key disagree")
    manifest_path = folder / "release-manifest.json"
    if manifest_path.is_symlink() or not 0 < manifest_path.stat().st_size <= 2_000_000:
        raise ValueError("Unsafe or oversized signed manifest")
    raw = manifest_path.read_bytes()
    signature_path = folder / "release-manifest.sig"
    if signature_path.is_symlink() or not 0 < signature_path.stat().st_size <= 1024:
        raise ValueError("Unsafe signed manifest signature")
    manager.verify_signature(raw, signature_path.read_bytes())
    release = json.loads(raw)
    version, commit = release.get("version", ""), release.get("source_commit", "")
    if (
        release.get("schema") != 1
        or not re.fullmatch(r"5\.0\.\d+", version)
        or not re.fullmatch(r"[a-f0-9]{40}", commit)
    ):
        raise ValueError("Invalid signed Core release identity")
    inventory = {}
    for meta in release.get("packages", []):
        name = meta["name"]
        if (
            name in inventory
            or PurePosixPath(name).name != name
            or type(meta["size"]) is not int
            or not 0 < meta["size"] <= manager.LIMIT
        ):
            raise ValueError("Unsafe or duplicate signed package entry")
        path = folder / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != meta["size"]
        ):
            raise ValueError("Unsafe signed package file")
        payload = path.read_bytes()
        if len(payload) != meta["size"] or digest(payload) != meta["sha256"]:
            raise ValueError("Signed Core package size/checksum mismatch")
        inventory[name] = meta
    source_name, wheel_name = (
        f"kagnode-core-{version}-source.tar.gz",
        f"kagnode_core-{version}-py3-none-any.whl",
    )
    if source_name not in inventory or wheel_name not in inventory:
        raise ValueError("Both signed source and Python wheel are required")
    with tarfile.open(folder / source_name, "r:gz") as source:
        candidates = []
        for member in source:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("Unsafe Core source archive")
            if member.name.endswith("/packages/python/manager.py"):
                candidates.append(member)
        if len(candidates) != 1 or not 0 < candidates[0].size <= 1 << 20:
            raise ValueError("Expected exactly one bounded canonical manager source")
        helper = source.extractfile(candidates[0]).read()
    with zipfile.ZipFile(folder / wheel_name) as wheel:
        if (
            wheel.namelist().count("kagnode_core_manager.py") != 1
            or wheel.read("kagnode_core_manager.py") != helper
        ):
            raise ValueError("Python wheel and canonical manager source differ")
    # The source commit is part of the signed manifest. Verify the readable
    # corresponding Git source before updating the build-time provenance record.
    checked = subprocess.check_output(
        ["git", "show", commit + ":packages/python/manager.py"], cwd=core_source
    )
    checked_key = subprocess.check_output(
        ["git", "show", commit + ":assets/release-public.pem"], cwd=core_source
    )
    if checked != helper or checked_key != key:
        raise ValueError("Signed artifacts disagree with the recorded Core Git source")
    (ROOT / "assets/core_manager.py").write_bytes(helper)
    (ROOT / "vendor/core-source/packages/python/manager.py").write_bytes(helper)
    proof = ROOT / "vendor/core-source/release"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "release-manifest.json").write_bytes(raw)
    (proof / "release-manifest.sig").write_bytes(signature_path.read_bytes())
    manifest = {
        "schema": 1,
        "repository": "every-lemon/kagnode-core",
        "version": version,
        "source_commit": commit,
        "source_path": "packages/python/manager.py",
        "sha256": digest(helper),
        "public_key_sha256": digest(key),
        "manager_api": 1,
        "upgrade_policy": "explicit-review",
        "release_manifest_sha256": digest(raw),
        "source_archive_sha256": inventory[source_name]["sha256"],
        "python_wheel_sha256": inventory[wheel_name]["sha256"],
    }
    (ROOT / "assets/core-manager-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "version": version,
                "source_commit": commit,
                "manager_sha256": digest(helper),
                "runtime_mutated": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument(
        "--core-source",
        type=Path,
        required=True,
        help="Existing Core Git checkout; reads committed source only",
    )
    args = parser.parse_args()
    bundle(args.release, args.core_source)
