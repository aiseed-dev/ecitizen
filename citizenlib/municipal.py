"""市町村の廃置分合 (e-Stat 統計LOD 由来) のローダとコード変換。

データは data/masters/municipal_changes.json (tools/fetch_sac_lod.py が生成、
DESIGN.md §18、DATA_CONTRACT.md §1.1)。1970-04-01 以降の全変更を収録。

自己チェック: python -m citizenlib.municipal
"""
import json
from pathlib import Path

_PATH = (Path(__file__).resolve().parent.parent
         / "data" / "masters" / "municipal_changes.json")
_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(_PATH.read_text(encoding="utf-8"))
    return _cache


def changes() -> list:
    """全変更ペア (date, old.code, new.code 順)。"""
    return load()["changes"]


def reasons() -> dict:
    """事由キー → 日本語ラベル。"""
    return load()["reasons"]


def history_of(code: str) -> list:
    """指定コードが関与した変更 (旧側・新側とも)。市町村ページの履歴表示用。"""
    return [c for c in changes()
            if c["old"]["code"] == code or c["new"]["code"] == code]


def build_code_trans(since: str, until: str | None = None) -> dict:
    """since < date <= until のコード変更を連鎖解決した {旧code: 現行code}。

    - コードが変わらない変更 (名称変更・境界変更等) は無視する
    - 分割 (1旧コード → 複数の新コード) は変換先が一意でないため除外し、
      戻り値とは別に ambiguous 集合として `build_code_trans.ambiguous` に残す
    - A→B、B→C と連鎖する場合は A→C まで解決する
    """
    hops: dict[str, set] = {}
    for c in changes():
        old, new = c["old"]["code"], c["new"]["code"]
        if old == new or c["date"] <= since or (until and c["date"] > until):
            continue
        hops.setdefault(old, set()).add(new)

    ambiguous = {old for old, news in hops.items() if len(news) > 1}
    single = {old: next(iter(news)) for old, news in hops.items()
              if len(news) == 1}

    resolved = {}
    for old in single:
        cur = old
        seen = set()
        while cur in single and cur not in seen:
            seen.add(cur)
            cur = single[cur]
        if cur not in ambiguous:
            resolved[old] = cur
    build_code_trans.ambiguous = ambiguous  # type: ignore[attr-defined]
    return resolved


def _selfcheck() -> None:
    from . import masters

    data = load()
    ch = changes()
    assert len(ch) > 2000, len(ch)
    assert all(len(c["old"]["code"]) == 5 and len(c["new"]["code"]) == 5
               for c in ch)
    assert set(c["reason"] for c in ch) <= set(data["reasons"]), "未知の事由"

    # 既知ケース: 市制施行によるコード変更
    trans = build_code_trans("2010-01-01")
    assert trans["40305"] == "40231", "那珂川町→那珂川市"
    assert trans["04423"] == "04216", "富谷町→富谷市"
    assert trans["03305"] == "03216", "滝沢村→滝沢市"
    # masters.IPSS_CODE_TRANS / CITY_REDIRECTS との整合
    for old, new in masters.IPSS_CODE_TRANS.items():
        assert trans.get(old) == new, (old, new, trans.get(old))
    for old, new in masters.CITY_REDIRECTS.items():
        assert trans.get(old) == new, (old, new, trans.get(old))

    # 手書きの CHANGE_CODE_AFTER_2010 (TFR用) との整合
    trans2 = build_code_trans("2010-01-01", "2016-10-10")
    mismatch = {k: (v, trans2.get(k))
                for k, v in masters.CHANGE_CODE_AFTER_2010.items()
                if trans2.get(k) != v}
    assert not mismatch, mismatch

    # 連鎖解決: 1970年以降の全変換が最終的に現行コードに到達している
    #  (変換先が更に旧コードのままになっていない)
    trans_all = build_code_trans("1970-04-01")
    stale = {o: n for o, n in trans_all.items()
             if n in trans_all and trans_all[n] != n}
    assert not stale, list(stale.items())[:5]

    print(f"municipal_changes: {len(ch)} 件 / 事由 {len(data['reasons'])} 種 / "
          f"2010年以降のコード変換 {len(trans)} 件 / "
          f"1970年以降 {len(trans_all)} 件 "
          f"(分割等の除外 {len(build_code_trans.ambiguous)} 件) — 自己チェック OK")


if __name__ == "__main__":
    _selfcheck()
