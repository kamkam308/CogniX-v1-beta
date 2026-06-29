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
COGNIX_NATIVE_PHYSICS_SOLVER_VERSION = "cognix_native_physics_solver_v1"

MAX_CALCULATOR_EXPRESSION_LENGTH = 300
MAX_CALCULATOR_AST_NODES = 80
MAX_CALCULATOR_ABS_VALUE = 1_000_000_000_000
MAX_CALCULATOR_EXPONENT_ABS = 12
MAX_PHYSICS_ABS_VALUE = 1_000_000_000_000

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


class PhysicsSolverValidationError(ValueError):
    """Raised when a physics formula request is not safe or solvable."""


PHYSICS_FORMULAS: dict[str, dict[str, Any]] = {
    "speed": {
        "label": "Speed",
        "variables": ["speed", "distance", "time"],
        "units": {"speed": "m/s", "distance": "m", "time": "s"},
        "solve": {
            "speed": lambda v: v["distance"] / v["time"],
            "distance": lambda v: v["speed"] * v["time"],
            "time": lambda v: v["distance"] / v["speed"],
        },
    },
    "force": {
        "label": "Newton second law",
        "variables": ["force", "mass", "acceleration"],
        "units": {"force": "N", "mass": "kg", "acceleration": "m/s^2"},
        "solve": {
            "force": lambda v: v["mass"] * v["acceleration"],
            "mass": lambda v: v["force"] / v["acceleration"],
            "acceleration": lambda v: v["force"] / v["mass"],
        },
    },
    "ohm_law": {
        "label": "Ohm law",
        "variables": ["voltage", "current", "resistance"],
        "units": {"voltage": "V", "current": "A", "resistance": "ohm"},
        "solve": {
            "voltage": lambda v: v["current"] * v["resistance"],
            "current": lambda v: v["voltage"] / v["resistance"],
            "resistance": lambda v: v["voltage"] / v["current"],
        },
    },
    "kinetic_energy": {
        "label": "Kinetic energy",
        "variables": ["kinetic_energy", "mass", "velocity"],
        "units": {"kinetic_energy": "J", "mass": "kg", "velocity": "m/s"},
        "solve": {
            "kinetic_energy": lambda v: 0.5 * v["mass"] * v["velocity"] ** 2,
            "mass": lambda v: (2 * v["kinetic_energy"]) / (v["velocity"] ** 2),
            "velocity": lambda v: math.sqrt((2 * v["kinetic_energy"]) / v["mass"]),
        },
    },
    "momentum": {
        "label": "Momentum",
        "variables": ["momentum", "mass", "velocity"],
        "units": {"momentum": "kg*m/s", "mass": "kg", "velocity": "m/s"},
        "solve": {
            "momentum": lambda v: v["mass"] * v["velocity"],
            "mass": lambda v: v["momentum"] / v["velocity"],
            "velocity": lambda v: v["momentum"] / v["mass"],
        },
    },
    "density": {
        "label": "Density",
        "variables": ["density", "mass", "volume"],
        "units": {"density": "kg/m^3", "mass": "kg", "volume": "m^3"},
        "solve": {
            "density": lambda v: v["mass"] / v["volume"],
            "mass": lambda v: v["density"] * v["volume"],
            "volume": lambda v: v["mass"] / v["density"],
        },
    },
    "work": {
        "label": "Mechanical work",
        "variables": ["work", "force", "distance"],
        "units": {"work": "J", "force": "N", "distance": "m"},
        "solve": {
            "work": lambda v: v["force"] * v["distance"],
            "force": lambda v: v["work"] / v["distance"],
            "distance": lambda v: v["work"] / v["force"],
        },
    },
}


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


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


def _finite_physics_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsSolverValidationError("Physics variables must be finite numbers.")
    number = float(value)
    if not math.isfinite(number):
        raise PhysicsSolverValidationError("Physics variables must be finite.")
    if abs(number) > MAX_PHYSICS_ABS_VALUE:
        raise PhysicsSolverValidationError("Physics value exceeds the safety bound.")
    return number


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


def solve_physics_formula(
    *,
    formula_id: str,
    variables: dict[str, Any],
    precision: int = 12,
) -> dict[str, Any]:
    formula_key = _normalize_key(formula_id)
    formula = PHYSICS_FORMULAS.get(formula_key)
    if formula is None:
        raise PhysicsSolverValidationError("Unknown physics formula.")
    allowed_variables = list(formula["variables"])
    provided: dict[str, float] = {}
    for raw_key, raw_value in (variables or {}).items():
        key = _normalize_key(raw_key)
        if key not in allowed_variables:
            raise PhysicsSolverValidationError("Unknown variable for this physics formula.")
        if raw_value is None:
            continue
        provided[key] = _finite_physics_number(raw_value)
    missing = [key for key in allowed_variables if key not in provided]
    if len(missing) != 1:
        raise PhysicsSolverValidationError("Exactly one formula variable must be missing.")
    target = missing[0]
    try:
        result = _finite_physics_number(formula["solve"][target](provided))
    except (ZeroDivisionError, ValueError, OverflowError) as exc:
        raise PhysicsSolverValidationError("Formula cannot be solved with the provided values.") from exc
    precision = max(1, min(int(precision), 16))
    units = dict(formula["units"])
    return {
        "physicsSolverVersion": COGNIX_NATIVE_PHYSICS_SOLVER_VERSION,
        "mode": "native_deterministic_physics_solver",
        "status": "solved",
        "formulaId": formula_key,
        "formulaLabel": formula["label"],
        "targetVariable": target,
        "targetUnit": units.get(target),
        "providedVariableIds": sorted(provided),
        "result": result,
        "resultText": _format_result(result, precision),
        "precision": precision,
        "units": units,
        "formulaHash": sha256(
            f"{formula_key}|{target}|{sorted(provided.items())}".encode("utf-8")
        ).hexdigest()[:18],
        "safety": {
            "maxAbsValue": MAX_PHYSICS_ABS_VALUE,
            "availableFormulaIds": sorted(PHYSICS_FORMULAS),
            "requiresExactlyOneMissingVariable": True,
        },
        "sideEffects": {
            "physicsSolve": True,
            "modelLoad": False,
            "generation": False,
            "networkToolCall": False,
            "externalWrite": False,
            "secretRead": False,
            "secretWrite": False,
        },
    }
