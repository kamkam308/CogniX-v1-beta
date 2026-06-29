# SPDX-License-Identifier: AGPL-3.0-only

"""Native deterministic CogniX tools.

These tools run inside the backend without model calls, network calls, external
writes, or secret access. They are intentionally small and auditable.
"""

from __future__ import annotations

import ast
import math
from hashlib import sha256
from typing import Any, Callable


COGNIX_NATIVE_CALCULATOR_VERSION = "cognix_native_calculator_v1"

MAX_CALCULATOR_EXPRESSION_LENGTH = 300
MAX_CALCULATOR_AST_NODES = 80
MAX_CALCULATOR_ABS_VALUE = 1_000_000_000_000
MAX_CALCULATOR_EXPONENT_ABS = 12

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "ln": math.log,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}


class CalculatorValidationError(ValueError):
    """Raised when a calculator expression is not safe or valid."""


def _finite_number(value: Any) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalculatorValidationError("Only finite numeric values are allowed.")
    if not math.isfinite(float(value)):
        raise CalculatorValidationError("Result must be finite.")
    if abs(float(value)) > MAX_CALCULATOR_ABS_VALUE:
        raise CalculatorValidationError("Result exceeds the calculator safety bound.")
    return value


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        return _finite_number(node.value)
    if isinstance(node, ast.Name):
        if node.id not in CONSTANTS:
            raise CalculatorValidationError("Unknown calculator symbol.")
        return CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return _finite_number(value if isinstance(node.op, ast.UAdd) else -value)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return _finite_number(left + right)
        if isinstance(node.op, ast.Sub):
            return _finite_number(left - right)
        if isinstance(node.op, ast.Mult):
            return _finite_number(left * right)
        if isinstance(node.op, ast.Div):
            return _finite_number(left / right)
        if isinstance(node.op, ast.FloorDiv):
            return _finite_number(left // right)
        if isinstance(node.op, ast.Mod):
            return _finite_number(left % right)
        if isinstance(node.op, ast.Pow):
            if abs(float(right)) > MAX_CALCULATOR_EXPONENT_ABS:
                raise CalculatorValidationError("Exponent exceeds the calculator safety bound.")
            return _finite_number(left**right)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise CalculatorValidationError("Only approved calculator functions are allowed.")
        if node.keywords:
            raise CalculatorValidationError("Keyword arguments are not allowed.")
        if len(node.args) > 2:
            raise CalculatorValidationError("Too many calculator function arguments.")
        args = [_eval_node(arg) for arg in node.args]
        return _finite_number(FUNCTIONS[node.func.id](*args))
    raise CalculatorValidationError("Unsupported calculator expression.")


def _format_result(value: float | int, precision: int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{float(value):.{precision}g}"


def evaluate_calculator_expression(expression: str, *, precision: int = 12) -> dict[str, Any]:
    cleaned = " ".join(str(expression or "").strip().split())
    if not cleaned:
        raise CalculatorValidationError("Expression is required.")
    if len(cleaned) > MAX_CALCULATOR_EXPRESSION_LENGTH:
        raise CalculatorValidationError("Expression is too long.")
    try:
        parsed = ast.parse(cleaned, mode = "eval")
    except SyntaxError as exc:
        raise CalculatorValidationError("Expression syntax is invalid.") from exc
    if sum(1 for _ in ast.walk(parsed)) > MAX_CALCULATOR_AST_NODES:
        raise CalculatorValidationError("Expression is too complex.")
    precision = max(1, min(int(precision), 16))
    result = _finite_number(_eval_node(parsed))
    return {
        "calculatorVersion": COGNIX_NATIVE_CALCULATOR_VERSION,
        "mode": "native_deterministic_calculator",
        "status": "evaluated",
        "expression": cleaned,
        "expressionHash": sha256(cleaned.encode("utf-8")).hexdigest()[:18],
        "result": result,
        "resultText": _format_result(result, precision),
        "precision": precision,
        "safety": {
            "maxExpressionLength": MAX_CALCULATOR_EXPRESSION_LENGTH,
            "maxAstNodes": MAX_CALCULATOR_AST_NODES,
            "maxAbsValue": MAX_CALCULATOR_ABS_VALUE,
            "allowedConstants": sorted(CONSTANTS),
            "allowedFunctions": sorted(FUNCTIONS),
        },
        "sideEffects": {
            "calculatorEvaluation": True,
            "modelLoad": False,
            "generation": False,
            "networkToolCall": False,
            "externalWrite": False,
            "secretRead": False,
            "secretWrite": False,
        },
    }
