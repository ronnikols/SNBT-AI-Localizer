import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_cli_help_starts():
    """The CLI entry point (snbt-tr = cli:main) starts and prints its usage."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "cli.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()
