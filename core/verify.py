"""ЖИ құрастырған жаттығулардың жауабын Python арқылы дәл тексеру.

ЖИ әр жаттығуға жауапты есептейтін арифметикалық өрнек береді
(мысалы "(2+1/3) + (1+3/4)"). Бұл модуль өрнекті жай бөлшектермен
(Fraction) дөңгелектеусіз есептеп, ЖИ жазған жауаппен салыстырады.
Сәйкес келмесе — жаттығу мұғалімге көрсетілмейді.
"""
from __future__ import annotations

import ast
import operator
import re
from fractions import Fraction

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


class VerifyError(ValueError):
    pass


def _eval(node: ast.AST) -> Fraction:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Fraction(str(node.value))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise VerifyError("нөлге бөлу")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        val = _eval(node.operand)
        return -val if isinstance(node.op, ast.USub) else val
    raise VerifyError("рұқсат етілмеген өрнек")


def _normalize(text: str) -> str:
    text = str(text).strip()
    text = text.replace("−", "-").replace("–", "-").replace("×", "*").replace("·", "*").replace(":", "/").replace("÷", "/")
    # ондық үтір: 2,5 -> 2.5 (тек цифрлар арасында)
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    return text


def eval_expression(expr: str) -> Fraction:
    expr = _normalize(expr)
    if len(expr) > 200:
        raise VerifyError("өрнек тым ұзын")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise VerifyError("өрнек оқылмады") from exc
    return _eval(tree)


_MIXED = re.compile(r"^\s*(-?)(\d+)\s+(\d+)\s*/\s*(\d+)\s*$")


def parse_answer(answer: str) -> Fraction:
    """'7/12', '4 1/12' (аралас сан), '2,5', '-3' пішіндерін оқиды."""
    text = _normalize(answer)
    m = _MIXED.match(text)
    if m:
        sign, whole, num, den = m.groups()
        if int(den) == 0:
            raise VerifyError("бөлім нөлге тең")
        val = int(whole) + Fraction(int(num), int(den))
        return -val if sign else val
    return eval_expression(text)


def check(expression: str, answer_value: str) -> bool:
    """Өрнектің мәні жауапқа тең болса True."""
    try:
        return eval_expression(expression) == parse_answer(answer_value)
    except (VerifyError, ZeroDivisionError, OverflowError):
        return False


def format_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    whole, rem = divmod(abs(value.numerator), value.denominator)
    sign = "-" if value < 0 else ""
    if whole:
        return f"{sign}{whole} {rem}/{value.denominator}"
    return f"{sign}{rem}/{value.denominator}"
