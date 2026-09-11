# Baseline Project: OrchiCare AI (Smart Greenhouse IoT)

Dokumen ini berisi informasi dasar (baseline) dari arsitektur, teknologi, dan struktur proyek untuk sistem monitoring cerdas **OrchiCare AI**. Dokumentasi ini bertujuan untuk memudahkan pemeliharaan dan pengembangan kode lebih lanjut.

## 1. Deskripsi Proyek
**OrchiCare AI** adalah aplikasi web dasbor terintegrasi untuk memantau keadaan lingkungan greenhouse secara *real-time* berbasis Internet of Things (IoT) yang diperkuat dengan analisis kecerdasan buatan (AI) dari Google Gemini. Sistem ini dapat melakukan *short-polling* data telemetri, memberikan diagnosis penyakit anggrek dari gambar, serta mengontrol aktuator (seperti *exhaust fan* dan pendingin kabut/mist).

---

## 2. Tumpukan Teknologi (Tech Stack)

Sistem dirancang untuk menjadi sangat ringan (lightweight) tanpa bergantung pada framework pihak ketiga yang berat.

### Frontend
- **HTML5 & Vanilla CSS3:** Antarmuka responsif dengan desain *glassmorphism*. **TIDAK menggunakan** framework CSS tambahan seperti Tailwind atau Bootstrap.
- **Vanilla JavaScript:** Menangani fungsionalitas UI, *tab-switching*, REST API *fetching*, dan *short-polling*.
- **Chart.js (via CDN):** Digunakan untuk merender grafik `Live Environment` yang bergerak secara dinamis sesuai data masuk.
- **Inline SVG Gauges:** Visualisasi data meteran (suhu, kelembapan, TDS) murni dibangun dengan SVG matematika tanpa library eksternal.

### Backend
- **Python 3.11+:** Bahasa server utama.
- **FastAPI & Uvicorn:** Framework backend yang sangat cepat (Asynchronous) untuk menyediakan *endpoints* API dan melayani *static files* (HTML).
- **Google GenAI SDK (`google-generativeai`):** Model LLM **Gemini 1.5 Flash** untuk fitur *Dokter Anggrek* (menerima input gambar penyakit dan teks).
- **Paho-MQTT (`paho-mqtt`):** Digunakan untuk berkomunikasi dengan *HiveMQ Cloud Broker* sebagai *background worker* tanpa memblokir proses HTTP server. Mengambil data ESP32 secara instan.

---

## 3. Struktur Direktori dan File

Proyek ini menggunakan pendekatan monolitis sederhana:

```text
D:\Tugas\TA BRIN\LLM1
│
├── main.py                # Core Backend Engine (FastAPI, MQTT, Gemini AI logic)
├── index.html             # Core Frontend UI (HTML, CSS Layouts, JS Fetching Logic)
├── .env                   # File environment rahasia (API Keys, MQTT Credentials)
├── requirements.txt       # Daftar pustaka Python (fastapi, uvicorn, paho-mqtt, dll.)
├── greenhouse_bg.png      # Gambar statis untuk lapisan background
└── env/                   # Virtual Environment Python
```

---

## 4. Fitur Utama

1. **Dashboard Monitoring Real-Time:** 
   - Grid layout yang proporsional (menggunakan CSS Grid 33% dan 50%).
   - Fetching cuaca Kota Bandung dari *Open-Meteo API*.
   - Grafik garis waktu nyata dan alat pengukur (suhu, kelembapan tanah/udara, NPK, TDS, Pyranometer).
2. **Kecerdasan Buatan (Dokter Anggrek):**
   - Integrasi langsung dengan *Gemini 1.5 Flash*.
   - Fitur obrolan interaktif dan ulasan gambar untuk mendeteksi hama / kelainan tanaman anggrek.
3. **IoT Telemetry Sync:**
   - Background thread `paho-mqtt` yang mendengarkan `esp32/dht11/telemetry`.
   - Endpoint `/latest-telemetry` untuk memancarkan hasil memori lokal ke Web.

---

## 5. Cara Menjalankan Server (Local)

1. Pastikan Anda berada di direktori `D:\Tugas\TA BRIN\LLM1`.
2. Jika Anda menggunakan PowerShell dan tidak bisa melakukan aktivasi *Virtual Environment* biasa, eksekusi perintah ini:
   ```powershell
   .\env\Scripts\python.exe main.py
   ```
3. Akses halaman melalui browser di: [http://localhost:8000](http://localhost:8000).

---

## 6. Konvensi Kode (Guidelines)
- **CSS:** Semua modifikasi gaya harus berada di dalam tag `<style>` pada `index.html`. Gunakan variabel root (contoh: `var(--primary)`) untuk konsistensi warna.
- **Pembaruan Grid:** Gunakan utility classes (`.col-33` untuk 1/3 lebar, `.col-50` untuk 1/2 lebar) untuk memastikan layout tetap simetris pada rasio layar yang berbeda.
- **Keamanan:** Kredensial *TIDAK BOLEH* di-_hardcode_ ke dalam `main.py`. Semua *API Keys* (Gemini) dan *MQTT Passwords* wajib memanggil fungsi `os.getenv()` yang dibaca dari file `.env`.
