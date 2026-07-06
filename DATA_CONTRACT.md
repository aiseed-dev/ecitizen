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

`codetrans20180401.json` (pp 用) は現行 C# で空辞書。空ファイルとして扱う
(2026-07-05 の変更で pp 自体を読まなくなったため実質未使用)。

`citizenlib/masters.py` にはこの他、コード抽出ではなく手書きの小さな辞書として
`IPSS_CODE_TRANS`(`CITY_DIC` 以降の市制施行等による IPSS 側コード差異、1件)
と `CHANGE_CODE_AFTER_2010`(TFRランキングのリンク先解決用)がある。

### 1.1 `municipal_changes.json` — 市町村の廃置分合 (e-Stat LOD 由来)

`tools/fetch_sac_lod.py` が e-Stat 統計LOD (標準地域コード) の SPARQL から
生成する (DESIGN.md §18)。1970-04-01 以降の全変更。**コミットする**マスター。
ローダとコード変換は `citizenlib/municipal.py`。

```jsonc
{"fetched_at": "2026-07-06",
 "reasons": {   // 事由キー → 日本語ラベル (16種)
   "establishmentOfNewMunicipalityByMerging": "新設合併",
   "absorption": "編入合併", "changesToCity": "市制施行", ...},
 "changes": [   // sacs:succeedingMunicipality の全ペア (date, old.code 順)
   {"date": "2004-10-12",
    "reason": "establishmentOfNewMunicipalityByMerging",
    "old": {"code": "46388", "name": "里村"},
    "new": {"code": "46215", "name": "薩摩川内市"}},
   ...]}
```

- `old`/`new` の code は5桁ゼロ埋め文字列。名称変更・境界変更等では
  old.code == new.code のペアも含まれる (名称履歴として保持。
  `build_code_trans()` はコード不変ペアを無視する)
- `citizenlib.municipal.build_code_trans(since, until=None)` は
  `since < date <= until` の変更を連鎖解決した `{旧code: 現行code}` を返す

## 2. 取得層の中間データ (`data/population/`)

### 2.1 `city/{code}.json` — 市町村 1 件の描画用モデル

旧 `PopulationChart` (GetCity 実行後) のシリアライズ。descriptor:

```jsonc
{
  "code": "01100",
  "name": "札幌市",
  "pref": "01",
  "pref_name": "北海道",
  "fukushima": false,          // true なら将来推計なし (IPSS未推計。福島県浜通り13町村)
  "census": [                  // 国勢調査: 21 行 × 9 列 (1980..2020, 5年刻み)
    {"series": "総数", "population": [1401757, ...9個]},
    ...
  ],
  "projection": [              // 将来推計: 21 行 × 7 列 (2020..2050)。fukushima 時は []
    {"series": "総数", "population": [1973395, ...7個]},
    ...
  ],
  "index": [                   // 人口指数: census 9 件 + projection 7 件 (fukushima 時は 9 件)
    {
      "year": 1980,            // projection 側は 2020..2050
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

- `census` は 21 行・各行 9 要素(1980-2020)。**ただし `fukushima: true` の市町村
  (福島県浜通り13町村。IPSSが2020年時点でも推計・実績値を公表していない)は
  各行 8 要素(1980-2015)のままで2020列を持たない**。`projection` は 21 行・
  各行 7 要素 or (fukushima 時) 空配列。
  **census と projection は同一の行構成** (総数, 0～4歳, …, 85～89歳, 90歳以上,
  年齢不詳)。旧仕様では projection に「年齢不詳」行が無い20行構成だったが、
  IPSS 令和5年推計への切替に伴い年齢不詳=0の行を補って census と統一した
  (2026-07-05 の変更。指数計算式が census/projection で共通化された)。
- `index` の割合・指数は**丸め前の値** (描画層で .NET `"0.0"` 互換に丸める)。
- 割合・指数は分母が 0 の場合 **null**(避難等による人口 0: 福島6町村の2015年、
  三宅村の2000年)。描画層は null を「-」と表示する。
  旧 C# は NaN/∞ を表示していたが、意図的に挙動を改善した箇所。
- コード変換 (codetrans) の合算は取得層で解決済み。描画層は変換を知らない
  (ただし codetrans は 1980～2015 の census 列にのみ適用。2020 census 列と
  projection 列は IPSS の現行(2023年12月時点)市町村コードでそのまま取得できる
  ため変換不要)。

**データソース(2026-07-05 更新)**:
- census 1980～2015 (8列): 旧 `App_Data/Population2015/City/pd{code}.json` (従来通り)
- census 2020 (1列) と projection 全体 (7列): 国立社会保障・人口問題研究所
  「日本の地域別将来推計人口(令和5(2023)年推計)」都道府県別 Excel
  (`https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/3kekka/Municipalities/{01..47}.xlsx`)。
  2020年列は「国勢調査による実績値」(推計ではない)。旧 `pp{code}.json`
  (平成30年推計、2015～2045年) は**もう使わない**(全面置き換え)。
  90～94歳・95歳以上の2区分は合算して「90歳以上」に正規化 (`citizenlib/ipss.py`)。
  ファイルは1回限りダウンロードし `data/raw/ipss/` にキャッシュ (git管理外)。

### 2.2 `cityinfo2015.json` — サイドバー基本情報

旧 `App_Data/Population2015/2015/population2015.json` をそのまま採用 (キーは旧 C# の
JsonProperty 名: `code, name, popu2015, order2015, popu2010, order2010, area,
house2015, house2010`)。描画層は `code` で検索し、無ければサイドバー部品を出さない。

### 2.3 `pref/{code}.json` — 都道府県 1 件の描画用モデル

`city/{code}.json` と同一構造 (`code, name, census, projection, index`)。
相違点のみ:

- `fukushima` フィールドは無し (都道府県単位では将来推計が必ずある)
- `census` は必ず 21 行×9列、`projection` は必ず 21 行×7列 (空になるケースなし)
- `index` は必ず 16 件 (census 9 + projection 7)
- ソース: census 1980～2015 は旧 `App_Data/Population2015/Pref/pd{code}.json`
  (コード変換なし)。census 2020 と projection は IPSS 令和5年推計の
  都道府県計シート (`citizenlib/ipss.py` の `IpssData.prefecture()`)

### 2.4 `country/{code}.json` — 国 1 件の描画用モデル

```jsonc
{
  "code": "JP",
  "name": "日本",
  "is_jp": true,              // true: 21行 Ages3 census (kaikyu=90) / false: 20行 Ages2 census (kaikyu=85)
  "census": [...],            // JP: 21行×9列(1980-2020, Ages3)。それ以外: 20行×9列(1980-2020, Ages2)
  "projection": [...],        // JP: 21行×7列(2020-2050)。それ以外: 20行×6列(2025-2050)
  "index": [...]              // JP: 16件(census 9+projection 7)。それ以外: 15件(census 9+projection 6)
}
```

- **JP (2026-07-06、IPSS令和5年推計へ更新)**: City/Pref と同一構成。
  census 1980-2015 は旧 `App_Data/Population2015/Country/edJP.json`、
  2020年列(実績値)と projection 全体は IPSS 令和5年推計の
  **47都道府県合算** (`IpssData.japan()`。合算値は2020年国勢調査の確定人口
  126,146,099人と一致することを確認済み)。census 最終年(2020)と projection
  開始年(2020)が重複するためチャートでは `[1:]` で1点飛ばす (City/Pref と同じ)。
- **JP 以外 32 カ国(2026-07-05、Eurostat/ONS へ切替)**:
  - census: **Eurostat `demo_pjangroup`**(男女，年齢(5歳階級)別人口。
    UKも含め全32カ国を1980-2020(9点)で取得。appId不要、認証不要のオープンAPI)。
    `citizenlib/eurostat.py` の `load_census()`、キャッシュは
    `data/raw/eurostat/census.json`(`tools/fetch_eurostat.py` で1回限り取得)。
  - projection: **Eurostat `proj_23np`(EUROPOP2023、基準シナリオ`BSL`)**を
    1歳刻みから5歳階級に合算(2025-2050、6点)。ただし **UK のみ EUROPOP2023
    対象外**(EU離脱国のため)なので、代わりに **英国統計局(ONS)
    「National population projections: 2024-based」の Principal projection**
    (5歳階級・年次データ、`data/raw/ons/uk_ppp_machine_readable.xlsx`、
    `tools/fetch_ons.py` で1回限り取得)から2025・2030・...・2050年を抜き出す
    (`citizenlib/eurostat.py` の `load_projection_uk()`)。UK の推計は基準年・
    手法が他国と異なるため、その旨を Country/UK ページに脚注として表示する。
  - "EU"(ヨーロッパ連合)は Eurostat の集計コード `EU27_2020` を使う
    (`citizenlib/eurostat.py` の `GEO_CODES`)。
  - **census 最終年(2020)と projection 開始年(2025)は重複しない**
    (旧データは両方 2015年で重複していたため `[1:]` で1点飛ばしていたが、
    非JPはその処理をしない。JP は census 2020 と projection 2020 が重複するため `[1:]` のまま)。
- `index` の算出は city/pref と同じ `_index_of` 計算式を使う。JP以外の census は
  「90歳以上を老年人口に含めない」(`include90_in_old=False`) 条件で計算する
  (Ages2 の census データでは 85歳以上が「85+」1行に合算されているため、
  `include90_in_old=False` のまま該当行 [14:19] を合計すると 65+ 全体を正しく捕捉する)。
  `projection` は JP/非JP 問わず常に `include90_in_old=True` (常に90歳以上が分離済み)。
- census の値が `0` の要素は「データなし」を意味する (Eurostat が一部年齢階級・
  年で未収集の場合がある)。描画層は `numz` フィルタで `0 → "-"` 表示する
  (`index` の `young`/`working`/`old`/`old_old` も同様に `numz` を使う)。

### 2.5 `pyramid/city/{code}.json` — 市町村の人口ピラミッド (男女別)

旧 `PopulationPyramid` のシリアライズ。年ごとの JSON エンドポイントには分割せず
(Cloudflare Pages のファイル数上限対策、§9.1)、1 市町村 = 1 ファイルに
全 15 年分(2026-07-05 IPSS 令和5年推計への切替で14年→15年に増加)を束ねる。

```jsonc
{
  "code": "01100",
  "max_value": 101607,       // 全年・男女通しての最大値 (グラフスケール用)
  "years": [                 // 15 年分 (1980..2020 は census、2025..2050 は projection)
    {"year": 1980, "kind": "census",
     "male": [70754, ...19個, 0-4から90+の順],   // 行1..19 (総数・年齢不詳を除く19階級)
     "female": [...19個]},
    ...
  ],
  "census_m": [...],         // 生表示用の全列テーブル。city の census/projection と同一shape
  "census_f": [...],         // (21行×9列)
  "projection_m": [...],     // (21行×7列。福島県浜通り13町村は [])
  "projection_f": [...]
}
```

- `years` はピラミッド SVG 生成専用 (年ごとに男女19階級ずつ抽出済み)。
  `census_m/f`・`projection_m/f` は元の全期間テーブル表示用 (city の
  `census`/`projection` と同じ shape) で、値の出典は同じデータの異なる切り口。
- 福島県内の市町村は `years` が census 8 件のみ、`projection_m/f` は `[]`
- 年齢階級は `ages3.json` の 1..19 番目 (0～4歳 … 90歳以上、総数と年齢不詳を除く)
- 符号は付けない (男女とも正の値。グラフ描画時に男性側を負に反転するのは描画層の責務)

`pyramid/pref/{pref}.json` は上記と同一 shape (都道府県版)。ただし都道府県は
将来推計の欠損(fukushima相当)が無いため、`years` は常に15件、`fukushima`
キー自体を持たない。ソースは `citizenlib.ipss.IpssData.prefecture()`
(census 1980-2015 は旧 `App_Data/Population2015/PrefM,PrefF`)。

`pyramid/country/{code}.json` は国版。`fukushima` の代わりに `is_jp` を持つ。
JP は `years` 14件(census 8 + projection 6、旧データ)、非JP は15件
(census 9 + projection 6、Eurostat/ONS)。census 年の19区分のうち、非JP
(Ages2、90歳以上のデータなし)は最後の1区分(90歳以上相当)を `0` で埋めて
19区分に揃えている(JPは Ages3 で実データがあるため埋めない)。
ソースは `citizenlib.population.build_country_pyramid_model()`
(非JPは `citizenlib.eurostat` の `sex="M"/"F"` 呼び出し、JPは旧
`App_Data/Population2015/CountryM,CountryF`)。

### 2.6 ランキング系 (`data/rankings/`)

| ファイル | 内容 | 件数 |
|---------|------|------|
| `ranking2050_national.json` | IPSS令和5年推計による2050年ランキング (`code,name,pref_name,value2050,value2020,order2050,order2020`。市町村モデルから計算) | 1,728 (浜通り13町村除く) |
| `ranking2050_pref/{pref}.json` | 都道府県ビュー (`pref,pref_name,total2050,total2020,cities[]`+県内順位) | 47県 |
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

### 2.7 Population2015 ランキング

新規の中間ファイルは持たない。`data/cityinfo2015.json`(既存、§2.2)を
`citizenlib.rankings.build_population2015_ranking(cityinfo, order, pref)`
で並べ替えるだけで、生成層(generate.py)がビルド時に直接計算する。

- `order`: `"popu"`(人口順)・`"inc"`(増減数順)・`"rate"`(増減率順)・
  `"code"`(コード順)の4種 (`citizenlib.rankings.POPULATION2015_ORDERS`)
- `pref`: 都道府県コード(2桁)または `None`(全国)。フィルタのみ行い、
  「順位」列(`order2015`/`order2010`)は都道府県内で再計算せず全国順位のまま
  表示する(旧実装のまま)
- 出力ページ: `Population/Population2015/{order}/index.html`(全国)、
  `Population/Population2015/{pref}/{order}/index.html`(都道府県別)。
  4種 × 48地域(全国+47県) = 192ページ

### 2.8 `census2010.json` — 2010年国勢調査 実績・推計比較

旧 `Population2010Controller.Census2010()` の移植。新規の外部データ取得は
不要 (旧 `App_Data/Population2010/2010/census2010List.json` + `App_Data/
NAreaCode/StandardAreaCodeList.json` をそのまま一次ソースとして使う。
`citizenlib.census2010.build_census2010_rows()`)。

フラットな配列。都道府県ヘッダー行 (`is_pref: true`、傘下市区町村の合計) と
市区町村・行政区行がコード順に交互に並ぶ (旧実装の描画順そのまま)。
行政区 (政令指定都市の区。`StandardAreaCodeList.json` の `種別==8`) は
都道府県合計に含めない (親の市の行が既に計上済みのため)。

市区町村・行政区の名称は `StandardAreaCodeList.json` から**2010-10-01時点で
有効な名称**を引く (`施行年月日 <= 2010-10-01 < 廃止年月日`)。現行の
`data/masters/citydic20161010.json` は使わない — 2010年時点の団体コード
(1,878件、行政区含む) は現行の市町村マスタ (1,741件) と直接対応しないため。

```jsonc
{"code": 1100, "name": "札幌市", "is_pref": false, "is_ward": false,
 "popu2010": 1913545, "popu2005": 1880863, "popu2000": 1822368,
 "est2010": 1910791, "closed2010": 1876350,
 "inc": 32682, "est_diff": 2754, "net_inc": 37195,
 "inc_rate": 1.74, "est_diff_rate": 0.14, "net_inc_rate": 1.98}
```

- `est2010`: 国立社会保障・人口問題研究所「日本の市区町村別将来推計人口
  (2008年12月推計)」の2010年推計値
- `closed2010`: 同推計の2010年封鎖人口 (転入出がないと仮定した場合の推計人口)
- `inc`/`inc_rate`: 人口増減 = 2010年人口−2005年人口 (収束前の実際の人口増減)
- `est_diff`/`est_diff_rate`: 推計差 = 2010年人口−2010年推計人口
- `net_inc`/`net_inc_rate`: 純増減 = 2010年人口−2010年封鎖人口
  (プラスなら転入超過、マイナスなら転出超過の目安)
- 分母が0の場合の `*_rate` は `null` (`f1` フィルタで「-」表示。§4)

旧実装は増減6項目それぞれを独自の連続グラデーション色 (`差色`/`率色`) で
着色していたが、静的版では他ページと統一された `rate_class` フィルタ
(5%刻み・赤=増加/青=減少) で代替する。**意図的な逸脱**: 人口増減・推計差・
純増減 (人数) のセルも、対応する増減率 (`inc_rate`/`est_diff_rate`/
`net_inc_rate`) と同じ `rate_class` で着色する (符号は常に一致するため)。

出力: `Population/Census2010/index.html` (1ページ、都道府県ごとに表と
アンカーを分けて1画面に収録。旧実装と同じ構成)。

### 2.9 Statdb カタログ (`data/statdb/`、Phase 4・K13)

`tools/fetch_statdb.py`(旧 statdbcron の移植)が生成する。DESIGN.md §17。
描画層は `data/statdb/` をそのまま `public/Statdb/data/` にコピーし、
Flutter SPA が fetch で読む。**キー名は snake_case に正規化する**
(旧 C# の PascalCase から変換。Flutter/Dart 側のモデルと揃えるため)。

#### `catalog.json` — 統計名一覧 (旧 JStatsName.json)

```jsonc
{"fetched_at": "2026-07-06",       // スナップショット取得日
 "stats": [
   {"kind": 1,                     // 1=統計、2=小地域・地域メッシュ、3=社会・人口統計体系
    "id": "00200521",              // 政府統計コード (8桁)
    "name": "国勢調査",
    "gov_org": "総務省"},
   ...]}
```

#### `list/{code}.json` / `list/T{code}.json` / `list/C00200502.json` — 統計表一覧

kind1 は `{code}.json`、kind2 は `T{code}.json`、kind3 は `C{code}.json`
(旧 statsList ディレクトリの命名を踏襲)。フラットな配列で、階層ツリーは
クライアント (Flutter) が `statics` を空白分割して構築する (旧 StatsClass
.GetStatsClass と同じロジック)。

```jsonc
[{"id": "0003448237",              // statsDataId (10桁)
  "statics": "国勢調査 令和2年国勢調査 人口等基本集計",  // STATISTICS_NAME (空白区切り階層)
  "no": "1-1",                     // TITLE_NO (表番号、null あり)
  "title": "男女別人口...",         // TITLE
  "cycle": "-",                    // CYCLE
  "sdate": "2020",                 // SURVEY_DATE ("0" は調査年月なし)
  "open": "2021-11-30",            // OPEN_DATE
  "num": 12345,                    // OVERALL_TOTAL_NUMBER (データ件数)
  "update": "2022-05-20",          // UPDATED_DATE
  "sequence": "000101"},           // 表番号の正規化キー (並べ替え用、旧 Sequence)
 ...]
```

#### `latest.json` — 更新情報 (旧 latestStats.json)

差分検出 (旧 ChangeInfo の移植) で追記される。`update_type`:
0=新規(取得日公開)、1=公開日変更(取得日公開)、2=新規、3=公開日変更、
4=属性変更 (0/1 は公開日が取得当日のもの。旧実装の datetimetype と同じ)。

```jsonc
[{"id": "202607061200000",         // 取得時刻(yyyyMMddHHmm)+連番3桁
  "stat_code": "00200521",
  "title": "国勢調査 令和2年国勢調査",   // 統計名の先頭2階層
  "open": "2026-07-01",
  "update_type": 0},
 ...]
```

旧実装の `DeleteCheck` は移植しない (キャッシュ削除確認フラグ。静的版では
表示条件 `UpdateType < 2 && DeleteCheck == 0` のうち DeleteCheck は常に
満たされたものとして扱う)。

#### `latest_tables/{id}.json` — 更新ID別の統計表リスト

```jsonc
[{"stats_data_id": "0003448237", "statics": "...", "title": "...",
  "no": "1-1", "sequence": "000101", "update_type": 0},
 ...]
```

#### 初回実行の扱い

初回 (前回スナップショットが存在しない) は差分を取らず `latest.json` は
空配列で生成する (全統計表を「新規」扱いにしない。旧 statdbcron も
statsList0 が無い場合は保存のみで ChangeInfo を呼ばない)。

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

日本 (`JP`) は `CityData` と同一構造 (年齢不詳 + 19系列、各15点。
2026-07-06 に IPSS 令和5年推計へ更新され City/Pref と完全に同形になった)。

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
