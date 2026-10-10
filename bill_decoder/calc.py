"""Safe arithmetic evaluator. The LLM *plans* expressions, this code *computes* them exactly.

Only numbers, names from the supplied environment, + - * / // % **, comparisons, a few
whitelisted functions, list literals and list indexing are allowed. No eval(), no attributes.
"""
from __future__ import annotations

import ast
import operator

MAX_EXPR_LEN = 600


class CalcError(ValueError):
    pass


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


def _flat(args) -> list:
    out: list = []
    for a in args:
        if isinstance(a, (list, tuple)):
            out.extend(_flat(a))
        else:
            out.append(a)
    return out


def _nonempty(args) -> list:
    vals = _flat(args)
    if not vals:
        raise CalcError("empty list")
    return vals


def _pct(part, whole):
    if whole == 0:
        raise CalcError("division by zero in pct()")
    return part / whole * 100


FUNCS = {
    "sum": lambda *a: sum(_flat(a)),
    "avg": lambda *a: sum(_nonempty(a)) / len(_nonempty(a)),
    "mean": lambda *a: sum(_nonempty(a)) / len(_nonempty(a)),
    "min": lambda *a: min(_nonempty(a)),
    "max": lambda *a: max(_nonempty(a)),
    "round": lambda x, n=0: round(x, int(n)),
    "abs": abs,
    "len": lambda x: len(x),
    "count_gt": lambda lst, x: sum(1 for v in _flat([lst]) if v > x),
    "count_ge": lambda lst, x: sum(1 for v in _flat([lst]) if v >= x),
    "count_lt": lambda lst, x: sum(1 for v in _flat([lst]) if v < x),
    "count_le": lambda lst, x: sum(1 for v in _flat([lst]) if v <= x),
    "pct": _pct,
}


def safe_eval(expr: str, env: dict | None = None):
    env = env or {}
    expr = (expr or "").strip()
    if not expr:
        raise CalcError("empty expression")
    if len(expr) > MAX_EXPR_LEN:
        raise CalcError("expression too long")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CalcError(f"syntax error: {exc.msg}") from exc
    return _ev(tree.body, env)


def _ev(node, env):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise CalcError("only numeric constants are allowed")
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise CalcError(f"unknown name: {node.id}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _ev(node.left, env), _ev(node.right, env)
        if isinstance(node.op, ast.Pow) and (abs(right) > 20 or abs(left) > 1e9):
            raise CalcError("exponent too large")
        try:
            return _BIN[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalcError("division by zero") from exc
        except TypeError as exc:
            raise CalcError(f"bad operands: {exc}") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_ev(node.operand, env))
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_ev(e, env) for e in node.elts]
    if isinstance(node, ast.Subscript):
        seq, idx = _ev(node.value, env), _ev(node.slice, env)
        if not isinstance(seq, list) or not isinstance(idx, int):
            raise CalcError("only list[int] indexing is allowed")
        try:
            return seq[idx]
        except IndexError as exc:
            raise CalcError("index out of range") from exc
    if isinstance(node, ast.Compare):
        left = _ev(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            if type(op) not in _CMP:
                raise CalcError("unsupported comparison")
            right = _ev(comp, env)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = [_ev(v, env) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.IfExp):
        return _ev(node.body, env) if _ev(node.test, env) else _ev(node.orelse, env)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS or node.keywords:
            raise CalcError("function not allowed")
        args = [_ev(a, env) for a in node.args]
        try:
            return FUNCS[node.func.id](*args)
        except CalcError:
            raise
        except Exception as exc:  # TypeError, ValueError, ...
            raise CalcError(f"{node.func.id}() failed: {exc}") from exc
    raise CalcError(f"unsupported syntax: {type(node).__name__}")
