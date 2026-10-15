"""Deterministic output: floats rounded to 10 significant digits, sorted keys, LF endings."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path


def r10(x):
    if isinstance(x, bool) or x is None or isinstance(x, (int, str)):
        return x
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            raise ValueError("non-finite float in output")
        v = float(f"{x:.10g}")
        return 0.0 if v == 0 else v
    try:  # numpy scalars
        return r10(x.item())
    except AttributeError:
        raise TypeError(f"cannot format {type(x)}") from None


def canon(obj):
    if isinstance(obj, dict):
        return {str(k): canon(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [canon(v) for v in obj]
    return r10(obj)


def dumps(obj) -> str:
    return json.dumps(canon(obj), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_json(path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(dumps(obj), encoding="utf-8", newline="\n")


def cell(v) -> str:
    v = r10(v)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def write_csv(path, header: list[str], rows: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for row in rows:
        w.writerow([cell(v) for v in row])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(buf.getvalue(), encoding="utf-8", newline="\n")


def write_text(path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8", newline="\n")
