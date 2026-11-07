"""Fetch the upstream corpora at pinned commits and fingerprint the files used.

Each source is a sparse, blob-filtered clone that materialises only the files
matched by `patterns`, so ~400 MB of ART binaries are never downloaded.
"""
from __future__ import annotations

import glob
import hashlib
import os
import subprocess


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          capture_output=True).stdout.strip()


def fetch(name, spec, root):
    """Ensure `root/name` is checked out at spec['commit']; return its path."""
    d = os.path.join(root, name)
    if not os.path.isdir(os.path.join(d, ".git")):
        os.makedirs(d, exist_ok=True)
        _git("init", "-q", cwd=d)
        _git("remote", "add", "origin", spec["url"], cwd=d)
        _git("sparse-checkout", "set", "--no-cone", *spec["patterns"], cwd=d)
    if _head(d) != spec["commit"]:
        _git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", spec["commit"], cwd=d)
        _git("checkout", "-q", "--detach", spec["commit"], cwd=d)
    head = _head(d)
    if head != spec["commit"]:
        raise RuntimeError(f"{name}: expected {spec['commit']}, got {head}")
    return d


def _head(d):
    try:
        return _git("rev-parse", "HEAD", cwd=d)
    except subprocess.CalledProcessError:
        return None


def fingerprint(path, patterns):
    """SHA-256 over (relative path, file SHA-256) of every file matching patterns."""
    files = sorted({os.path.relpath(f, path) for p in patterns
                    for f in glob.glob(os.path.join(path, p)) if os.path.isfile(f)})
    h = hashlib.sha256()
    for rel in files:
        h.update(rel.encode() + b"\0" + sha256_file(os.path.join(path, rel)).encode() + b"\n")
    return dict(n_files=len(files), sha256=h.hexdigest())


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
