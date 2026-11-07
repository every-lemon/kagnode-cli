#!/usr/bin/env python3
"""Format first-party browser source; generated bundles and fixtures stay separate."""

import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(check):
    files = json.loads((ROOT / "packaging/source-files.json").read_text())
    selected = [
        name
        for name in files
        if name.endswith((".js", ".css"))
        and "/built/" not in name
        and not name.startswith(("assets/frame-", "assets/kn-core-", "vendor/"))
    ]
    selected += [
        name
        for name in files
        if name
        in {"web/gallery.html", "web/index.html", "authentactor/static/index.html"}
    ]
    if not selected:
        return
    command = (
        [os.environ["PRETTIER"]]
        if os.environ.get("PRETTIER")
        else ["npx", "--yes", "--package=prettier@3.7.4", "prettier"]
    )
    subprocess.run(
        command
        + [
            "--check" if check else "--write",
            "--embedded-language-formatting=off",
            *selected,
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    run(parser.parse_args().check)
