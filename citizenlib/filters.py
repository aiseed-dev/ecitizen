"""Jinja2 フィルタ。.NET の数値書式を再現する (DATA_CONTRACT.md §4)。

丸めは常に round-half-away-from-zero (.NET MidpointRounding.AwayFromZero 互換)。
Python 組み込みの round() は銀行丸めのため使わない。
"""
from decimal import Decimal, ROUND_HALF_UP


def _dec(v) -> Decimal:
    # float の 2 進誤差を持ち込まないよう、最短往復表現の文字列を経由する
    return Decimal(repr(float(v)))


def _round_away(v, digits: int) -> Decimal:
    q = Decimal(1).scaleb(-digits)
    return _dec(v).quantize(q, rounding=ROUND_HALF_UP)


def num(v) -> str:
    """.NET ToString("#,##0")"""
    return f"{int(_round_away(v, 0)):,}"


def f1(v) -> str:
    """.NET ToString("0.0") / Math.Round(x, 1, AwayFromZero)。

    None は「-」(分母 0 の指標。DATA_CONTRACT §2.1)。
    """
    if v is None:
        return "-"
    return str(_round_away(v, 1))


def numf1(v) -> str:
    """.NET ToString("#,##0.0")"""
    return f"{_round_away(v, 1):,}"


def dstr(v) -> str:
    """.NET double.ToString() — 100.0 は "100"、1121.26 は "1121.26"。"""
    s = repr(float(v))
    return s[:-2] if s.endswith(".0") else s


FILTERS = {"num": num, "f1": f1, "numf1": numf1, "dstr": dstr}
