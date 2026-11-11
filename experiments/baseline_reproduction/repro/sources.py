"""Fetch the upstream corpora at pinned commits and fingerprint the files used.

Each source is a sparse, blob-filtered clone that materialises only the files matched by
`patterns`, so about 400 MB of Atomic Red Team binaries are never downloaded.

    directories = sources.fetch_all(configuration)   # {"art": ..., "redcode": ..., "nl2bash": ..., "older_art": ...}
"""
from __future__ import annotations

import glob
import hashlib
import os
import subprocess

from .configuration import EXPERIMENT

DIRECTORY_OF = {   # name in config.yaml -> name used by the corpus loaders
    "atomic-red-team": "art",
    "RedCode": "redcode",
    "nl2bash": "nl2bash",
    "atomic-red-team-2026-03-24": "older_art",   # construction variant V3 only
}


def fetch_all(configuration):
    """Clone every corpus at its pinned commit and require its fingerprint to match config.yaml."""
    root = os.path.join(EXPERIMENT, "data", "sources")
    directories = {}
    for name, pin in configuration["sources"].items():
        directory = fetch(name, pin, root)
        found = fingerprint(directory, pin["patterns"])
        assert found == pin["fingerprint"], f"{name}: fingerprint {found} differs from config.yaml"
        print(f"✓ {name} at {pin['commit'][:10]}: {found['n_files']} files, fingerprint verified")
        directories[DIRECTORY_OF[name]] = directory
    return directories


def fetch(name, pin, root):
    """Ensure `root/name` is checked out at pin['commit']; return its path."""
    directory = os.path.join(root, name)
    if not os.path.isdir(os.path.join(directory, ".git")):
        os.makedirs(directory, exist_ok=True)
        _git("init", "-q", cwd=directory)
        _git("remote", "add", "origin", pin["url"], cwd=directory)
        _git("sparse-checkout", "set", "--no-cone", *pin["patterns"], cwd=directory)
    if _head(directory) != pin["commit"]:
        _git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", pin["commit"], cwd=directory)
        _git("checkout", "-q", "--detach", pin["commit"], cwd=directory)
    if _head(directory) != pin["commit"]:
        raise RuntimeError(f"{name}: expected {pin['commit']}, got {_head(directory)}")
    return directory


def fingerprint(directory, patterns):
    """SHA-256 over (relative path, file SHA-256) of every file matching `patterns`."""
    files = sorted({os.path.relpath(path, directory)
                    for pattern in patterns
                    for path in glob.glob(os.path.join(directory, pattern))
                    if os.path.isfile(path)})
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode() + b"\0" + sha256_file(os.path.join(directory, relative)).encode() + b"\n")
    return dict(n_files=len(files), sha256=digest.hexdigest())


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*arguments, cwd=None):
    return subprocess.run(["git", *arguments], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def _head(directory):
    try:
        return _git("rev-parse", "HEAD", cwd=directory)
    except subprocess.CalledProcessError:
        return None
