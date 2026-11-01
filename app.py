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
# Di Render: file ada di /etc/secrets/ (Secret File).
# Di laptop: file ada di folder proyek.
DATABASE_URL = 'https://joki-iot-winda-default-rtdb.asia-southeast1.firebasedatabase.app'
CRED_PATHS = [
    '/etc/secrets/firebase-service-account.json',
    'firebase-service-account.json',
]

firebase_connected = False
try:
    cred_path = next((p for p in CRED_PATHS if os.path.exists(p)), CRED_PATHS[-1])
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
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

# ─── Sensor Data (disinkronkan dari Firebase RTDB) ──────────────────
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
# (catatan: di Render free tier file ini hilang saat restart/redeploy)
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
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({'sensor': sensor_data, 'chart': chart_data}, f, indent=2)
    except Exception as e:
        print(f"⚠️ Gagal menyimpan data ke disk: {e}")


# ═══════════════════════════════════════════════════════════════════
# Sinkronisasi dari Firebase (polling, stabil di Gunicorn/Render)
# ═══════════════════════════════════════════════════════════════════
data_lock = threading.Lock()
last_sync = 0.0
last_waktu = None
SYNC_INTERVAL = 2  # detik


def sync_from_firebase():
    """Ambil data terbaru dari /monitoring, update sensor_data & chart."""
    global last_sync, last_waktu
    if not firebase_connected:
        return
    if time.time() - last_sync < SYNC_INTERVAL:
        return

    with data_lock:
        # cek ulang setelah dapat lock (thread lain mungkin sudah sync)
        if time.time() - last_sync < SYNC_INTERVAL:
            return
        last_sync = time.time()

        try:
            snap = db.reference('monitoring').get()
            if not isinstance(snap, dict):
                return

            for key in sensor_data:
                if key in snap:
                    sensor_data[key] = snap[key]

            waktu = sensor_data.get("waktu") or datetime.now(TIMEZONE).strftime("%H:%M:%S")

            # Tambah titik chart hanya kalau ada pembacaan baru dari ESP
            if waktu != last_waktu:
                last_waktu = waktu
                chart_data["labels"].append(waktu)
                chart_data["suhu"].append(sensor_data.get("suhu", 0))
                chart_data["kelembaban"].append(sensor_data.get("kelembaban", 0))
                chart_data["gas"].append(sensor_data.get("gas", 0))

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
            print(f"⚠️ Sync error: {e}")


def poll_loop():
    """Thread latar belakang: isi grafik walau tidak ada yang membuka dashboard."""
    while True:
        sync_from_firebase()
        time.sleep(3)


# ═══════════════════════════════════════════════════════════════════
# Flask Routes
# ═══════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data', strict_slashes=False)
def api_data():
    """Return sensor & chart data untuk HTTP polling dari dashboard."""
    sync_from_firebase()  # pastikan data segar setiap dashboard meminta
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
            # Tulis ke Firebase → ESP akan membaca perubahan ini
            db.reference('monitoring/motor').set(value)
            sensor_data["motor"] = value
            print(f"📤 Motor control → {value}")

        return jsonify({"status": "ok", "action": action, "value": value})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# ═══════════════════════════════════════════════════════════════════
# Startup (jalan di Gunicorn maupun python app.py)
# ═══════════════════════════════════════════════════════════════════
load_persisted_data()
threading.Thread(target=poll_loop, daemon=True).start()
print("🐔 PoultryPro Dashboard Ready!")
print(f"🔥 Firebase: {'Connected' if firebase_connected else 'Disabled'}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Dashboard: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)