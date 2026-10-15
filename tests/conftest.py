import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hookup_planner import scenario  # noqa: E402
from hookup_planner.planner import plan  # noqa: E402


def small_config():
    cfg = copy.deepcopy(scenario.load_config())
    cfg.update({"name": "small", "seed": 314, "bays_x": 3, "bays_y": 3, "n_existing_tools": 3, "n_new_tools": 3})
    return cfg


@pytest.fixture(scope="session")
def rates():
    return scenario.load_rates()


@pytest.fixture(scope="session")
def small_site(rates):
    return scenario.generate(small_config(), rates)


@pytest.fixture(scope="session")
def small_plan(small_site, rates):
    return plan(small_site, rates)
