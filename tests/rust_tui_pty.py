"""Real Rust terminal navigation, resizing, cancellation and terminal restoration."""

from pathlib import Path
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
binary = Path(
    os.environ.get("KAGNODE_RUST_BINARY", str(ROOT / "target/debug/kagnode"))
).resolve()
with tempfile.TemporaryDirectory(prefix="kagnode-rust-tui-") as temporary:
    folder = Path(temporary)
    password = folder / "password"
    password.write_text("fixture-long-terminal-password")
    password.chmod(0o600)
    state = folder / "controller"
    subprocess.run(
        [
            str(binary),
            "--root",
            str(state),
            "init",
            "--email",
            "owner@fixture.invalid",
            "--password-file",
            str(password),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    marker = folder / "application-data"
    marker.write_text("retained")
    for width, height in [(30, 10), (80, 24), (140, 40)]:
        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))
        process = subprocess.Popen(
            [str(binary), "--root", str(state), "tui", "--no-mouse"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env={**os.environ, "TERM": "xterm-256color"},
            start_new_session=True,
        )
        output = bytearray()

        def drain(seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        output.extend(os.read(master, 65536))
                    except OSError:
                        break

        try:
            drain(0.5)
            assert process.poll() is None
            assert b"KagNode. Daemon" in output
            os.write(master, b"/netctl\r")
            drain(0.3)
            # Browse, scroll and cancel; service-changing keys are deliberately absent.
            os.write(master, b"\x1b[6~\x1b[5~\x1b[D")
            drain(0.3)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 16, 55, 0, 0))
            process.send_signal(signal.SIGWINCH)
            drain(0.3)
            os.write(master, b"\x03")
            process.wait(timeout=5)
            drain(0.1)
            assert process.returncode == 0
            assert termios.tcgetattr(slave) == before, "terminal settings leaked"
            assert b"\x1b[?1000h" not in output and b"\x1b[?1006h" not in output
            assert marker.read_text() == "retained"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)
print(
    "PASS Rust terminal at 30/80/140 columns; search, folders, resize, Ctrl+C and restoration"
)
