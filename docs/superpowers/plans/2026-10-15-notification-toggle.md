# Googleカレンダー通知ON/OFF設定 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garoonから同期されるGoogle Calendarイベントについて、Googleカレンダーのリマインダー（ポップアップ・プッシュ通知）を有効/無効にするON/OFF設定を追加する。

**Architecture:** `EventConverter.garoon_to_google()` に `enable_notifications: bool` 引数を追加し、OFF時のみ `reminders: {"useDefault": false, "overrides": []}` を明示的に付与する。この値は `GaroonToGoogleSync` のコンストラクタを経由して2つの呼び出し箇所に伝播し、最終的にGUIのチェックボックス（`sync_config.json` に永続化）と `--auto` モードの設定読み込みの両方から供給される。

**Tech Stack:** Python 3.12 / Tkinter（GUI） / `unittest`（標準ライブラリ、新規テスト基盤）。既存の venv（`C:\dev\GaroonGoogleSync_Build\venv`）を使用する。新規の外部依存は追加しない。

## Global Constraints

- 対象ファイルは `C:\dev\GaroonGoogleSync_Build\garoon_google_sync_gui.py` の1ファイルに集約する（既存のシングルファイル構成に従う）
- デフォルト値は `True`（ON）とし、既存の `sync_config.json` を持つユーザーの挙動を変えない
- `enable_notifications=True` のとき、生成イベントに `reminders` キーを一切含めない（今日と完全に同一の挙動を維持する）
- `enable_notifications=False` のときのみ `reminders: {"useDefault": false, "overrides": []}` を設定する
- 設定は GUI モードと `--auto`/`--silent` モードの両方で有効にする
- 適用範囲は今後新規作成・更新されるイベントのみ。既存の同期済みイベントへの遡及更新処理は実装しない
- テストはすべて `venv\Scripts\python.exe` で実行する（グローバルPythonには `google-auth-oauthlib` 等が入っていないため、`garoon_google_sync_gui.py` の import が失敗する）

---

## File Structure

- **Modify:** `garoon_google_sync_gui.py` — `ConfigManager.default_config`、`EventConverter.garoon_to_google`、`GaroonToGoogleSync.__init__`、2箇所の `garoon_to_google` 呼び出し、GUIチェックボックス、設定読み込み/保存、2箇所の `GaroonToGoogleSync` インスタンス化
- **Create:** `tests/test_event_converter.py` — `EventConverter.garoon_to_google` の `enable_notifications` パラメータに対する単体テスト
- **Create:** `tests/test_sync_engine.py` — `ConfigManager` のデフォルト値、`GaroonToGoogleSync` のコンストラクタ属性保存、および `_add_to_google`/`_update_google_from_garoon` が `enable_notifications` を正しく反映した `reminders` 付きイベントを送信することを検証する単体テスト（`unittest.mock.Mock` でGoogle/DBをモック化し、ネットワーク・ファイルI/Oなしで検証する）

---

### Task 1: `EventConverter.garoon_to_google` に `enable_notifications` パラメータを追加する

**Files:**
- Modify: `garoon_google_sync_gui.py:505`（シグネチャ）, `garoon_google_sync_gui.py:605-607`（`return google_event` 直前）
- Test: `tests/test_event_converter.py`

**Interfaces:**
- Produces: `EventConverter.garoon_to_google(garoon_event: Dict, log_func=None, enable_notifications: bool = True) -> Optional[Dict]` — 戻り値の辞書は `enable_notifications=False` のときのみ `"reminders": {"useDefault": False, "overrides": []}` を含む

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_event_converter.py` を新規作成する:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from garoon_google_sync_gui import EventConverter

SAMPLE_EVENT = {
    "id": "123",
    "subject": "テスト予定",
    "eventMenu": "",
    "eventType": "REGULAR",
    "isAllDay": False,
    "notes": "",
    "updatedAt": "2026-10-15T01:00:00Z",
    "start": {"dateTime": "2026-10-20T10:00:00+09:00"},
    "end": {"dateTime": "2026-10-20T11:00:00+09:00"},
}


class TestGaroonToGoogleNotifications(unittest.TestCase):
    def test_enable_notifications_true_omits_reminders(self):
        result = EventConverter.garoon_to_google(SAMPLE_EVENT, enable_notifications=True)
        self.assertIsNotNone(result)
        self.assertNotIn("reminders", result)

    def test_enable_notifications_false_sets_no_reminders(self):
        result = EventConverter.garoon_to_google(SAMPLE_EVENT, enable_notifications=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["reminders"], {"useDefault": False, "overrides": []})

    def test_enable_notifications_defaults_to_true(self):
        result = EventConverter.garoon_to_google(SAMPLE_EVENT)
        self.assertIsNotNone(result)
        self.assertNotIn("reminders", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run（プロジェクトルート `C:\dev\GaroonGoogleSync_Build` で実行）:
```powershell
& ".\venv\Scripts\python.exe" -m unittest discover -s tests -p "test_event_converter.py" -v
```
Expected: `TypeError: garoon_to_google() got an unexpected keyword argument 'enable_notifications'` で3件とも FAIL

- [ ] **Step 3: 最小限の実装を行う**

`garoon_google_sync_gui.py:505` のシグネチャを変更する。

Before:
```python
    def garoon_to_google(garoon_event: Dict, log_func=None) -> Optional[Dict]:
```

After:
```python
    def garoon_to_google(garoon_event: Dict, log_func=None, enable_notifications: bool = True) -> Optional[Dict]:
```

`garoon_google_sync_gui.py:601-607`（`return google_event` 直前）を変更する。

Before:
```python
            else:
                if log_func:
                    log_func(f"    → RRULE変換失敗")
        
        return google_event
```

After:
```python
            else:
                if log_func:
                    log_func(f"    → RRULE変換失敗")
        
        if not enable_notifications:
            google_event["reminders"] = {"useDefault": False, "overrides": []}
        
        return google_event
```

- [ ] **Step 4: テストを実行して成功することを確認する**

Run:
```powershell
& ".\venv\Scripts\python.exe" -m unittest discover -s tests -p "test_event_converter.py" -v
```
Expected: 3件とも `OK`

- [ ] **Step 5: コミット**

```powershell
git add tests/test_event_converter.py garoon_google_sync_gui.py
git commit -m "feat: add enable_notifications param to EventConverter.garoon_to_google"
```

---

### Task 2: `ConfigManager` と `GaroonToGoogleSync` に設定値を配線する

**Files:**
- Modify: `garoon_google_sync_gui.py:79-88`（`ConfigManager.default_config`）, `garoon_google_sync_gui.py:747-755`（`GaroonToGoogleSync.__init__`）, `garoon_google_sync_gui.py:847`（`_add_to_google` 内の呼び出し）, `garoon_google_sync_gui.py:876`（`_update_google_from_garoon` 内の呼び出し）
- Test: `tests/test_sync_engine.py`

**Interfaces:**
- Consumes: `EventConverter.garoon_to_google(garoon_event, log_func=None, enable_notifications=True)`（Task 1で追加）
- Produces: `GaroonToGoogleSync(garoon, google, db, log_callback=None, enable_notifications: bool = True)` — インスタンスは `self.enable_notifications` 属性を持ち、`_add_to_google`/`_update_google_from_garoon` はこの属性を `EventConverter.garoon_to_google` に渡す。`ConfigManager.load()` が返す辞書は常に `"enable_notifications"` キー（デフォルト `True`）を含む。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_sync_engine.py` を新規作成する:

```python
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from garoon_google_sync_gui import ConfigManager, GaroonToGoogleSync

SAMPLE_EVENT = {
    "id": "123",
    "subject": "テスト予定",
    "eventMenu": "",
    "eventType": "REGULAR",
    "isAllDay": False,
    "notes": "",
    "updatedAt": "2026-10-15T01:00:00Z",
    "start": {"dateTime": "2026-10-20T10:00:00+09:00"},
    "end": {"dateTime": "2026-10-20T11:00:00+09:00"},
}


class TestConfigManagerDefaults(unittest.TestCase):
    def test_default_config_enables_notifications(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "sync_config.json")
            manager = ConfigManager(config_path)
            config = manager.load()
            self.assertTrue(config["enable_notifications"])


class TestGaroonToGoogleSyncNotificationWiring(unittest.TestCase):
    def test_constructor_stores_enable_notifications_false(self):
        engine = GaroonToGoogleSync(garoon=None, google=None, db=None, enable_notifications=False)
        self.assertFalse(engine.enable_notifications)

    def test_constructor_defaults_enable_notifications_true(self):
        engine = GaroonToGoogleSync(garoon=None, google=None, db=None)
        self.assertTrue(engine.enable_notifications)

    def test_add_to_google_respects_disabled_notifications(self):
        mock_google = Mock()
        mock_google.create_event.return_value = {"id": "g1", "updated": "2026-10-15T01:00:00Z"}
        mock_db = Mock()
        engine = GaroonToGoogleSync(garoon=None, google=mock_google, db=mock_db,
                                     enable_notifications=False)
        engine._add_to_google(SAMPLE_EVENT)
        sent_event = mock_google.create_event.call_args[0][0]
        self.assertEqual(sent_event["reminders"], {"useDefault": False, "overrides": []})

    def test_update_google_from_garoon_respects_disabled_notifications(self):
        mock_google = Mock()
        mock_google.update_event.return_value = {"id": "g1", "updated": "2026-10-15T01:00:00Z"}
        mock_db = Mock()
        engine = GaroonToGoogleSync(garoon=None, google=mock_google, db=mock_db,
                                     enable_notifications=False)
        engine._update_google_from_garoon(SAMPLE_EVENT, google_id="g1")
        sent_event = mock_google.update_event.call_args[0][1]
        self.assertEqual(sent_event["reminders"], {"useDefault": False, "overrides": []})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストを実行して失敗することを確認する**

Run:
```powershell
& ".\venv\Scripts\python.exe" -m unittest discover -s tests -p "test_sync_engine.py" -v
```
Expected: `test_default_config_enables_notifications` は `KeyError: 'enable_notifications'` で FAIL。残り4件は `TypeError: __init__() got an unexpected keyword argument 'enable_notifications'` で FAIL。

- [ ] **Step 3: 最小限の実装を行う**

`garoon_google_sync_gui.py:79-88`（`ConfigManager.default_config`）を変更する。

Before:
```python
        self.default_config = {
            "garoon_username": "",
            "garoon_password": "",  # 注意: 平文保存
            "calendar_name": "Garoon",
            "past_value": 7,
            "past_unit": "days",
            "future_value": 3,
            "future_unit": "months",
            "save_password": False
        }
```

After:
```python
        self.default_config = {
            "garoon_username": "",
            "garoon_password": "",  # 注意: 平文保存
            "calendar_name": "Garoon",
            "past_value": 7,
            "past_unit": "days",
            "future_value": 3,
            "future_unit": "months",
            "save_password": False,
            "enable_notifications": True
        }
```

`garoon_google_sync_gui.py:747-755`（`GaroonToGoogleSync.__init__`）を変更する。

Before:
```python
    def __init__(self, garoon: GaroonClient, google: GoogleCalendarClient, db: SyncDatabase, log_callback=None):
        self.garoon = garoon
        self.google = google
        self.db = db
        self.log = log_callback or print
        self.stats = {
            'google_added': 0, 'google_updated': 0, 'google_deleted': 0,
            'errors': 0
        }
```

After:
```python
    def __init__(self, garoon: GaroonClient, google: GoogleCalendarClient, db: SyncDatabase,
                 log_callback=None, enable_notifications: bool = True):
        self.garoon = garoon
        self.google = google
        self.db = db
        self.log = log_callback or print
        self.enable_notifications = enable_notifications
        self.stats = {
            'google_added': 0, 'google_updated': 0, 'google_deleted': 0,
            'errors': 0
        }
```

`garoon_google_sync_gui.py:847`（`_add_to_google` 内）を変更する。

Before:
```python
        google_data = EventConverter.garoon_to_google(garoon_event, log_func=self.log if event_type == "REPEATING" else None)
```

After:
```python
        google_data = EventConverter.garoon_to_google(
            garoon_event,
            log_func=self.log if event_type == "REPEATING" else None,
            enable_notifications=self.enable_notifications
        )
```

`garoon_google_sync_gui.py:876`（`_update_google_from_garoon` 内）を変更する。

Before:
```python
        google_data = EventConverter.garoon_to_google(garoon_event, log_func=self.log if event_type == "REPEATING" else None)
```

After:
```python
        google_data = EventConverter.garoon_to_google(
            garoon_event,
            log_func=self.log if event_type == "REPEATING" else None,
            enable_notifications=self.enable_notifications
        )
```

- [ ] **Step 4: テストを実行して成功することを確認する**

Run:
```powershell
& ".\venv\Scripts\python.exe" -m unittest discover -s tests -p "test_sync_engine.py" -v
```
Expected: 5件とも `OK`

- [ ] **Step 5: コミット**

```powershell
git add tests/test_sync_engine.py garoon_google_sync_gui.py
git commit -m "feat: wire enable_notifications through ConfigManager and GaroonToGoogleSync"
```

---

### Task 3: GUIチェックボックスと両方のインスタンス化箇所を配線する

**Files:**
- Modify: `garoon_google_sync_gui.py:1178-1179`（`sync_frame` 内に通知チェックボックスの行を追加）, `garoon_google_sync_gui.py:1246`（`_load_config_to_ui`）, `garoon_google_sync_gui.py:1307`（`_save_config`）, `garoon_google_sync_gui.py:1555`（GUIモードの `GaroonToGoogleSync` インスタンス化）, `garoon_google_sync_gui.py:1675`（`--auto` モードの `GaroonToGoogleSync` インスタンス化）

**Interfaces:**
- Consumes: `GaroonToGoogleSync(garoon, google, db, log_callback=None, enable_notifications: bool = True)`（Task 2で追加）、`ConfigManager.load()` が返す `config["enable_notifications"]`（Task 2で追加）
- Produces: `self.notifications_var: tk.BooleanVar`（`SyncApp` 上のGUI状態。GUIテストは本タスクでは自動化せず、手動検証で代替する — 既存コードベースにTkinter用のテスト基盤が存在しないため）

このタスクはTkinterウィジェットの生成・設定ファイルの読み書き・実際のGoogle/Garoon接続を伴うGUIの配線であり、既存コードベースにGUI自動テストの前例がないため、自動テストは追加せず手動検証で確認する。

- [ ] **Step 1: `sync_frame` にチェックボックスを追加する**

`garoon_google_sync_gui.py:1178-1180` を変更する。

Before:
```python
        ttk.Label(period_frame, text="後", style='Card.TLabel').pack(side=tk.LEFT)
        
        # === 実行ボタンエリア（同期設定とログの間）===
```

After:
```python
        ttk.Label(period_frame, text="後", style='Card.TLabel').pack(side=tk.LEFT)
        
        # 通知設定行
        notification_row = ttk.Frame(sync_frame, style='Card.TFrame')
        notification_row.pack(fill=tk.X, pady=(5, 0))
        
        self.notifications_var = tk.BooleanVar()
        ttk.Checkbutton(notification_row, text="Google通知（リマインダー）を有効にする",
                       variable=self.notifications_var,
                       style='Card.TCheckbutton').pack(side=tk.LEFT)
        
        # === 実行ボタンエリア（同期設定とログの間）===
```

- [ ] **Step 2: 設定読み込み・保存に配線する**

`garoon_google_sync_gui.py:1246` 付近（`_load_config_to_ui`）を変更する。

Before:
```python
        self.save_password_var.set(self.config.get("save_password", False))
        self.calendar_var.set(self.config.get("calendar_name", "Garoon"))
```

After:
```python
        self.save_password_var.set(self.config.get("save_password", False))
        self.notifications_var.set(self.config.get("enable_notifications", True))
        self.calendar_var.set(self.config.get("calendar_name", "Garoon"))
```

`garoon_google_sync_gui.py:1307` 付近（`_save_config`）を変更する。

Before:
```python
        self.config["save_password"] = self.save_password_var.get()
        self.config["calendar_name"] = self.calendar_var.get()
```

After:
```python
        self.config["save_password"] = self.save_password_var.get()
        self.config["enable_notifications"] = self.notifications_var.get()
        self.config["calendar_name"] = self.calendar_var.get()
```

- [ ] **Step 3: GUIモードのインスタンス化箇所に配線する**

`garoon_google_sync_gui.py:1555` 付近を変更する。

Before:
```python
            sync_engine = GaroonToGoogleSync(garoon, google, db, self._log)
```

After:
```python
            sync_engine = GaroonToGoogleSync(
                garoon, google, db, self._log,
                enable_notifications=self.notifications_var.get()
            )
```

- [ ] **Step 4: `--auto` モードのインスタンス化箇所に配線する**

`garoon_google_sync_gui.py:1675` 付近を変更する。

Before:
```python
        sync_engine = GaroonToGoogleSync(garoon, google, db, log)
```

After:
```python
        sync_engine = GaroonToGoogleSync(
            garoon, google, db, log,
            enable_notifications=config.get("enable_notifications", True)
        )
```

- [ ] **Step 5: 既存の自動テストが引き続き通ることを確認する**

Run（プロジェクトルートで実行）:
```powershell
& ".\venv\Scripts\python.exe" -m unittest discover -s tests -p "test_*.py" -v
```
Expected: Task 1・Task 2で作成した計8件のテストすべてが `OK`（GUI変更はこれらのテストに影響しない）

- [ ] **Step 6: 手動検証**

1. `C:\dev\GaroonGoogleSync_Build` で以下を実行してGUIを起動する:
   ```powershell
   & ".\venv\Scripts\python.exe" garoon_google_sync_gui.py
   ```
2. 「⚙️ 同期設定」カード内に「Google通知（リマインダー）を有効にする」チェックボックスが表示され、デフォルトでチェック済みであることを確認する
3. チェックを外し、「💾 設定を保存」をクリックする
4. `sync_config.json` を開き、`"enable_notifications": false` が含まれることを確認する
5. アプリを終了し再起動する。チェックボックスが外れた状態で復元されることを確認する
6. 再度チェックを入れて保存し、`sync_config.json` の値が `true` に戻ることを確認する

- [ ] **Step 7: コミット**

```powershell
git add garoon_google_sync_gui.py
git commit -m "feat: add GUI toggle for Google Calendar notification reminders"
```

---

## Self-Review

**Spec coverage:**
- ConfigManagerのデフォルト値追加 → Task 2 Step 3で実装
- EventConverter.garoon_to_googleのシグネチャ・reminders付与ロジック → Task 1 Step 3で実装
- GaroonToGoogleSyncコンストラクタ・2呼び出し箇所 → Task 2 Step 3で実装
- GUIチェックボックス・読み込み・保存 → Task 3 Step 1-2で実装
- 2箇所のインスタンス化（GUIモード・autoモード） → Task 3 Step 3-4で実装
- 適用範囲（今後の新規・更新のみ、遡及処理なし） → 既存の更新検知ロジック（`updatedAt`比較）を変更していないため自然に満たされる。新規コードは追加していない
- テスト（spec section 7の2パターン） → Task 1でカバー、さらにTask 2で配線レベルのテストを追加

**Placeholder scan:** "TBD"・"TODO"・"later" 等の記述なし。すべてのコードブロックは完全な実装を含む。

**Type consistency:** `enable_notifications: bool = True` のシグネチャは `EventConverter.garoon_to_google`・`GaroonToGoogleSync.__init__` で統一。呼び出し箇所（Task 2のcall site、Task 3の2箇所のインスタンス化）もすべて同じキーワード引数名 `enable_notifications` を使用しており不整合なし。
