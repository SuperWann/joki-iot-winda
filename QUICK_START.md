# 🚀 PoultryPro WiFi Mode - Quick Start

## Pilihan Koneksi

### ✅ WiFi Mode (ESP8266/ESP32) - **RECOMMENDED**
Backend menunggu data dari ESP via HTTP, **tanpa perlu kabel ke PC**

```powershell
# Jalankan (default = WiFi mode)
d:\poultry-pro\.venv\Scripts\python.exe app.py
```

Kalau mau set explicit:
```powershell
$env:USE_SERIAL = "false"  # WiFi mode
d:\poultry-pro\.venv\Scripts\python.exe app.py
```

---

### 🔌 Serial Mode (Arduino + Kabel USB)
Backend baca langsung dari COM port

```powershell
$env:USE_SERIAL = "true"
d:\poultry-pro\.venv\Scripts\python.exe app.py
```

---

## 📡 WiFi Mode Setup (Recommended)

### Step 1: Siapkan ESP Hardware
```
ESP32/ESP8266
├── D4 (GPIO4) ──→ DHT22 Data
├── D1 (GPIO5) ──→ Relay Signal (conveyor)
└── A0 (GPIO32) ──→ Gas Sensor
```

### Step 2: Program ESP
1. Buka Arduino IDE
2. Paste kode dari: [esp_example.ino](esp_example.ino)
3. Set WiFi credentials di kode:
   ```cpp
   const char* SSID = "YOUR_SSID";
   const char* PASSWORD = "YOUR_PASSWORD";
   const char* SERVER_IP = "192.168.1.100";  // ← PC IP kamu!
   ```
4. Upload ke ESP

### Step 3: Start Server
```powershell
d:\poultry-pro\.venv\Scripts\python.exe app.py
```

Output akan seperti:
```
🐔 PoultryPro Ready!
📡 Mode: ESP WiFi (POST ke /api/sensor-data)
🌐 WebSocket: ws://localhost:8765
🌐 Dashboard: http://localhost:5000
```

### Step 4: Open Dashboard
Browser: **http://localhost:5000**

Akan lihat:
✅ Sensor readings real-time
✅ Grafik suhu/humidity/gas  
✅ Mode control (Otomatis/Manual)
✅ ON/OFF buttons

---

## 🎯 Testing tanpa Hardware

Test API manual untuk verifikasi:

```powershell
# Send sensor data
curl -X POST http://localhost:5000/api/sensor-data `
  -H "Content-Type: application/json" `
  -d '{"suhu":31.2,"kelembaban":65,"gas":450,"status":"OFF"}'

# Get control status
curl http://localhost:5000/api/control

# Send command
curl -X POST http://localhost:5000/api/command/ON
```

Dashboard akan update otomatis!

---

## 📍 Cari IP PC

**Windows PowerShell:**
```powershell
ipconfig
```
Cari baris: `IPv4 Address : 192.168.X.X`

---

## 🔧 Environment Variables (Optional)

```powershell
# WiFi mode (default - no need to set)
$env:USE_SERIAL = "false"

# Serial mode
$env:USE_SERIAL = "true"
$env:SERIAL_PORT = "COM13"

# Firebase integration
$env:FIREBASE_DATABASE_URL = "https://your-db.firebasedatabase.app"
$env:FIREBASE_CREDENTIALS_PATH = "firebase-service-account.json"

# Conveyor schedule
$env:CONVEYOR_MODE = "otomatis"  # or "manual"
$env:CONVEYOR_AUTO_TIME = "09:00"
$env:CONVEYOR_AUTO_DURATION = "20"
```

---

## ✅ Checklist

- [ ] WiFi credentials set di `esp_example.ino`
- [ ] `SERVER_IP` = PC IP address
- [ ] ESP uploaded dan connected to WiFi
- [ ] Server app berjalan (`http://localhost:5000` bisa akses)
- [ ] Data sensor tampil di dashboard

---

## 📖 Full Documentation

Lihat [WIFI_MODE_SETUP.md](WIFI_MODE_SETUP.md) untuk detail lengkap

---

**Ready? Start at: http://localhost:5000 🚀**
