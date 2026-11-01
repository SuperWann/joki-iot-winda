import os
import json
import threading
import time
from datetime import datetime

import pytz
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, db

# ─── Timezone WIB (UTC+7) ───────────────────────────────────────────
TIMEZONE = pytz.timezone('Asia/Jakarta')

# ─── Initialize Firebase ────────────────────────────────────────────
# PENTING: Ganti firebase-service-account.json dengan service account
# dari project joki-iot-winda di Firebase Console!
firebase_connected = False
try:
    cred = credentials.Certificate('firebase-service-account.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://joki-iot-winda-default-rtdb.asia-southeast1.firebasedatabase.app'
    })
    firebase_connected = True
    print(f"✅ Firebase {cred.project_id} connected!")
except Exception as e:
    print(f"⚠️ Firebase error: {e}")

# ─── Flask App ──────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), 'template')
)
CORS(app)

DATA_FILE = os.path.join('data', 'sensor_data.json')

# ─── Sensor Data (synced dari Firebase RTDB) ────────────────────────
sensor_data = {
    "suhu": 0.0,
    "kelembaban": 0.0,
    "gas": 0,
    "gas_persen": 0.0,
    "motor": "OFF",
    "sinyal_wifi": 0,
    "tanggal": "",
    "waktu": ""
}

# ─── Chart History ──────────────────────────────────────────────────
MAX_CHART_POINTS = 50
chart_data = {
    "labels": [],
    "suhu": [],
    "kelembaban": [],
    "gas": []
}


# ═══════════════════════════════════════════════════════════════════
# Persistence: simpan/muat data ke disk agar chart tidak hilang
# ═══════════════════════════════════════════════════════════════════
def load_persisted_data():
    """Muat data chart terakhir dari file JSON."""
    global sensor_data, chart_data
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
            if isinstance(saved, dict):
                sensor_data.update(saved.get('sensor', {}))
                loaded_chart = saved.get('chart', {})
                if isinstance(loaded_chart, dict):
                    for key in chart_data:
                        chart_data[key] = loaded_chart.get(key, chart_data[key])
    except Exception as e:
        print(f"⚠️ Gagal memuat data tersimpan: {e}")


def save_persisted_data():
    """Simpan snapshot data ke file JSON."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({'sensor': sensor_data, 'chart': chart_data}, f, indent=2)
    except Exception as e:
        print(f"⚠️ Gagal menyimpan data ke disk: {e}")


# ═══════════════════════════════════════════════════════════════════
# Firebase Realtime Listener
# ═══════════════════════════════════════════════════════════════════
def firebase_listener(event):
    """Callback ketika data berubah di Firebase path /monitoring."""
    global sensor_data
    if event.data is None:
        return

    try:
        if event.path == '/':
            # Full snapshot (pertama kali atau data besar berubah)
            if isinstance(event.data, dict):
                for key in sensor_data:
                    if key in event.data:
                        sensor_data[key] = event.data[key]
        else:
            # Single field update (misal /suhu berubah)
            key = event.path.lstrip('/')
            if key in sensor_data:
                sensor_data[key] = event.data

        # Tambah ke chart history
        waktu = sensor_data.get("waktu", datetime.now(TIMEZONE).strftime("%H:%M:%S"))
        chart_data["labels"].append(waktu)
        chart_data["suhu"].append(sensor_data.get("suhu", 0))
        chart_data["kelembaban"].append(sensor_data.get("kelembaban", 0))
        chart_data["gas"].append(sensor_data.get("gas", 0))

        # Batasi jumlah titik chart
        if len(chart_data["labels"]) > MAX_CHART_POINTS:
            for key in chart_data:
                chart_data[key] = chart_data[key][-MAX_CHART_POINTS:]

        save_persisted_data()
        print(
            f"📡 Data update: suhu={sensor_data.get('suhu')}°C, "
            f"kelembaban={sensor_data.get('kelembaban')}%, "
            f"gas={sensor_data.get('gas')}, "
            f"motor={sensor_data.get('motor')}"
        )
    except Exception as e:
        print(f"⚠️ Listener error: {e}")


def start_firebase_listener():
    """Start listener pada path /monitoring di Firebase RTDB."""
    if not firebase_connected:
        print("⚠️ Firebase tidak terhubung, listener tidak dimulai")
        return
    try:
        ref = db.reference('monitoring')
        ref.listen(firebase_listener)
        print("👂 Firebase listener aktif pada /monitoring")
    except Exception as e:
        print(f"⚠️ Firebase listener error: {e}")


# ═══════════════════════════════════════════════════════════════════
# Flask Routes
# ═══════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data', strict_slashes=False)
def api_data():
    """Return sensor & chart data untuk HTTP polling dari dashboard."""
    return jsonify({
        "sensor": sensor_data,
        "chart": chart_data
    })


@app.route('/api/control', methods=['POST'])
def api_control():
    """Terima perintah kontrol motor dari dashboard, kirim ke Firebase."""
    try:
        data = request.get_json()
        action = data.get('action')
        value = data.get('value')

        if action == 'motor' and firebase_connected:
            # Tulis ke Firebase → ESP akan baca perubahan ini
            db.reference('monitoring/motor').set(value)
            sensor_data["motor"] = value
            print(f"📤 Motor control → {value}")

        return jsonify({"status": "ok", "action": action, "value": value})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════
load_persisted_data()
threading.Thread(target=start_firebase_listener, daemon=True).start()
print("🐔 PoultryPro Dashboard Ready!")
print(f"🔥 Firebase: {'Connected' if firebase_connected else 'Disabled'}")

if __name__ == '__main__':
    print("🌐 Dashboard: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
