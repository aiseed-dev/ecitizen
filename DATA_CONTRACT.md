# DATA_CONTRACT — eCitizenStatic

取得層 (`build_data.py`) と描画層 (`generate.py`) の境界、および公開 JSON
(旧 JSON エンドポイント互換) のスキーマ定義。ここに書かれていないフィールドを
テンプレートから参照してはならない。

共通規約:

- 文字コード UTF-8、非 ASCII はエスケープしない (`ensure_ascii=False`)
- 公開 JSON はコンパクト表記 (`separators=(',', ':')`) — 旧 ContentResult と同形
- 市町村コードは 5 桁ゼロ埋め文字列 (例 `"01100"`)、都道府県コードは 2 桁 (例 `"13"`)
- 人口は整数 (人)。欠測・非公表は行自体を出さない (null は使わない)

---

## 1. マスター (`data/masters/`, 抽出元 = PopulationClass.cs)

| ファイル | 型 | 内容 |
|---------|----|------|
| `prefcode.json` | `{code: 県名}` | 47 都道府県。表示順 = コード順 |
| `citydic20161010.json` | `{code: 市町村名}` | 1,741 市区町村 (2016-10-10 時点の市町村構成) |
| `codetrans20151001.json` | `{新code: "旧code[:旧code...]"}` | pd (国勢調査) 用コード変換 |
| `codetrans20140401.json` | 同上 | 旧データ用 (参考。Phase 1 では未使用) |
| `countrycode.json` | `{code: 国名}` | Phase 2 (Country) 用 |
| `ages3.json` | `[string]` | 21 要素: 総数, 0～4歳, …, 90歳以上, 年齢不詳 |

`codetrans20180401.json` (pp 用) は現行 C# で空辞書。空ファイルとして扱う。

## 2. 取得層の中間データ (`data/population/`)

### 2.1 `city/{code}.json` — 市町村 1 件の描画用モデル

旧 `PopulationChart` (GetCity 実行後) のシリアライズ。descriptor:

```jsonc
{
  "code": "01100",
  "name": "札幌市",
  "pref": "01",
  "pref_name": "北海道",
  "fukushima": false,          // true なら将来推計なし
  "census": [                  // 国勢調査: 21 行 × 8 列 (1980..2015)
    {"series": "総数", "population": [1401757, ...8個]},
    ...
  ],
  "projection": [              // 将来推計: 20 行 × 7 列 (2015..2045)。fukushima 時は []
    {"series": "総数", "population": [1952356, ...7個]},
    ...
  ],
  "index": [                   // 人口指数: census 8 件 + projection 7 件 (fukushima 時は 8 件)
    {
      "year": 1980,            // projection 側は 2015..2045
      "kind": "census",        // "census" | "projection"
      "young": 323473,         // 年少人口 (0-14)
      "working": 989009,       // 生産年齢人口 (15-64)
      "old": 89275,            // 老年人口 (65+, 90歳以上を含む)
      "old_old": 30184,        // 後期老年人口 (75+)
      "young_pct": 23.06,      // 割合・指数は double のまま格納し、
      "working_pct": 70.5,     //   丸めは描画層のフィルタで行う
      "old_pct": 6.36,
      "old_old_pct": 2.15,
      "young_index": 32.7,
      "old_index": 9.02,
      "dependency_index": 41.7,
      "aging_index": 27.6
    },
    ...
  ]
}
```

制約:

- `census` は必ず 21 行・各行 8 要素。`projection` は 20 行・各行 7 要素 or 空配列。
- `index` の割合・指数は**丸め前の値** (描画層で .NET `"0.0"` 互換に丸める)。
- 割合・指数は分母が 0 の場合 **null**(避難等による人口 0: 福島6町村の2015年、
  三宅村の2000年)。描画層は null を「-」と表示する。
  旧 C# は NaN/∞ を表示していたが、意図的に挙動を改善した箇所。
- コード変換 (codetrans) の合算は取得層で解決済み。描画層は変換を知らない。

### 2.2 `cityinfo2015.json` — サイドバー基本情報

旧 `App_Data/Population2015/2015/population2015.json` をそのまま採用 (キーは旧 C# の
JsonProperty 名: `code, name, popu2015, order2015, popu2010, order2010, area,
house2015, house2010`)。描画層は `code` で検索し、無ければサイドバー部品を出さない。

## 3. 公開 JSON (public/ 配下、旧エンドポイント互換)

### 3.1 `Population/CityData/{code}.json`

旧 `/Population/CityData/{id}` と同一形式。Highcharts series 配列:

```json
[{"name":"年齢不詳","data":[d1,...,d8]},
 {"name":"90歳以上","data":[c1,...,c8,p2020,...,p2045]},
 ...,
 {"name":"0～4歳","data":[...]}]
```

- 系列順: 年齢不詳 → 90歳以上 → … → 0～4歳 (20 系列)
- 年齢不詳のみ 8 点。他は census 8 点 + projection 6 点 (2020–2045) の 14 点
- 福島県: 年齢不詳 8 点、他系列は census 8 点 + `0` を 5 点 (旧実装を忠実に再現)
- x 軸カテゴリ (1980..2045) は JSON に含まれない (テンプレート側定数)

### 3.2 `Population/CityList/{pref}.json`

旧 `/Population/CityList/{id}` と同一形式:

```json
[{"code":"01100","name":"札幌市"},{"code":"01202","name":"函館市"},...]
```

順序は `citydic20161010.json` の定義順 (= コード昇順)。

## 4. 描画層フィルタの書式規約 (citizenlib/filters.py)

| フィルタ | .NET 相当 | 例 |
|---------|-----------|----|
| `num` | `ToString("#,##0")` | `1952356 → "1,952,356"` |
| `f1` | `ToString("0.0")` / `Math.Round(x,1,AwayFromZero)` | `11.649 → "11.6"`, `0.25 → "0.3"` |
| `numf1` | `ToString("#,##0.0")` | `1741.26 → "1,741.3"` |
| `dstr` | `double.ToString()` | `1121.26 → "1121.26"`, `100.0 → "100"` |

丸めは常に **round-half-away-from-zero** (Python 既定の銀行丸めは使用しない)。

## 5. スキーマ変更の手順

1. 本書を先に更新する (フィールド追加・削除・意味変更)
2. `build_data.py` と `generate.py`/テンプレートを同一コミットで追随させる
3. ビルド時スキーマ検証 (generate.py 内 assert) を更新する
