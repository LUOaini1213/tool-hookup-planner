"""3-D routing lattice, obstacle distance fields, A* with bend penalty, BFS distances.

Nodes sit at (i*step, j*step, k*step).  Routable nodes have kmin <= k <= kmax; the layer
k = kmax + 1 (slab underside) is only entered as a route's final node, straight up into
the tool's floor penetration.  Static obstacles are centred on lattice lines, so the
closest point of any lattice edge to an obstacle is one of its end nodes; checking nodes
is therefore enough for edges too (see docs/method.md).
"""
from __future__ import annotations

import heapq
from collections import deque

import numpy as np

from .geometry import EPS, Solid, node_gap_field

DIRS = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
UP = 4
STEP_COST = 5      # cost units per lattice step
BEND_COST = 5      # extra cost per change of direction (= one step) -- ILLUSTRATIVE
PEN_DEPTH = 2      # lattice nodes kept free below each floor penetration


class Lattice:
    def __init__(self, step: float, nx: int, ny: int, nz: int, kmin: int, kmax: int):
        self.step, self.nx, self.ny, self.nz = step, nx, ny, nz
        self.kmin, self.kmax = kmin, kmax
        n = nx * ny * nz
        idx = np.arange(n)
        self.I = idx % nx
        self.J = (idx // nx) % ny
        self.K = idx // (nx * ny)
        self.X = self.I * step
        self.Y = self.J * step
        self.Z = self.K * step
        self.n = n
        self.static_all = np.full(n, np.inf)
        self.static_wo: dict[str, np.ndarray] = {}   # field without one header (for take-off stubs)
        self.routes = np.full(n, np.inf)
        self.reserved = np.zeros(n, dtype=bool)   # penetration columns of all tools

    # --- indexing ------------------------------------------------------------------
    def node(self, i, j, k) -> int:
        return (k * self.ny + j) * self.nx + i

    def ijk(self, n: int):
        return n % self.nx, (n // self.nx) % self.ny, n // (self.nx * self.ny)

    def xyz(self, n: int):
        i, j, k = self.ijk(n)
        return (i * self.step, j * self.step, k * self.step)

    def snap(self, x, y, z) -> int:
        i, j, k = (int(round(v / self.step)) for v in (x, y, z))
        if not (0 <= i < self.nx and 0 <= j < self.ny and 0 <= k < self.nz):
            raise ValueError(f"point {(x, y, z)} outside lattice")
        return self.node(i, j, k)

    # --- obstacles -----------------------------------------------------------------
    def set_static(self, solids: list[Solid]) -> None:
        nonheader = np.full(self.n, np.inf)
        per_header = {}
        for s in solids:
            f = node_gap_field(self.X, self.Y, self.Z, s)
            if s.kind == "header":
                per_header[s.eid] = f
            else:
                nonheader = np.minimum(nonheader, f)
        self.static_all = nonheader.copy()
        for f in per_header.values():
            self.static_all = np.minimum(self.static_all, f)
        for h in per_header:
            wo = nonheader.copy()
            for h2, f in per_header.items():
                if h2 != h:
                    wo = np.minimum(wo, f)
            self.static_wo[h] = wo

    def add_route(self, solids: list[Solid]) -> None:
        for s in solids:
            self.routes = np.minimum(self.routes, node_gap_field(self.X, self.Y, self.Z, s))

    def reserve_penetration(self, x: float, y: float) -> None:
        """Keep the node under a floor penetration free for the hookup that ends there."""
        top = self.snap(x, y, (self.kmax + 1) * self.step)
        for depth in range(PEN_DEPTH + 1):
            self.reserved[top - depth * self.nx * self.ny] = True

    def free_mask(self, r: float, clearance: float, goal: int | None = None) -> bytearray:
        f = np.minimum(self.static_all, self.routes)
        ok = ((f >= r + clearance - EPS) & (f > EPS) & (self.K >= self.kmin) & (self.K <= self.kmax)
              & ~self.reserved)   # f > EPS: a node inside or on a solid is never free
        m = bytearray(ok.astype(np.uint8).tobytes())
        if goal is not None:
            m[goal] = 1
            for depth in range(1, PEN_DEPTH + 1):
                below = goal - depth * self.nx * self.ny
                if f[below] >= r + clearance - EPS:
                    m[below] = 1
        return m

    def stub(self, header_id: str, poc_node: int, r: float, clearance: float, max_steps: int = 4):
        """Straight take-off upwards from a POC until clear of every obstacle.

        Returns the list of stub nodes (POC node first) or None if blocked.
        """
        wo = np.minimum(self.static_wo[header_id], self.routes)
        full = np.minimum(self.static_all, self.routes)
        nodes = [poc_node]
        cur = poc_node
        need = r + clearance - EPS
        for _ in range(max_steps):
            i, j, k = self.ijk(cur)
            if k + 1 > self.kmax:
                return None
            cur = self.node(i, j, k + 1)
            if wo[cur] < need:
                return None
            nodes.append(cur)
            if full[cur] >= need:
                return nodes
        return None

    # --- search --------------------------------------------------------------------
    def neighbours(self, n: int):
        i, j, k = self.ijk(n)
        for d, (di, dj, dk) in enumerate(DIRS):
            a, b, c = i + di, j + dj, k + dk
            if 0 <= a < self.nx and 0 <= b < self.ny and 0 <= c < self.nz:
                yield d, self.node(a, b, c)

    def manhattan(self, a: int, b: int) -> int:
        ia, ja, ka = self.ijk(a)
        ib, jb, kb = self.ijk(b)
        return abs(ia - ib) + abs(ja - jb) + abs(ka - kb)

    def astar(self, free: bytearray, start: int, start_dir: int, goal: int):
        """Least-cost path (steps + bend penalties).  Returns (nodes, cost) or (None, None).

        The goal is entered only by an upward move (it is the penetration node).
        """
        h0 = STEP_COST * self.manhattan(start, goal)
        openh = [(h0, 0, start, start_dir)]
        best = {(start, start_dir): 0}
        parent = {}
        while openh:
            f, g, n, d = heapq.heappop(openh)
            if best.get((n, d), None) != g:
                continue
            if n == goal:
                path = [n]
                key = (n, d)
                while key in parent:
                    key = parent[key]
                    path.append(key[0])
                return path[::-1], g
            for nd, m in self.neighbours(n):
                if not free[m]:
                    continue
                if m == goal and nd != UP:
                    continue
                g2 = g + STEP_COST + (BEND_COST if nd != d else 0)
                key = (m, nd)
                if g2 < best.get(key, 1 << 60):
                    best[key] = g2
                    parent[key] = (n, d)
                    heapq.heappush(openh, (g2 + STEP_COST * self.manhattan(m, goal), g2, m, nd))
        return None, None

    def bfs_from_goal(self, free: bytearray, goal: int) -> dict:
        """Unit-step distances from the penetration node to every reachable free node."""
        i, j, k = self.ijk(goal)
        below = self.node(i, j, k - 1)
        dist = {goal: 0}
        if not free[below]:
            return dist
        dist[below] = 1
        q = deque([below])
        while q:
            n = q.popleft()
            dn = dist[n] + 1
            for _, m in self.neighbours(n):
                if free[m] and m not in dist and m != goal:
                    dist[m] = dn
                    q.append(m)
        return dist


def compress(points: list[tuple]) -> list[tuple]:
    """Drop collinear interior points of an axis-aligned polyline."""
    out = [points[0]]
    for n in range(1, len(points) - 1):
        a, b, c = out[-1], points[n], points[n + 1]
        d1 = tuple(round(b[t] - a[t], 9) for t in range(3))
        d2 = tuple(round(c[t] - b[t], 9) for t in range(3))
        if _unit(d1) != _unit(d2):
            out.append(b)
    out.append(points[-1])
    return out


def _unit(d):
    return tuple((v > 0) - (v < 0) for v in d)


def bends(points: list[tuple]) -> int:
    return max(0, len(compress(points)) - 2)


def length(points: list[tuple]) -> float:
    return sum(sum(abs(points[n + 1][t] - points[n][t]) for t in range(3)) for n in range(len(points) - 1))
