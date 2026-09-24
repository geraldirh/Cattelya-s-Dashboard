# Walkthrough: Integrasi Kontrol 6 Aktuator MQTT

Berikut adalah ringkasan perubahan dan penyelesaian tugas untuk mengimplementasikan kendali MQTT terpusat untuk 6 aktuator di sistem Smart Greenhouse (OrchiCare AI).

## 🛠️ Perubahan yang Dilakukan

### 1. Update Backend & Model Data (`main.py`)
- Memperbarui model Pydantic `ActuatorActions` untuk mencakup:
  - `exhaust_fan`
  - `penyiraman_meja_1`
  - `penyiraman_meja_2`
  - `penyiraman_meja_3`
  - `penyiraman_pupuk`
  - `mist_ruangan`
- Mendeklarasikan `mqtt_client_instance` sebagai *global variable* untuk memastikan *publish* perintah MQTT tidak memerlukan pembuatan koneksi baru.
- Menambahkan **Endpoint Baru**: `@app.post("/control-actuator")`. Endpoint ini menerima permintaan `device` dan `state`, lalu mempublikasikannya ke *broker* dengan format *topic* `inianggrek/control/{device}`.
- Memperbarui **Prompt AI (`system_instruction`)** di `/analyze-metrics` sesuai dengan logika aktuator spesifik (misal, `penyiraman_meja_1` hidup jika Moisture Meja 1 < 60%).

### 2. Update Dashboard UI (`index.html`)
- Mengganti layout `actuators-grid` menjadi grid berukuran **3x2** (berisi 6 buah kotak sakelar aktuator yang rapi).
- Menambahkan ID yang relevan untuk setiap aktuator dan memperbarui status pewarnaan manual.
- Mengubah fungsi Javascript `toggleManualActuator()` agar dapat meneruskan parameter sakelar (ON/OFF) ke Endpoint Backend (melalui *fetch* HTTP POST ke `/control-actuator`).
- Menyelaraskan struktur *Data Logger Table*. Memperbarui bagian _header_ agar mencakup kelembapan dari 3 meja, Lux (intensitas cahaya), dan 6 aktuator, menghapus metrik usang seperti NPK atau Pyranometer (yang disesuaikan dengan permintaan sebelumnya).

## ✅ Pengujian Otomatis (*Browser Subagent*)
Sistem agen virtual secara otomatis menguji fungsionalitas UI:
- Agen memverifikasi keberadaan tab **KONTROL AKTUATOR** beserta tampilannya.
- Agen mengaktifkan *Mode Manual* dan menekan tombol sakelar `Exhaust Fan`, `Pompa Siram M1`, serta `Mist Ruangan`, di mana UI dengan sukses merespons pembaruan warna (Hijau/Biru) dan secara logis mengirimkan *payload* MQTT.
- Agen memverifikasi bahwa menu **Data Logger** memetakan kolom baru secara sempurna dan menyertakan data yang valid.

### 🖼️ Hasil Tampilan UI Baru
Berikut adalah tampilan layar aktual yang ditangkap selama pengujian:

![Status Aktuator di Mode Manual](/C:/Users/LQQ/.gemini/antigravity-ide/brain/e8936a8e-6df0-49a1-adcd-83ebed4e34d4/actuators_manual_on_1787268135624.png)

![Tabel Data Logger dengan 6 Aktuator & Metrik Terpisah](/C:/Users/LQQ/.gemini/antigravity-ide/brain/e8936a8e-6df0-49a1-adcd-83ebed4e34d4/data_logger_table_1787268168183.png)

> [!TIP]
> Modifikasi sistem berjalan dengan baik. Jika aktuator MQTT IoT Anda (*hardware*) sudah mendengarkan topik **`inianggrek/control/{nama-device}`** dan mengurai payload **`{"status": "ON"}`** maka integrasi keras Anda sudah siap!
