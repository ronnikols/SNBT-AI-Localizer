import subprocess

def test_snbt_tr_in_path():
    result = subprocess.run(
        ["snbt-tr", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "snbt" in result.stdout.lower()
