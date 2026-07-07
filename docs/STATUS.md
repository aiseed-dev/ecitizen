# 実装状況 (フェーズ別)

移行プロジェクトの進捗チェックリスト。設計は [DESIGN.md](DESIGN.md)。

- [x] Phase 0: 基盤 (レイアウト・自前 CSS・マスター抽出・アセット)
- [x] Phase 1: `/Population/City/{code}` 1,741 市町村 + `CityData/{code}.json` + `CityList/{pref}.json`
- [x] Phase 2: Prefecture (47) / Country (33) / CityPyramid (1,741) /
      Ranking2045 (全国+都道府県別) / ListOfCitiesByArea / ListOfCitiesByTfr /
      CityAging2045 / CityOldOld2045
- [x] Population2020統合(K11): City/Pref の census に2020年実績値を追加、
      projection を IPSS令和5年推計(2020-2050)に全面更新 (DESIGN.md §13)
- [x] Country(海外)データ更新(K12): census を Eurostat、projection を
      EUROPOP2023(UKのみONS 2024年基準)に全面更新 (DESIGN.md §14)
- [x] PrefPyramid (47件、都道府県版人口ピラミッド)
- [x] CountryPyramid (33件、JP含む。Eurostat/ONSから男女別データを追加取得。DESIGN.md §15.2)
- [x] Population2015 ランキング (人口順/増減数順/増減率順/コード順 × 全国+47都道府県 = 192ページ)
- [x] Census2010 (2010年国勢調査人口と2008年推計の比較。DESIGN.md §16。
      旧Population2010Controllerの他ルートはPhase2既存機能の重複ルート、
      またはe-Stat直叩き系のためPhase3へ整理・移動)
      (City3d/Country3d/Prefecture3d は廃止・移植しない。K10)
- [x] Phase 3 (一部): Ssds 都道府県ランキング (社会・人口統計体系26表、
      5,356項目×47都道府県。トップ+分野別カタログ26+県別1,222+項目別5,356ページ。
      DESIGN.md §21)
- [ ] Phase 3 (残り): CPI / Sac / Lg / Aging2015 / Young2015 / Migration 系
- [ ] Phase 4: 静的コンテンツ・Statdb (**Flutter に決定 K13、Web + PC + スマホの
      マルチプラットフォーム展開。仕様書 = DESIGN.md §17**。
      未決 D6: 統計表実データの扱い / D7: ネイティブ版の配布方法。
      データ契約 = DATA_CONTRACT.md §2.9)
- [x] 季節調整セクション刷新 (X-13ARIMA-SEATS 中心・Linux中心の新3ページ、
      旧X-12-ARIMA記事4本は /x-12-arima/archive/ へ301+バナー。DESIGN.md §19)
- [x] ホーム (/) と人口トップ (/Population/)。JP/EUの4区分チャートは
      ビルド時SVG (旧CountryBy4AgeGroupの置き換え)
- [x] 静的コンテンツ: /about/ /privacy/ /gdp/ /gdp/fertility-rate-and-gdp/
      /io/ /excel-vba/ (旧Razorから本文抽出して移植。/Search は廃止APIのため
      移植せず、ヘッダーの検索フォームで代替)
- [x] Phase 5 (一部): 404.html、sitemap.xml (全ページ自動生成)
- [ ] Phase 5 (残り): 本番切替 (カスタムドメイン割り当て。DEPLOY.md §4)
