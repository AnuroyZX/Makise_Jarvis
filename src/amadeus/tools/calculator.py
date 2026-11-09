from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any, Optional

ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "pi": math.pi,
    "e": math.e,
}


class CalculatorTool:
    """
    Module 7 (Herramientas - Calculadora y Conversor Matemático):
    Safe AST-based arithmetic evaluator and natural language math solver.
    """

    @classmethod
    def _eval_node(cls, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Literal no numérico: {node.value}")
        if isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            op_type = type(node.op)
            if op_type in ALLOWED_OPERATORS:
                return ALLOWED_OPERATORS[op_type](left, right)
            raise ValueError(f"Operador no soportado: {op_type}")
        if isinstance(node, ast.UnaryOp):
            operand = cls._eval_node(node.operand)
            op_type = type(node.op)
            if op_type in ALLOWED_OPERATORS:
                return ALLOWED_OPERATORS[op_type](operand)
            raise ValueError(f"Operador unario no soportado: {op_type}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ALLOWED_FUNCTIONS:
                func = ALLOWED_FUNCTIONS[node.func.id]
                args = [cls._eval_node(a) for a in node.args]
                return func(*args)
            raise ValueError(f"Función no permitida: {ast.dump(node)}")
        if isinstance(node, ast.Name) and node.id in ALLOWED_FUNCTIONS:
            return ALLOWED_FUNCTIONS[node.id]
        raise ValueError(f"Expresión no soportada: {ast.dump(node)}")

    @classmethod
    def safe_calculate(cls, expression: str) -> Optional[float]:
        clean = expression.strip()
        # Normalization
        clean = clean.replace("x", "*").replace("X", "*").replace("×", "*").replace("÷", "/")
        clean = clean.replace("^", "**")
        clean = re.sub(r"\s+", "", clean)
        try:
            tree = ast.parse(clean, mode="eval")
            res = cls._eval_node(tree.body)
            return float(res)
        except Exception:
            return None

    @classmethod
    def evaluate_natural_language(cls, text: str) -> Optional[str]:
        lower = text.lower().strip()

        # 1. Percentages: "calcula el 15% de 3000", "cuánto es el 20 por ciento de 80"
        m_pct = re.search(
            r"\b(?:cu[aá]nto\s+es|calcula|calcular)?\s*(?:el\s+)?(\d+(?:\.\d+)?)\s*(?:%|por\s+ciento)\s+de\s+(\d+(?:\.\d+)?)\b",
            lower,
        )
        if m_pct:
            pct = float(m_pct.group(1))
            total = float(m_pct.group(2))
            res = (pct / 100.0) * total
            res_str = f"{round(res, 2):g}"
            return (
                f"[emotion:smug] [gesture:nod] El {pct:g}% de {total:g} es {res_str}.\n"
                f"---DETALLE---\n🔢 Cálculo de Porcentaje:\n• {pct:g}% de {total:g} = **{res_str}**"
            )

        # 2. Unit Conversions:
        # km to miles
        m_km = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:km|kil[oó]metros?)\s+a\s+(?:millas?)\b", lower)
        if m_km:
            km = float(m_km.group(1))
            miles = km * 0.621371
            return (
                f"[emotion:analytical] [gesture:nod] {km:g} kilómetros equivalen a {round(miles, 2):g} millas.\n"
                f"---DETALLE---\n📏 Conversión de Longitud:\n• {km:g} km = **{round(miles, 2):g} mi**"
            )

        # miles to km
        m_mi = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:millas?)\s+a\s+(?:km|kil[oó]metros?)\b", lower)
        if m_mi:
            miles = float(m_mi.group(1))
            km = miles * 1.60934
            return (
                f"[emotion:analytical] [gesture:nod] {miles:g} millas equivalen a {round(km, 2):g} kilómetros.\n"
                f"---DETALLE---\n📏 Conversión de Longitud:\n• {miles:g} mi = **{round(km, 2):g} km**"
            )

        # Celsius to Fahrenheit
        m_cf = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:grados?\s+)?(?:celsius|c|cent[ií]grados?)\s+a\s+(?:fahrenheit|f)\b", lower)
        if m_cf:
            c = float(m_cf.group(1))
            f = (c * 9.0 / 5.0) + 32.0
            return (
                f"[emotion:analytical] [gesture:nod] {c:g}°C equivalen a {round(f, 2):g}°F.\n"
                f"---DETALLE---\n🌡️ Conversión de Temperatura:\n• {c:g}°C = **{round(f, 2):g}°F**"
            )

        # 3. Arithmetic: "cuánto es 15 por 24", "calcula 450 + 23", "cuánto es 144 / 12"
        m_arith = re.search(
            r"\b(?:cu[aá]nto\s+es|calcula|calcular|resuelve|resolver)\s+([0-9\s\+\-\*\/\^\(\)\.xX×÷por|más|mas|menos|entre|dividido]+)\b",
            lower,
        )
        if m_arith:
            expr_raw = m_arith.group(1)
            # Spanish words to operators
            norm = expr_raw.replace("por", "*").replace("más", "+").replace("mas", "+")
            norm = norm.replace("menos", "-").replace("dividido entre", "/").replace("dividido por", "/").replace("entre", "/")
            # If it contains digits and arithmetic symbols
            if re.search(r"\d", norm) and re.search(r"[\+\-\*\/\^]", norm):
                val = cls.safe_calculate(norm)
                if val is not None:
                    res_fmt = f"{round(val, 4):g}"
                    clean_expr = norm.strip()
                    return (
                        f"[emotion:smug] [gesture:nod] El resultado es {res_fmt}.\n"
                        f"---DETALLE---\n🧮 Operación Matemática:\n• Expresión: `{clean_expr}`\n• Resultado: **{res_fmt}**"
                    )

        return None
