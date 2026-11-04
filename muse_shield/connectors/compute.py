"""Arithmetic on hidden amounts, done on this device.

The model writes `<SALARY_1> * 12 - <LOAN_1>`; the policy fills in the real amounts here
("₹10 lakh * 12 - ₹38 lakh"); this evaluates it and stores the answer as a new placeholder
(<RESULT_1>), so the model can use the result without ever seeing a number. A comparison
returns only yes or no. `unit` says how to show the answer: money (the amounts' currency),
percent or number.
"""

from __future__ import annotations

import ast
import math
import operator
import re

from ..app.vault import Vault

SCALE = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5, "lpa": 1e5, "crore": 1e7,
         "crores": 1e7, "cr": 1e7, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}
CURRENCY = {"₹": "₹", "rs": "₹", "rs.": "₹", "inr": "₹", "rupees": "₹", "$": "$", "usd": "$", "dollars": "$",
            "€": "€", "eur": "€", "£": "£", "gbp": "£"}
AMOUNT = re.compile(
    r"(?P<cur>₹|\$|€|£|\b(?:rs\.?|inr|usd|eur|gbp)\b)?\s*(?P<num>\d(?:[\d,]*\d)?(?:\.\d+)?)"
    r"(?:\s*(?P<scale>lpa|lakhs?|lacs?|crores?|cr|thousand|million|mn|billion|bn|[klmb])\b)?"
    r"(?:\s*(?P<word>rupees|dollars|inr|usd))?", re.I)
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Eq: operator.eq,
       ast.NotEq: operator.ne}
FUNCS = {"min": min, "max": max, "abs": abs, "round": round, "sum": lambda *xs: math.fsum(xs)}
# A filled-in amount is the text the analysis marked, which can carry its period ("₹1,60,000 a month",
# "₹4.2 lakh per annum", "$90/hr"): the period isn't part of the number, so it goes before evaluating.
PERIOD = re.compile(r"\s*(?:/|\bper\b|\ba\b|\beach\b|\bevery\b)\s*(?:month|mo|year|yr|annum|day|week|wk|hour|hr|night)s?\b"
                    r"|\s*\bp\.?\s?[am]\.?(?=\s|$|[)*/+-])|\s*\b(?:monthly|yearly|annually|weekly|daily)\b", re.I)
WORD = re.compile(r"[^\W\d_][\w.]*(?:-[^\W\d_][\w.]*)*")  # whole words, hyphens included ("take-home")


def to_python(expression: str) -> tuple[str, str]:
    """Turn every amount ("₹2,40,000", "10 lakh rupees", "$1.5m") into a plain number. Returns (expr, currency)."""
    currency = ""

    def number(m: re.Match) -> str:
        nonlocal currency
        cur = (m.group("cur") or m.group("word") or "").lower()
        currency = currency or CURRENCY.get(cur, "")
        value = float(m.group("num").replace(",", "")) * SCALE.get((m.group("scale") or "").lower(), 1.0)
        return repr(int(value)) if value.is_integer() else repr(value)  # whole stays whole: round(x, 2) needs an int

    expr = PERIOD.sub("", expression.replace("×", "*").replace("÷", "/").replace("−", "-"))
    expr = AMOUNT.sub(number, expr)
    # any other words left from a filled-in value ("take-home", "net") aren't arithmetic; function names stay
    expr = WORD.sub(lambda m: m.group(0) if m.group(0) in FUNCS else "", expr)
    return expr, currency


def evaluate(expr: str):
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in CMP:
            return CMP[type(node.ops[0])](ev(node.left), ev(node.comparators[0]))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and not node.keywords:
            return FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError("only numbers, + - * / % **, comparisons and min/max/sum/abs/round are allowed")

    return ev(ast.parse(expr, mode="eval"))


def fmt(value: float, currency: str) -> str:
    if currency == "₹":
        neg, whole, frac = value < 0, f"{abs(value):.2f}".split(".")[0], f"{abs(value):.2f}".split(".")[1]
        head, tail, groups = whole[:-3], whole[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        text = ",".join(groups + [tail]) + ("" if frac == "00" else "." + frac)
        return ("-" if neg else "") + "₹" + text
    text = f"{value:,.2f}".removesuffix(".00")
    return f"{currency}{text}" if currency else text


def compute(vault: Vault, chat_id: str, args: dict) -> dict:
    expr, currency = to_python(args["expression"])
    value = evaluate(expr)
    if isinstance(value, bool):
        return {"status": "compared on this device", "result": "yes" if value else "no"}
    unit = (args.get("unit") or ("money" if currency else "number")).lower()
    shown = f"{float(value):.1f}".removesuffix(".0") + "%" if unit == "percent" else fmt(float(value), currency if unit == "money" else "")
    vault.entity_placeholder(chat_id, "AMOUNT", shown, base="RESULT")  # the executor swaps it for <RESULT_n> before any agent sees it
    return {"status": "computed on this device", "result": shown}
