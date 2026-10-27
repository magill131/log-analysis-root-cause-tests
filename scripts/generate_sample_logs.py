"""Write the two sample logs in data/: one with an incident after the deploy, one without."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from generator import generate_logs  # noqa: E402

SEED = 7

if __name__ == "__main__":
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    for name, incident in (("incident.log", True), ("clean.log", False)):
        lines = generate_logs(seed=SEED, incident=incident)
        (data / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {data / name} ({len(lines)} lines)")
