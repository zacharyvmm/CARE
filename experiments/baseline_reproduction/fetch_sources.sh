#!/usr/bin/env bash
# Clone the three public corpora at the exact commits used for the committed results.
set -euo pipefail
cd "$(dirname "$0")/data" && mkdir -p raw && cd raw
fetch() {  # name url commit
  [ -d "$1" ] || git clone -q --filter=blob:none "$2" "$1"
  git -C "$1" fetch -q --depth 1 origin "$3" && git -C "$1" checkout -q "$3"
  echo "$1 @ $(git -C "$1" rev-parse HEAD)"
}
fetch atomic-red-team https://github.com/redcanaryco/atomic-red-team a0e3f9bc69fed2fd711bd1f1aa87a40c33482fe6
fetch RedCode         https://github.com/AI-secure/RedCode          664e4793dc7309f98b8271baed5bbc04d6ef4c39
fetch nl2bash         https://github.com/TellinaTool/nl2bash        d6b9f5bdff45621d190134e31ab63b7bf7002190
# Sensitivity variant V3 (older ART snapshot) -- optional:
#   git -C atomic-red-team worktree add ../art-2026-03-24 40a54bf631ced8799676680d78eff30db90abb80
#   CARE_ART_SNAPSHOT=$PWD/art-2026-03-24 python ../../analyze.py
