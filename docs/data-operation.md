# 「まどろみ季節帖」データ運用手順書 (Data Operation Guide)

本書は、アプリ「まどろみ季節帖」が参照する季節データリポジトリ（`madoromi-kisetsucho-data`）の運用方針およびデータ更新・検証手順をまとめたドキュメントです。

---

## 1. データ運用の基本方針

### 公式情報優先ポリシー（信頼性の確保）
- **原則一次情報を採用**:
  データソースには自治体、公式観光協会、気象会社（ウェザーニュース、日本気象協会等）、学術・行政機関（国立天文台、内閣府等）の公式発表のみを採用します。
- **不採用ソースの例**:
  SNS（X, Instagram 等）の投稿、個人ブログ、真偽不明のまとめサイト、口コミサイト、非公式カレンダー等は、正式な出典（`sources`）として扱いません。
- **実在イベントの日程未確認時の扱い**:
  日程が公式に確定していないイベントは、出典なしに日付を確定させず、`commonStatus` を `CHECKING`（情報確認中 / 公式発表待ち）として登録します。

### ステータス管理ポリシー
1. **`CHECKING` (情報確認中)**:
   - まだ公式から日程が発表されていない場合や、今年の開催可否が未決定のデータ。
   - `notificationMeta.notifyEnabled` を `false` にするか、`priority` を低く設定して、ユーザーに不確かな通知が強く出すぎないように制御します。
   - 出典の `certaintyLabel` に「公式発表待ち」「情報確認中」などのキーワードを含めて登録します。
2. **`ENDED` (期間終了)**:
   - 期間が終了したイベント。
   - 定期更新スクリプトにより、終了日が今日よりも過去であると検知された場合、自動的に `ENDED` に移行します。
3. **`CANCELLED_OR_CHANGED` (中止・変更)**:
   - 災害や悪天候により、イベントが急遽中止または日程変更になったデータ。
   - このステータスにする場合、必ず `warnings` 配下に重要度 `high` の警告メッセージ（中止理由や払い戻し案内など）を追加して、詳細画面で警告として表示されるようにします。

---

## 2. 自動データ更新と検証の仕組み

本リポジトリでは、以下のスクリプトと GitHub Actions によって、データの整合性を維持しながら安全に更新・配信を行います。

### 構成ファイル
- **[seasonal_data_v1.json](file:///C:/Users/keych/Documents/antigravity/madoromi-kisetsucho-data/data/seasonal_data_v1.json)**:
  アプリが直接取得する本番季節データ。
- **[sources_registry.json](file:///C:/Users/keych/Documents/antigravity/madoromi-kisetsucho-data/data/sources_registry.json)**:
  信頼できる情報源の一覧を管理する「情報源台帳」。
- **[update_report.json](file:///C:/Users/keych/Documents/antigravity/madoromi-kisetsucho-data/data/update_report.json)**:
  検証結果や登録件数サマリーを自動記録するレポート。

### 運用手順

#### ① 定期・手動更新 (scripts/update_seasonal_data.py)
- **処理内容**:
  1. 毎年固定の祝日や季節行事（こどもの日、七夕、初日の出、節分、夏至、冬至など）の日付を、実行時の年に自動でマッピングして更新します。
  2. 終了日（`endLocalDate`）が今日より過去のデータを自動的に `ENDED` に移行させます。
  3. `dataVersion` を日付＋連番（例: `2026.05.23-001`）で自動インクリメントし、`generatedAt` を更新します。
- **安全性確保**:
  破損JSONの公開を防ぐため、一度一時ファイル（`.tmp.json`）に出力し、後述のバリデータが成功した場合のみ本番の `seasonal_data_v1.json` に上書き（ロールバック機構付き）します。

#### ② JSON検証 (scripts/validate_seasonal_data.py)
本番JSONがアプリ側で正常に読み込める状態かを以下のルールで検証し、違反がある場合は exit code `1` で処理を停止します。
- JSONフォーマットが正しいこと。
- `dataVersion`, `generatedAt` などのルート必須項目が存在すること。
- 各 `item` の `id` が重複していないこと。
- 各 `item` に 1 件以上の `sources` (URL含む) と `lastVerifiedAt` が存在すること。
- `CHECKING` の場合、`certaintyLabel` に確認中等のワードがあり、`notifyEnabled` が `false` か優先度が低いこと。
- `CANCELLED_OR_CHANGED` の場合、`high` 重要度の `warnings` があること。
- APIキーやシークレット情報が含まれていないこと。

---

## 3. GitHub Actions の利用手順

### 手動実行方法
1. GitHub リポジトリの **Actions** タブを開きます。
2. 左メニューから **Update and Validate Seasonal Data** ワークフローを選択します。
3. 画面右側の **Run workflow** ボタンをクリックし、ブランチ（通常は `main`）を指定して実行します。

### 定期実行スケジュール
- 週 1 回、毎週月曜日の日本時間 午前9:00頃 (UTC 0:00頃) に自動で更新および検証が行われます。
- 検証に合格し、データに変更があった場合のみ、自動コミット＆プッシュされ GitHub Pages へ反映されます。検証に失敗した場合は Pages の更新がストップし、エラーログが残ります。

---

## 4. seasonal_data_v1.json の直接（手動）編集時の注意

1. 直接編集した後は、必ずローカルでバリデータを実行して整合性を確認してください。
    ```bash
    python scripts/validate_seasonal_data.py
    ```
    ※ローカルにPythonがインストールされていない、またはNode.js環境が利用可能な場合は、Node.js版の検証スクリプトを使用できます：
    ```bash
    node scripts/validate.js
    ```
   ※ エラーが出た状態のままリポジトリにプッシュすると、GitHub Actions の検証で弾かれ、本番配信されません。
2. 日付関連の形式（`startLocalDate`, `endLocalDate`, `startDate`, `endDate`）は新旧併記（`YYYY-MM-DD`）を維持し、アプリの画面表示が崩れないようにしてください。

---

## 5. 反映および実機テストでの確認方法

### GitHub Pages 反映確認
GitHub Actions 成功後、数分以内に GitHub Pages がデプロイされます。ブラウザ等で以下の公開 URL にアクセスし、`dataVersion` や追加したデータが反映されているか確認してください。
`https://keychrome-lab.github.io/madoromi-kisetsucho-data/data/seasonal_data_v1.json`

### アプリ実機での確認方法
1. アプリを起動し、「設定」タブから「データ同期」を選択し、手動同期を行います。
2. 「ホーム」タブに戻り、以下を確認します：
   - 登録地域、または現在地周辺に応じたおすすめアイテムや並べ替えが正しく反映されていること。
   - `CHECKING` のイベント（「情報確認中」など）がホームのおすすめ最上位や通知対象に出てきていないこと。
   - イベントをタップして「詳細」画面を開き、出典URL、出典名、最終確認日、確からしさラベル（`certaintyLabel`）が正常に表示されていること。

---

## 6. カテゴリ別の運用注意事項

| カテゴリ | 対象イベント例 | 更新頻度 / 注意点 |
| :--- | :--- | :--- |
| **自然 (NATURE)** | 桜、紅葉の見頃スポット | 開花シーズン（3月〜4月、10月〜12月）は週2〜3回、気象協会の実況データを確認の上、見頃ステータス（`BEST_SEASON` など）をこまめに更新。オフシーズンは `ENDED` で固定。 |
| **イベント (EVENT)** | 花火大会、イルミネーション | 毎年春頃から各花火大会の公式ページを巡回し、日程が発表されるまでは `CHECKING` で管理。確定後に `UPCOMING` / 日程を入力して出典を更新する。 |
| **天文 (ASTRONOMY)** | 流星群、月食、日食 | 国立天文台の暦情報をベースにするため、基本的に年の初めに一括で日程や極大時刻、観測環境を入力し、ステータスは `UPCOMING` で維持。イベント終了後に `ENDED` へ移行。 |
| **季節行事 (SEASONAL_CUSTOM)** | 節分、七夕、冬至など | 基本的に毎年固定、あるいは祝日法・二十四節気のカレンダー通りに日付が推移するため、定期更新スクリプトで翌年の西暦に自動更新可能。 |
