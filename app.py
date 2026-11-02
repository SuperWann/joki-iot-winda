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
    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL,
        'httpTimeout': 10,  # detik, supaya panggilan Firebase tidak menggantung
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
# Sinkronisasi dari Firebase
# Dipanggil dari dalam request /api/data (jalur yang terbukti jalan
# di Gunicorn). Lock TIDAK pernah ditunggu: kalau request lain sedang
# mengambil data, request ini langsung memakai data terakhir.
# ═══════════════════════════════════════════════════════════════════
sync_lock = threading.Lock()
last_sync = 0.0
last_waktu = None
SYNC_INTERVAL = 2  # detik


def _sync_once():
    """Ambil /monitoring dari Firebase, update sensor_data & chart."""
    global last_waktu
    snap = db.reference('monitoring').get()
    if not isinstance(snap, dict):
        print(f"⚠️ /monitoring kosong atau bukan objek: {snap!r}")
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


def sync_from_firebase():
    global last_sync
    if not firebase_connected:
        return
    if time.time() - last_sync < SYNC_INTERVAL:
        return
    if not sync_lock.acquire(blocking=False):
        return  # ada request lain yang sedang sync, pakai data terakhir
    try:
        _sync_once()
    except Exception as e:
        print(f"⚠️ Sync error: {e}")
    finally:
        last_sync = time.time()
        sync_lock.release()


# ═══════════════════════════════════════════════════════════════════
# Flask Routes
# ═══════════════════════════════════════════════════════════════════
MAX_DURASI = 120      # detik, batas aman (sama dengan di ESP)
COOLDOWN = 3          # detik minimal antar perintah "jalan"
last_control = 0.0

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data', strict_slashes=False)
def api_data():
    """Return sensor & chart data untuk HTTP polling dari dashboard."""
    sync_from_firebase()
    return jsonify({
        "sensor": sensor_data,
        "chart": chart_data
    })


@app.route('/api/control', methods=['POST'])
def api_control():
    """Terima perintah motor dari dashboard, tulis ke Firebase /kontrol."""
    global last_control
    try:
        data = request.get_json(silent=True) or {}

        if data.get('action') != 'motor':
            return jsonify({"status": "error", "message": "aksi tidak dikenal"}), 400
        if not firebase_connected:
            return jsonify({"status": "error", "message": "Firebase tidak terhubung"}), 503

        try:
            durasi = int(data.get('durasi', 0))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "durasi tidak valid"}), 400

        # batasi di server, jangan percaya angka dari browser
        durasi = max(0, min(durasi, MAX_DURASI))

        now = time.time()
        # perintah STOP (durasi 0) selalu boleh; perintah jalan dibatasi cooldown
        if durasi > 0 and now - last_control < COOLDOWN:
            return jsonify({"status": "error", "message": "Tunggu sebentar sebelum perintah berikutnya"}), 429
        last_control = now

        db.reference('kontrol').set({
            'durasi': durasi,
            'id': str(int(now * 1000))
        })
        print(f"📤 Kontrol motor → durasi {durasi} detik")
        return jsonify({"status": "ok", "durasi": durasi})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
# Startup (jalan di Gunicorn maupun python app.py)
# ═══════════════════════════════════════════════════════════════════
load_persisted_data()
print("🐔 PoultryPro Dashboard Ready!")
print(f"🔥 Firebase: {'Connected' if firebase_connected else 'Disabled'}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Dashboard: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)