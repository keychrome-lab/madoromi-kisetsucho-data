import json
import os
import sys
from datetime import datetime
import subprocess

# 二十四節気等の計算テーブル（2025〜2030年）
CALENDAR_TABLE = {
    2025: {"setsubun": "02-02", "summer_solstice": "06-21", "winter_solstice": "12-22"},
    2026: {"setsubun": "02-03", "summer_solstice": "06-21", "winter_solstice": "12-22"},
    2027: {"setsubun": "02-03", "summer_solstice": "06-22", "winter_solstice": "12-22"},
    2028: {"setsubun": "02-03", "summer_solstice": "06-21", "winter_solstice": "12-21"},
    2029: {"setsubun": "02-02", "summer_solstice": "06-21", "winter_solstice": "12-21"},
    2030: {"setsubun": "02-03", "summer_solstice": "06-21", "winter_solstice": "12-22"},
}

def update_date_string(date_str, target_year):
    if not date_str:
        return date_str
    try:
        parts = date_str.split("-")
        if len(parts) == 3:
            return f"{target_year:04d}-{parts[1]}-{parts[2]}"
    except Exception:
        pass
    return date_str

def run_update():
    scripts_dir = os.path.dirname(__file__)
    data_dir = os.path.join(os.path.dirname(scripts_dir), "data")
    json_path = os.path.join(data_dir, "seasonal_data_v1.json")
    tmp_path = os.path.join(data_dir, "seasonal_data_v1.tmp.json")
    
    if not os.path.exists(json_path):
        print(f"Error: {json_path} does not exist.")
        sys.exit(1)
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    current_time = datetime.now()
    current_year = current_time.year
    
    # 1. バージョンの更新 (日付ベース + 連番)
    prev_version = data.get("dataVersion", "2026.05.01-000")
    today_version_prefix = current_time.strftime("%Y.%m.%d")
    
    if prev_version.startswith(today_version_prefix):
        try:
            seq = int(prev_version.split("-")[-1]) + 1
        except Exception:
            seq = 1
        new_version = f"{today_version_prefix}-{seq:03d}"
    else:
        new_version = f"{today_version_prefix}-001"
        
    data["dataVersion"] = new_version
    data["generatedAt"] = current_time.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    
    items = data.get("items", [])
    updated_count = 0
    ended_count = 0
    warnings = []
    
    # 2. 各アイテムの更新・終了判定
    for item in items:
        item_id = item.get("id")
        sub_cat = item.get("subCategory")
        status = item.get("commonStatus")
        
        # 毎年固定の季節行事/天文の自動日付更新
        is_fixed = False
        fixed_month_day = None
        
        if sub_cat == "childrens_day":
            is_fixed = True
            fixed_month_day = "05-05"
        elif sub_cat == "tanabata":
            is_fixed = True
            fixed_month_day = "07-07"
        elif sub_cat == "first_sunrise":
            is_fixed = True
            fixed_month_day = "01-01"
        elif sub_cat == "setsubun" and current_year in CALENDAR_TABLE:
            is_fixed = True
            fixed_month_day = CALENDAR_TABLE[current_year]["setsubun"]
        elif sub_cat == "summer_solstice" and current_year in CALENDAR_TABLE:
            is_fixed = True
            fixed_month_day = CALENDAR_TABLE[current_year]["summer_solstice"]
        elif sub_cat == "winter_solstice" and current_year in CALENDAR_TABLE:
            is_fixed = True
            fixed_month_day = CALENDAR_TABLE[current_year]["winter_solstice"]
            
        if is_fixed and fixed_month_day:
            target_date = f"{current_year}-{fixed_month_day}"
            date_info = item.get("dateInfo", {})
            if date_info.get("startLocalDate") != target_date:
                date_info["startLocalDate"] = target_date
                date_info["endLocalDate"] = target_date
                if "startDate" in date_info:
                    date_info["startDate"] = target_date
                if "endDate" in date_info:
                    date_info["endDate"] = target_date
                
                # notificationMeta の日付も西暦を更新
                notif = item.get("notificationMeta", {})
                if "advanceNotifyDate" in notif:
                    notif["advanceNotifyDate"] = update_date_string(notif["advanceNotifyDate"], current_year)
                if "lastMinuteNotifyDate" in notif:
                    notif["lastMinuteNotifyDate"] = update_date_string(notif["lastMinuteNotifyDate"], current_year)
                
                item["updatedAt"] = current_time.strftime("%Y-%m-%dT%H:%M:%S+09:00")
                updated_count += 1
                
        # 過去日付のイベントの自動ステータス更新
        end_date_str = item.get("dateInfo", {}).get("endLocalDate")
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                if end_date < current_time.date():
                    if status not in ["ENDED", "CHECKING", "CANCELLED_OR_CHANGED"]:
                        item["commonStatus"] = "ENDED"
                        item["categoryStatus"] = "ended"
                        item["updatedAt"] = current_time.strftime("%Y-%m-%dT%H:%M:%S+09:00")
                        ended_count += 1
                        warnings.append(f"Auto-transitioned item '{item_id}' to ENDED because its endDate ({end_date_str}) has passed.")
            except Exception as e:
                warnings.append(f"Error checking date for item '{item_id}': {e}")
                
    # 一時ファイルへの保存
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print("Temporary file written. Validating...")
    
    # 安全に本番と置き換えて検証
    backup_path = json_path + ".bak"
    if os.path.exists(json_path):
        os.rename(json_path, backup_path)
    os.rename(tmp_path, json_path)
    
    validate_script = os.path.join(scripts_dir, "validate_seasonal_data.py")
    
    try:
        res = subprocess.run([sys.executable, validate_script], capture_output=True, text=True)
        if res.returncode == 0:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            print("=== Update Successful ===")
            print(f"DataVersion: {new_version}")
            print(f"Updated fixed events: {updated_count}")
            print(f"Transitioned to ENDED: {ended_count}")
            if warnings:
                print("Warnings:")
                for w in warnings:
                    print(f"- {w}")
        else:
            print("Validation FAILED. Rolling back changes...")
            print(res.stdout)
            print(res.stderr)
            if os.path.exists(json_path):
                os.remove(json_path)
            os.rename(backup_path, json_path)
            sys.exit(1)
            
    except Exception as e:
        print(f"Unexpected error during validation/commit: {e}")
        if os.path.exists(backup_path):
            if os.path.exists(json_path):
                os.remove(json_path)
            os.rename(backup_path, json_path)
        sys.exit(1)

if __name__ == "__main__":
    run_update()
