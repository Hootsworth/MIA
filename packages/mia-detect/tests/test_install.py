import os
import subprocess
import sys
from pathlib import Path


def test_installs_and_imports_without_project_dependencies(tmp_path):
    project = Path(__file__).resolve().parents[1]
    target = tmp_path / "installed"
    env = {**os.environ, "PYTHONPATH": str(target)}
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "--target", str(target), str(project)],
        check=True, capture_output=True, text=True, env=env,
    )
    result = subprocess.run(
        [sys.executable, "-c", "import mia_detect; from mia_detect.similarity import normalize_text, fingerprint_text; print(mia_detect.__version__, len(fingerprint_text(normalize_text('One two three four five six seven eight.'))))"],
        check=True, capture_output=True, text=True, env=env,
    )
    assert result.stdout.strip().startswith("0.1.0 ")
    cli = subprocess.run(
        [sys.executable, "-m", "mia_detect", "--help"],
        check=True, capture_output=True, text=True, env=env,
    )
    assert "index" in cli.stdout and "check" in cli.stdout
