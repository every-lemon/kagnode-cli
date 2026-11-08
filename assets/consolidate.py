#!/usr/bin/env python3
"""Explicit, journaled KagNode path migration. Dry-run by default; no service restart."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from ecosystem import Manager, ManagerError, atomic, read, validate_root
from pathlib import Path

PROJECT = None
MAPPINGS = []
SERVICES = []
LAYOUTS = {
    "mail": (
        [
            ("/opt/kagnode/mail", "runtime"),
            ("/etc/kagnode/mail", "config"),
            ("/var/lib/kagnode/mail", "data"),
            ("/var/vmail", "mailboxes"),
        ],
        ["kagnode-web", "kagnode-guard", "postfix", "dovecot", "opendkim"],
    ),
    "vpn": (
        [
            ("/opt/kagnode/vpn", "runtime"),
            ("/etc/kagnode/vpn", "config"),
            ("/var/lib/kagnode/vpn", "data"),
            ("/var/log/kagnode/vpn", "logs"),
        ],
        [
            "vpn-control",
            "vpn-management",
            "vpn-downloads",
            "vpn-watchdog",
            "vpn-maintenance",
        ],
    ),
    "httpboot": (
        [
            ("/opt/kagnode/httpboot/source", "runtime"),
            ("/var/lib/kagnode/httpboot-server", "data"),
        ],
        [
            "httpboot-server",
            "httpboot-server-console",
            "httpboot-bootstrap-v2",
            "kagnode-httpboot-web",
            "httpboot-server-maintenance",
        ],
    ),
}


def digest(path):
    stat = path.lstat()
    rows = [[".", "dir", stat.st_mode & 0o7777, stat.st_uid, stat.st_gid]]
    for p in sorted(path.rglob("*")):
        relative = str(p.relative_to(path))
        st = p.lstat()
        if p.is_symlink():
            rows.append([relative, "link", os.readlink(p)])
        elif p.is_file():
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            rows.append(
                [
                    relative,
                    "file",
                    st.st_size,
                    h.hexdigest(),
                    st.st_mode & 0o7777,
                    st.st_uid,
                    st.st_gid,
                ]
            )
        elif p.is_dir():
            rows.append([relative, "dir", st.st_mode & 0o7777, st.st_uid, st.st_gid])
        else:
            raise RuntimeError(
                "Unsupported socket/device in " + relative + "; stop the service first."
            )
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def invalid_journal(reason):
    raise RuntimeError("Invalid migration journal: " + reason)


def journal_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            invalid_journal("duplicate field " + key)
        result[key] = value
    return result


def load_journal(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
        invalid_journal("expected a regular JSON file no larger than 1 MiB")
    try:
        return json.loads(path.read_text(), object_pairs_hook=journal_object)
    except (ValueError, UnicodeError):
        invalid_journal("cannot read valid JSON")


def validate_journal(data, args, root, local):
    project = "ecosystem-" + args.project
    mappings = [
        (old, str(args.destination / args.project / new))
        for old, new in LAYOUTS[args.project][0]
    ]
    if not isinstance(data, dict):
        invalid_journal("expected an object")
    if (data.get("project"), data.get("root"), data.get("destination")) != (
        project,
        str(root),
        str(args.destination),
    ):
        invalid_journal("belongs to another project/root/destination")
    if data.get("schema", 1) != 1 or type(data.get("schema", 1)) is not int:
        invalid_journal("unsupported schema")
    if type(data.get("created")) is not int or data["created"] < 0:
        invalid_journal("invalid creation time")
    if data.get("status") not in ("planned", "complete", "rolling-back", "rolled-back"):
        invalid_journal("unknown migration status")
    records = data.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= len(mappings):
        invalid_journal("invalid record inventory")
    rollback_mode = (
        args.rollback
        or data["status"] == "rolling-back"
        or any(
            isinstance(row, dict) and row.get("stage") == "rolled-back"
            for row in records
        )
    )
    if args.apply and rollback_mode and data["status"] != "rolled-back":
        invalid_journal("rollback is unfinished; resume with --rollback")
    allowed = dict(mappings)
    seen = []
    for record in records:
        if not isinstance(record, dict):
            invalid_journal("expected a record object")
        old = record.get("old")
        if not isinstance(old, str) or old not in allowed or old in seen:
            invalid_journal("unknown or duplicate source")
        seen.append(old)
        if record.get("new") != allowed[old]:
            invalid_journal("destination does not match the application layout")
        original = Path(old)
        backup_name = str(
            original.with_name(original.name + ".before-kagnode-" + project)
        ).lstrip("/")
        if record.get("backup") != backup_name:
            invalid_journal("backup does not match the retained original path")
        stage = record.get("stage")
        if stage not in (
            "planned",
            "ready",
            "retained",
            "copying",
            "copied",
            "complete",
            "rolled-back",
        ):
            invalid_journal("unknown record stage")
        fingerprint = record.get("digest")
        if fingerprint is not None and (
            not isinstance(fingerprint, str)
            or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
        ):
            invalid_journal("invalid inventory digest")
        if (
            stage in ("ready", "retained", "copying", "copied", "complete")
            and fingerprint is None
        ):
            invalid_journal("record stage requires an inventory digest")
        if data["status"] == "complete" and not rollback_mode and stage != "complete":
            invalid_journal("completed migration contains unfinished records")
        if data["status"] == "rolled-back" and stage not in (
            "planned",
            "ready",
            "rolled-back",
        ):
            invalid_journal("rolled-back migration contains unrestored records")
        src, dst, backup = local(old), local(allowed[old]), local("/" + backup_name)
        if src.is_symlink() and src.resolve() != dst:
            invalid_journal("source link does not point to its recorded destination")
        for candidate in (dst, backup):
            if candidate.is_symlink() or (
                candidate.exists() and not candidate.is_dir()
            ):
                invalid_journal("destination and backup must be real directories")
        if src.exists() and not src.is_dir():
            invalid_journal("source is not a directory")
        if not any(p.is_dir() and not p.is_symlink() for p in (src, dst, backup)):
            invalid_journal("source, destination and retained original are all missing")
        source_real = src.is_dir() and not src.is_symlink()
        source_link = src.is_symlink()
        source_missing = not src.exists() and not source_link
        destination_real, backup_real = dst.is_dir(), backup.is_dir()
        if rollback_mode:
            if backup_real and source_real:
                invalid_journal(
                    "both source and retained original exist; rollback needs manual recovery review"
                )
            if not backup_real and not (source_real and not destination_real):
                invalid_journal(
                    "retained original is missing; rollback needs manual recovery review"
                )
            original = backup if backup_real else src
            verify_inventory = backup_real or stage not in (
                "planned",
                "ready",
                "rolled-back",
            )
        else:
            consistent = {
                "planned": source_real and not backup_real and not destination_real,
                "ready": not destination_real
                and (
                    (source_real and not backup_real)
                    or (source_missing and backup_real)
                ),
                "retained": backup_real and source_missing and not destination_real,
                "copying": backup_real and source_missing,
                "copied": backup_real
                and destination_real
                and (source_missing or source_link),
                "complete": backup_real and destination_real and source_link,
                "rolled-back": source_real and not backup_real and not destination_real,
            }
            if not consistent[stage]:
                invalid_journal("filesystem does not match the saved record stage")
            original = backup if backup_real else src
            verify_inventory = stage in (
                "ready",
                "retained",
                "copying",
                "copied",
                "complete",
            )
        if (args.apply or args.rollback) and verify_inventory:
            if fingerprint is None or original.is_symlink() or not original.is_dir():
                invalid_journal("retained original has no verifiable inventory")
            print("Verifying saved inventory for " + old, file=sys.stderr, flush=True)
            if digest(original) != fingerprint:
                invalid_journal("original inventory changed since the saved checkpoint")
        retained = record.get("retained_new")
        if retained is not None:
            prefix = allowed[old].lstrip("/") + ".after-migration-"
            if not isinstance(retained, str) or not re.fullmatch(
                re.escape(prefix) + r"[0-9]+(?:-[a-f0-9]{8})?", retained
            ):
                invalid_journal("invalid retained-write path")
            retained_path = local("/" + retained)
            if retained_path.is_symlink() or (
                retained_path.exists() and not retained_path.is_dir()
            ):
                invalid_journal("retained writes must be a real directory")
            if rollback_mode and retained_path.exists() and dst.exists():
                invalid_journal(
                    "retained-write destination already exists; nothing was overwritten"
                )
        if args.project == "mail" and not args.rollback:
            for candidate in (src, dst, backup):
                if any(
                    (candidate / name).exists() or (candidate / name).is_symlink()
                    for name in ("portal.sqlite", "PLAN.md", "data/plan.json")
                ):
                    raise RuntimeError(
                        "Detected portal data; refusing a Mail migration."
                    )
    expected_order = [
        old
        for old, _ in sorted(mappings, key=lambda pair: len(Path(pair[1]).parts))
        if old in seen
    ]
    if seen != expected_order or mappings[0][0] not in seen:
        invalid_journal("missing runtime or out-of-order records")


def main():
    global PROJECT, MAPPINGS, SERVICES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=LAYOUTS)
    parser.add_argument("--destination", type=Path, default=Path("/srv/kagnode"))
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/"),
        help="Alternate root for disposable fixture testing",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if (
        not args.destination.is_absolute()
        or ".." in args.destination.parts
        or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(args.destination))
    ):
        raise RuntimeError("Use an absolute dedicated application root.")
    PROJECT = "ecosystem-" + args.project
    mappings, SERVICES = LAYOUTS[args.project]
    MAPPINGS = [
        (old, str(args.destination / args.project / new)) for old, new in mappings
    ]
    for old, new in MAPPINGS:
        if Path(new).is_relative_to(old) or Path(old).is_relative_to(new):
            raise RuntimeError(
                "The chosen destination overlaps an existing installation path."
            )
    if not root.is_dir():
        raise RuntimeError("Root must exist.")

    def local(raw):
        p = root / raw.lstrip("/")
        for parent in p.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise RuntimeError("Symlink parent is not allowed: " + str(parent))
        return p

    manager = Manager(local(str(args.destination)), root == Path("/"), system_root=root)
    if args.apply or args.rollback:
        with manager.lock(args.project) as app:
            manager.require_recovered(
                app, read(app / "state.json", {}), allow_migration=True
            )
            check_services(root)
            migrate(args, root, local, app, manager.migration_marker(args.project))
    else:
        migrate(
            args,
            root,
            local,
            manager.project(args.project)[1],
            manager.migration_marker(args.project),
        )


def check_services(root):
    if root == Path("/"):
        if os.geteuid() != 0:
            raise RuntimeError("Root is required for a system migration.")
        active = [
            unit
            for unit in SERVICES
            if subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode
            == 0
        ]
        if active:
            raise RuntimeError(
                "Stop these services before migration: " + ", ".join(active)
            )


def migrate(args, root, local, app, shared_marker):
    journal = (
        args.journal or local("/var/lib/kagnode-migrations/" + PROJECT + ".json")
    ).absolute()
    validate_root(journal, root == Path("/"))
    protected = [app, shared_marker, shared_marker.with_name(PROJECT + ".lock")]
    for old, new in MAPPINGS:
        src = local(old)
        protected.extend(
            (src, local(new), src.with_name(src.name + ".before-kagnode-" + PROJECT))
        )
    if any(journal == path or journal.is_relative_to(path) for path in protected):
        invalid_journal(
            "journal must remain outside application files, retained originals and lock/marker paths"
        )
    marker = app / "migration.json"
    identity = {
        "project": PROJECT,
        "journal": str(journal.absolute()),
        "destination": str(args.destination),
    }
    for candidate in (marker, shared_marker):
        if candidate.exists() and load_journal(candidate) != identity:
            raise RuntimeError(
                "Unfinished migration belongs to another journal or destination. Resume or roll back its recorded journal first."
            )
    if journal.exists():
        data = load_journal(journal)
    else:
        if args.rollback:
            invalid_journal("no saved migration exists to roll back")
        records = []
        expected = {
            "mail": "/opt/kagnode/mail/kagnode/web.py",
            "vpn": "/opt/kagnode/vpn/manage.py",
            "httpboot": "/opt/kagnode/httpboot/source/httpboot/server_v2.py",
        }
        if not local(expected[args.project]).is_file():
            raise RuntimeError(
                "Expected project installation not found; no data was moved."
            )
        for old, new in sorted(MAPPINGS, key=lambda pair: len(Path(pair[1]).parts)):
            src, dst = local(old), local(new)
            if not src.exists() and not src.is_symlink():
                continue
            if src.is_symlink():
                raise RuntimeError(
                    "Legacy source is already a symlink; inspect existing migration: "
                    + old
                )
            if not src.is_dir():
                raise RuntimeError("Expected a directory: " + old)
            if dst.exists() or dst.is_symlink():
                raise RuntimeError("Destination already exists: " + new)
            backup = src.with_name(src.name + ".before-kagnode-" + PROJECT)
            if backup.exists():
                raise RuntimeError(
                    "A retained original already exists; resume using its journal."
                )
            records.append(
                {
                    "old": old,
                    "new": new,
                    "backup": str(backup.relative_to(root)),
                    "stage": "planned",
                }
            )
        for parent in records:
            for child in records:
                a, b = Path(parent["new"]), Path(child["new"])
                if a != b and b.is_relative_to(a):
                    reserved = local(parent["old"]) / b.relative_to(a)
                    if reserved.exists() or reserved.is_symlink():
                        raise RuntimeError(
                            "Overlapping destination content requires manual review: "
                            + str(reserved)
                        )
        data = {
            "schema": 1,
            "project": PROJECT,
            "root": str(root),
            "destination": str(args.destination),
            "created": int(time.time()),
            "records": records,
            "status": "planned",
        }
    validate_journal(data, args, root, local)
    print(json.dumps(data, indent=2))
    if not args.apply and not args.rollback:
        return
    journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save():
        atomic(journal, data)
        Manager.sync_directory(journal.parent)

    if data["status"] == "rolled-back" and not args.rollback:
        raise RuntimeError(
            "This journal has been rolled back. Archive it before planning a new migration."
        )
    if args.rollback:
        data["status"] = "rolling-back"
    atomic(shared_marker, identity)
    Manager.sync_directory(shared_marker.parent)
    atomic(marker, identity)
    Manager.sync_directory(app)
    save()
    for record in reversed(data["records"]) if args.rollback else data["records"]:
        src, dst = local(record["old"]), local(record["new"])
        backup = root / record["backup"]
        if args.rollback:
            if not backup.exists():
                record["stage"] = "rolled-back"
                save()
                continue
            # Keep post-migration writes in a quarantine tree; never delete user data.
            if src.is_symlink():
                src.unlink()
            if dst.exists():
                retained = (
                    local("/" + record["retained_new"])
                    if record.get("retained_new")
                    else dst.with_name(
                        dst.name
                        + ".after-migration-"
                        + str(int(time.time()))
                        + "-"
                        + os.urandom(4).hex()
                    )
                )
                if retained.exists() or retained.is_symlink():
                    invalid_journal(
                        "retained-write destination already exists; nothing was overwritten"
                    )
                record["retained_new"] = str(retained.relative_to(root))
                save()  # Persist the quarantine path before moving user writes.
                dst.rename(retained)
            if src.exists() or src.is_symlink():
                invalid_journal(
                    "source unexpectedly reappeared; rollback needs manual recovery review"
                )
            src.parent.mkdir(parents=True, exist_ok=True)
            backup.rename(src)
            record["stage"] = "rolled-back"
            save()
            continue
        if record["stage"] == "complete":
            continue
        if record["stage"] == "planned":
            size = sum(
                p.stat().st_size
                for p in src.rglob("*")
                if p.is_file() and not p.is_symlink()
            )
            destination_parent = dst.parent
            while not destination_parent.exists():
                destination_parent = destination_parent.parent
            if shutil.disk_usage(destination_parent).free < size + 1024 * 1024 * 1024:
                raise RuntimeError(
                    "Insufficient destination space for verified copying; original retained."
                )
            record["digest"] = digest(src)
            record["stage"] = "ready"
            save()
        if record["stage"] == "ready":
            if not backup.exists():
                src.rename(backup)
            record["stage"] = "retained"
            save()
        if record["stage"] == "retained":
            if dst.exists() or dst.is_symlink():
                raise RuntimeError(
                    "Unexpected destination exists; original retained: " + str(dst)
                )
            record["stage"] = "copying"
            save()
        if record["stage"] == "copying":
            if dst.is_symlink():
                raise RuntimeError("Destination cannot be a symlink.")
            dst.parent.mkdir(parents=True, exist_ok=True)
            # cp -a preserves file owners, modes, timestamps and links. Retry merges
            # only this journal's interrupted copy, never an unrelated destination.
            dst.mkdir(exist_ok=True)
            subprocess.run(
                ["cp", "-a", "--reflink=auto", str(backup) + "/.", str(dst)], check=True
            )
            if digest(dst) != record["digest"]:
                raise RuntimeError("Copied data did not verify; original retained.")
            record["stage"] = "copied"
            save()
        if record["stage"] == "copied":
            if dst.is_relative_to(src):
                for child in backup.iterdir():
                    target = src / child.name
                    if target.exists() or target.is_symlink():
                        continue
                    target.symlink_to(
                        os.path.relpath(dst / child.name, target.parent),
                        target_is_directory=child.is_dir(),
                    )
            elif not src.exists() and not src.is_symlink():
                src.symlink_to(
                    os.path.relpath(dst, src.parent), target_is_directory=True
                )
            record["stage"] = "complete"
            save()
    data["status"] = "rolled-back" if args.rollback else "complete"
    save()
    marker.unlink()
    Manager.sync_directory(app)
    shared_marker.unlink()
    Manager.sync_directory(shared_marker.parent)
    print(
        "Migration "
        + data["status"]
        + ". Original data retained; no service was started. Install the matching release, review configuration, then start and verify services explicitly."
    )


if __name__ == "__main__":
    try:
        main()
    except (
        ManagerError,
        RuntimeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        raise SystemExit(str(error))
