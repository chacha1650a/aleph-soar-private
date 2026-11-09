"""Build/check D workflow exports without touching credentials or running n8n."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infra/n8n/workflows"


def build(folder):
    env = {**os.environ, "ALEPH_N8N_OUTPUT": str(folder), "PYTHONIOENCODING": "utf-8"}
    # These legacy generators import the base generator; order is intentional.
    for name in ("gen_n8n_workflows.py", "gen_n8n_cases.py", "gen_n8n_actions.py", "gen_n8n_stage2.py"):
        subprocess.run([sys.executable, str(ROOT / "tools" / name)], cwd=ROOT,
                       env=env, check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aleph-n8n-build-") as name:
        folder = Path(name)
        build(folder)
        changed = []
        for source in sorted(folder.glob("*.json")):
            target = OUT / source.name
            if not target.exists() or target.read_bytes() != source.read_bytes():
                changed.append(source.name)
                if not args.check:
                    target.write_bytes(source.read_bytes())
        if args.check and changed:
            print("Stale n8n exports: " + ", ".join(changed))
            return 1
        print(f"n8n exports {'verified' if args.check else 'built'}: {len(list(folder.glob('*.json')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
