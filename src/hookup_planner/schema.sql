-- Utilities database for tool hookup planning (SQLite).
-- All rows produced by this repository are ILLUSTRATIVE synthetic data.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS utility_system (
    code               TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    kind               TEXT NOT NULL CHECK (kind IN ('liquid', 'gas', 'exhaust', 'power')),
    role               TEXT NOT NULL CHECK (role IN ('supply', 'return', 'exhaust')),
    fluid              TEXT NOT NULL,
    flow_unit          TEXT NOT NULL,
    material           TEXT NOT NULL,
    v_max              REAL NOT NULL,          -- m/s, 0 for power
    coincidence_factor REAL NOT NULL CHECK (coincidence_factor > 0 AND coincidence_factor <= 1)
);

CREATE TABLE IF NOT EXISTS structural_column (
    id TEXT PRIMARY KEY,
    x REAL NOT NULL, y REAL NOT NULL, w REAL NOT NULL, d REAL NOT NULL,
    z0 REAL NOT NULL, z1 REAL NOT NULL CHECK (z1 > z0)
);

CREATE TABLE IF NOT EXISTS header (
    id             TEXT PRIMARY KEY,
    system         TEXT NOT NULL REFERENCES utility_system(code),
    corridor       TEXT NOT NULL,
    y REAL NOT NULL, z REAL NOT NULL, x0 REAL NOT NULL, x1 REAL NOT NULL CHECK (x1 > x0),
    od             REAL NOT NULL CHECK (od > 0),
    capacity       REAL NOT NULL CHECK (capacity >= 0),   -- design capacity in the system flow unit
    pressure_kpa_g REAL NOT NULL,                          -- supply/return pressure or exhaust static
    upgrade_step   REAL NOT NULL,                          -- capacity added by one header capacity step
    upgrade_cost   REAL NOT NULL,                          -- illustrative cost of one step
    upgrade_days   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS poc (
    id         TEXT PRIMARY KEY,
    header     TEXT NOT NULL REFERENCES header(id),
    system     TEXT NOT NULL REFERENCES utility_system(code),
    x REAL NOT NULL, y REAL NOT NULL, z REAL NOT NULL,
    size       TEXT NOT NULL,
    rated_flow REAL NOT NULL CHECK (rated_flow > 0),
    status     TEXT NOT NULL CHECK (status IN ('free', 'in_use', 'reserved', 'planned'))
);

CREATE TABLE IF NOT EXISTS equipment (
    id TEXT PRIMARY KEY,
    x0 REAL NOT NULL, y0 REAL NOT NULL, z0 REAL NOT NULL,
    x1 REAL NOT NULL, y1 REAL NOT NULL, z1 REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tool (
    id       TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    status   TEXT NOT NULL CHECK (status IN ('existing', 'new')),
    x0 REAL NOT NULL, y0 REAL NOT NULL, x1 REAL NOT NULL, y1 REAL NOT NULL,
    height   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_demand (
    tool   TEXT NOT NULL REFERENCES tool(id),
    system TEXT NOT NULL REFERENCES utility_system(code),
    flow   REAL NOT NULL CHECK (flow > 0),     -- peak demand in the system flow unit
    p_req  REAL NOT NULL,                      -- supply: min inlet kPa g; PCWR: tool internal drop kPa; exhaust: port static kPa g
    px REAL NOT NULL, py REAL NOT NULL,        -- floor penetration (connection point) on the fab level
    PRIMARY KEY (tool, system)
);

CREATE TABLE IF NOT EXISTS hookup (
    id     TEXT PRIMARY KEY,
    tool   TEXT NOT NULL,
    system TEXT NOT NULL,
    poc    TEXT NOT NULL REFERENCES poc(id),
    status TEXT NOT NULL CHECK (status IN ('planned', 'installed', 'tested', 'released')),
    size   TEXT NOT NULL,
    FOREIGN KEY (tool, system) REFERENCES tool_demand(tool, system)
);

CREATE TABLE IF NOT EXISTS route_point (
    hookup TEXT NOT NULL REFERENCES hookup(id),
    seq    INTEGER NOT NULL,
    x REAL NOT NULL, y REAL NOT NULL, z REAL NOT NULL,
    PRIMARY KEY (hookup, seq)
);

-- Connected (coincidence-weighted) load and remaining capacity per header.
CREATE VIEW IF NOT EXISTS v_header_load AS
SELECT h.id AS header, h.system, h.capacity,
       COALESCE(SUM(CASE WHEN k.status IN ('installed', 'tested', 'released')
                         THEN d.flow * s.coincidence_factor END), 0.0) AS connected_load,
       h.capacity - COALESCE(SUM(CASE WHEN k.status IN ('installed', 'tested', 'released')
                                      THEN d.flow * s.coincidence_factor END), 0.0) AS remaining
FROM header h
JOIN utility_system s ON s.code = h.system
LEFT JOIN poc p ON p.header = h.id
LEFT JOIN hookup k ON k.poc = p.id
LEFT JOIN tool_demand d ON d.tool = k.tool AND d.system = k.system
GROUP BY h.id;

CREATE VIEW IF NOT EXISTS v_free_poc AS
SELECT p.* FROM poc p
WHERE p.status = 'free' AND NOT EXISTS (SELECT 1 FROM hookup k WHERE k.poc = p.id);

CREATE VIEW IF NOT EXISTS v_tool_demand_total AS
SELECT t.status, d.system, SUM(d.flow) AS total_flow, COUNT(*) AS n
FROM tool_demand d JOIN tool t ON t.id = d.tool
GROUP BY t.status, d.system;
