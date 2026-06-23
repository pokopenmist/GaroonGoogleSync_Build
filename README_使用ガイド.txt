# Garoon → Google Calendar 同期ツール

GaroonのスケジュールをGoogle Calendarに一方向同期するツールです。

---

## 📦 配布ファイル構成

```
配布フォルダ/
├── GaroonGoogleSync.exe    # メインプログラム
├── credentials.json         # Google認証情報（※要設定）
└── README.txt              # この説明書
```

---

## 🚀 セットアップ手順

### Step 1: Google Cloud Console でプロジェクト作成

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 新しいプロジェクトを作成（または既存のプロジェクトを選択）
3. 左メニューから「APIとサービス」→「ライブラリ」を選択
4. 「Google Calendar API」を検索して有効化

### Step 2: OAuth 2.0 認証情報の作成

1. 左メニューから「APIとサービス」→「認証情報」を選択
2. 「認証情報を作成」→「OAuth クライアント ID」をクリック
3. 「OAuth 同意画面」を設定（まだの場合）
   - ユーザータイプ: 外部
   - アプリ名: 任意（例: Garoon Sync）
   - サポートメール: 自分のメールアドレス
   - スコープ: 追加不要（後で自動設定されます）
   - テストユーザー: 自分のGoogleアカウントを追加
4. 「認証情報を作成」→「OAuth クライアント ID」
   - アプリケーションの種類: デスクトップアプリ
   - 名前: 任意（例: Garoon Sync Desktop）
5. 作成後、「JSONをダウンロード」をクリック
6. ダウンロードしたファイルを「credentials.json」にリネーム

### Step 3: ファイル配置

1. `GaroonGoogleSync.exe` と同じフォルダに `credentials.json` を配置

```
GaroonGoogleSync/
├── GaroonGoogleSync.exe
└── credentials.json         ← ここに配置
```

### Step 4: 初回起動

1. `GaroonGoogleSync.exe` をダブルクリックして起動
2. Garoon設定を入力
   - ユーザー名: Garoonのログインユーザー名
   - パスワード: Garoonのログインパスワード
3. 「Google認証」ボタンをクリック
4. ブラウザが開くのでGoogleアカウントでログイン
5. 「許可」をクリックして認証完了
6. 同期先のカレンダーを選択
7. 「同期実行」ボタンで同期開始

---

## ⚙️ 設定項目

| 項目 | 説明 |
|------|------|
| ユーザー名 | Garoonのログインユーザー名 |
| パスワード | Garoonのログインパスワード |
| カレンダー | 同期先のGoogleカレンダー |
| 過去〇日前 | 何日前までの予定を同期するか |
| 未来〇日後 | 何日後までの予定を同期するか |

---

## 📁 自動生成されるファイル

初回実行後、以下のファイルが自動生成されます：

| ファイル | 説明 |
|----------|------|
| `token.pickle` | Google認証トークン（削除すると再認証が必要） |
| `sync_config.json` | 設定ファイル（ユーザー名、期間設定など） |
| `sync_mapping.db` | 同期マッピングDB（削除すると全件再同期） |

---

## 🔄 同期の動作

- **Garoon → Google の一方向同期**です
- Google側で編集・削除してもGaroonには反映されません
- Garoonで予定を追加/更新/削除すると、次回同期時にGoogleに反映されます

### 繰り返し予定

以下の繰り返しパターンに対応：
- 毎日
- 平日（月〜金）
- 毎週〇曜日
- 隔週〇曜日
- 4週ごと〇曜日
- 毎月
- 毎年

---

## ❓ トラブルシューティング

### 「credentials.json が見つかりません」エラー
→ `credentials.json` を exe と同じフォルダに配置してください

### Google認証でエラーが出る
→ Google Cloud Console で以下を確認：
  - Google Calendar API が有効になっているか
  - OAuth同意画面でテストユーザーに自分が追加されているか

### 同期が重複する
→ `sync_mapping.db` を削除して、Google Calendar 上の重複イベントを削除後、再同期

### 繰り返し予定が登録されない
→ ログに表示される繰り返し情報を確認し、未対応のパターンの場合は開発者に連絡

---

## ⏰ タスクスケジューラで自動実行

定期的に自動同期したい場合は、タスクスケジューラを使用できます。

### コマンドライン引数

```
GaroonGoogleSync.exe --auto --silent
```

| 引数 | 説明 |
|------|------|
| --auto | 自動同期モード（GUIなし） |
| --silent | サイレントモード（ログファイルのみ） |

### 事前準備

1. GUIで設定を保存（Garoon設定、Google認証、カレンダー選択）
2. 同期が正常に動作することを確認

### タスクスケジューラ設定

1. タスクスケジューラを開く
2. 「タスクの作成」をクリック
3. プログラム: `C:\path\to\GaroonGoogleSync.exe`
4. 引数: `--auto --silent`
5. 開始フォルダ: `C:\path\to\`（EXEがあるフォルダ）
6. トリガー: 毎日 or 毎週 + 希望時刻

### ログファイル

自動実行時のログは `sync_log.txt` に出力されます。

詳細は「タスクスケジューラ設定.txt」を参照してください。

---

## 📝 注意事項

- パスワードを保存する場合、`sync_config.json` に平文で保存されます
- `credentials.json` と `token.pickle` は第三者に共有しないでください
- このツールはGaroonのサブドメイン「mrh-garoon」専用です

---

## 📞 サポート

問題が発生した場合は、ログ画面に表示されるエラーメッセージと共に
開発者までご連絡ください。
