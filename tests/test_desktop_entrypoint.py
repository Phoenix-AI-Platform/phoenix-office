"""Packaging-only desktop entry point checks; never start Tk in CI."""

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_entrypoints_and_existing_package_contract() -> None:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document["project"]
    assert project["scripts"] == {"phoenix-office": "phoenix_office.cli:main"}
    assert project["gui-scripts"] == {
        "phoenix-office-desktop": "phoenix_office.proposal_desktop:main"
    }
    assert project["name"] == "phoenix-office"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.12"
    assert project["dependencies"] == [
        "phoenix-sdk @ git+https://github.com/Phoenix-AI-Platform/phoenix-sdk.git"
        "@972770eb68d51a4f476bb03d67b1dab56f5b8b5c",
        "pydantic>=2.0",
        "python-docx>=1.1",
    ]
    assert project["optional-dependencies"] == {"dev": ["pytest>=7.0", "ruff>=0.3"]}
    assert document["build-system"] == {
        "requires": ["setuptools>=68"], "build-backend": "setuptools.build_meta"
    }


def test_desktop_target_is_callable_and_import_does_not_load_tk() -> None:
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys; "
            "import phoenix_office.proposal_desktop as desktop; "
            "assert callable(desktop.main); "
            "assert not any(k == 'tkinter' or k.startswith('tkinter.') for k in sys.modules)"
        )],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_readme_documents_supported_launch_paths_and_limits() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m phoenix_office.proposal_desktop" in readme
    assert "python -m pip install -e . --no-deps" in readme
    assert "\nphoenix-office-desktop\n" in readme
    assert "not a standalone portable EXE or frozen installer" in readme
    assert "does not automatically\ncreate a Windows Desktop shortcut" in readme
    assert "After acceptance, an operator may explicitly" in readme
