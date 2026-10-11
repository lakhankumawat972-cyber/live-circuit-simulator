"""Safe parser for Formula-node expressions.

The expression is user text that ends up inside a netlist ngspice executes, so
it is never pasted into the netlist. Instead:

1. a hand-written tokenizer accepts ONLY numbers, ``a``, ``b``, ``+ - * /``,
   brackets and blanks/tabs (newlines and every other character are rejected);
2. a recursive-descent parser builds an AST (anything that does not fit the
   grammar is rejected);
3. the netlist text is *re-generated from the AST* with every operation fully
   parenthesised, so nothing the user typed reaches ngspice verbatim.
"""

from __future__ import annotations

import math
from typing import Callable

MAX_LENGTH = 200
MAX_DEPTH = 40
VARIABLES = ("a", "b")
_BLANKS = (" ", "\t")
_OPERATORS = "+-*/"


class FormulaError(ValueError):
    """The expression is not allowed; the message is shown to the user."""


def _describe(ch: str) -> str:
    if ch == "\n":
        return "a new line"
    if ch == "\r":
        return "a carriage return"
    if not ch.isprintable():
        return f"control character U+{ord(ch):04X}"
    return f"'{ch}'"


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _BLANKS:
            i += 1
        elif ch.isascii() and (ch.isdigit() or ch == "."):
            j, dots = i, 0
            while j < n and text[j].isascii() and (text[j].isdigit() or text[j] == "."):
                dots += text[j] == "."
                j += 1
            lexeme = text[i:j]
            if dots > 1 or lexeme == ".":
                raise FormulaError(f"'{lexeme}' is not a valid number")
            tokens.append(("num", lexeme))
            i = j
        elif ch in VARIABLES:
            tokens.append(("var", ch))
            i += 1
        elif ch in _OPERATORS:
            tokens.append(("op", ch))
            i += 1
        elif ch in "()":
            tokens.append((ch, ch))
            i += 1
        else:
            raise FormulaError(
                f"{_describe(ch)} is not allowed - use only numbers, a, b, + - * / and brackets"
            )
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0
        self.depth = 0

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _take(self):
        tok = self._peek()
        self.pos += 1
        return tok

    def parse(self):
        if not self.tokens:
            raise FormulaError("Formula is empty")
        node = self._expr()
        kind, lexeme = self._peek()
        if kind is not None:
            raise FormulaError(f"Unexpected '{lexeme}'")
        return node

    def _enter(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise FormulaError("Formula is nested too deeply")

    def _expr(self):
        self._enter()
        node = self._term()
        while self._peek() in (("op", "+"), ("op", "-")):
            op = self._take()[1]
            node = ("bin", op, node, self._term())
        self.depth -= 1
        return node

    def _term(self):
        node = self._unary()
        while self._peek() in (("op", "*"), ("op", "/")):
            op = self._take()[1]
            node = ("bin", op, node, self._unary())
        return node

    def _unary(self):
        if self._peek() in (("op", "-"), ("op", "+")):
            op = self._take()[1]
            self._enter()
            operand = self._unary()
            self.depth -= 1
            return ("neg", operand) if op == "-" else operand
        return self._primary()

    def _primary(self):
        kind, lexeme = self._take()
        if kind == "num":
            value = float(lexeme)
            if not math.isfinite(value):
                raise FormulaError(f"Number '{lexeme[:12]}...' is too large")
            return ("num", value)
        if kind == "var":
            return ("var", lexeme)
        if kind == "(":
            node = self._expr()
            if self._take()[0] != ")":
                raise FormulaError("Missing closing bracket )")
            return node
        if kind is None:
            raise FormulaError("Formula ends unexpectedly")
        raise FormulaError(f"Unexpected '{lexeme}'")


def _variables(ast, found: set[str]) -> None:
    if ast[0] == "var":
        found.add(ast[1])
    elif ast[0] == "neg":
        _variables(ast[1], found)
    elif ast[0] == "bin":
        _variables(ast[2], found)
        _variables(ast[3], found)


class Formula:
    """A validated expression. Build it with :func:`compile_formula`."""

    def __init__(self, ast):
        self._ast = ast
        found: set[str] = set()
        _variables(ast, found)
        self.variables: tuple[str, ...] = tuple(v for v in VARIABLES if v in found)

    def to_spice(self, net_of: Callable[[str], str]) -> str:
        """Netlist text for the expression, regenerated from the AST."""

        def emit(node) -> str:
            kind = node[0]
            if kind == "num":
                return repr(node[1])
            if kind == "var":
                return f"V({net_of(node[1])})"
            if kind == "neg":
                return f"(0-{emit(node[1])})"
            return f"({emit(node[2])}{node[1]}{emit(node[3])})"

        return emit(self._ast)

    def evaluate(self, values: dict[str, float]) -> float:
        """Reference evaluation; raises ZeroDivisionError on division by zero."""

        def ev(node) -> float:
            kind = node[0]
            if kind == "num":
                return node[1]
            if kind == "var":
                return values[node[1]]
            if kind == "neg":
                return -ev(node[1])
            left, right = ev(node[2]), ev(node[3])
            op = node[1]
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            return left / right

        return ev(self._ast)


def compile_formula(text) -> Formula:
    if not isinstance(text, str):
        raise FormulaError("Formula must be text")
    if len(text) > MAX_LENGTH:
        raise FormulaError(f"Formula is longer than {MAX_LENGTH} characters")
    return Formula(_Parser(_tokenize(text)).parse())
