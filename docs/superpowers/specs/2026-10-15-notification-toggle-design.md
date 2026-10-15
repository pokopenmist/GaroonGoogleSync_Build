# Googleカレンダー通知（リマインダー）ON/OFF設定 — 設計

## 背景・目的

現在 `EventConverter.garoon_to_google()` は生成する Google Calendar イベントに `reminders` フィールドを一切設定していない。そのため、Garoon から同期されるすべてのイベントは Google Calendar 側の対象カレンダーのデフォルト通知設定（ポップアップ／アラート）をそのまま継承している。

ユーザーから、同期されたイベントに対する Google カレンダーのプッシュ通知（リマインダー）を ON/OFF で制御したいという要望があった。ヒアリングの結果、対象は「事象のリマインダー（ポップアップ・アラート）」であり、カレンダー全体の「予定追加・変更」通知（`notificationSettings`）は対象外と確認した。

## 要件

- GUIに「Google通知（リマインダー）を有効にする」のON/OFFチェックボックスを追加する
- ONの場合: 従来通り `reminders` フィールドを付与しない（Googleカレンダー側のデフォルト設定に委ねる）。これは現状の挙動と完全に同一。
- OFFの場合: 生成するイベントに明示的に `reminders: {"useDefault": false, "overrides": []}` を設定し、通知を発生させない。
- デフォルト値は ON（既存ユーザーの挙動を変えない）。
- 設定は `sync_config.json` に保存し、GUIモード・`--auto`（タスクスケジューラ）モードの両方で有効とする。
- 適用範囲は「今後新規作成・更新されるイベントのみ」。設定変更時に既存の同期済みイベントを遡及的に更新する処理は実装しない。

## 不採用にした代替案

| 案 | 内容 | 不採用理由 |
|---|---|---|
| カレンダー全体の通知設定制御 | `CalendarListEntry.notificationSettings`（予定追加/変更/キャンセル等の通知）をon/off | ユーザーが意図したのは個々の予定のリマインダーであり、カレンダー全体の追加・変更通知ではないと確認したため |
| カスタム分数指定リマインダー | GUIで「予定開始のN分前にポップアップ」等を設定可能にする | ONの場合はGoogleカレンダーのデフォルト設定に任せる方針で合意したため、カスタム値の指定機能は不要 |

## 設計詳細

### 1. 設定データ（`ConfigManager`）

`default_config` に以下を追加する。

```python
"enable_notifications": True,
```

`load()` は既存のロジック（`default_config` の各キーで不足分を補完）により、既存の `sync_config.json`（このキーを持たない）を読み込んだ場合も自動的に `True` を補完する。後方互換のため追加の移行処理は不要。

### 2. GUI（`SyncApp`）

「パスワードを保存」チェックボックス（既存、`garoon_google_sync_gui.py` 1109〜1112行目付近）と同じ設定カード内に追加する。

```python
self.notifications_var = tk.BooleanVar()
ttk.Checkbutton(check_btn_frame, text="Google通知（リマインダー）を有効にする",
               variable=self.notifications_var,
               style='Card.TCheckbutton').pack(side=tk.LEFT)
```

設定読み込み（1246行目付近のブロック）:
```python
self.notifications_var.set(self.config.get("enable_notifications", True))
```

設定保存（1307行目付近のブロック）:
```python
self.config["enable_notifications"] = self.notifications_var.get()
```

### 3. 同期エンジン（`GaroonToGoogleSync`）

コンストラクタに引数を追加する。

```python
def __init__(self, garoon: GaroonClient, google: GoogleCalendarClient, db: SyncDatabase,
             log_callback=None, enable_notifications: bool = True):
    ...
    self.enable_notifications = enable_notifications
```

インスタンス化箇所（GUIモード 1555行目付近、`--auto` モード 1675行目付近）の両方を更新する。

```python
sync_engine = GaroonToGoogleSync(garoon, google, db, self._log,
                                  enable_notifications=self.config.get("enable_notifications", True))
```

### 4. イベント変換（`EventConverter.garoon_to_google`）

シグネチャに引数を追加する。

```python
@staticmethod
def garoon_to_google(garoon_event: Dict, log_func=None, enable_notifications: bool = True) -> Optional[Dict]:
```

関数末尾、`return google_event` の直前（607行目付近、繰り返し予定のRRULE付与の後）に以下を追加する。

```python
if not enable_notifications:
    google_event["reminders"] = {"useDefault": False, "overrides": []}

return google_event
```

呼び出し箇所2箇所（847行目・876行目付近、新規作成用・更新用）に `enable_notifications=self.enable_notifications` を渡すよう変更する。

### 5. 適用範囲・データ移行

既存の同期済みイベント（Google Calendar上に既に作成済みのもの）は対象外。`GaroonToGoogleSync` の既存ロジック（Garoon側 `updatedAt` がDB記録より新しい場合のみGoogle側を更新）を変更しないため、設定変更後に当該イベントが何らかの理由（Garoon側の編集等）で更新対象になった場合は、その時点の設定値で `reminders` が再計算される。これは既存の「全フィールドをGaroon側のデータから都度再構築する」という設計と一貫しており、特別な移行処理は不要。

### 6. エラーハンドリング

新規の失敗モードは発生しない。`GoogleCalendarClient.create_event`/`update_event` の既存の `try/except` をそのまま通過する。設定キーが存在しない場合は `config.get("enable_notifications", True)` によりデフォルト値 `True` にフォールバックする。

### 7. テスト

`EventConverter.garoon_to_google()` に対する単体テストを追加する。

- `enable_notifications=True`（またはデフォルト）で呼び出した場合、戻り値の辞書に `"reminders"` キーが存在しないことを確認する
- `enable_notifications=False` で呼び出した場合、戻り値の `"reminders"` が `{"useDefault": False, "overrides": []}` と一致することを確認する

## スコープ外

- カレンダー全体の通知設定（`notificationSettings`）の制御
- リマインダーの分数・方式（ポップアップ／メール）のカスタマイズ
- 既存の同期済みイベントへの遡及的な `reminders` 適用
