# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Garoon（サイボウズ `mrh-garoon.cybozu.com`）のスケジュールを Google Calendar へ**一方向同期**する Windows 向けデスクトップツール。ソースコードは `garoon_google_sync_gui.py` の 1 ファイルに完結している。

## 実行コマンド

```bash
# 通常起動（GUI）
python garoon_google_sync_gui.py

# 自動同期モード（タスクスケジューラ向け、GUIなし）
python garoon_google_sync_gui.py --auto

# サイレントモード（ログファイルのみ、stdout なし）
python garoon_google_sync_gui.py --auto --silent
```

## 依存ライブラリのインストール

```bash
pip install requests google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dateutil
```

## EXE ビルド

```bash
# 仮想環境込みの完全ビルド（推奨）
build_exe.bat

# グローバル Python で簡易ビルド
build_simple.bat
```

出力: `dist\GaroonGoogleSync.exe`（`--onefile --noconsole`）

## アーキテクチャ

### クラス構成（`garoon_google_sync_gui.py`）

| クラス | 役割 |
|---|---|
| `ConfigManager` | `sync_config.json` の読み書き |
| `SyncDatabase` | SQLite3（`sync_mapping.db`）で Garoon ↔ Google のイベント ID マッピングを管理 |
| `GaroonClient` | Garoon REST API クライアント（`X-Cybozu-Authorization` ヘッダー、Basic 認証） |
| `GoogleCalendarClient` | Google Calendar API v3 クライアント（OAuth2） |
| `EventConverter` | Garoon ↔ Google イベント形式の相互変換（繰り返し予定の RRULE 変換含む） |
| `GaroonToGoogleSync` | 同期エンジン。Step1:データ取得 → Step2:削除処理 → Step3:新規・更新処理 |
| `SyncApp` | tkinter GUI（ダークテーマ、PanedWindow で上下分割） |

### 同期フロー

```
Garoon API → [GaroonClient] → [GaroonToGoogleSync] → [GoogleCalendarClient] → Google Calendar API
                                        ↕
                               [SyncDatabase] (SQLite3)
```

同期は Garoon 主導の一方向。Garoon 側の `updatedAt` が DB の記録より新しい場合のみ Google を更新する。

### 実行時ファイル（EXE と同じフォルダに配置）

| ファイル | 説明 |
|---|---|
| `credentials.json` | Google Cloud Console から取得（**必須・手動配置**） |
| `token.pickle` | OAuth2 トークン（初回認証後に自動生成） |
| `sync_config.json` | GUI 設定の保存先 |
| `sync_mapping.db` | Garoon↔Google ID マッピング DB |
| `sync_log.txt` | `--auto` モード時のログ出力先 |

## 重要な定数・制約

- **`GAROON_SUBDOMAIN = "mrh-garoon"`**（L40）: マルハン固定。別組織に転用する際はここを変更する。
- **SSL 検証無効**（L34: `urllib3.disable_warnings` + 全リクエストで `verify=False`）: 社内プロキシ対応のため。
- **Google Calendar スコープ**: `https://www.googleapis.com/auth/calendar`（読み書き両方）。
- パスワードは `sync_config.json` に平文保存（`save_password` フラグが True の場合のみ）。

## 繰り返し予定の扱い

`EventConverter._convert_repeat_to_rrule()`（L563〜）が Garoon の `repeatInfo.type` を Google の RRULE 文字列に変換する。対応タイプ: `EVERY_DAY`, `EVERY_WEEKDAY`, `EVERY_WEEK`, `EVERY_1STWEEK`〜`EVERY_LASTWEEK`, `EVERY_MONTH`, `EVERY_YEAR`（旧形式 `DAY`/`WEEK`/`MONTH`/`YEAR` も互換対応）。

## 終日イベントの判定ロジック

`isAllDay=True` の他に、時刻が `00:00〜23:59` または `00:00〜翌00:00` のイベントも擬似終日として Google の `date` 形式で登録する（`EventConverter.garoon_to_google` L475〜）。
