from flask import Flask, request, jsonify
from datetime import datetime, timedelta, time
from dateutil import parser
import requests
import os

app = Flask(__name__)

# --- Config ---
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

# Custom field IDs (оновлені)
FIELD_START_TIME = "customfield_10752"
FIELD_END_TIME = "customfield_10753"
FIELD_ITERATION_COUNT = "customfield_10751"
FIELD_CURRENT_DURATION = "customfield_10754"
FIELD_TOTAL_DURATION = "customfield_10755"
FIELD_AVG_DURATION = "customfield_10756"

# === Розрахунок: до 14:00 = 0.5, після 14:00 = 1.0 дня ===
def calculate_iteration_days(start_time: datetime, end_time: datetime) -> float:
    total_days = 0.0
    current = start_time

    while current.date() <= end_time.date():
        is_weekend = current.weekday() >= 5
        day_start = datetime.combine(current.date(), time(0, 0), tzinfo=start_time.tzinfo)
        day_mid = datetime.combine(current.date(), time(14, 0), tzinfo=start_time.tzinfo)
        day_end = datetime.combine(current.date(), time(23, 59), tzinfo=start_time.tzinfo)

        if not is_weekend:
            interval_start = max(start_time, day_start)
            interval_end = min(end_time, day_end)

            if interval_end <= interval_start:
                counted = 0.0
            elif interval_end <= day_mid:
                counted = 0.5
            else:
                counted = 1.0

            total_days += counted
            print(f"📅 {current.date()} → {counted} днів")

        current += timedelta(days=1)

    return round(total_days, 2)

@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.json
    issue_key = data["issue"]["key"]
    fields = data["issue"]["fields"]

    start_str = fields.get(FIELD_START_TIME)
    end_str = fields.get(FIELD_END_TIME)
    current_total = float(fields.get(FIELD_TOTAL_DURATION) or 0)
    iteration_count = float(fields.get(FIELD_ITERATION_COUNT) or 1)

    print("Raw Start:", start_str)
    print("Raw End:", end_str)

    print("🧪 DEBUG START")
    print("Start (raw):", repr(fields.get(FIELD_START_TIME)))
    print("End   (raw):", repr(fields.get(FIELD_END_TIME)))
    print("🧪 DEBUG END")

    if not start_str or not end_str:
        return jsonify({"error": "Missing start or end time"}), 400

    try:
        start_time = parser.parse(start_str)
        end_time = parser.parse(end_str)
        print("Parsed Start:", start_time)
        print("Parsed End:", end_time)
    except Exception as e:
        return jsonify({"error": "Date parsing failed", "details": str(e)}), 400

    # 1. Обчислення поточної ітерації
    current_duration = calculate_iteration_days(start_time, end_time)

    # 2. Обчислення нової загальної тривалості
    new_total = round(current_total + current_duration, 2)

    # 3. Обчислення середньої тривалості
    avg_duration = round((new_total / iteration_count) * 2) / 2

    # Підготовка оновлення в Jira
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    headers = {"Content-Type": "application/json"}
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)

    payload = {
        "fields": {
            FIELD_CURRENT_DURATION: current_duration,
            FIELD_TOTAL_DURATION: new_total,
            FIELD_AVG_DURATION: avg_duration
        }
    }

    print("Payload to Jira:", payload)
    response = requests.put(url, json=payload, headers=headers, auth=auth)
    print("Response from Jira:", response.status_code, response.text)

    if response.status_code == 204:
        return jsonify({"status": "success", "duration": current_duration}), 200
    else:
        return jsonify({"error": "Jira update failed", "details": response.text}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
