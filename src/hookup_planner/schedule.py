"""Resource-constrained install schedule (serial schedule generation) and Gantt chart.

Sequence per tool (all durations ILLUSTRATIVE, from data/unit_rates.json):
  process lateral (PLS) work: header capacity steps (LH) and new POCs (NP)
  -> hookups from POC to the tool connection (HU, needs the PLS work on its header/POC)
  tool move-in and set (MS, rigging crew), in parallel with the sub-fab hookup work
  -> test of each hookup (TS, needs its hookup and the tool set in place)
  -> utilities turned on and handed to the vendor (UO, needs every test of the tool)
  -> vendor start-up (VS, vendor's own team, no crew limit here).
Time is counted in half-day slots so everything stays in integers.
"""
from __future__ import annotations

import math

from . import engineering as E

TRADE = {"liquid": "pipe", "gas": "pipe", "exhaust": "duct", "power": "elec"}
TYPE_ORDER = {"LH": 0, "NP": 0, "MS": 1, "HU": 1, "TS": 2, "UO": 3, "VS": 4}
PLS_TYPES = ("LH", "NP")


def slots(days: float) -> int:
    return max(1, math.ceil(days * 2 - 1e-9))


def build_tasks(rates: dict, hookups: list[dict], upgrades: dict, site: dict) -> list[dict]:
    sch = rates["schedule"]
    hdr = {h["id"]: h for h in site["headers"]}
    tasks = []
    for h, n in sorted(upgrades.items()):
        tasks.append({"id": f"LH-{h}", "tool": "", "type": "LH", "resource": "pls",
                      "dur": slots(hdr[h]["upgrade_days"] * n), "preds": []})
    for p in sorted({hk["poc"] for hk in hookups if hk.get("new_poc")}):
        tasks.append({"id": f"NP-{p}", "tool": "", "type": "NP", "resource": "pls",
                      "dur": slots(sch["new_poc_days"]), "preds": []})
    ids = {t["id"] for t in tasks}
    by_tool: dict[str, list] = {}
    for tool in sorted({hk["tool"] for hk in hookups}):
        tasks.append({"id": f"MS-{tool}", "tool": tool, "type": "MS", "resource": "rigging",
                      "dur": slots(sch["move_in_set_days"]), "preds": []})
    for hk in sorted(hookups, key=lambda h: h["id"]):
        kind = E.SYSTEMS[hk["system"]]["kind"]
        work_h = sch["hookup_setup_h"][kind] + hk["length_m"] * rates["labour_h_per_m"][kind]
        preds = [x for x in (f"LH-{hk['header']}", f"NP-{hk['poc']}") if x in ids]
        tasks.append({"id": f"HU-{hk['id']}", "tool": hk["tool"], "type": "HU", "resource": TRADE[kind],
                      "dur": slots(work_h / sch["hours_per_day"]), "preds": preds})
        tasks.append({"id": f"TS-{hk['id']}", "tool": hk["tool"], "type": "TS", "resource": "test",
                      "dur": slots(sch["test_days"][kind]), "preds": [f"HU-{hk['id']}", f"MS-{hk['tool']}"]})
        by_tool.setdefault(hk["tool"], []).append(f"TS-{hk['id']}")
    for tool in sorted(by_tool):
        tasks.append({"id": f"UO-{tool}", "tool": tool, "type": "UO", "resource": "",
                      "dur": slots(sch["utilities_on_days"]), "preds": by_tool[tool]})
        tasks.append({"id": f"VS-{tool}", "tool": tool, "type": "VS", "resource": "",
                      "dur": slots(sch["vendor_startup_days"]), "preds": [f"UO-{tool}"]})
    return tasks


def serial_sgs(tasks: list[dict], crews: dict) -> list[dict]:
    """Serial schedule generation: highest-priority eligible task at its earliest feasible slot."""
    byid = {t["id"]: dict(t) for t in tasks}
    usage: dict[str, list] = {r: [] for r in crews}
    done: dict[str, int] = {}
    key = lambda t: (0 if t["type"] in PLS_TYPES else 1, t["tool"], TYPE_ORDER[t["type"]], t["id"])
    pending = sorted(byid.values(), key=key)
    while pending:
        for n, t in enumerate(pending):
            if all(p in done for p in t["preds"]):
                break
        else:
            raise ValueError("precedence cycle")
        t = pending.pop(n)
        start = max([done[p] for p in t["preds"]], default=0)
        res = t["resource"]
        if res:
            if crews.get(res, 0) < 1:
                raise ValueError(f"no crew for resource {res}")
            u = usage[res]
            while True:
                need = start + t["dur"]
                if len(u) < need:
                    u.extend([0] * (need - len(u)))
                if all(u[s] < crews[res] for s in range(start, need)):
                    break
                start += 1
            for s in range(start, start + t["dur"]):
                u[s] += 1
        t["start"], t["finish"] = start, start + t["dur"]
        done[t["id"]] = t["finish"]
        byid[t["id"]] = t
    return [byid[t["id"]] for t in sorted(tasks, key=key)]


def schedule(rates: dict, hookups: list[dict], upgrades: dict, site: dict) -> dict:
    tasks = serial_sgs(build_tasks(rates, hookups, upgrades, site), rates["schedule"]["crews"])
    rows = [{"id": t["id"], "tool": t["tool"], "type": t["type"], "resource": t["resource"],
             "start_day": t["start"] / 2, "finish_day": t["finish"] / 2, "duration_days": t["dur"] / 2,
             "preds": ";".join(t["preds"])} for t in tasks]
    uo = {t["tool"]: t["finish"] / 2 for t in tasks if t["type"] == "UO"}
    vs = {t["tool"]: t["finish"] / 2 for t in tasks if t["type"] == "VS"}
    return {"tasks": rows, "makespan_days": max(t["finish"] for t in tasks) / 2 if tasks else 0.0,
            "utilities_on_day": dict(sorted(uo.items())), "startup_done_day": dict(sorted(vs.items())),
            "last_utilities_on_day": max(uo.values()) if uo else 0.0}


# --- Gantt ---------------------------------------------------------------------------------
PHASE_COLOURS = {"PLS work": "#2a78d6", "Move-in/set": "#8a5cc7", "Hookup": "#eb6834", "Test": "#1baf7a",
                 "Utilities on": "#eda100", "Vendor start-up": "#9b9a94"}


def gantt_png(sched: dict, path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    matplotlib.rcParams["svg.hashsalt"] = "thp"
    tasks = sched["tasks"]
    tools = sorted({t["tool"] for t in tasks if t["tool"]})
    rows = ["PLS work"] + tools
    fig, ax = plt.subplots(figsize=(10, 0.6 * len(rows) + 1.8), dpi=110)
    surface, ink, muted = "#fcfcfb", "#0b0b0b", "#52514e"
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)
    bb = [t for t in tasks if t["type"] in PLS_TYPES]
    for n, t in enumerate(bb):
        ax.barh(len(rows) - 1, t["duration_days"], left=t["start_day"], height=0.5,
                color=PHASE_COLOURS["PLS work"], edgecolor=surface, linewidth=2)
        ax.text(t["start_day"] + 0.2, len(rows) - 1 + (0.38 if n % 2 == 0 else -0.38), t["id"], fontsize=6.5,
                color=muted, va="center")
    for r, tool in enumerate(tools):
        y = len(rows) - 2 - r
        own = [t for t in tasks if t["tool"] == tool]
        for phase, typ, off, h in (("Move-in/set", "MS", 0.27, 0.18), ("Hookup", "HU", 0.08, 0.18),
                                   ("Test", "TS", -0.11, 0.18)):
            ts = [t for t in own if t["type"] == typ]
            s, f = min(t["start_day"] for t in ts), max(t["finish_day"] for t in ts)
            ax.barh(y + off, f - s, left=s, height=h, color=PHASE_COLOURS[phase], edgecolor=surface, linewidth=1)
        uo = next(t for t in own if t["type"] == "UO")
        vs = next(t for t in own if t["type"] == "VS")
        ax.barh(y - 0.27, uo["duration_days"], left=uo["start_day"], height=0.18, color=PHASE_COLOURS["Utilities on"],
                edgecolor=surface, linewidth=1)
        ax.barh(y - 0.27, vs["duration_days"], left=vs["start_day"], height=0.18,
                color=PHASE_COLOURS["Vendor start-up"], edgecolor=surface, linewidth=1)
        ax.text(uo["finish_day"] + 0.3, y + 0.05, f"utilities on day {uo['finish_day']:g}", fontsize=7, color=ink,
                va="center")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(list(reversed(rows)), fontsize=8.5, color=ink)
    ax.set_xlabel("Working days from start (illustrative durations)", fontsize=8.5, color=muted)
    ax.set_xlim(0, sched["makespan_days"] * 1.12 + 1)
    ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c9c8c2")
    ax.tick_params(colors=muted, labelsize=8)
    ax.set_title(f"Install schedule: last tool's utilities on day {sched['last_utilities_on_day']:g}, "
                 f"vendor start-up done day {sched['makespan_days']:g}", fontsize=10, color=ink, loc="left", pad=30)
    labels = {"PLS work": "Process lateral work", "Move-in/set": "Move-in and set",
              "Hookup": "Hookups (first start to last finish)", "Test": "Tests (first start to last finish)",
              "Utilities on": "Utilities on / handed to vendor", "Vendor start-up": "Vendor start-up"}
    ax.legend(handles=[Patch(color=c, label=labels[k]) for k, c in PHASE_COLOURS.items()], loc="lower left",
              bbox_to_anchor=(0.0, 1.0), fontsize=7.5, frameon=False, ncol=3, borderaxespad=0.2)
    fig.tight_layout()
    fig.savefig(str(path), facecolor=surface, metadata={"Software": None})
    plt.close(fig)
