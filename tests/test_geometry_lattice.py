import heapq
import math
import random

import numpy as np
import pytest

from hookup_planner.geometry import Solid, box_gap, find_clashes, polyline_solids, segment_solid, surface_gap
from hookup_planner.lattice import BEND_COST, DIRS, STEP_COST, UP, Lattice, bends, compress, length


def test_box_gap_and_surface_gap():
    assert box_gap((0, 0, 0), (1, 1, 1), (1.7, 1.24, 0.5), (2, 2, 2)) == pytest.approx(math.sqrt(0.49 + 0.0576))
    assert box_gap((0, 0, 0), (1, 1, 1), (0.5, 0.5, 0.5), (3, 3, 3)) == 0.0
    a = Solid("a", "route", (0, 0, 0), (4, 0, 0), 0.07)
    b = Solid("b", "header", (2, 0.3, 0), (2, 0.3, 5), 0.11)
    assert surface_gap(a, b) == pytest.approx(0.3 - 0.18)


def test_segment_must_be_axis_aligned():
    with pytest.raises(ValueError):
        segment_solid("x", (0, 0, 0), (1, 1, 0), 0.1, "x")


def test_find_clashes_types_and_exemptions():
    existing = [Solid("COL", "column", (1.75, -0.25, 0), (2.25, 0.25, 6), 0.0)]
    hard = polyline_solids("H1", [(0, 0, 3), (4, 0, 3)], 0.05)            # through the column
    near = polyline_solids("H2", [(0, 0.33, 3.5), (4, 0.33, 3.5)], 0.05)   # 0.03 m from column face
    far = polyline_solids("H3", [(0, 1.5, 1), (0, 1.5, 4)], 0.05)
    own = polyline_solids("H3", [(0, 1.5, 4), (3, 1.5, 4)], 0.05)          # same hookup, touching
    para = polyline_solids("H4", [(0, -0.12, 3), (1, -0.12, 3)], 0.05)     # 0.02 m from H1, stops short of COL
    cl = find_clashes(hard + near + far + own + para, existing, 0.05)
    kinds = {(c["a"], c["b"]): c["type"] for c in cl}
    assert kinds[("H1#0", "COL")] == "hard"
    assert kinds[("H2#0", "COL")] == "clearance"
    assert kinds[("H1#0", "H4#0")] == "clearance"
    assert ("H4#0", "H1#0") not in kinds
    assert ("H1#0", "H2#0") not in kinds and ("H4#0", "COL") not in kinds
    assert len(cl) == 3
    assert not any("H3" in c["a"] and "H3" in c["b"] for c in cl)
    assert not any(c["a"].startswith("H3") or c["b"].startswith("H3") for c in cl)
    ex = find_clashes(hard, existing, 0.05, exempt=lambda a, b: b.eid == "COL")
    assert ex == []


def test_compress_bends_length():
    pts = [(0, 0, 0), (0, 0, 0.6), (0, 0, 1.2), (0.6, 0, 1.2), (1.2, 0, 1.2), (1.2, 1.8, 1.2)]
    c = compress(pts)
    assert c == [(0, 0, 0), (0, 0, 1.2), (1.2, 0, 1.2), (1.2, 1.8, 1.2)]
    assert bends(pts) == 2
    assert length(pts) == pytest.approx(4.2)


def reference_cost(lat, free, start, start_dir, goal):
    """Plain Dijkstra over (node, direction) states: the ground truth for A*."""
    best = {(start, start_dir): 0}
    pq = [(0, start, start_dir)]
    while pq:
        g, n, d = heapq.heappop(pq)
        if best[(n, d)] != g:
            continue
        if n == goal:
            return g
        i, j, k = lat.ijk(n)
        for nd, (di, dj, dk) in enumerate(DIRS):
            a, b, c = i + di, j + dj, k + dk
            if not (0 <= a < lat.nx and 0 <= b < lat.ny and 0 <= c < lat.nz):
                continue
            m = lat.node(a, b, c)
            if not free[m] or (m == goal and nd != UP):
                continue
            g2 = g + STEP_COST + (BEND_COST if nd != d else 0)
            if g2 < best.get((m, nd), 1 << 60):
                best[(m, nd)] = g2
                heapq.heappush(pq, (g2, m, nd))
    return None


@pytest.mark.parametrize("seed", [3, 17, 29, 41, 58])
def test_astar_is_optimal_against_dijkstra(seed):
    rng = random.Random(seed)
    lat = Lattice(0.6, 9, 7, 5, 1, 3)
    free = bytearray(1 if (lat.kmin <= lat.ijk(n)[2] <= lat.kmax and rng.random() > 0.3) else 0
                     for n in range(lat.n))
    start = lat.node(1, 1, 1)
    goal = lat.node(7, 5, 4)
    free[start] = 1
    free[goal] = 1
    free[lat.node(7, 5, 3)] = 1
    path, cost = lat.astar(free, start, UP, goal)
    ref = reference_cost(lat, free, start, UP, goal)
    assert cost == ref
    if path is not None:
        assert path[0] == start and path[-1] == goal
        assert all(free[n] for n in path)
        assert lat.ijk(path[-2])[2] == lat.ijk(goal)[2] - 1   # entered from below
        steps = len(path) - 1
        pts = [lat.xyz(n) for n in path]
        assert cost == STEP_COST * steps + BEND_COST * (bends(pts) + (0 if pts[1][2] > pts[0][2] else 1))


def test_astar_returns_none_when_walled_off():
    lat = Lattice(0.6, 6, 5, 4, 1, 2)
    free = bytearray(1 if lat.ijk(n)[2] in (1, 2) and lat.ijk(n)[0] != 3 else 0 for n in range(lat.n))
    goal = lat.node(5, 2, 3)
    free[goal] = 1
    assert lat.astar(free, lat.node(0, 2, 1), UP, goal) == (None, None)


def test_free_mask_respects_radius_and_reservations():
    lat = Lattice(0.6, 8, 6, 5, 1, 3)
    lat.set_static([Solid("C", "column", (1.55, 1.55, 0), (2.05, 2.05, 3), 0.0)])   # centred at (1.8, 1.8)
    n_adj = lat.node(4, 3, 2)   # (2.4, 1.8): 0.35 m from the column face
    assert lat.free_mask(0.29, 0.05)[n_adj] == 1
    assert lat.free_mask(0.31, 0.05)[n_adj] == 0
    assert lat.free_mask(0.0, 0.0)[lat.node(3, 3, 2)] == 0
    assert lat.free_mask(0.0, 0.0)[lat.node(5, 5, 0)] == 0       # below kmin
    lat.reserve_penetration(0.6, 2.4)
    m = lat.free_mask(0.05, 0.05)
    assert m[lat.node(1, 4, 3)] == 0 and m[lat.node(1, 4, 2)] == 0 and m[lat.node(1, 4, 1)] == 1
    g = lat.node(1, 4, 4)
    m2 = lat.free_mask(0.05, 0.05, goal=g)
    assert m2[g] == 1 and m2[lat.node(1, 4, 3)] == 1 and m2[lat.node(1, 4, 2)] == 1


def test_stub_rises_until_clear_of_own_header():
    lat = Lattice(0.6, 10, 7, 9, 1, 7)
    hdr = Solid("H", "header", (0.6, 1.8, 1.8), (4.8, 1.8, 1.8), 0.45)
    lat.set_static([hdr])
    poc = lat.node(4, 3, 3)
    stub = lat.stub("H", poc, 0.2, 0.05)
    # need 0.45 + 0.2 + 0.05 = 0.70 m from the axis: two steps (1.2 m), one step (0.6 m) is not enough
    assert [lat.ijk(n)[2] for n in stub] == [3, 4, 5]
    assert lat.stub("H", poc, 0.2, 0.05, max_steps=1) is None


def test_bfs_distance_matches_manhattan_without_obstacles():
    lat = Lattice(0.6, 7, 6, 6, 1, 4)
    goal = lat.node(5, 4, 5)
    free = lat.free_mask(0.0, 0.0, goal)
    dist = lat.bfs_from_goal(free, goal)
    for n in (lat.node(0, 0, 1), lat.node(2, 5, 3), lat.node(6, 1, 4)):
        assert dist[n] == lat.manhattan(n, goal)


def test_node_field_matches_box_gap():
    lat = Lattice(0.6, 5, 4, 3, 0, 2)
    s = Solid("B", "equipment", (0.7, 0.2, 0.1), (1.3, 0.9, 0.5), 0.0)
    lat.set_static([s])
    for n in range(lat.n):
        p = lat.xyz(n)
        assert lat.static_all[n] == pytest.approx(box_gap(p, p, s.lo, s.hi), abs=1e-12)
    assert np.isfinite(lat.static_all).all()


def test_goal_is_entered_only_from_below_even_if_side_is_free():
    lat = Lattice(0.6, 6, 4, 4, 0, 3)
    free = bytearray([1]) * lat.n
    start = lat.node(0, 1, 3)
    goal = lat.node(4, 1, 3)      # same level: a straight run would enter sideways
    path, cost = lat.astar(free, start, UP, goal)
    assert lat.ijk(path[-2]) == (4, 1, 2)
    assert cost > STEP_COST * 4 + BEND_COST
