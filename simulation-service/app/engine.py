"""Graph -> checks -> netlist -> ngspice -> per-node results.

Order of work (cheapest and most specific first):

1. read the graph; per-node problems: bad settings, unwired inputs, formulas
   that are not allowed;
2. loop detection (strongly connected components);
3. everything downstream of a broken node is marked *blocked*;
4. a reference evaluation in Python catches divide-by-zero before ngspice;
5. build the netlist from the healthy nodes only, run ngspice, read values;
   if ngspice names a node in an error, or returns a non-finite number, that
   node is marked, its dependents are blocked and the rest is re-run.

The result for every node is one of ``ok`` (value), ``error`` (kind +
message) or ``blocked`` (blockedBy = the node that broke it); engine trouble
(timeout, crash, ngspice missing) is reported separately in ``engine``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .graph import downstream, find_loops, topological_order
from .netlist import Element, build_netlist, net_name
from .nodes import NODE_TYPES, NodeError, NodeSpec
from .runner import NgspiceRunner

MAX_NODES = 500
MAX_EDGES = 2000


class GraphFormatError(ValueError):
    """The request is not a graph at all (as opposed to a graph with a broken node)."""


@dataclass
class _Node:
    id: str
    type: Any
    spec: NodeSpec | None
    data: dict
    eid: str
    params: dict = field(default_factory=dict)


def _clean(value: float) -> float:
    return 0.0 if value == 0 else float(f"{value:.12g}")


def _list_names(names: list[str]) -> str:
    if len(names) == 1:
        return f"Input {names[0]} is not connected"
    return f"Inputs {' and '.join(names)} are not connected"


class _Run:
    def __init__(self, payload: dict, runner: NgspiceRunner):
        self.runner = runner
        self.nodes: dict[str, _Node] = {}
        self.order: list[str] = []
        self.status: dict[str, dict] = {}
        self.successors: dict[str, set[str]] = {}
        self.inputs: dict[str, dict[str, str]] = {}
        self.engine = {"state": "ok", "message": ""}
        self.netlist = ""
        self._read(payload)

    # -- reading ---------------------------------------------------------

    def _read(self, payload: dict) -> None:
        raw_nodes, raw_edges = payload.get("nodes"), payload.get("edges", [])
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise GraphFormatError("Graph needs 'nodes' and 'edges' lists")
        if len(raw_nodes) > MAX_NODES or len(raw_edges) > MAX_EDGES:
            raise GraphFormatError(f"Graph is too large (max {MAX_NODES} nodes, {MAX_EDGES} wires)")
        for index, raw in enumerate(raw_nodes):
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
                raise GraphFormatError(f"Node {index} needs a text id")
            if raw["id"] in self.nodes:
                raise GraphFormatError(f"Duplicate node id '{raw['id'][:40]}'")
            data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
            node_type = raw.get("type")
            spec = NODE_TYPES.get(node_type) if isinstance(node_type, str) else None
            self.nodes[raw["id"]] = _Node(raw["id"], node_type, spec, data, f"n{index + 1}")
            self.order.append(raw["id"])
            self.inputs[raw["id"]] = {}
            self.successors[raw["id"]] = set()

        multiple: dict[str, set[str]] = {}
        for raw in raw_edges:
            if not isinstance(raw, dict):
                continue
            source, target = self.nodes.get(raw.get("source")), self.nodes.get(raw.get("target"))
            if not source or not target or not source.spec or not target.spec or not source.spec.has_output:
                continue
            handle = raw.get("targetHandle")
            if handle is None and len(target.spec.inputs) == 1:
                handle = target.spec.inputs[0]
            if handle not in target.spec.inputs:
                continue
            if handle in self.inputs[target.id]:
                multiple.setdefault(target.id, set()).add(handle)
                continue
            self.inputs[target.id][handle] = source.id
            self.successors[source.id].add(target.id)

        for node in self.nodes.values():
            self._check_node(node, multiple.get(node.id, set()))
        self.loops = find_loops(self.order, self.successors)
        for loop in self.loops:
            for node_id in loop:
                self.status.pop(node_id, None)
                self._set_error(node_id, "loop", "Part of a loop - a node cannot depend on itself")
        for node_id in self.order:
            if self.status.get(node_id, {}).get("status") == "error":
                self._block_downstream(node_id)

    def _check_node(self, node: _Node, multiple: set[str]) -> None:
        if node.spec is None:
            self._set_error(node.id, "unknown_type", f"Unknown node type '{str(node.type)[:30]}'")
            return
        try:
            node.params = node.spec.prepare(node.data)
        except NodeError as exc:
            self._set_error(node.id, exc.kind, exc.message)
            return
        if multiple:
            self._set_error(node.id, "multiple_wires", f"Input {', '.join(sorted(multiple))} has more than one wire")
            return
        missing = [h for h in node.spec.needed(node.params) if h not in self.inputs[node.id]]
        if missing:
            self._set_error(node.id, "missing_input", _list_names(missing))

    # -- status bookkeeping ----------------------------------------------

    def _set_error(self, node_id: str, kind: str, message: str) -> None:
        self.status[node_id] = {"status": "error", "kind": kind, "message": message}

    def _block_downstream(self, root: str) -> None:
        for node_id in downstream(root, self.successors):
            if node_id not in self.status:
                self.status[node_id] = {
                    "status": "blocked",
                    "blockedBy": root,
                    "message": "Blocked - an upstream node has an error",
                }

    def _fail(self, node_id: str, kind: str, message: str) -> None:
        self._set_error(node_id, kind, message)
        self._block_downstream(node_id)

    def _healthy(self) -> list[str]:
        return [n for n in self.order if n not in self.status]

    # -- reference evaluation (before ngspice) ---------------------------

    def _reference_values(self) -> dict[str, float]:
        values: dict[str, float] = {}
        for node_id in topological_order(self._healthy(), self.successors):
            if node_id in self.status:  # blocked by a failure found a moment ago
                continue
            node = self.nodes[node_id]
            wired = {h: values[src] for h, src in self.inputs[node_id].items()}
            try:
                value = node.spec.evaluate(node.params, wired)
            except ZeroDivisionError:
                self._fail(node_id, "divide_by_zero", "Division by zero")
                continue
            if not math.isfinite(value):
                self._fail(node_id, "non_finite", "Result is too large to represent")
                continue
            values[node_id] = value
        return values

    # -- ngspice ---------------------------------------------------------

    def _elements(self) -> list[Element]:
        elements = []
        for node_id in self._healthy():
            node = self.nodes[node_id]
            if node.spec.netlist is None:
                continue
            nets = {h: net_name(self.nodes[src].eid) for h, src in self.inputs[node_id].items()}
            out = net_name(node.eid)
            elements.append(Element(node_id, node.eid, out, node.spec.netlist(node.eid, out, node.params, nets)))
        return elements

    def _culprits(self, text: str, elements: list[Element]) -> dict[str, str]:
        """Nodes named in ngspice's error text -> the line that names them."""
        by_element = {f"{e.line[0]}{e.eid}".lower(): e.node_id for e in elements}
        by_net = {e.net.lower(): e.node_id for e in elements}
        found: dict[str, str] = {}
        for line in text.splitlines():
            words = set(re.findall(r"[a-z_][a-z0-9_]*", line.lower()))
            for word in words:
                node_id = by_element.get(word) or by_net.get(word)
                if node_id and node_id not in found:
                    found[node_id] = line.strip()[:200]
        return found

    def solve(self) -> dict[str, float]:
        guesses = self._reference_values()
        results: dict[str, float] = {}
        for _ in range(len(self.nodes) + 2):
            elements = self._elements()
            if not elements:
                return results
            self.netlist = build_netlist(elements, guesses)
            run = self.runner.run(self.netlist)
            if run.state == "failed":
                culprits = self._culprits(run.output, elements)
                if not culprits:
                    self.engine = {"state": "error", "message": run.message}
                    return {}
                for node_id, line in culprits.items():
                    self._fail(node_id, "ngspice_error", f"ngspice: {line}")
                continue
            if run.state != "ok":
                self.engine = {"state": run.state, "message": run.message}
                return {}
            results = {}
            clean = True
            for element in elements:
                value = run.values.get(element.net)
                if value is None:
                    self._fail(element.node_id, "no_result", "ngspice returned no value for this node")
                    clean = False
                elif not math.isfinite(value):
                    self._fail(element.node_id, "non_finite", "Result is not finite (division by zero or overflow)")
                    clean = False
                else:
                    results[element.node_id] = value
            if clean:
                return results
        self.engine = {"state": "error", "message": "Could not settle on a result"}
        return {}

    # -- output ----------------------------------------------------------

    def report(self, results: dict[str, float]) -> dict:
        engine_ok = self.engine["state"] == "ok"
        nodes: dict[str, dict] = {}
        for node_id in self.order:
            node = self.nodes[node_id]
            if node_id in self.status:
                nodes[node_id] = dict(self.status[node_id])
            elif not engine_ok:
                nodes[node_id] = {"status": "unavailable", "message": self.engine["message"]}
            else:
                source = self.inputs[node_id].get("x") if node.spec.netlist is None else node_id
                nodes[node_id] = {"status": "ok", "value": _clean(results[source])}
        return {
            "nodes": nodes,
            "loops": self.loops,
            "engine": self.engine,
            "netlist": self.netlist,
        }


def simulate(payload: dict, runner: NgspiceRunner) -> dict:
    run = _Run(payload, runner)
    results = run.solve()
    return run.report(results)
