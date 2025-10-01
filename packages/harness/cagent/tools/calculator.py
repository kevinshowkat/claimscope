"""Deterministic arithmetic evaluator used by the agent harness."""

from __future__ import annotations

import ast
import operator
from decimal import Decimal, getcontext
from typing import Any, Dict

getcontext().prec = 28

_ALLOWED_NODES = {
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.FloorDiv,
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Load,
    ast.Tuple,
}

_BIN_OPS: Dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def _ensure_safe(node: ast.AST) -> None:
    for child in ast.walk(node):
        if type(child) not in _ALLOWED_NODES:
            raise ValueError(f"unsupported expression node: {type(child).__name__}")
        if isinstance(child, ast.Constant) and not isinstance(child.value, (int, float)):
            raise ValueError("constants must be numeric")


def _eval(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        return Decimal(str(node.value))
    if isinstance(node, ast.Num):  # pragma: no cover - legacy AST
        return Decimal(str(node.n))
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        raise ValueError("unsupported unary operator")
    if isinstance(node, ast.BinOp):
        left = _eval(node.left)
        right = _eval(node.right)
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError("unsupported binary operator")
        return Decimal(op(left, right))
    if isinstance(node, ast.Tuple):
        raise ValueError("tuple literal not allowed")
    raise ValueError("unsupported expression")


def run(expression: str) -> str:
    if not expression or not expression.strip():
        raise ValueError("expression required")
    tree = ast.parse(expression, mode="eval")
    _ensure_safe(tree)
    result = _eval(tree)
    # normalise ints vs decimals
    if result == result.to_integral():
        return str(int(result))
    return format(result.normalize(), "f")
