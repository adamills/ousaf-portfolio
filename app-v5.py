import os
import json
from flask import Flask, request, jsonify, send_from_directory

import requests
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
DATABASE_URL = os.environ.get("DATABASE_URL", "dbname=ousaf_calls")
PORT = int(os.environ.get("PORT", 8080))

PROJECTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.json")

# Connection pool instead of a fresh connection per request — avoids
# connection-setup overhead and caps concurrent DB connections under load.
db_pool = ThreadedConnectionPool(1, 10, DATABASE_URL)


def get_db_conn():
    return db_pool.getconn()


def release_db(conn):
    if conn is not None:
        db_pool.putconn(conn)


# Asterisk DIALSTATUS values -> our schema's status enum
DIALSTATUS_MAP = {
    "ANSWER": "completed",
    "NOANSWER": "missed",
    "BUSY": "missed",
    "CONGESTION": "failed",
    "CHANUNAVAIL": "failed",
    "CANCEL": "missed",
    "DONTCALL": "missed",
    "TORTURE": "failed",
    "INVALIDARGS": "failed",
}


def load_projects():
    try:
        with open(PROJECTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def find_project(message):
    lower_msg = message.lower()
    for p in load_projects():
        if p.get("id", "").lower() in lower_msg or p.get("title", "").lower() in lower_msg:
            return p
    return None


def format_project_reply(p):
    lines = [f"📌 {p['title']}", "", p['summary'], "", f"Tech used: {', '.join(p.get('tech', []))}", f"Status: {p.get('status', '')}"]
    if p.get("link"):
        lines.append(f"🔗 {p['link']}")
    return "\n".join(lines)


@app.route('/api/health')
def health():
    """Used by Render's uptime/deploy health checks."""
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.close()
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "degraded", "database": "unreachable", "error": str(e)}), 503
    finally:
        release_db(conn)


@app.route('/api/log_call', methods=['POST'])
def log_call():
    data = request.get_json(silent=True) or {}

    call_id = data.get("call_id")
    phone_number = data.get("phone_number")
    campaign_id = data.get("campaign_id")
    duration = data.get("duration", 0)
    dial_status = data.get("dial_status", "")

    if not call_id or not phone_number or not campaign_id:
        return jsonify({"error": "call_id, phone_number, and campaign_id are required"}), 400

    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 0

    status = DIALSTATUS_MAP.get(dial_status.upper(), "failed")

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO campaigns (campaign_id, name) VALUES (%s, %s) ON CONFLICT (campaign_id) DO NOTHING;",
            (campaign_id, campaign_id),
        )
        cur.execute(
            """
            INSERT INTO call_logs (call_id, campaign_id, phone_number, status, duration)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (call_id) DO UPDATE
            SET status = EXCLUDED.status, duration = EXCLUDED.duration;
            """,
            (call_id, campaign_id, phone_number, status, duration),
        )
        conn.commit()
        cur.close()
        return jsonify({"ok": True, "status": status}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    finally:
        release_db(conn)


@app.route('/')
def index():
    return send_from_directory('.', 'muhammad-ousaf-landing.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()
    if not user_message:
        return jsonify({"error": "No message provided."}), 400

    project = find_project(user_message)
    if project:
        return jsonify({"reply": format_project_reply(project)})

    if not OPENAI_API_KEY:
        return jsonify({"error": "OPENAI_API_KEY is not set on the server."}), 500

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are the AI assistant embedded in Muhammad Ousaf's portfolio "
                            "landing page. He is a full-stack developer and AI/telephony systems "
                            "builder (Asterisk, SIP trunking, ElevenLabs voice, React, Python). "
                            "Answer questions briefly and accurately. If a coding question is asked, "
                            "give a short, correct, working code snippet. Keep responses under 120 words "
                            "unless code requires more."
                        ),
                    },
                    {"role": "user", "content": user_message},
                ],
                "max_completion_tokens": 350,
                "temperature": 0.4,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": content})
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"OpenAI API error: {e.response.status_code} {e.response.text[:200]}"}), 502
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
