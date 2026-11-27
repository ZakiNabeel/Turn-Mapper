#!/usr/bin/env bash
# Create the release tags on your machine and push them (tag pushes are blocked from the cloud session).
# Run once from the repo root:  bash scripts/create_release_tags.sh   (on Windows: Git Bash)
# Then on GitHub: Releases -> Draft a new release -> pick v0.4.0 -> paste docs/RELEASE_NOTES_v0.4.0.md.
set -euo pipefail
git fetch origin
git tag -a v0.1.0 ae395f6 -m "v0.1.0: M1 skeleton + contract draft + M2 classical chain, first FAST results" 2>/dev/null || true
git tag -a v0.2.0 5d092b1 -m "v0.2.0: C block features, 14/14 FAST floors valid" 2>/dev/null || true
git tag -a v0.3.0 e00ee57 -m "v0.3.0: style-generic segmentation, JSON output (contract 0.1.1), learned segmenter scaffold, ground-truth eval, mid-eval package" 2>/dev/null || true
git tag -a v0.4.0 047e726 -m "v0.4.0: FYP-1 final - Studio (FR-19), multi-floor + multi-building routing (FR-18, contract 0.1.3), scale from measurements, learned S4 on real CAD (classical stays default). Notes: docs/RELEASE_NOTES_v0.4.0.md" 2>/dev/null || true
git push origin v0.1.0 v0.2.0 v0.3.0 v0.4.0
git tag -n1 | sort -V
