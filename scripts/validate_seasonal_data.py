import json
import os
import sys
import re
from datetime import datetime

def check_secret(val):
    if not isinstance(val, str):
        return False
    
    # Google API Key
    google_key = r"AIza[0-9A-Za-z-_]{35}"
    if re.search(google_key, val):
        return True
    
    # Generic Secret Patterns (API key, token, secret, password)
    patterns = [
        r"(?i)api[-_]?key",
        r"(?i)secret",
        r"(?i)token",
        r"(?i)password",
    ]
    
    # High entropy strings longer than 40 chars
    if len(val) > 40 and re.match(r"^[A-Za-z0-9+/=_-]+$", val):
        for p in patterns:
            if re.search(p, val):
                return True
    return False

def validate():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    json_path = os.path.join(data_dir, "seasonal_data_v1.json")
    report_path = os.path.join(data_dir, "update_report.json")
    
    errors = []
    warnings_list = []
    
    if not os.path.exists(json_path):
        print(f"Error: {json_path} does not exist.")
        sys.exit(1)
        
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        sys.exit(1)
        
    # 基本構成チェック
    if "dataVersion" not in data:
        errors.append("Missing 'dataVersion' in root.")
    if "generatedAt" not in data:
        errors.append("Missing 'generatedAt' in root.")
    if "items" not in data or not isinstance(data["items"], list):
        errors.append("'items' is missing or not a list.")
        
    items = data.get("items", [])
    seen_ids = set()
    category_counts = {}
    status_counts = {}
    checking_count = 0
    
    allowed_categories = {"NATURE", "EVENT", "ASTRONOMY", "SEASONAL_CUSTOM"}
    allowed_statuses = {
        "UPCOMING", "PEAK_SOON", "BEST_SEASON", "ONGOING", 
        "PAST_PEAK", "ENDED", "CHECKING", "CANCELLED_OR_CHANGED"
    }
    
    for i, item in enumerate(items):
        item_id = item.get("id", f"index_{i}")
        
        # ID重複
        if item_id in seen_ids:
            errors.append(f"Duplicate item ID: '{item_id}'")
        seen_ids.add(item_id)

        # Androidアプリ側の必須プロパティチェック
        required_fields = [
            "id", "title", "category", "subCategory", "tags", "dateInfo", 
            "location", "commonStatus", "categoryStatus", "description", 
            "recommendationReason", "rarityLabel", "imageUrl", "sources", 
            "warnings", "notificationMeta", "toriComment", "updatedAt", "lastVerifiedAt"
        ]
        for field in required_fields:
            if field not in item:
                errors.append(f"Item '{item_id}' misses required field: '{field}'")

        # dateInfo の必須チェック
        if "dateInfo" in item and isinstance(item["dateInfo"], dict):
            di = item["dateInfo"]
            for f in ["startLocalDate", "endLocalDate", "displayDate"]:
                if f not in di:
                    errors.append(f"Item '{item_id}' misses dateInfo field: '{f}'")

        # location の必須チェック
        if "location" in item and isinstance(item["location"], dict):
            loc = item["location"]
            for f in ["prefecture", "areaName", "latitude", "longitude"]:
                if f not in loc:
                    errors.append(f"Item '{item_id}' misses location field: '{f}'")

        # sources の必須チェック
        if "sources" in item and isinstance(item["sources"], list):
            for s_idx, src in enumerate(item["sources"]):
                for f in ["name", "url", "sourceType", "lastVerifiedAt", "certaintyLabel", "isPrimary"]:
                    if f not in src:
                        errors.append(f"Source {s_idx} in Item '{item_id}' misses field: '{f}'")

        # warnings の必須チェック
        if "warnings" in item and isinstance(item["warnings"], list):
            for w_idx, w in enumerate(item["warnings"]):
                for f in ["label", "severity", "message"]:
                    if f not in w:
                        errors.append(f"Warning {w_idx} in Item '{item_id}' misses field: '{f}'")

        # notificationMeta の必須チェック
        if "notificationMeta" in item and isinstance(item["notificationMeta"], dict):
            nm = item["notificationMeta"]
            for f in ["notifyEnabled", "notificationTitle", "notificationBodyTemplate", "priority", "targetRegions"]:
                if f not in nm:
                    errors.append(f"Item '{item_id}' misses notificationMeta field: '{f}'")
        
        # タイトル
        title = item.get("title")
        if not title:
            errors.append(f"Item '{item_id}' has empty title.")
            
        # カテゴリ
        cat = item.get("category")
        if cat not in allowed_categories:
            errors.append(f"Item '{item_id}' has invalid category: '{cat}'")
        else:
            category_counts[cat] = category_counts.get(cat, 0) + 1
            
        # サブカテゴリ
        sub_cat = item.get("subCategory")
        if not sub_cat:
            errors.append(f"Item '{item_id}' has empty subCategory.")
            
        # ステータス
        status = item.get("commonStatus")
        if status not in allowed_statuses:
            errors.append(f"Item '{item_id}' has invalid commonStatus: '{status}'")
        else:
            status_counts[status] = status_counts.get(status, 0) + 1
            if status == "CHECKING":
                checking_count += 1
                
        # 日付情報
        date_info = item.get("dateInfo", {})
        if not date_info.get("displayText") and not date_info.get("displayDate"):
            errors.append(f"Item '{item_id}' misses both dateInfo.displayText and dateInfo.displayDate.")
            
        # 位置情報
        loc = item.get("location", {})
        if not loc.get("displayText") and not loc.get("prefecture") and not loc.get("region"):
            errors.append(f"Item '{item_id}' misses location.displayText/prefecture/region.")
            
        # 出典
        sources = item.get("sources", [])
        if not isinstance(sources, list) or len(sources) == 0:
            errors.append(f"Item '{item_id}' must have at least one source.")
        else:
            for s_idx, src in enumerate(sources):
                if not src.get("url"):
                    errors.append(f"Source {s_idx} in Item '{item_id}' misses URL.")
                    
        # 最終確認日
        last_verified = item.get("lastVerifiedAt")
        if not last_verified:
            # sources 内に lastVerifiedAt があるかチェック
            has_ver = any(src.get("lastVerifiedAt") for src in sources)
            if not has_ver:
                errors.append(f"Item '{item_id}' misses lastVerifiedAt in root and all sources.")
                
        # CHECKINGの制約
        if status == "CHECKING":
            # certaintyLabel
            has_checking_label = False
            for src in sources:
                label = src.get("certaintyLabel", "")
                if any(w in label for w in ["確認中", "公式発表待ち", "未発表", "情報確認中", "順次確認"]):
                    has_checking_label = True
            if not has_checking_label:
                warnings_list.append(f"Item '{item_id}' is CHECKING but certaintyLabel does not mention '確認中' or '公式発表待ち' etc.")
                
            # notifyEnabled/priority
            notif = item.get("notificationMeta", {})
            if notif.get("notifyEnabled", False) is True:
                priority = notif.get("priority", 3)
                if priority > 1:
                    warnings_list.append(f"Item '{item_id}' is CHECKING but has notifyEnabled=true and high priority={priority}.")
                    
        # CANCELLED_OR_CHANGEDの制約
        if status == "CANCELLED_OR_CHANGED":
            warnings = item.get("warnings", [])
            has_high_severity = any(w.get("severity") == "high" for w in warnings)
            if not has_high_severity:
                warnings_list.append(f"Item '{item_id}' is CANCELLED_OR_CHANGED but misses a high severity warning.")
                
        # シークレット・APIキーのチェック
        for k, v in item.items():
            if check_secret(v):
                errors.append(f"Possible API Key/Secret detected in item '{item_id}' field '{k}': {v}")
            if isinstance(v, dict):
                for sk, sv in v.items():
                    if check_secret(sv):
                        errors.append(f"Possible API Key/Secret detected in item '{item_id}' field '{k}.{sk}': {sv}")
            elif isinstance(v, list):
                for idx, entry in enumerate(v):
                    if isinstance(entry, dict):
                        for sk, sv in entry.items():
                            if check_secret(sv):
                                errors.append(f"Possible API Key/Secret detected in item '{item_id}' field '{k}[{idx}].{sk}': {sv}")
                                
    # レポート作成
    success = len(errors) == 0
    report = {
        "validationSuccess": success,
        "validationErrors": errors,
        "validationWarnings": warnings_list,
        "runAt": datetime.now().isoformat(),
        "summary": {
            "dataVersion": data.get("dataVersion", "unknown"),
            "generatedAt": data.get("generatedAt", "unknown"),
            "schemaVersion": data.get("schemaVersion", "unknown"),
            "totalItems": len(items),
            "categoryCounts": category_counts,
            "statusCounts": status_counts,
            "checkingCount": checking_count
        }
    }
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing report: {e}")
        
    # 結果出力
    if not success:
        print("=== Validation Failed ===")
        for err in errors:
            print(f"- {err}")
        print(f"Total Errors: {len(errors)}")
        sys.exit(1)
        
    print("=== Validation Success ===")
    print(f"Checked {len(items)} items.")
    if warnings_list:
        print(f"Warnings ({len(warnings_list)}):")
        for warn in warnings_list:
            print(f"- {warn}")
    sys.exit(0)

if __name__ == "__main__":
    validate()
