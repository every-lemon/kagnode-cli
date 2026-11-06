#!/usr/bin/env python3
"""Check or format human-editable Python, Go and JSON without generated assets."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {"src/vpn_ui_assets.py", "httpboot/server_web_assets.py"}


def run(check):
    files = json.loads((ROOT / "packaging/source-files.json").read_text())
    python = [
        name
        for name in files
        if name.endswith(".py")
        and name not in GENERATED
        and not any(part in name.split("/") for part in ["vendor", "assets"])
    ]
    if python:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                *(["--check"] if check else []),
                *python,
            ],
            cwd=ROOT,
            check=True,
        )
    go = [name for name in files if name.endswith(".go")]
    if go:
        if check:
            result = subprocess.check_output(["gofmt", "-l", *go], cwd=ROOT, text=True)
            if result.strip():
                raise ValueError("Run gofmt on: " + result)
        else:
            subprocess.run(["gofmt", "-w", *go], cwd=ROOT, check=True)
    for name in files:
        if (
            not name.endswith(".json")
            or name in {"package-lock.json"}
            or "built/" in name
        ):
            continue
        path = ROOT / name
        formatted = (
            json.dumps(json.loads(path.read_text()), indent=2, ensure_ascii=False)
            + "\n"
        )
        if check and path.read_text() != formatted:
            raise ValueError("JSON needs formatting: " + name)
        if not check:
            path.write_text(formatted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    run(parser.parse_args().check)
