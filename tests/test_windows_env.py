import subprocess
import pytest

@pytest.mark.skip(reason="Windows-specific test")
def test_snbt_tr_in_path():
    import os
    # Get the absolute path to the snbt-tr executable
    snbt_tr_path = os.path.abspath("snbt-tr")
    
    result = subprocess.run(
        [snbt_tr_path, "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "snbt" in result.stdout.lower()
