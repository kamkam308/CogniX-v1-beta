# SPDX-License-Identifier: AGPL-3.0-only

"""Native deterministic CogniX tools.

These tools run inside the backend without model calls, network calls, external
writes, or secret access. They are intentionally small and auditable.
"""

from __future__ import annotations

import ast
import math
import re
from hashlib import sha256
from html import escape as html_escape
from typing import Any, Callable


COGNIX_NATIVE_CALCULATOR_VERSION = "cognix_native_calculator_v1"
COGNIX_NATIVE_PHYSICS_SOLVER_VERSION = "cognix_native_physics_solver_v1"
COGNIX_NATIVE_LATEX_RENDERER_VERSION = "cognix_native_latex_renderer_v1"

MAX_CALCULATOR_EXPRESSION_LENGTH = 300
MAX_CALCULATOR_AST_NODES = 80
MAX_CALCULATOR_ABS_VALUE = 1_000_000_000_000
MAX_CALCULATOR_EXPONENT_ABS = 12
MAX_PHYSICS_ABS_VALUE = 1_000_000_000_000
MAX_LATEX_SOURCE_LENGTH = 2000
MAX_LATEX_COMMAND_COUNT = 160
SAFE_LATEX_RENDER_TARGET = "streamdown_katex"

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


class LatexRendererValidationError(ValueError):
    """Raised when a LaTeX render request is not safe or valid."""


BLOCKED_LATEX_COMMANDS = {
    "catcode",
    "csname",
    "def",
    "directlua",
    "edef",
    "endinput",
    "futurelet",
    "gdef",
    "href",
    "htmlclass",
    "htmldata",
    "htmlid",
    "htmlstyle",
    "immediate",
    "include",
    "includegraphics",
    "includeonly",
    "input",
    "let",
    "loop",
    "luaexec",
    "newcommand",
    "openout",
    "providecommand",
    "read",
    "renewcommand",
    "repeat",
    "special",
    "url",
    "usepackage",
    "verbatiminput",
    "write",
    "write18",
    "xdef",
}

ALLOWED_LATEX_ENVIRONMENTS = {
    "align",
    "align*",
    "aligned",
    "bmatrix",
    "cases",
    "equation",
    "equation*",
    "gather",
    "gather*",
    "matrix",
    "pmatrix",
    "smallmatrix",
    "split",
    "vmatrix",
    "Vmatrix",
}

LATEX_COMMAND_RE = re.compile(r"\\([A-Za-z]+|.)")
LATEX_ENV_RE = re.compile(r"\\(begin|end)\s*\{([^}]+)\}")
LATEX_HTML_RISK_RE = re.compile(
    r"<\s*script\b|javascript:|onerror\s*=|onload\s*=|data:text/html",
    re.IGNORECASE,
)


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


def _clean_latex_source(source: Any) -> str:
    text = str(source or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise LatexRendererValidationError("LaTeX source is required.")
    if len(text) > MAX_LATEX_SOURCE_LENGTH:
        raise LatexRendererValidationError("LaTeX source is too long.")
    if any((ord(ch) < 32 and ch not in "\n\t") for ch in text):
        raise LatexRendererValidationError("LaTeX source contains unsupported control characters.")
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _latex_commands(source: str) -> list[str]:
    commands: list[str] = []
    for match in LATEX_COMMAND_RE.finditer(source):
        raw = match.group(1)
        if raw.isalpha():
            commands.append(raw.lower())
        elif raw in {"\\", "{", "}", "_", "^", "&", "%", "#", "$"}:
            commands.append(raw)
    return commands


def _validate_latex_braces(source: str) -> None:
    depth = 0
    escaped = False
    for char in source:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise LatexRendererValidationError("LaTeX braces are not balanced.")
    if depth != 0:
        raise LatexRendererValidationError("LaTeX braces are not balanced.")


def _latex_environments(source: str) -> list[str]:
    begins: list[str] = []
    ends: list[str] = []
    for match in LATEX_ENV_RE.finditer(source):
        env = match.group(2).strip()
        if env not in ALLOWED_LATEX_ENVIRONMENTS:
            raise LatexRendererValidationError("LaTeX environment is not allowed.")
        if match.group(1) == "begin":
            begins.append(env)
        else:
            ends.append(env)
    for env in set(begins + ends):
        if begins.count(env) != ends.count(env):
            raise LatexRendererValidationError("LaTeX environments are not balanced.")
    return sorted(set(begins + ends))


def render_latex_expression(
    *,
    source: str,
    display_mode: bool = True,
    context: str = "math",
) -> dict[str, Any]:
    cleaned = _clean_latex_source(source)
    if LATEX_HTML_RISK_RE.search(cleaned):
        raise LatexRendererValidationError("LaTeX source contains unsupported HTML or script content.")
    for command in BLOCKED_LATEX_COMMANDS:
        if re.search(rf"\\{re.escape(command)}\b", cleaned, re.IGNORECASE):
            raise LatexRendererValidationError("LaTeX command is not allowed.")
    _validate_latex_braces(cleaned)
    command_list = _latex_commands(cleaned)
    if len(command_list) > MAX_LATEX_COMMAND_COUNT:
        raise LatexRendererValidationError("LaTeX source has too many commands.")
    blocked = sorted({command for command in command_list if command in BLOCKED_LATEX_COMMANDS})
    if blocked:
        raise LatexRendererValidationError("LaTeX command is not allowed.")
    environments = _latex_environments(cleaned)
    context_key = _normalize_key(context)
    if context_key not in {"general", "math", "physics"}:
        context_key = "math"
    markdown = f"$$\n{cleaned}\n$$" if display_mode else f"${cleaned}$"
    html_tag = "div" if display_mode else "span"
    source_hash = sha256(cleaned.encode("utf-8")).hexdigest()[:18]
    return {
        "latexRendererVersion": COGNIX_NATIVE_LATEX_RENDERER_VERSION,
        "mode": "native_latex_render_packet",
        "status": "render_packet_ready",
        "renderTarget": SAFE_LATEX_RENDER_TARGET,
        "context": context_key,
        "displayMode": bool(display_mode),
        "source": cleaned,
        "sourceHash": source_hash,
        "sourceLength": len(cleaned),
        "commands": sorted(set(command_list)),
        "commandCount": len(command_list),
        "environments": environments,
        "markdown": markdown,
        "htmlPreview": (
            f'<{html_tag} data-cognix-latex="math" data-render-target="{SAFE_LATEX_RENDER_TARGET}">'
            f"{html_escape(cleaned)}</{html_tag}>"
        ),
        "safety": {
            "maxSourceLength": MAX_LATEX_SOURCE_LENGTH,
            "maxCommandCount": MAX_LATEX_COMMAND_COUNT,
            "blockedCommands": sorted(BLOCKED_LATEX_COMMANDS),
            "allowedEnvironments": sorted(ALLOWED_LATEX_ENVIRONMENTS),
            "serverSideCompilation": False,
            "rendererTrustsHtml": False,
        },
        "sideEffects": {
            "latexRenderPacket": True,
            "modelLoad": False,
            "generation": False,
            "networkToolCall": False,
            "fileRead": False,
            "fileWrite": False,
            "externalWrite": False,
            "secretRead": False,
            "secretWrite": False,
        },
    }


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
