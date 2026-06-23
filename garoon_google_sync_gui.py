#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garoon → Google Calendar 一方通行同期ツール（GUI版）

機能:
- GUIで設定入力
- GaroonのイベントをGoogleに同期
- 更新されたイベントを同期
- Garoonで削除されたイベントをGoogleから削除
- SQLiteでマッピング情報を管理
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import os
import sys
import requests
import base64
import sqlite3
import pickle
import urllib3
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from typing import Optional, Dict, List, Any

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# SSL証明書検証エラーの警告を抑制（社内プロキシ対応）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# 定数
# ============================================
SCOPES = ['https://www.googleapis.com/auth/calendar']
GAROON_SUBDOMAIN = "mrh-garoon"  # Garoonサブドメイン（固定）

def get_app_dir():
    """アプリケーション（スクリプト/exe）のディレクトリを取得"""
    if getattr(sys, 'frozen', False):
        # exe化されている場合
        return os.path.dirname(sys.executable)
    else:
        # スクリプトとして実行されている場合
        return os.path.dirname(os.path.abspath(__file__))

APP_DIR = get_app_dir()
CONFIG_FILE = os.path.join(APP_DIR, "sync_config.json")
DB_FILE = os.path.join(APP_DIR, "sync_mapping.db")
TOKEN_FILE = os.path.join(APP_DIR, "token.pickle")
CREDENTIALS_FILE = os.path.join(APP_DIR, "credentials.json")


# ============================================
# 設定管理
# ============================================
class ConfigManager:
    """設定の保存・読み込み"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.default_config = {
            "garoon_username": "",
            "garoon_password": "",  # 注意: 平文保存
            "calendar_name": "Garoon",
            "past_days": 7,
            "future_days": 90,  # 約3ヶ月
            "save_password": False
        }
    
    def load(self) -> Dict:
        """設定を読み込み"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # デフォルト値で補完
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception:
                pass
        return self.default_config.copy()
    
    def save(self, config: Dict):
        """設定を保存"""
        save_config = config.copy()
        if not config.get("save_password", False):
            save_config["garoon_password"] = ""
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(save_config, f, ensure_ascii=False, indent=2)


# ============================================
# データベース
# ============================================
class SyncDatabase:
    """同期マッピング情報を管理するデータベース"""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                garoon_id TEXT UNIQUE,
                google_id TEXT UNIQUE,
                garoon_updated_at TEXT,
                google_updated_at TEXT,
                last_synced_at TEXT,
                deleted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                synced_at TEXT,
                garoon_added INTEGER,
                garoon_updated INTEGER,
                garoon_deleted INTEGER,
                google_added INTEGER,
                google_updated INTEGER,
                google_deleted INTEGER,
                errors INTEGER
            )
        ''')
        self.conn.commit()
    
    def get_mapping_by_garoon_id(self, garoon_id: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM event_mapping WHERE garoon_id = ? AND deleted = 0',
            (garoon_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_mapping_by_google_id(self, google_id: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM event_mapping WHERE google_id = ? AND deleted = 0',
            (google_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_all_mappings(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM event_mapping WHERE deleted = 0')
        return [dict(row) for row in cursor.fetchall()]
    
    def add_mapping(self, garoon_id: str, google_id: str, 
                    garoon_updated: str, google_updated: str):
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            INSERT OR REPLACE INTO event_mapping 
            (garoon_id, google_id, garoon_updated_at, google_updated_at, last_synced_at, deleted)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (garoon_id, google_id, garoon_updated, google_updated, now))
        self.conn.commit()
    
    def update_mapping(self, garoon_id: str = None, google_id: str = None,
                       garoon_updated: str = None, google_updated: str = None):
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        if garoon_id:
            cursor.execute('''
                UPDATE event_mapping 
                SET garoon_updated_at = COALESCE(?, garoon_updated_at),
                    google_updated_at = COALESCE(?, google_updated_at),
                    last_synced_at = ?
                WHERE garoon_id = ?
            ''', (garoon_updated, google_updated, now, garoon_id))
        elif google_id:
            cursor.execute('''
                UPDATE event_mapping 
                SET garoon_updated_at = COALESCE(?, garoon_updated_at),
                    google_updated_at = COALESCE(?, google_updated_at),
                    last_synced_at = ?
                WHERE google_id = ?
            ''', (garoon_updated, google_updated, now, google_id))
        
        self.conn.commit()
    
    def mark_deleted(self, garoon_id: str = None, google_id: str = None):
        cursor = self.conn.cursor()
        if garoon_id:
            cursor.execute(
                'UPDATE event_mapping SET deleted = 1 WHERE garoon_id = ?',
                (garoon_id,)
            )
        elif google_id:
            cursor.execute(
                'UPDATE event_mapping SET deleted = 1 WHERE google_id = ?',
                (google_id,)
            )
        self.conn.commit()
    
    def add_sync_history(self, stats: Dict):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO sync_history 
            (synced_at, garoon_added, garoon_updated, garoon_deleted,
             google_added, google_updated, google_deleted, errors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(timezone.utc).isoformat(),
            stats.get('garoon_added', 0),
            stats.get('garoon_updated', 0),
            stats.get('garoon_deleted', 0),
            stats.get('google_added', 0),
            stats.get('google_updated', 0),
            stats.get('google_deleted', 0),
            stats.get('errors', 0)
        ))
        self.conn.commit()
    
    def close(self):
        self.conn.close()


# ============================================
# Garoonクライアント
# ============================================
class GaroonClient:
    
    def __init__(self, subdomain: str, username: str, password: str):
        self.base_url = f"https://{subdomain}.cybozu.com/g/api/v1"
        self.username = username
        credentials = f"{username}:{password}"
        self.auth_header = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            "X-Cybozu-Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
    
    def test_connection(self) -> tuple:
        """接続テスト"""
        url = f"{self.base_url}/schedule/events"
        try:
            response = requests.get(url, headers=self.headers, params={"limit": 1}, timeout=10, verify=False)
            if response.status_code == 200:
                return True, "接続成功"
            elif response.status_code == 401:
                return False, "認証エラー（ユーザー名/パスワードを確認）"
            else:
                return False, f"エラー: {response.status_code}"
        except Exception as e:
            return False, f"接続エラー: {e}"
    
    def get_events(self, start_date: str, end_date: str) -> List[Dict]:
        all_events = []
        seen_ids = set()
        
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        current_start = start
        
        while current_start <= end:
            current_end = current_start + relativedelta(months=1) - timedelta(days=1)
            if current_end > end:
                current_end = end
            
            events = self._get_events_chunk(
                current_start.strftime("%Y-%m-%d"),
                current_end.strftime("%Y-%m-%d")
            )
            
            for event in events:
                event_id = str(event.get("id"))
                if event_id not in seen_ids:
                    seen_ids.add(event_id)
                    all_events.append(event)
            
            current_start = current_end + timedelta(days=1)
        
        return all_events
    
    def _get_events_chunk(self, start_date: str, end_date: str) -> List[Dict]:
        url = f"{self.base_url}/schedule/events"
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        end_date_next = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        
        params = {
            "rangeStart": f"{start_date}T00:00:00+09:00",
            "rangeEnd": f"{end_date_next}T00:00:00+09:00",
            "orderBy": "start asc",
        }
        
        response = requests.get(
            url,
            headers=self.headers,
            params=params,
            verify=False
        )
        
        if response.status_code == 200:
            return response.json().get("events", [])
        return []
    
    def create_event(self, event_data: Dict) -> Optional[Dict]:
        url = f"{self.base_url}/schedule/events"
        response = requests.post(url, headers=self.headers, json=event_data, verify=False)
        if response.status_code in [200, 201]:
            return response.json()
        return None
    
    def update_event(self, event_id: str, event_data: Dict) -> Optional[Dict]:
        url = f"{self.base_url}/schedule/events/{event_id}"
        response = requests.patch(url, headers=self.headers, json=event_data, verify=False)
        if response.status_code in [200, 201]:
            return response.json()
        return None
    
    def delete_event(self, event_id: str) -> bool:
        url = f"{self.base_url}/schedule/events/{event_id}"
        response = requests.delete(url, headers=self.headers, verify=False)
        return response.status_code in [200, 204]


# ============================================
# Google Calendarクライアント
# ============================================
class GoogleCalendarClient:
    
    def __init__(self, calendar_name: str):
        self.service = self._get_service()
        self.calendar_id = self._get_calendar_id(calendar_name)
        if not self.calendar_id:
            raise ValueError(f"カレンダー '{calendar_name}' が見つかりません")
    
    def _get_service(self):
        creds = None
        
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    if os.path.exists(TOKEN_FILE):
                        os.remove(TOKEN_FILE)
                    creds = None
            
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
        
        return build('calendar', 'v3', credentials=creds)
    
    def _get_calendar_id(self, calendar_name: str) -> Optional[str]:
        calendars = self.service.calendarList().list().execute()
        for cal in calendars.get('items', []):
            if cal['summary'] == calendar_name:
                return cal['id']
        return None
    
    def get_calendar_list(self) -> List[str]:
        """利用可能なカレンダー一覧を取得"""
        calendars = self.service.calendarList().list().execute()
        return [cal['summary'] for cal in calendars.get('items', [])]
    
    def get_events(self, start_date: str, end_date: str) -> List[Dict]:
        time_min = f"{start_date}T00:00:00+09:00"
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        end_date_next = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        time_max = f"{end_date_next}T00:00:00+09:00"
        
        all_events = []
        page_token = None
        
        while True:
            # singleEvents=False で繰り返しイベントのマスターも取得
            result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=False,
                pageToken=page_token
            ).execute()
            
            all_events.extend(result.get('items', []))
            
            page_token = result.get('nextPageToken')
            if not page_token:
                break
        
        return all_events
    
    def create_event(self, event_data: Dict) -> Optional[Dict]:
        try:
            return self.service.events().insert(
                calendarId=self.calendar_id,
                body=event_data
            ).execute()
        except Exception as e:
            print(f"Google Calendar API エラー: {e}")
            return None
    
    def update_event(self, event_id: str, event_data: Dict) -> Optional[Dict]:
        try:
            return self.service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event_data
            ).execute()
        except Exception:
            return None
    
    def delete_event(self, event_id: str) -> bool:
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            return True
        except Exception:
            return False


# ============================================
# イベント変換
# ============================================
class EventConverter:
    
    # Garoonの曜日コード → GoogleのRRULE曜日
    GAROON_DAY_TO_RRULE = {
        0: "SU",
        1: "MO",
        2: "TU",
        3: "WE",
        4: "TH",
        5: "FR",
        6: "SA",
    }
    
    @staticmethod
    def garoon_to_google(garoon_event: Dict, log_func=None) -> Optional[Dict]:
        title = EventConverter._get_garoon_title(garoon_event)
        notes = garoon_event.get("notes", "") or ""
        is_all_day = garoon_event.get("isAllDay", False)
        start_info = garoon_event.get("start", {})
        end_info = garoon_event.get("end", {})
        event_type = garoon_event.get("eventType", "REGULAR")
        
        google_event = {
            "summary": title,
            "description": f"[Garoonから同期]\n{notes}",
        }
        
        start_dt = start_info.get("dateTime", "")
        end_dt = end_info.get("dateTime", "")
        
        # 00:00〜23:59 または 00:00〜24:00 のパターンは終日イベントとして扱う
        is_pseudo_all_day = False
        if start_dt and end_dt and not is_all_day:
            try:
                start_datetime = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                end_datetime = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
                
                # 時間部分を確認
                start_time = start_datetime.strftime("%H:%M")
                end_time = end_datetime.strftime("%H:%M")
                
                # 00:00〜23:59 または同日の00:00開始で翌日00:00終了
                if start_time == "00:00" and end_time in ["23:59", "00:00"]:
                    is_pseudo_all_day = True
                    if log_func:
                        log_func(f"    → 00:00-{end_time}を終日イベントとして処理")
            except:
                pass
        
        if is_all_day or is_pseudo_all_day:
            # 終日イベント・期間予定 → Googleの終日イベントとして登録
            if start_dt:
                start_datetime = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                start_date = start_datetime.strftime("%Y-%m-%d")
            else:
                start_date = start_info.get("date", "")
            
            if not start_date:
                return None
            
            # 終了日を取得
            if end_dt:
                end_datetime = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
                end_time = end_datetime.strftime("%H:%M")
                
                if end_time == "00:00":
                    # 翌日00:00終了の場合、その日自体が終了日
                    end_date = end_datetime.strftime("%Y-%m-%d")
                else:
                    # Googleの終日イベントは終了日の翌日を指定する必要がある
                    end_date = (end_datetime + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                end_date = end_info.get("date", "")
                if end_date:
                    # dateフィールドの場合も翌日にする
                    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
                    end_date = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    # 終了日がない場合は開始日の翌日（1日間）
                    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
                    end_date = (start_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Googleの終日イベント形式（dateフィールドを使用）
            google_event["start"] = {"date": start_date}
            google_event["end"] = {"date": end_date}
        else:
            if start_dt:
                if not end_dt:
                    start_datetime = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                    end_datetime = start_datetime + timedelta(minutes=30)
                    end_dt = end_datetime.isoformat()
                
                google_event["start"] = {"dateTime": start_dt, "timeZone": "Asia/Tokyo"}
                google_event["end"] = {"dateTime": end_dt, "timeZone": "Asia/Tokyo"}
            else:
                start_date = start_info.get("date", "")
                if not start_date:
                    return None
                
                google_event["start"] = {"dateTime": f"{start_date}T00:00:00+09:00", "timeZone": "Asia/Tokyo"}
                google_event["end"] = {"dateTime": f"{start_date}T00:30:00+09:00", "timeZone": "Asia/Tokyo"}
        
        # 繰り返し予定の場合、RRULEを追加
        if event_type == "REPEATING":
            repeat_info = garoon_event.get("repeatInfo", {})
            if log_func:
                log_func(f"    → 繰り返し情報: {repeat_info}")
            rrule = EventConverter._convert_repeat_to_rrule(repeat_info, log_func)
            if rrule:
                google_event["recurrence"] = [rrule]
                if log_func:
                    log_func(f"    → RRULE: {rrule}")
            else:
                if log_func:
                    log_func(f"    → RRULE変換失敗")
        
        return google_event
    
    @staticmethod
    def _convert_repeat_to_rrule(repeat_info: Dict, log_func=None) -> Optional[str]:
        """Garoonの繰り返し情報をGoogleのRRULE形式に変換"""
        if not repeat_info:
            return None
        
        # Garoonの曜日文字列 → GoogleのRRULE曜日
        DAY_STR_TO_RRULE = {
            "SUN": "SU",
            "MON": "MO",
            "TUE": "TU",
            "WED": "WE",
            "THU": "TH",
            "FRI": "FR",
            "SAT": "SA",
        }
        
        repeat_type = repeat_info.get("type", "")
        day_of_week_str = repeat_info.get("dayOfWeek", "")  # 文字列形式 "FRI", "TUE" など
        
        # 終了日を取得（period オブジェクト内）
        until_str = ""
        period = repeat_info.get("period", {})
        if period:
            end_date = period.get("end", "")
            if end_date:
                try:
                    until_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                    until_str = f";UNTIL={until_datetime.strftime('%Y%m%dT235959Z')}"
                except Exception as e:
                    if log_func:
                        log_func(f"      終了日変換エラー: {e}")
        
        # 曜日コードを取得
        day_code = DAY_STR_TO_RRULE.get(day_of_week_str, "")
        
        # 繰り返しタイプに応じてRRULEを生成
        if repeat_type == "EVERY_DAY":
            # 毎日
            return f"RRULE:FREQ=DAILY{until_str}"
        
        elif repeat_type == "EVERY_WEEKDAY":
            # 平日（月〜金）
            return f"RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR{until_str}"
        
        elif repeat_type == "EVERY_WEEK":
            # 毎週特定の曜日
            if day_code:
                return f"RRULE:FREQ=WEEKLY;BYDAY={day_code}{until_str}"
            return f"RRULE:FREQ=WEEKLY{until_str}"
        
        elif repeat_type == "EVERY_1STWEEK":
            # 毎月第1週の特定曜日
            if day_code:
                return f"RRULE:FREQ=MONTHLY;BYDAY=1{day_code}{until_str}"
            return f"RRULE:FREQ=MONTHLY{until_str}"
        
        elif repeat_type == "EVERY_2NDWEEK":
            # 毎月第2週の特定曜日
            if day_code:
                return f"RRULE:FREQ=MONTHLY;BYDAY=2{day_code}{until_str}"
            return f"RRULE:FREQ=MONTHLY{until_str}"
        
        elif repeat_type == "EVERY_3RDWEEK":
            # 毎月第3週の特定曜日
            if day_code:
                return f"RRULE:FREQ=MONTHLY;BYDAY=3{day_code}{until_str}"
            return f"RRULE:FREQ=MONTHLY{until_str}"
        
        elif repeat_type == "EVERY_4THWEEK":
            # 毎月第4週の特定曜日
            if day_code:
                return f"RRULE:FREQ=MONTHLY;BYDAY=4{day_code}{until_str}"
            return f"RRULE:FREQ=MONTHLY{until_str}"
        
        elif repeat_type == "EVERY_LASTWEEK":
            # 毎月最終週の特定曜日
            if day_code:
                return f"RRULE:FREQ=MONTHLY;BYDAY=-1{day_code}{until_str}"
            return f"RRULE:FREQ=MONTHLY{until_str}"
        
        elif repeat_type == "EVERY_MONTH":
            # 毎月特定の日
            return f"RRULE:FREQ=MONTHLY{until_str}"
        
        elif repeat_type == "EVERY_YEAR":
            # 毎年
            return f"RRULE:FREQ=YEARLY{until_str}"
        
        # 旧形式への対応（念のため残す）
        elif repeat_type == "DAY":
            return f"RRULE:FREQ=DAILY{until_str}"
        elif repeat_type == "WEEKDAY":
            return f"RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR{until_str}"
        elif repeat_type == "WEEK":
            day_of_week = repeat_info.get("dayOfWeek", 0)
            if isinstance(day_of_week, int):
                day_code = EventConverter.GAROON_DAY_TO_RRULE.get(day_of_week, "MO")
            return f"RRULE:FREQ=WEEKLY;BYDAY={day_code}{until_str}"
        elif repeat_type == "MONTH":
            return f"RRULE:FREQ=MONTHLY{until_str}"
        elif repeat_type == "YEAR":
            return f"RRULE:FREQ=YEARLY{until_str}"
        
        if log_func:
            log_func(f"      未対応の繰り返しタイプ: {repeat_type}")
        
        return None
    
    @staticmethod
    def google_to_garoon(google_event: Dict, garoon_username: str) -> Dict:
        """GoogleイベントをGaroon形式に変換（期間予定として登録）"""
        import re
        
        summary = google_event.get("summary", "（件名なし）")
        description = google_event.get("description", "")
        
        if description.startswith("[Googleから同期]"):
            description = description.replace("[Googleから同期]\n", "").strip()
        if description.startswith("[Garoonから同期]"):
            description = description.replace("[Garoonから同期]\n", "").strip()
        
        event_menu = ""
        subject = summary
        
        match = re.match(r'^\[([^\]]+)\]\s*(.*)', summary)
        if match:
            event_menu = match.group(1)
            subject = match.group(2).strip()
        
        start = google_event.get("start", {})
        end = google_event.get("end", {})
        
        garoon_event = {
            "eventType": "REGULAR",
            "subject": subject,
            "notes": f"[Googleから同期]\n{description}",
            "attendees": [{"type": "USER", "code": garoon_username}],
        }
        
        if event_menu:
            garoon_event["eventMenu"] = event_menu
        
        if "date" in start:
            # Googleの終日イベント → Garoonの期間予定（帯状表示）
            garoon_event["isAllDay"] = True
            garoon_event["start"] = {"dateTime": f"{start['date']}T00:00:00+09:00", "timeZone": "Asia/Tokyo"}
            
            # Googleの終了日は翌日なので1日引く
            end_date = end.get("date", start["date"])
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=1)
            # Garoonの期間予定は終了日の23:59:59
            garoon_event["end"] = {"dateTime": f"{end_date_obj.strftime('%Y-%m-%d')}T23:59:59+09:00", "timeZone": "Asia/Tokyo"}
        else:
            garoon_event["isAllDay"] = False
            garoon_event["start"] = {"dateTime": start.get("dateTime"), "timeZone": "Asia/Tokyo"}
            garoon_event["end"] = {"dateTime": end.get("dateTime"), "timeZone": "Asia/Tokyo"}
        
        return garoon_event
    
    @staticmethod
    def _get_garoon_title(garoon_event: Dict) -> str:
        subject = (garoon_event.get("subject") or "").strip()
        event_menu = (garoon_event.get("eventMenu") or "").strip()
        
        if subject and event_menu:
            return f"[{event_menu}] {subject}"
        elif subject:
            return subject
        elif event_menu:
            return f"[{event_menu}]"
        else:
            return "（件名なし）"
    
    @staticmethod
    def get_garoon_updated_at(event: Dict) -> str:
        return event.get("updatedAt", event.get("createdAt", ""))
    
    @staticmethod
    def get_google_updated_at(event: Dict) -> str:
        return event.get("updated", event.get("created", ""))


# ============================================
# 同期エンジン
# ============================================
class GaroonToGoogleSync:
    """Garoon→Google 一方通行同期"""
    
    def __init__(self, garoon: GaroonClient, google: GoogleCalendarClient, db: SyncDatabase, log_callback=None):
        self.garoon = garoon
        self.google = google
        self.db = db
        self.log = log_callback or print
        self.stats = {
            'google_added': 0, 'google_updated': 0, 'google_deleted': 0,
            'errors': 0
        }
    
    def sync(self, start_date: str, end_date: str):
        self.log("【Step 1】データ取得中...")
        
        self.log("  Garoonからイベント取得中...")
        garoon_events = self.garoon.get_events(start_date, end_date)
        
        # イベントタイプ別にカウント
        regular_count = sum(1 for e in garoon_events if e.get("eventType") == "REGULAR")
        repeating_count = sum(1 for e in garoon_events if e.get("eventType") == "REPEATING")
        
        self.log(f"  → {len(garoon_events)}件（通常: {regular_count}, 繰り返し: {repeating_count}）")
        
        self.log("  Googleからイベント取得中...")
        google_events = self.google.get_events(start_date, end_date)
        self.log(f"  → {len(google_events)}件")
        
        garoon_by_id = {str(e.get("id")): e for e in garoon_events}
        google_by_id = {e.get("id"): e for e in google_events}
        mappings = self.db.get_all_mappings()
        
        self.log("\n【Step 2】削除イベントの処理...")
        deleted_garoon_ids = self._process_deletions(garoon_by_id, google_by_id, mappings)
        
        self.log("\n【Step 3】新規・更新イベントの処理...")
        self._process_garoon_events(garoon_events, google_by_id, deleted_garoon_ids)
        
        self.db.add_sync_history(self.stats)
        return self.stats
    
    def _process_deletions(self, garoon_by_id, google_by_id, mappings):
        """Garoonで削除されたイベントをGoogleから削除"""
        deleted_garoon_ids = set()
        
        for mapping in mappings:
            garoon_id = mapping['garoon_id']
            google_id = mapping['google_id']
            
            garoon_exists = garoon_id in garoon_by_id if garoon_id else False
            google_exists = google_id in google_by_id if google_id else False
            
            if garoon_id and not garoon_exists and google_id and google_exists:
                # Garoonで削除 → Googleから削除
                google_event = google_by_id[google_id]
                event_date = self._get_event_date(google_event)
                self.log(f"  🗑 削除: [{event_date}] {google_event.get('summary', '?')}")
                if self.google.delete_event(google_id):
                    self.db.mark_deleted(garoon_id=garoon_id)
                    self.stats['google_deleted'] += 1
                else:
                    self.stats['errors'] += 1
            
            elif not garoon_exists and not google_exists:
                # 両方で削除済み → マッピング削除
                self.db.mark_deleted(garoon_id=garoon_id)
        
        return deleted_garoon_ids
    
    def _process_garoon_events(self, garoon_events, google_by_id, deleted_garoon_ids):
        """Garoonイベントを処理（新規追加・更新）"""
        for event in garoon_events:
            garoon_id = str(event.get("id"))
            
            if garoon_id in deleted_garoon_ids:
                continue
            
            garoon_updated = EventConverter.get_garoon_updated_at(event)
            mapping = self.db.get_mapping_by_garoon_id(garoon_id)
            
            if mapping:
                # 既存マッピングあり → 更新チェック
                google_id = mapping['google_id']
                google_event = google_by_id.get(google_id)
                
                if google_event:
                    # Garoonが更新されていたらGoogleを更新
                    if self._is_newer(garoon_updated, mapping.get('garoon_updated_at', '')):
                        self._update_google_from_garoon(event, google_id)
                else:
                    # Googleにない → 再作成
                    self._add_to_google(event)
            else:
                # 新規 → Googleに追加
                self._add_to_google(event)
    
    def _add_to_google(self, garoon_event):
        event_type = garoon_event.get("eventType", "REGULAR")
        title = EventConverter._get_garoon_title(garoon_event)
        
        # 繰り返し予定の場合はデバッグログを出力
        if event_type == "REPEATING":
            self.log(f"  📅 繰り返し予定処理中: {title}")
        
        google_data = EventConverter.garoon_to_google(garoon_event, log_func=self.log if event_type == "REPEATING" else None)
        if not google_data:
            self.log(f"  ⚠ 変換スキップ: {title}")
            return
        
        # 日付を取得
        event_date = self._get_event_date(google_data)
        
        result = self.google.create_event(google_data)
        if result:
            garoon_id = str(garoon_event.get("id"))
            google_id = result.get("id")
            garoon_updated = EventConverter.get_garoon_updated_at(garoon_event)
            google_updated = EventConverter.get_google_updated_at(result)
            
            self.db.add_mapping(garoon_id, google_id, garoon_updated, google_updated)
            
            # 繰り返し予定の場合は表示
            if event_type == "REPEATING":
                self.log(f"  ✓ 追加: [{event_date}] {google_data['summary']}（繰り返し）")
            else:
                self.log(f"  ✓ 追加: [{event_date}] {google_data['summary']}")
            self.stats['google_added'] += 1
        else:
            self.log(f"  ✗ 追加失敗: [{event_date}] {title}（{event_type}）")
            self.stats['errors'] += 1
    
    def _update_google_from_garoon(self, garoon_event, google_id):
        event_type = garoon_event.get("eventType", "REGULAR")
        google_data = EventConverter.garoon_to_google(garoon_event, log_func=self.log if event_type == "REPEATING" else None)
        if not google_data:
            return
        
        # 日付を取得
        event_date = self._get_event_date(google_data)
        
        result = self.google.update_event(google_id, google_data)
        if result:
            garoon_id = str(garoon_event.get("id"))
            garoon_updated = EventConverter.get_garoon_updated_at(garoon_event)
            google_updated = EventConverter.get_google_updated_at(result)
            
            self.db.update_mapping(garoon_id=garoon_id, garoon_updated=garoon_updated, google_updated=google_updated)
            self.log(f"  ↻ 更新: [{event_date}] {google_data['summary']}")
            self.stats['google_updated'] += 1
        else:
            self.stats['errors'] += 1
    
    def _is_newer(self, dt1: str, dt2: str) -> bool:
        if not dt1:
            return False
        if not dt2:
            return True
        try:
            t1 = datetime.fromisoformat(dt1.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(dt2.replace("Z", "+00:00"))
            return t1 > t2
        except:
            return False
    
    def _get_event_date(self, event_data: dict) -> str:
        """イベントデータから日付文字列を取得"""
        try:
            start = event_data.get('start', {})
            if 'date' in start:
                # 終日イベント
                return start['date']
            elif 'dateTime' in start:
                # 時間指定イベント
                dt_str = start['dateTime']
                # ISO形式から日付部分を抽出
                if 'T' in dt_str:
                    return dt_str.split('T')[0]
                return dt_str[:10]
        except:
            pass
        return "?"


# ============================================
# GUIアプリケーション
# ============================================
class SyncApp:
    
    # カラーテーマ
    COLORS = {
        'bg_dark': '#2C3E50',        # ダークブルー（背景）
        'bg_light': '#34495E',       # ライトダークブルー
        'accent': '#3498DB',         # ブルー（アクセント）
        'accent_hover': '#2980B9',   # ダークブルー（ホバー）
        'success': '#27AE60',        # グリーン（成功）
        'warning': '#F39C12',        # オレンジ（警告）
        'danger': '#E74C3C',         # レッド（エラー）
        'text_light': '#ECF0F1',     # ライトグレー（テキスト）
        'text_dark': '#2C3E50',      # ダーク（テキスト）
        'input_bg': '#FFFFFF',       # 白（入力欄）
        'frame_bg': '#ECF0F1',       # フレーム背景
    }
    
    def __init__(self, root):
        self.root = root
        self.root.title("Garoon → Google Calendar 同期ツール")
        self.root.geometry("650x950")
        self.root.resizable(True, True)
        self.root.configure(bg=self.COLORS['bg_dark'])
        
        self.config_manager = ConfigManager(CONFIG_FILE)
        self.config = self.config_manager.load()
        
        self.google_authenticated = False
        self.is_syncing = False
        
        self._setup_styles()
        self._create_widgets()
        self._load_config_to_ui()
        
        # 初期サッシュ位置を設定（ログ窓を広く）
        self.root.after(100, self._set_initial_sash_position)
    
    def _setup_styles(self):
        """カスタムスタイルを設定"""
        style = ttk.Style()
        
        # テーマ設定
        style.theme_use('clam')
        
        # フレームスタイル
        style.configure('Card.TFrame', background=self.COLORS['frame_bg'])
        style.configure('Dark.TFrame', background=self.COLORS['bg_dark'])
        
        # ラベルスタイル
        style.configure('Card.TLabel', 
                       background=self.COLORS['frame_bg'],
                       foreground=self.COLORS['text_dark'],
                       font=('Yu Gothic UI', 10))
        
        style.configure('Header.TLabel',
                       background=self.COLORS['frame_bg'],
                       foreground=self.COLORS['accent'],
                       font=('Yu Gothic UI', 11, 'bold'))
        
        style.configure('Title.TLabel',
                       background=self.COLORS['bg_dark'],
                       foreground=self.COLORS['text_light'],
                       font=('Yu Gothic UI', 16, 'bold'))
        
        style.configure('Status.TLabel',
                       background=self.COLORS['frame_bg'],
                       font=('Yu Gothic UI', 10, 'bold'))
        
        # ボタンスタイル
        style.configure('Accent.TButton',
                       background=self.COLORS['accent'],
                       foreground='white',
                       font=('Yu Gothic UI', 10, 'bold'),
                       padding=(15, 8))
        style.map('Accent.TButton',
                 background=[('active', self.COLORS['accent_hover'])])
        
        style.configure('Success.TButton',
                       background=self.COLORS['success'],
                       foreground='white',
                       font=('Yu Gothic UI', 11, 'bold'),
                       padding=(20, 10))
        style.map('Success.TButton',
                 background=[('active', '#229954')])
        
        style.configure('Danger.TButton',
                       background=self.COLORS['danger'],
                       foreground='white',
                       font=('Yu Gothic UI', 10),
                       padding=(10, 5))
        style.map('Danger.TButton',
                 background=[('active', '#C0392B')])
        
        style.configure('Secondary.TButton',
                       background='#95A5A6',
                       foreground='white',
                       font=('Yu Gothic UI', 10),
                       padding=(10, 5))
        
        # LabelFrameスタイル
        style.configure('Card.TLabelframe',
                       background=self.COLORS['frame_bg'],
                       foreground=self.COLORS['text_dark'])
        style.configure('Card.TLabelframe.Label',
                       background=self.COLORS['frame_bg'],
                       foreground=self.COLORS['accent'],
                       font=('Yu Gothic UI', 11, 'bold'))
        
        # エントリースタイル
        style.configure('TEntry',
                       fieldbackground=self.COLORS['input_bg'],
                       font=('Yu Gothic UI', 10))
        
        # チェックボタンスタイル
        style.configure('Card.TCheckbutton',
                       background=self.COLORS['frame_bg'],
                       foreground=self.COLORS['text_dark'],
                       font=('Yu Gothic UI', 9))
    
    def _create_widgets(self):
        # メインコンテナ
        main_container = ttk.Frame(self.root, style='Dark.TFrame')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # PanedWindow（上下分割・可変）
        self.paned = tk.PanedWindow(main_container, orient=tk.VERTICAL, 
                               bg=self.COLORS['bg_dark'],
                               sashwidth=8,
                               sashrelief=tk.RAISED,
                               sashpad=2)
        self.paned.pack(fill=tk.BOTH, expand=True)
        
        # === 上部ペイン（設定エリア）===
        upper_frame = ttk.Frame(self.paned, style='Dark.TFrame')
        self.paned.add(upper_frame, minsize=400)
        
        # タイトル
        title_frame = ttk.Frame(upper_frame, style='Dark.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(title_frame, 
                 text="📅 Garoon → Google Calendar",
                 style='Title.TLabel').pack(side=tk.LEFT)
        
        # === Garoon設定 ===
        garoon_frame = ttk.LabelFrame(upper_frame, text="🔐 Garoon設定", 
                                      style='Card.TLabelframe', padding="8")
        garoon_frame.pack(fill=tk.X, pady=(0, 5))
        
        # ユーザー名
        ttk.Label(garoon_frame, text="ユーザー名:", style='Card.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=3, padx=(0, 10))
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(garoon_frame, textvariable=self.username_var, width=35)
        username_entry.grid(row=0, column=1, sticky=tk.W, pady=3)
        
        # パスワード
        ttk.Label(garoon_frame, text="パスワード:", style='Card.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=3, padx=(0, 10))
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(garoon_frame, textvariable=self.password_var, width=35, show="●")
        password_entry.grid(row=1, column=1, sticky=tk.W, pady=3)
        
        # パスワード保存チェックと接続テストを同じ行に
        check_btn_frame = ttk.Frame(garoon_frame, style='Card.TFrame')
        check_btn_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=3)
        
        self.save_password_var = tk.BooleanVar()
        ttk.Checkbutton(check_btn_frame, text="パスワードを保存", 
                       variable=self.save_password_var,
                       style='Card.TCheckbutton').pack(side=tk.LEFT)
        
        ttk.Button(check_btn_frame, text="🔗 接続テスト", 
                  command=self._test_garoon,
                  style='Accent.TButton').pack(side=tk.LEFT, padx=(20, 0))
        
        # === Google設定 ===
        google_frame = ttk.LabelFrame(upper_frame, text="🌐 Google Calendar設定",
                                      style='Card.TLabelframe', padding="8")
        google_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 認証状態と認証ボタンを1行に
        auth_row = ttk.Frame(google_frame, style='Card.TFrame')
        auth_row.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=3)
        
        ttk.Label(auth_row, text="認証状態:", style='Card.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        self.google_status_var = tk.StringVar(value="❌ 未認証")
        self.status_label = ttk.Label(auth_row, textvariable=self.google_status_var, style='Status.TLabel')
        self.status_label.pack(side=tk.LEFT)
        
        self.auth_button = ttk.Button(auth_row, text="🔑 Google認証",
                                      command=self._auth_google,
                                      style='Accent.TButton')
        self.auth_button.pack(side=tk.LEFT, padx=(15, 0))
        
        ttk.Label(auth_row, text="※初回のみ", 
                 style='Card.TLabel', foreground='#7F8C8D').pack(side=tk.LEFT, padx=(10, 0))
        
        # カレンダー選択
        cal_row = ttk.Frame(google_frame, style='Card.TFrame')
        cal_row.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=3)
        
        ttk.Label(cal_row, text="カレンダー:", style='Card.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        self.calendar_var = tk.StringVar()
        self.calendar_combo = ttk.Combobox(cal_row, textvariable=self.calendar_var, 
                                           width=30, state="readonly")
        self.calendar_combo.pack(side=tk.LEFT)
        
        ttk.Button(cal_row, text="🔄", command=self._refresh_calendars,
                  width=3).pack(side=tk.LEFT, padx=5)
        
        # === 同期設定 ===
        sync_frame = ttk.LabelFrame(upper_frame, text="⚙️ 同期設定",
                                    style='Card.TLabelframe', padding="10")
        sync_frame.pack(fill=tk.X, pady=(0, 8))
        
        # 期間設定行
        period_frame = ttk.Frame(sync_frame, style='Card.TFrame')
        period_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(period_frame, text="同期期間:", style='Card.TLabel').pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(period_frame, text="過去", style='Card.TLabel').pack(side=tk.LEFT)
        self.past_days_var = tk.StringVar()
        past_entry = ttk.Entry(period_frame, textvariable=self.past_days_var, width=6)
        past_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(period_frame, text="日前  ～  未来", style='Card.TLabel').pack(side=tk.LEFT)
        self.future_days_var = tk.StringVar()
        future_entry = ttk.Entry(period_frame, textvariable=self.future_days_var, width=6)
        future_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(period_frame, text="日後", style='Card.TLabel').pack(side=tk.LEFT)
        
        # === 実行ボタンエリア（同期設定とログの間）===
        button_frame = ttk.Frame(upper_frame, style='Dark.TFrame')
        button_frame.pack(fill=tk.X, pady=(10, 10))
        
        # 同期実行ボタン（大きめ・緑）
        self.sync_button = ttk.Button(button_frame, text="▶ 同期実行",
                                      command=self._run_sync,
                                      style='Success.TButton')
        self.sync_button.pack(side=tk.LEFT, padx=5)
        
        # 設定保存ボタン
        ttk.Button(button_frame, text="💾 設定を保存",
                  command=self._save_config,
                  style='Secondary.TButton').pack(side=tk.LEFT, padx=5)
        
        # 終了ボタン（右端・赤）
        ttk.Button(button_frame, text="✕ 終了",
                  command=self._quit_app,
                  style='Danger.TButton').pack(side=tk.RIGHT, padx=5)
        
        # === 下部ペイン（ログエリア）===
        lower_frame = ttk.Frame(self.paned, style='Dark.TFrame')
        self.paned.add(lower_frame, minsize=150)
        
        # ログ表示
        log_frame = ttk.LabelFrame(lower_frame, text="📋 ログ（境界線をドラッグでサイズ変更）",
                                   style='Card.TLabelframe', padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # ログテキスト（カスタムカラー）
        self.log_text = scrolledtext.ScrolledText(
            log_frame, 
            state=tk.DISABLED,
            bg='#1E272E',
            fg='#D5D8DC',
            font=('Consolas', 9),
            insertbackground='white',
            selectbackground=self.COLORS['accent']
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # ログクリアボタン
        ttk.Button(log_frame, text="🗑 ログをクリア", 
                  command=self._clear_log).pack(anchor=tk.E, pady=5)
    
    def _set_initial_sash_position(self):
        """初期サッシュ位置を設定"""
        try:
            # ウィンドウの高さの55%の位置にサッシュを配置（上部を広く）
            height = self.paned.winfo_height()
            if height > 1:
                self.paned.sash_place(0, 0, int(height * 0.55))
        except:
            pass
    
    def _load_config_to_ui(self):
        """設定をUIに反映"""
        self.username_var.set(self.config.get("garoon_username", ""))
        self.password_var.set(self.config.get("garoon_password", ""))
        self.save_password_var.set(self.config.get("save_password", False))
        self.calendar_var.set(self.config.get("calendar_name", "Garoon"))
        self.past_days_var.set(str(self.config.get("past_days", 7)))
        self.future_days_var.set(str(self.config.get("future_days", 90)))
        
        # Google認証状態を確認・自動リフレッシュ
        self._check_google_auth()
    
    def _check_google_auth(self):
        """Google認証状態を確認・自動リフレッシュ"""
        if not os.path.exists(TOKEN_FILE):
            self.google_authenticated = False
            self.google_status_var.set("❌ 未認証")
            self.auth_button.config(text="🔑 Google認証")
            return
        
        try:
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)
            
            if creds and creds.valid:
                # 有効なトークンがある
                self.google_authenticated = True
                self.google_status_var.set("✅ 認証済み")
                self.auth_button.config(text="🔄 再認証")
                self._refresh_calendars()
            elif creds and creds.expired and creds.refresh_token:
                # 期限切れだがリフレッシュ可能
                try:
                    creds.refresh(Request())
                    with open(TOKEN_FILE, "wb") as f:
                        pickle.dump(creds, f)
                    self.google_authenticated = True
                    self.google_status_var.set("✅ 認証済み")
                    self.auth_button.config(text="🔄 再認証")
                    self._refresh_calendars()
                except Exception as e:
                    # リフレッシュ失敗
                    self.google_authenticated = False
                    self.google_status_var.set("⚠️ 要再認証")
                    self.auth_button.config(text="🔑 Google認証")
            else:
                self.google_authenticated = False
                self.google_status_var.set("⚠️ 要再認証")
                self.auth_button.config(text="🔑 Google認証")
        except Exception:
            self.google_authenticated = False
            self.google_status_var.set("❌ 未認証")
            self.auth_button.config(text="🔑 Google認証")
    
    def _save_config(self):
        """設定を保存"""
        self.config["garoon_username"] = self.username_var.get()
        self.config["garoon_password"] = self.password_var.get()
        self.config["save_password"] = self.save_password_var.get()
        self.config["calendar_name"] = self.calendar_var.get()
        
        try:
            self.config["past_days"] = int(self.past_days_var.get())
            self.config["future_days"] = int(self.future_days_var.get())
        except ValueError:
            messagebox.showerror("エラー", "同期期間は数値で入力してください")
            return
        
        self.config_manager.save(self.config)
        messagebox.showinfo("保存完了", "設定を保存しました")
    
    def _log(self, message: str):
        """ログを追加"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update()
    
    def _clear_log(self):
        """ログをクリア"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _test_garoon(self):
        """Garoon接続テスト"""
        username = self.username_var.get()
        password = self.password_var.get()
        
        if not username or not password:
            messagebox.showerror("エラー", "Garoonの設定を入力してください")
            return
        
        self._log("🔗 Garoon接続テスト中...")
        
        try:
            client = GaroonClient(GAROON_SUBDOMAIN, username, password)
            success, message = client.test_connection()
            
            if success:
                self._log(f"✅ {message}")
                messagebox.showinfo("成功", "Garoonに接続できました")
            else:
                self._log(f"❌ {message}")
                messagebox.showerror("エラー", message)
        except Exception as e:
            self._log(f"❌ エラー: {e}")
            messagebox.showerror("エラー", str(e))
    
    def _auth_google(self):
        """Google認証"""
        if not os.path.exists(CREDENTIALS_FILE):
            messagebox.showerror("エラー", "credentials.json が見つかりません\n\nGoogle Cloud Consoleから取得してください")
            return
        
        self._log("🔑 Google認証中...")
        
        try:
            # 既存のトークンを削除して再認証
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)
            
            self.google_authenticated = True
            self.google_status_var.set("✅ 認証済み")
            self.auth_button.config(text="🔄 再認証")
            self._log("✅ Google認証完了")
            self._refresh_calendars()
            
        except Exception as e:
            self._log(f"❌ 認証エラー: {e}")
            messagebox.showerror("エラー", f"認証に失敗しました\n{e}")
    
    def _refresh_calendars(self):
        """カレンダー一覧を更新"""
        if not self.google_authenticated:
            return
        
        try:
            # 一時的にサービスを作成
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)
            service = build('calendar', 'v3', credentials=creds)
            calendars = service.calendarList().list().execute()
            calendar_names = [cal['summary'] for cal in calendars.get('items', [])]
            
            self.calendar_combo['values'] = calendar_names
            
            # 現在の選択が一覧にあれば維持
            current = self.calendar_var.get()
            if current not in calendar_names and calendar_names:
                self.calendar_var.set(calendar_names[0])
                
        except Exception as e:
            self._log(f"カレンダー取得エラー: {e}")
    
    def _run_sync(self):
        """同期実行"""
        if self.is_syncing:
            return
        
        # バリデーション
        if not self.username_var.get() or not self.password_var.get():
            messagebox.showerror("エラー", "Garoonの設定を入力してください")
            return
        
        if not self.google_authenticated:
            messagebox.showerror("エラー", "Google認証を行ってください")
            return
        
        if not self.calendar_var.get():
            messagebox.showerror("エラー", "カレンダーを選択してください")
            return
        
        try:
            past_days = int(self.past_days_var.get())
            future_days = int(self.future_days_var.get())
        except ValueError:
            messagebox.showerror("エラー", "同期期間は数値で入力してください")
            return
        
        # 同期実行（別スレッド）
        self.is_syncing = True
        self.sync_button.config(state=tk.DISABLED)
        
        thread = threading.Thread(target=self._sync_thread, args=(past_days, future_days))
        thread.start()
    
    def _sync_thread(self, past_days: int, future_days: int):
        """同期処理（別スレッド）"""
        try:
            # 日付範囲を計算
            today = datetime.now().date()
            start_date = (today - timedelta(days=past_days)).strftime("%Y-%m-%d")
            end_date = (today + timedelta(days=future_days)).strftime("%Y-%m-%d")
            
            self._log("=" * 50)
            self._log("🚀 同期開始")
            self._log(f"📅 期間: {start_date} ～ {end_date}")
            self._log("=" * 50)
            
            # クライアント初期化
            garoon = GaroonClient(
                GAROON_SUBDOMAIN,
                self.username_var.get(),
                self.password_var.get()
            )
            
            google = GoogleCalendarClient(self.calendar_var.get())
            
            db = SyncDatabase(DB_FILE)
            
            # 同期実行
            sync_engine = GaroonToGoogleSync(garoon, google, db, self._log)
            stats = sync_engine.sync(start_date, end_date)
            
            db.close()
            
            # 結果表示
            self._log("\n" + "=" * 50)
            self._log("🎉 【完了】")
            self._log(f"  ➕ 追加: {stats['google_added']}件")
            self._log(f"  🔄 更新: {stats['google_updated']}件")
            self._log(f"  🗑️ 削除: {stats['google_deleted']}件")
            if stats['errors'] > 0:
                self._log(f"  ⚠️ エラー: {stats['errors']}件")
            self._log("=" * 50)
            
            self.root.after(0, lambda: messagebox.showinfo("完了", "同期が完了しました"))
            
        except Exception as e:
            self._log(f"\n❌ エラー: {e}")
            self.root.after(0, lambda: messagebox.showerror("エラー", str(e)))
        
        finally:
            self.is_syncing = False
            self.root.after(0, lambda: self.sync_button.config(state=tk.NORMAL))
    
    def _quit_app(self):
        """アプリケーションを終了"""
        if self.is_syncing:
            if not messagebox.askyesno("確認", "同期中です。終了しますか？"):
                return
        self.root.quit()
        self.root.destroy()


# ============================================
# メイン
# ============================================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Garoon → Google Calendar 同期ツール')
    parser.add_argument('--auto', action='store_true', help='自動同期モード（GUIなし）')
    parser.add_argument('--silent', action='store_true', help='サイレントモード（ログファイルのみ）')
    args = parser.parse_args()
    
    if args.auto:
        # 自動同期モード（GUIなし）
        run_auto_sync(silent=args.silent)
    else:
        # 通常GUIモード
        root = tk.Tk()
        app = SyncApp(root)
        root.mainloop()


def run_auto_sync(silent=False):
    """自動同期モード（タスクスケジューラ用）"""
    log_file = os.path.join(APP_DIR, "sync_log.txt")
    
    def log(message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        if not silent:
            print(log_line)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    
    try:
        log("=" * 50)
        log("🚀 自動同期開始")
        
        # 設定を読み込み
        config_manager = ConfigManager(CONFIG_FILE)
        config = config_manager.load()
        
        username = config.get("garoon_username", "")
        password = config.get("garoon_password", "")
        calendar_name = config.get("calendar_name", "")  # GUIと同じキー名
        past_days = config.get("past_days", 7)
        future_days = config.get("future_days", 90)
        
        if not username or not password:
            log("❌ エラー: Garoon設定がありません。GUIで設定を保存してください。")
            return 1
        
        if not calendar_name:
            log("❌ エラー: Googleカレンダーが設定されていません。GUIで設定を保存してください。")
            return 1
        
        if not os.path.exists(TOKEN_FILE):
            log("❌ エラー: Google認証がされていません。GUIで認証してください。")
            return 1
        
        # 日付範囲を計算
        today = datetime.now().date()
        start_date = (today - timedelta(days=past_days)).strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=future_days)).strftime("%Y-%m-%d")
        
        log(f"📅 期間: {start_date} ～ {end_date}")
        
        # クライアント初期化
        garoon = GaroonClient(GAROON_SUBDOMAIN, username, password)
        google = GoogleCalendarClient(calendar_name)
        db = SyncDatabase(DB_FILE)
        
        # 同期実行
        sync_engine = GaroonToGoogleSync(garoon, google, db, log)
        stats = sync_engine.sync(start_date, end_date)
        
        db.close()
        
        # 結果表示
        log("=" * 50)
        log("🎉 【完了】")
        log(f"  ➕ 追加: {stats['google_added']}件")
        log(f"  🔄 更新: {stats['google_updated']}件")
        log(f"  🗑️ 削除: {stats['google_deleted']}件")
        if stats['errors'] > 0:
            log(f"  ⚠️ エラー: {stats['errors']}件")
        log("=" * 50)
        
        return 0
        
    except Exception as e:
        log(f"❌ エラー: {e}")
        return 1


if __name__ == "__main__":
    main()
