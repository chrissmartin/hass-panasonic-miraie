#!/usr/bin/env python3
# ruff: noqa: T201

"""Script to synchronize version numbers from git tag across project files."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import tomlkit


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
        print(f"Invalid version format: {version}. Expected format: X.Y.Z")
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
        # Read the TOML file preserving the formatting
        with open(pyproject_path, encoding="utf-8") as f:
            toml_content = f.read()
            pyproject_data = tomlkit.parse(toml_content)

        # Update the version field under the [project] section
        pyproject_data["project"]["version"] = new_version

        # Write the updated data back to the file preserving formatting
        with open(pyproject_path, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(pyproject_data))

        return True
    except Exception as e:
        print(f"Error updating pyproject.toml: {e}")
        return False


def get_git_root():
    """Get the root directory of the git repository."""
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], encoding="utf-8"
        ).strip()
        return Path(git_root)
    except subprocess.CalledProcessError:
        print(
            "Failed to find git repository root. Ensure this script is run within a git repository."
        )
        sys.exit(1)


def main():
    """Synchronize versions."""
    # Get version from git tag
    version = get_version_from_tag()
    print(f"Using version from tag: {version}")

    # Get project root directory using git repository root
    project_root = get_git_root()

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
