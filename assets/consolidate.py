#!/usr/bin/env python3
"""Explicit, journaled KagNode path migration. Dry-run by default; no service restart."""

import argparse, hashlib, json, os, shutil, subprocess, time
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
        or not __import__("re").fullmatch(r"/[A-Za-z0-9_./-]+", str(args.destination))
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
    if root == Path("/") and (args.apply or args.rollback):
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

    def local(raw):
        p = root / raw.lstrip("/")
        for parent in p.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise RuntimeError("Symlink parent is not allowed: " + str(parent))
        return p

    journal = args.journal or local("/var/lib/kagnode-migrations/" + PROJECT + ".json")
    if journal.is_symlink():
        raise RuntimeError("Journal must not be a symlink.")
    if journal.exists():
        data = json.loads(journal.read_text())
        if (
            data.get("project") != PROJECT
            or data.get("root") != str(root)
            or data.get("destination") != str(args.destination)
        ):
            raise RuntimeError("Journal belongs to another project/root.")
    else:
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
            if (
                PROJECT == "mail"
                and old == "/opt/kagnode"
                and not (src / "kagnode/web.py").is_file()
            ):
                raise RuntimeError(
                    "The old /opt/kagnode is not a Mail installation. Refusing to touch another project."
                )
            if PROJECT == "mail" and any(
                (src / p).exists()
                for p in ["portal.sqlite", "PLAN.md", "data/plan.json"]
            ):
                raise RuntimeError("Detected portal data; refusing a Mail migration.")
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
            "project": PROJECT,
            "root": str(root),
            "destination": str(args.destination),
            "created": int(time.time()),
            "records": records,
            "status": "planned",
        }
    print(json.dumps(data, indent=2))
    if not args.apply and not args.rollback:
        return
    journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save():
        temp = journal.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n")
        temp.chmod(0o600)
        os.replace(temp, journal)

    if data["status"] == "rolled-back" and not args.rollback:
        raise RuntimeError(
            "This journal has been rolled back. Archive it before planning a new migration."
        )
    save()
    for record in reversed(data["records"]) if args.rollback else data["records"]:
        src, dst = local(record["old"]), local(record["new"])
        backup = root / record["backup"]
        if args.rollback:
            if not backup.exists():
                continue
            # Keep post-migration writes in a quarantine tree; never delete user data.
            if src.is_symlink():
                src.unlink()
            if dst.exists():
                retained = dst.with_name(
                    dst.name + ".after-migration-" + str(int(time.time()))
                )
                dst.rename(retained)
                record["retained_new"] = str(retained.relative_to(root))
            if src.exists():
                # Nested layouts may leave only compatibility links in the old parent.
                if any(not p.is_symlink() for p in src.iterdir()):
                    retained = src.with_name(
                        src.name + ".migration-container-" + str(int(time.time()))
                    )
                    src.rename(retained)
                else:
                    for p in src.iterdir():
                        p.unlink()
                    src.rmdir()
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
    print(
        "Migration "
        + data["status"]
        + ". Original data retained; no service was started. Install the matching release, review configuration, then start and verify services explicitly."
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
