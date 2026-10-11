"""Test helpers: graph builders and a stand-in for ngspice.

``FakeSpice`` reads the generated netlist the way ngspice would and prints
the result in ngspice's ``Node  Voltage`` table. It refuses any line the
generator should never produce, so a test fails if user text leaks into the
netlist.
"""

import math
import re

from app.runner import RunResult, parse_output

_ALLOWED = re.compile(
    r"^(\*.*|\.options .*|\.nodeset V\(o_n\d+\)=[-+0-9.e]+|\.op|\.end"
    r"|V(n\d+) (o_n\d+) 0 DC [-+0-9.e]+"
    r"|B(n\d+) (o_n\d+) 0 V = [-+*/()0-9.eV_no ]+)$"
)


class FakeSpice:
    def __init__(self, divide_by_zero="inf"):
        self.divide_by_zero = divide_by_zero  # "inf" | "error"
        self.netlists = []

    def run(self, netlist):
        self.netlists.append(netlist)
        sources, exprs = {}, {}
        for line in netlist.splitlines():
            assert _ALLOWED.match(line), f"unexpected netlist line: {line!r}"
            if line.startswith("V") and " DC " in line:
                _, net, _, _, value = line.split()
                sources[net] = float(value)
            elif line.startswith("B"):
                head, expr = line.split(" V = ")
                exprs[head.split()[1]] = expr
        values = dict(sources)
        for _ in range(len(exprs) + 1):
            for net, expr in exprs.items():
                py = re.sub(r"V\((o_n\d+)\)", lambda m: repr(values.get(m.group(1), 0.0)), expr)
                try:
                    values[net] = eval(py, {"__builtins__": {}}, {})
                except ZeroDivisionError:
                    if self.divide_by_zero == "error":
                        return RunResult("failed", output=f"Error: division by zero in b{net[2:]}", message="division by zero", returncode=1)
                    values[net] = math.inf
        text = "Node                                  Voltage\n----                                  -------\n"
        text += "".join(f"{net:<30}{value!r}\n" for net, value in values.items())
        return RunResult("ok", parse_output(text), text, returncode=0)


def node(node_id, node_type, **data):
    return {"id": node_id, "type": node_type, "data": data}


def wire(source, target, handle=None):
    edge = {"id": f"{source}-{target}-{handle}", "source": source, "target": target}
    if handle:
        edge["targetHandle"] = handle
    return edge


class RaisingRunner:
    def run(self, netlist):
        raise AssertionError("ngspice must not be called for this graph")
