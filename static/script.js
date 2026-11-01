// PoultryPro Dashboard - HTTP Polling Client v3
// Membaca data sensor dari Flask backend (yang sync dari Firebase RTDB)
console.log('PoultryPro script.js v3 loaded');

let chartSuhu, chartKelembaban, chartGas;
let isConnected = false;
let pollInterval = null;

// ─── Initialize Charts ─────────────────────────────────────────────
function initCharts() {
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: true, labels: { color: '#94a3b8' } } },
        scales: {
            x: { ticks: { color: '#64748b', maxRotation: 45 }, grid: { color: 'rgba(255,255,255,0.05)' } },
            y: { ticks: { color: '#64748b' }, grid: { color: 'rgba(255,255,255,0.1)' } }
        }
    };

    const ctxSuhu = document.getElementById('chartSuhu');
    if (ctxSuhu) {
        chartSuhu = new Chart(ctxSuhu.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Suhu (°C)',
                    data: [],
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239,68,68,0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 2
                }]
            },
            options: commonOptions
        });
    }

    const ctxKelembaban = document.getElementById('chartKelembaban');
    if (ctxKelembaban) {
        chartKelembaban = new Chart(ctxKelembaban.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Kelembaban (%)',
                    data: [],
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34,197,94,0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 2
                }]
            },
            options: commonOptions
        });
    }

    const ctxGas = document.getElementById('chartGas');
    if (ctxGas) {
        chartGas = new Chart(ctxGas.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Gas NH3',
                    data: [],
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245,158,11,0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 2
                }]
            },
            options: commonOptions
        });
    }
}

// ─── Fetch Data dari Backend ────────────────────────────────────────
async function fetchData() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        updateUI(data);
        isConnected = true;
        document.getElementById('statusText').textContent = 'Firebase Live';
        document.getElementById('statusIndicator').classList.remove('status-disconnected');
    } catch (error) {
        console.error('Fetch error:', error);
        isConnected = false;
        document.getElementById('statusText').textContent = 'Disconnected';
        document.getElementById('statusIndicator').classList.add('status-disconnected');
    }
}

// ─── Update UI dengan Data Baru ─────────────────────────────────────
function updateUI(data) {
    const sensor = data.sensor;

    // Stat cards
    const suhu = parseFloat(sensor.suhu) || 0;
    const kelembaban = parseFloat(sensor.kelembaban) || 0;
    const gas = sensor.gas || 0;
    const gasPersen = parseFloat(sensor.gas_persen) || 0;
    const motor = sensor.motor || 'OFF';
    const sinyalWifi = sensor.sinyal_wifi || 0;
    const waktu = sensor.waktu || '--:--:--';
    const tanggal = sensor.tanggal || '--';

    document.getElementById('suhu').textContent = suhu.toFixed(1) + '°C';
    document.getElementById('kelembaban').textContent = kelembaban.toFixed(1) + '%';
    document.getElementById('gas').textContent = gas;
    document.getElementById('gasPersen').textContent = gasPersen.toFixed(1) + '%';
    document.getElementById('motor').textContent = motor;
    document.getElementById('motorStatus').textContent = motor;
    document.getElementById('sinyalWifi').textContent = sinyalWifi + ' dBm';
    document.getElementById('waktu').textContent = waktu;
    document.getElementById('tanggal').textContent = tanggal;

    // Motor icon color
    const motorIcon = document.getElementById('motorIcon');
    if (motor === 'ON') {
        motorIcon.innerHTML = '<i class="fas fa-cog fa-spin" style="color:#10b981"></i>';
        document.getElementById('motor').style.color = '#10b981';
    } else {
        motorIcon.innerHTML = '<i class="fas fa-cog" style="color:#ef4444"></i>';
        document.getElementById('motor').style.color = '#ef4444';
    }

    // WiFi signal color
    const wifiEl = document.getElementById('sinyalWifi');
    if (sinyalWifi > -50) {
        wifiEl.style.color = '#10b981'; // Bagus
    } else if (sinyalWifi > -70) {
        wifiEl.style.color = '#f59e0b'; // Sedang
    } else {
        wifiEl.style.color = '#ef4444'; // Lemah
    }

    // Update charts
    const chart = data.chart;
    if (chartSuhu && chart.labels) {
        chartSuhu.data.labels = chart.labels;
        chartSuhu.data.datasets[0].data = chart.suhu;
        chartSuhu.update('none');
    }
    if (chartKelembaban && chart.labels) {
        chartKelembaban.data.labels = chart.labels;
        chartKelembaban.data.datasets[0].data = chart.kelembaban;
        chartKelembaban.update('none');
    }
    if (chartGas && chart.labels) {
        chartGas.data.labels = chart.labels;
        chartGas.data.datasets[0].data = chart.gas;
        chartGas.update('none');
    }
}

// ─── Motor Control ──────────────────────────────────────────────────
async function setMotor(state) {
    try {
        const response = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'motor', value: state })
        });
        const result = await response.json();
        if (result.status === 'ok') {
            document.getElementById('motorStatus').textContent = state;
            console.log('Motor →', state);
        }
    } catch (e) {
        console.error('Control error:', e);
    }
}

// ─── Manual Refresh ─────────────────────────────────────────────────
async function manualRefresh() {
    await fetchData();
}

// ─── Init ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    fetchData();
    pollInterval = setInterval(fetchData, 2500);  // Poll setiap 2.5 detik
});
