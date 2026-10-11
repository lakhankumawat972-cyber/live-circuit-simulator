"""Turns a set of nodes into an ngspice netlist.

Line formats come straight from the task's mapping (see ``nodes.py``):

    Number    V<id> <out> 0 DC <value>
    Add       B<id> <out> 0 V = V(<a>) + V(<b>)
    Multiply  B<id> <out> 0 V = V(<a>) * V(<b>)
    Divide    B<id> <out> 0 V = V(<a>) / V(<b>)
    Display   (no line - its input net is read from the result)

A wire puts an output and an input on the same net, so every node's output
net is named after the node and every input simply refers to its source's net.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Element:
    node_id: str  # id used by the editor
    eid: str  # id used inside the netlist ("n1", "n2", ...)
    net: str  # name of the node's output net
    line: str


def net_name(eid: str) -> str:
    return f"o_{eid}"


def build_netlist(elements: list[Element], guesses: dict[str, float]) -> str:
    """``guesses`` maps editor node ids to a starting value for ngspice.

    They go in ``.nodeset`` lines: ngspice still solves the circuit and its
    answer is what gets reported; the guess only keeps Newton's first
    iteration away from 0/0 on Divide nodes and speeds up convergence.
    """
    lines = ["* live graph netlist (generated, do not edit)", ".options numdgt=15 itl1=1000"]
    lines.extend(e.line for e in elements)
    for e in elements:
        guess = guesses.get(e.node_id)
        if guess is not None and math.isfinite(guess):
            lines.append(f".nodeset V({e.net})={guess!r}")
    lines.extend([".op", ".end"])
    return "\n".join(lines) + "\n"
