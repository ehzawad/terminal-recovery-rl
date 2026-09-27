"""Freeze the sealed test rows once, before any arm is evaluated on test (amendments A5, A6).

Writes the primary rows (faulted configurations for the recovery headline, clean ones for the collateral
headline; 4 configurations per task, 1 attempt), the held-out FIFO rows (2 per task) and the clean retention
rows (2 per task), then records sha256 identities of every rows file, the frozen contracts, the validity
records and the split in results/test_rows_manifest.json. Refuses to run if the manifest already exists.

Usage: python scripts/freeze_test_rows.py --headline recovery_failure
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

PY = sys.executable
MANIFEST = "results/test_rows_manifest.json"


def sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def rows(families: str, configs: int, out: str) -> None:
    subprocess.run([PY, "scripts/make_rows.py", "--partition", "test", "--families", families,
                    "--configs-per-task", str(configs), "--attempts", "1", "--salt", "test-v4", "--out", out], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headline", choices=["recovery_failure", "collateral"], required=True)
    args = ap.parse_args()
    if os.path.exists(MANIFEST):
        sys.exit(f"{MANIFEST} exists: test rows are already frozen")
    os.makedirs("data/rows", exist_ok=True)
    files = {"primary": "data/rows/test_primary.jsonl", "heldout_fifo": "data/rows/test_heldout_fifo.jsonl",
             "clean": "data/rows/test_clean.jsonl"}
    rows("train" if args.headline == "recovery_failure" else "clean", 4, files["primary"])
    rows("heldout", 2, files["heldout_fifo"])
    rows("clean", 2, files["clean"])
    manifest = {"headline": args.headline,
                "rows": {k: {"path": p, "sha256": sha(p), "rows": sum(1 for _ in open(p))} for k, p in files.items()},
                "contracts": {"path": "data/contracts_v4_frozen.jsonl", "sha256": sha("data/contracts_v4_frozen.jsonl")},
                "split": {"path": "data/splits_v1.json", "sha256": sha("data/splits_v1.json")}}
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=1)
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
