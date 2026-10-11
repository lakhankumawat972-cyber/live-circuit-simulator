"""Node-type registry: the single place that knows what each node does.

To add a node type on the backend, add one ``NodeSpec`` to ``NODE_TYPES``
(and one entry in ``frontend/src/nodeDefs.js`` so the editor can draw it).
Nothing else in the service is node-specific.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Optional

from .formula import FormulaError, compile_formula

MAX_ABS_VALUE = 1e15
_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


class NodeError(Exception):
    """A problem that belongs to one node (shown on that node)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class NodeSpec:
    label: str
    inputs: tuple[str, ...]
    has_output: bool
    # data -> params; raises NodeError when the node's own settings are invalid.
    prepare: Callable[[dict], dict]
    # (element id, output net, params, {input handle: net}) -> netlist line.
    # None for nodes that produce no netlist line (Display).
    netlist: Optional[Callable[[str, str, dict, dict], str]]
    # (params, {input handle: value}) -> value. Used for pre-checks and as the
    # initial guess handed to ngspice; ngspice's result is what is reported.
    evaluate: Callable[[dict, dict], float]
    # params -> input handles that must be wired. Defaults to all inputs.
    required_inputs: Optional[Callable[[dict], tuple[str, ...]]] = None

    def needed(self, params: dict) -> tuple[str, ...]:
        return self.required_inputs(params) if self.required_inputs else self.inputs


def _no_params(_data: dict) -> dict:
    return {}


def _prepare_number(data: dict) -> dict:
    raw = data.get("value")
    if isinstance(raw, bool) or raw is None:
        raise NodeError("invalid_value", "Enter a number")
    if isinstance(raw, str):
        text = raw.strip()
        if not _NUMBER.match(text):
            shown = text[:20] or "(empty)"
            raise NodeError("invalid_value", f"'{shown}' is not a number")
        raw = text
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise NodeError("invalid_value", "Value must be a number") from None
    if not math.isfinite(value) or abs(value) > MAX_ABS_VALUE:
        raise NodeError("invalid_value", f"Value must be between -{MAX_ABS_VALUE:g} and {MAX_ABS_VALUE:g}")
    return {"value": value}


def _prepare_formula(data: dict) -> dict:
    try:
        return {"formula": compile_formula(data.get("expr", ""))}
    except FormulaError as exc:
        raise NodeError("invalid_formula", str(exc)) from None


def _binary(symbol: str, op: Callable[[float, float], float]) -> NodeSpec:
    return NodeSpec(
        label={"+": "Add", "*": "Multiply", "/": "Divide"}[symbol],
        inputs=("a", "b"),
        has_output=True,
        prepare=_no_params,
        netlist=lambda eid, out, _p, ins: f"B{eid} {out} 0 V = V({ins['a']}) {symbol} V({ins['b']})",
        evaluate=lambda _p, v: op(v["a"], v["b"]),
    )


def _divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b


NODE_TYPES: dict[str, NodeSpec] = {
    "number": NodeSpec(
        label="Number",
        inputs=(),
        has_output=True,
        prepare=_prepare_number,
        netlist=lambda eid, out, p, _ins: f"V{eid} {out} 0 DC {p['value']!r}",
        evaluate=lambda p, _v: p["value"],
    ),
    "add": _binary("+", lambda a, b: a + b),
    "multiply": _binary("*", lambda a, b: a * b),
    "divide": _binary("/", _divide),
    "display": NodeSpec(
        label="Display",
        inputs=("x",),
        has_output=False,
        prepare=_no_params,
        netlist=None,
        evaluate=lambda _p, v: v["x"],
    ),
    "formula": NodeSpec(
        label="Formula",
        inputs=("a", "b"),
        has_output=True,
        prepare=_prepare_formula,
        netlist=lambda eid, out, p, ins: (
            f"B{eid} {out} 0 V = {p['formula'].to_spice(lambda name: ins[name])}"
        ),
        evaluate=lambda p, v: p["formula"].evaluate(v),
        required_inputs=lambda p: p["formula"].variables,
    ),
}
