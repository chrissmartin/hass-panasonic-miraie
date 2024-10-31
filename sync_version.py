#!/usr/bin/env python3
# ruff: noqa: T201
"""Script to synchronize version numbers from git tag across project files."""

import json
import os
from pathlib import Path
import re
import sys


def get_version_from_tag():
    """Get version from git tag, removing 'v' prefix."""
    tag = os.environ.get("TAG")
    if not tag:
        print("No TAG environment variable found")
        sys.exit(1)

    # Remove 'v' prefix if present
    version = tag[1:] if tag.startswith("v") else tag

    # Validate version format
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        print(f"Invalid version format: {version}. Expected format: vX.Y.Z")
        sys.exit(1)
    return version


def update_manifest_version(manifest_path, new_version):
    """Update version in manifest.json."""
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        manifest["version"] = new_version

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")  # Add newline at end of file

        return True
    except Exception as e:
        print(f"Error updating manifest.json: {e}")
        return False


def update_pyproject_version(pyproject_path, new_version):
    """Update version in pyproject.toml."""
    try:
        with open(pyproject_path) as f:
            content = f.read()

        # Replace version using regex
        new_content = re.sub(
            r'version\s*=\s*"[^"]+"', f'version = "{new_version}"', content
        )

        with open(pyproject_path, "w") as f:
            f.write(new_content)

        return True
    except Exception as e:
        print(f"Error updating pyproject.toml: {e}")
        return False


def main():
    """Synchronize versions."""
    # Get version from git tag
    version = get_version_from_tag()
    print(f"Using version from tag: {version}")

    # Get project root directory
    project_root = Path(__file__).parent

    # Define file paths
    manifest_path = project_root / "custom_components/panasonic_miraie/manifest.json"
    pyproject_path = project_root / "pyproject.toml"

    # Update manifest.json
    if update_manifest_version(manifest_path, version):
        print(f"Successfully updated manifest.json to version {version}")
    else:
        print("Failed to update manifest.json")
        sys.exit(1)

    # Update pyproject.toml
    if update_pyproject_version(pyproject_path, version):
        print(f"Successfully updated pyproject.toml to version {version}")
    else:
        print("Failed to update pyproject.toml")
        sys.exit(1)


if __name__ == "__main__":
    main()
