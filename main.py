import os
import sys
import json
import urllib.request
import ssl  # SSL証明書エラーを回避するために追加

# 定数定義
GDMF_URL = "https://gdmf.apple.com/v2/pmv"
CACHE_FILE = "last_macOS_version.txt"

# GitHub Secretsから環境変数を取得
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")

if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
    print("Error: SLACK_BOT_TOKEN or SLACK_CHANNEL_ID is not set.")
    sys.exit(1)

def get_latest_macos_versions():
    """AppleのAPIからmacOSの最新バージョン情報を取得し、
    全体の中で『最新のメジャーバージョン』のみを返す"""
    req = urllib.request.Request(GDMF_URL)
    
    # ─── SSL/TLS証明書の検証を完全に無視する設定 ───
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # ──────────────────────────────────────────────
    
    try:
        # urlopenに context=ctx を渡してSSLエラーを回避
        with urllib.request.urlopen(req, context=ctx) as response:
            data = json.loads(response.read().decode())
            
        macos_assets = data.get("PublicAssetSets", {}).get("macOS", [])
        
        # 全データから、もっとも大きなメジャーバージョン番号を特定する
        max_major_num = 0
        all_latest_versions = {}
        
        for asset in macos_assets:
            product_version = asset.get("ProductVersion")
            build = asset.get("Build")
            posting_date = asset.get("PostingDate")
            
            if not product_version:
                continue
                
            major_version_str = product_version.split('.')[0]
            major_version_num = int(major_version_str)
            version_tuple = tuple(map(int, product_version.split('.')))
            
            # 最大のメジャーバージョン番号（例: 15や16など）を更新
            if major_version_num > max_major_num:
                max_major_num = major_version_num
            
            # メジャーバージョンごとの最新を一時保持
            current_latest = all_latest_versions.get(major_version_str)
            if not current_latest or version_tuple > current_latest["tuple"]:
                all_latest_versions[major_version_str] = {
                    "version": product_version,
                    "build": build,
                    "date": posting_date,
                    "tuple": version_tuple
                }
                
        # 特定した「最大（最新）のメジャーバージョン」のデータだけを抽出して辞書にする
        latest_major_str = str(max_major_num)
        if latest_major_str in all_latest_versions:
            v = all_latest_versions[latest_major_str]
            return {
                "version": v["version"],
                "build": v["build"],
                "date": v["date"]
            }
        
        return {}
        
    except Exception as e:
        print(f"Failed to fetch or parse Apple PMV data: {e}")
        sys.exit(1)

def send_slack_notification(message):
    """Slack Web API (chat.postMessage) を使って通知する"""
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": SLACK_CHANNEL_ID,
        "text": message
    }
    
    # Slack側へのリクエスト送信でも同様にSSLエラーを無視する設定を適用
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res_data = json.loads(response.read().decode())
            if not res_data.get("ok"):
                print(f"Slack API Error: {res_data.get('error')}")
            else:
                print("Slack notification sent successfully.")
    except Exception as e:
        print(f"Failed to send Slack notification: {e}")

def main():
    # print("Fetching latest macOS version from Apple...")
    latest_version = get_latest_macos_versions()
    print(f"latest_version = {latest_version}")
    # バージョン情報が空の場合は終了
    if not latest_version:
        print("No macOS data found.")
        return

    past_version = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                past_version = json.load(f)
            print("Loaded past versions from cache.")
        except Exception:
            print("Failed to load cache, treating as first run.")

    new_updates = False
    if not past_version:
        new_updates = True
    
    if latest_version["version"] != past_version["version"]:
        new_updates = True

    if new_updates:
        print("New latest major OS update detected!")
        message = "*macOSの更新を検知しました*\n\n" + "Version: " + latest_version["version"] + "\nRelease date: " + latest_version["date"]
        send_slack_notification(message)
    else:
        print("No new updates for the latest major OS.")

    # キャッシュを更新して保存
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(latest_version, f, indent=2)
        print("Cache updated.")
    except Exception as e:
        print(f"Failed to save cache: {e}")

if __name__ == "__main__":
    main()