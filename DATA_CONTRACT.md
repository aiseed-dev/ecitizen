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
| `countrycode.json` | `{code: 国名}` | 33 カ国 (JP含む) |
| `ages2.json` | `[string]` | 20 要素: 総数, 0～4歳, …, 85歳以上, 年齢不詳 (日本以外の国の census 用) |
| `ages3.json` | `[string]` | 21 要素: 総数, 0～4歳, …, 90歳以上, 年齢不詳 (市町村・都道府県・日本の census 用) |

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

### 2.3 `pref/{code}.json` — 都道府県 1 件の描画用モデル

`city/{code}.json` と同一構造 (`code, name, census, projection, index`)。
相違点のみ:

- `pref_name`/`fukushima` フィールドは無し (プレフィックスが無く常に将来推計あり)
- `census` は必ず 21 行×8列、`projection` は必ず 20 行×7列 (空になるケースなし)
- `index` は必ず 15 件 (census 8 + projection 7)
- ソース: 旧 `App_Data/Population2015/Pref/pd{code}.json` / `pp{code}.json`
  (コード変換なし。市町村合併の影響を受けない)

### 2.4 `country/{code}.json` — 国 1 件の描画用モデル

```jsonc
{
  "code": "JP",
  "name": "日本",
  "is_jp": true,              // true: 21行 Ages3 census (kaikyu=90) / false: 20行 Ages2 census (kaikyu=85)
  "census": [...],            // JP: 21行×8列。それ以外: 20行×8列 (Ages2, "85歳以上"で合算済み)
  "projection": [...],        // 常に 20行×7列 (どの国も 90歳以上まで分離した粒度)
  "index": [...]              // 常に 15件 (census 8 + projection 7)。city/pref と同一 shape
}
```

- ソース: 旧 `App_Data/Population2015/Country/ed{code}.json` (census) /
  `ep{code}.json` (projection)。33 カ国 (JP + EU + 32 カ国、`countrycode.json` 参照)
- `index` の算出は city/pref と同じ `_index_of` 計算式を使う。JP以外は
  「90歳以上を老年人口に含めない」(`include90_in_old=False`) 条件で計算する
  (Ages2 の census データでは 85歳以上が「85+」1行に合算されているため、
  `include90_in_old=False` のまま該当行 [14:19] を合計すると 65+ 全体を正しく捕捉する)。
  `projection` は JP/非JP 問わず常に `include90_in_old=True` (常に90歳以上が分離済み)。
- census の値が `0` の要素は「データなし」を意味する (欧州の一部年齢階級・年で
  収集されていない場合がある)。描画層は `numz` フィルタで `0 → "-"` 表示する
  (`index` の `young`/`working`/`old`/`old_old` も同様に `numz` を使う)。

### 2.5 `pyramid/city/{code}.json` — 市町村の人口ピラミッド (男女別)

旧 `PopulationPyramid` のシリアライズ。年ごとの JSON エンドポイントには分割せず
(Cloudflare Pages のファイル数上限対策、§9.1)、1 市町村 = 1 ファイルに
全 14 年分を束ねる。

```jsonc
{
  "code": "01100",
  "max_value": 101607,       // 全年・男女通しての最大値 (グラフスケール用)
  "years": [                 // 14 年分 (1980..2015 は census、2020..2045 は projection)
    {"year": 1980, "kind": "census",
     "male": [70754, ...19個, 65-69から90+の順],   // 行1..19 (総数・年齢不詳を除く19階級)
     "female": [...19個]},
    ...
  ],
  "census_m": [...],         // 生表示用の全列テーブル。city の census/projection と同一shape
  "census_f": [...],         // (21行×8列)
  "projection_m": [...],     // (20行×7列。福島県は [])
  "projection_f": [...]
}
```

- `years` はピラミッド SVG 生成専用 (年ごとに男女19階級ずつ抽出済み)。
  `census_m/f`・`projection_m/f` は元の全期間テーブル表示用 (city の
  `census`/`projection` と同じ shape) で、値の出典は同じデータの異なる切り口。
- 福島県内の市町村は `years` が census 8 件のみ、`projection_m/f` は `[]`
- 年齢階級は `ages3.json` の 1..19 番目 (0～4歳 … 90歳以上、総数と年齢不詳を除く)
- 符号は付けない (男女とも正の値。グラフ描画時に男性側を負に反転するのは描画層の責務)

### 2.6 ランキング系 (`data/rankings/`)

| ファイル | 内容 | 件数 |
|---------|------|------|
| `ranking2045.json` | 旧 `Ranking/CityRanking2045.json` そのまま (`Order,Code,Name,Pref,Value,Order2015,Value2015`) | 1,682 (福島県除く) |
| `cityarea.json` | 旧 `Area/CityAreaData2015.json` + 順位計算 (`団体コード,団体名,面積,参考値,順位`) | 1,741 |
| `citytfr.json` | 旧 `Tfr/CityTfr.xml` を JSON化 + 順位計算・除外フィルタ適用済み (`code,url,name,tfr,order`) | 東京都区部除く |
| `population2015.json` | 旧 `2015/population2015.json` (既存 `cityinfo2015.json` と同一データ。再利用) | 1,741 |
| `city_aging_oldold_2045.json` | `data/population/city/*.json` の projection index から再計算 (65歳以上/75歳以上の 2015→2045 増減) | 1,682 |

`city_aging_oldold_2045.json` は新規の外部データではなく、Phase 1/2 で
生成済みの `data/population/city/{code}.json` の `index` (kind=projection) を
集計したものなので、取得層で改めてファイルを読み込む必要はない
(生成層 = build_data.py 内で完結)。

```jsonc
// city_aging_oldold_2045.json の1件
{"code": "13101", "name": "千代田区",
 "old":     [4931, 5310, ...7個, 2015..2045],   // 65歳以上人口の推移
 "old_old": [2419, 2701, ...7個]}               // 75歳以上人口の推移
```

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

### 3.3 `Population/PrefData/{code}.json`

`CityData` と完全に同一の系列構造 (旧実装のアルゴリズムが同一のため)。
福島県相当の特例なし (全都道府県に将来推計あり)。

### 3.4 `Population/CountryData/{code}.json`

日本 (`JP`) は `CityData` と同一構造 (年齢不詳 + 19系列、各14点)。

日本以外は census が Ages2 (20行、85歳以上で合算済み) だが projection は
常に90歳以上まで分離されているため、系列がずれる。旧実装を忠実に再現する:

```
[0] 年齢不詳: census 8点のみ
[1] "90歳以上": census側は 0 を8個 (対応データなし) + projection 6点(2020-2045)
[2..19] pps[r] (r=1..18, "85歳以上"→"0～4歳"の順): census側は pds[r] の8点
        (pds[1]="85歳以上"の値をそのまま流用) + projection 6点
```

### 3.5 `Population/CityPyramidData/{code}.json`

`data/population/pyramid/city/{code}.json` の `years` をそのまま Highcharts
系列風に整形したもの。旧エンドポイントは年ごと (`CityPyramidData/{id}/{year}`)
だったが、静的化にあたり **1 市町村 = 1 ファイルに全年収録** (§9.1 のファイル数対策)。
クライアントはこの1ファイルを取得し、年の切替はブラウザ内で行う
(男性は表示直前に符号反転する。JSON自体は正の値)。

```jsonc
{"years": {
  "1980": [{"name":"男性","data":[...19個(正の値)]}, {"name":"女性","data":[...19個]}],
  ...
}}
```

## 4. 描画層フィルタの書式規約 (citizenlib/filters.py)

| フィルタ | .NET 相当 | 例 |
|---------|-----------|----|
| `num` | `ToString("#,##0")` | `1952356 → "1,952,356"` |
| `f1` | `ToString("0.0")` / `Math.Round(x,1,AwayFromZero)` | `11.649 → "11.6"`, `0.25 → "0.3"` |
| `numf1` | `ToString("#,##0.0")` | `1741.26 → "1,741.3"` |
| `dstr` | `double.ToString()` | `1121.26 → "1121.26"`, `100.0 → "100"` |
| `numz` | `ZinkoHyoji()` (`p==0 ? "-" : ToString("#,##0")`) | `0 → "-"`, `1234 → "1,234"` |

丸めは常に **round-half-away-from-zero** (Python 既定の銀行丸めは使用しない)。

## 5. スキーマ変更の手順

1. 本書を先に更新する (フィールド追加・削除・意味変更)
2. `build_data.py` と `generate.py`/テンプレートを同一コミットで追随させる
3. ビルド時スキーマ検証 (generate.py 内 assert) を更新する
