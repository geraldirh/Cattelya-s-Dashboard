# 🌸 OrchiCare AI - Smart Orchid Greenhouse

Sistem monitoring cerdas untuk greenhouse anggrek terintegrasi dengan Google Gemini AI dan MQTT IoT.

## 📋 Persyaratan Sistem
- Python 3.10 atau versi lebih baru
- Sistem Operasi Windows (Panduan di bawah disesuaikan untuk Windows)
- Koneksi Internet (untuk akses API Gemini dan Cloud MQTT)

## ⚙️ Langkah Instalasi & Konfigurasi

### 1. Buka Terminal / Command Prompt
Buka folder proyek ini di terminal pilihan Anda (seperti Command Prompt, PowerShell, atau Terminal di Visual Studio Code). Pastikan jalur kerja Anda sudah berada di direktori proyek ini (misalnya `D:\Tugas\TA BRIN\LLM1`).

### 2. Buat Virtual Environment
Virtual Environment (`env`) digunakan untuk mengisolasi instalasi pustaka khusus untuk proyek ini. Jalankan perintah berikut:
```bash
python -m venv env
```

### 3. Instal Pustaka / Dependensi
Gunakan `pip` yang ada di dalam folder `env` untuk menginstal seluruh pustaka pendukung secara otomatis dari file `requirements.txt`:
```bash
.\env\Scripts\pip install -r requirements.txt
```

### 4. Konfigurasi Kredensial di `.env`
Sistem membutuhkan kunci API (API Key) dan server MQTT untuk bekerja. Pastikan ada file bernama `.env` di dalam folder proyek Anda, lalu isi dengan format seperti ini:
```env
# Gemini AI Configuration
GEMINI_API_KEY="MASUKKAN_API_KEY_ANDA_DISINI"

# MQTT Broker Configuration (contoh pakai HiveMQ)
MQTT_HOST="MASUKKAN_HOST_MQTT_ANDA"
MQTT_PORT=8883
MQTT_USERNAME="MASUKKAN_USER_MQTT_ANDA"
MQTT_PASSWORD="MASUKKAN_PASSWORD_MQTT_ANDA"
```
*(Ganti isian di atas sesuai dengan pengaturan akun Anda)*

---

## 🚀 Cara Menjalankan Aplikasi

Agar aplikasi berjalan lancar dan tidak muncul pesan *`ModuleNotFoundError`*, jalankan program menggunakan `uvicorn` yang berada di dalam folder `env` Anda.

Ketikkan dan jalankan perintah ini di Terminal:
```bash
.\env\Scripts\uvicorn main:app --reload
```

Tunggu beberapa detik. Jika server sukses menyala, Anda akan melihat pesan seperti ini di terminal:
```text
INFO:     Will watch for changes in these directories: ...
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

## 🌐 Cara Membuka Dashboard Web
1. Buka peramban (browser) web kesayangan Anda seperti Chrome, Edge, atau Safari.
2. Ketik alamat berikut di URL bar: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**
3. Tekan Enter, dan halaman **OrchidCare — Smart Orchid Greenhouse** akan langsung menyambut Anda!

---

## 🛑 Cara Mematikan Server
Jika Anda sudah selesai menggunakan aplikasi dan ingin mematikan server lokal, cukup kembali ke jendela Terminal, lalu tekan kombinasi *keyboard*:
**`CTRL + C`**
Pekerjaan *background* akan segera dimatikan.
