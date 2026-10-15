"""Reproduce every file in results/ (run from the repository root)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hookup_planner.pipeline import run  # noqa: E402

if __name__ == "__main__":
    s = run(ROOT / "results", ROOT / "build")
    print(f"{s['hookups_routed']} hookups routed, {s['astar_clashes']} clashes; results written to results/")
