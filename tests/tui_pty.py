"""Keyboard-only real-manager TUI with disposable config/root, no installs."""

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
with tempfile.TemporaryDirectory(prefix="kagnode-tui-") as temporary:
    folder = Path(temporary)
    binary = folder / "kagnode"
    subprocess.run(["go", "build", "-o", str(binary), "."], cwd=ROOT, check=True)
    for width, height in [(30, 10), (80, 24), (140, 40)]:
        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))
        env = {
            **os.environ,
            "TERM": "xterm-256color",
            "XDG_CONFIG_HOME": str(folder / "config"),
            "XDG_DATA_HOME": str(folder / "data"),
            "KAGNODE_ROOT": str(folder / "apps"),
        }
        process = subprocess.Popen(
            [str(binary), "tui"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            start_new_session=True,
        )
        output = bytearray()

        def collect(until):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    output.extend(os.read(master, 65536))
                    if until in output:
                        return
                if process.poll() is not None:
                    break
            assert until in output, "expected terminal state missing"

        try:
            collect(b"KagNode. CLI")
            os.write(master, b"/help\r")
            collect(b"installer plan.")
            os.write(master, b"/catalog\r")
            collect(b"core  Core")
            assert (
                b"Fictional examples" not in output
                and b"PRODUCT EXAMPLES" not in output
            )
            assert b"\x1b[?1000h" not in output and b"\x1b[?1006h" not in output
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 12, 40, 0, 0))
            process.send_signal(signal.SIGWINCH)
            time.sleep(0.1)
            os.write(master, b"\x03")
            process.wait(timeout=5)
            assert process.returncode == 0
            assert termios.tcgetattr(slave) == before, "raw terminal settings leaked"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)
print(
    "PASS keyboard-only PTY manager at30/80/140 columns; resize, command, exit and terminal restoration"
)
