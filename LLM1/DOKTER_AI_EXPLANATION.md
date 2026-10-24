# Dokumentasi Teknis: Dokter Anggrek AI & Sistem Gemini AI

Dokumen ini menjelaskan arsitektur, kapabilitas, alur kerja, prompt mentah, pemanggilan fungsi (*Function Calling / Tools*), dan kode sumber implementasi modul kecerdasan buatan (**Dokter Anggrek AI**) pada sistem Smart Greenhouse Anggrek.

---

## 1. Ringkasan Kapabilitas (Bisa Ngapain Aja?)

Dokter Anggrek AI berfungsi sebagai asisten cerdas botani dan pengendali greenhouse terintegrasi yang memiliki 3 pilar kapabilitas utama:

1. **Konsultasi Interaktif & Multimodal Vision (Chatbot & Diagnosa Foto)**:
   - Menjawab pertanyaan fisiologi, hama, penyakit, pupuk, dan perawatan berbagai varietas anggrek (Phalaenopsis, Dendrobium, Cattleya, dll).
   - Menganalisis foto kondisi fisik daun/bunga anggrek secara multimodal (via Base64 upload atau kamera) untuk mendeteksi penyakit/hama beserta rekomendasi obatnya.
   - Menyimpan dan memuat kembali sesi riwayat chat (*session-based chat history*) ke Supabase.

2. **Grounding Kondisi Real-Time Greenhouse**:
   - Mengetahui waktu lokal real-time (WIB).
   - Membaca telemetri sensor saat ini secara langsung (Suhu Udara, RH, Lux, TDS, Suhu/Moisture/EC/pH tanah Meja 1-3) serta status on/off aktuator (Kipas, Pompa Air, Pompa Nutrisi, Mist).

3. **Function Calling / AI Agent Tools (Otomasi Terhubung)**:
   - **`set_greenhouse_thresholds`**: Mengubah nilai ambang batas (*setpoints*) logika kendali PLC melalui MQTT secara otomatis sesuai instruksi pengguna.
   - **`query_database_stats`**: Melakukan kueri analitik ke Supabase untuk menghitung total durasi menyala aktuator, rekor *streak* operasional, rata-rata parameter sensor, serta estimasi konsumsi air & pupuk (liter) berdasarkan rentang waktu atau tanggal tertentu.
   - **`get_weather_forecast`**: Mengambil data satelit prakiraan cuaca 3 hari ke depan (suhu, curah hujan, probabilitas hujan) via Open-Meteo API sebagai pertimbangan preventif perawatan.

4. **Analisis Klimatologi & Nutrisi Greenhouse Terstruktur**:
   - Endpoint terpisah (`/analyze-greenhouse`) untuk mengevaluasi data lingkungan dan menentukan status aktuator otomatis dalam bentuk JSON murni.

---

## 2. Peta File Kode Sumber

| Komponen / Fitur | Lokasi File | Fungsi / Baris Utama |
|---|---|---|
| **Chatbot Engine & Agent Loop** | `main.py` | `chat_orchid()` (Endpoint `/chat`, baris ~1354-1455) |
| **Model Data Input Chat** | `main.py` | `ChatMessage`, `ChatRequest` (baris ~794-806) |
| **Tool: Setpoint via MQTT** | `main.py` | `set_greenhouse_thresholds()` (baris ~1113-1140) |
| **Tool: Statistik & Konsumsi DB** | `main.py` | `query_database_stats()` (baris ~1142-1319) |
| **Tool: Prakiraan Cuaca Satelit** | `main.py` | `get_weather_forecast()` (baris ~1320-1352) |
| **Diagnosa Foto Daun Mandiri** | `main.py` | `diagnose_orchid()` (Endpoint `/analyze-leaves`, baris ~699-740) |
| **Analisis Klimatologi JSON** | `main.py` | `analyze_greenhouse()` (Endpoint `/analyze-greenhouse`, baris ~858-958) |
| **Frontend Chat UI & Typewriter** | `public/app.js` | `sendChatMessage()`, `appendBubble()`, `resetChat()` (baris ~330-464) |
| **Frontend Chat Structure & HTML**| `public/index.html`| Section Tab Dokter Anggrek AI (baris ~90-170) |

---

## 3. Detail Prompt & Konfigurasi Model

### 3.1. Chatbot Dokter Anggrek AI (`/chat`)
- **File**: `main.py`
- **Model**: `gemini-3.5-flash-lite`
- **Konfigurasi**: `enable_automatic_function_calling=True`

#### System Instruction (Prompt Mentah):
```python
system_instruction = (
    "Anda adalah Dokter Anggrek AI, pakar botani spesialis tanaman anggrek terintegrasi dengan sistem IoT Greenhouse.\n\n"
    f"WAKTU SEKARANG (REAL-TIME): {wib_str}\n"
    f"KONDISI GREENHOUSE SAAT INI (REAL-TIME):\n- Data Sensor: {live_telemetry_str}\n- Status Aktuator: {live_actuator_str}\n\n"
    "Tugas Anda:\n"
    "1. Menjawab pertanyaan pengguna tentang anggrek (perawatan, penyakit, hama, pemupukan, dll).\n"
    "2. Anda BOLEH membaca dan menganalisis KONDISI GREENHOUSE SAAT INI di atas jika pengguna bertanya tentang keadaan greenhouse saat ini (contoh: 'Berapa suhu sekarang?', 'Apakah GH aman?', 'Apakah kipas sekarang menyala?').\n"
    "3. Jika Anda menilai kondisinya tidak wajar (misal suhu >35C atau <20C, kelembapan terlalu rendah), sarankan solusi atau perubahan batas suhu.\n"
    "4. Jika pengguna meminta Anda untuk menyetel, mengubah, atau menerapkan parameter (misalnya 'atur parameter ke suhu 28', 'bantu setel parameter yang ideal'), Anda memiliki ALAT (Function Calling) bernama `set_greenhouse_thresholds` untuk mengubahnya secara langsung! Eksekusi alat tersebut dengan angka yang tepat untuk Suhu Siang, Suhu Malam, Hum low, TDS, dll sesuai standar anggrek (seperti Phalaenopsis atau Dendrobium) atau sesuai angka permintaan pengguna.\n"
    "5. Jika pengguna menanyakan riwayat/statistik aktuator (kipas exhaust, pompa air, pompa nutrisi, mist), rekor menyala, atau ESTIMASI KONSUMSI AIR & PUPUK (contoh: 'ada riwayat pompa air hari rabu 7 oktober', 'berapa jam kipas menyala hari ini', 'konsumsi air kemarin'): JANGAN MENEBAK atau menolak! Selalu gunakan alat `query_database_stats` dengan argumen `target_date` (misal '2026-10-07'), `hours`, atau `start_date` yang tepat sesuai tanggal yang dimaksud pengguna.\n"
    "6. Jika pengguna menanyakan prakiraan cuaca atau Anda butuh data cuaca untuk merencanakan perawatan hari esok, gunakan alat `get_weather_forecast`.\n\n"
    "PENTING: Anda hanya boleh membahas hal seputar anggrek dan kendali Greenhouse. Tolak pertanyaan di luar itu dengan sopan."
)
```

#### Injeksi Multimodal (Gambar):
Jika pengguna melampirkan foto tanpa menyertakan pertanyaan tertulis, sistem secara otomatis memasang prompt *fallback*:
```text
"Tolong periksa dan analisis kondisi tanaman anggrek pada foto ini. Apakah tanaman ini sehat atau mengalami penyakit/hama? Berikan penjelasan gejala dan solusi penanganannya."
```

---

### 3.2. Diagnosa Foto Daun (`/analyze-leaves`)
- **File**: `main.py` (baris ~720-729)
- **Model**: `gemini-3.5-flash-lite`

#### Prompt Mentah:
```text
Anda adalah pakar botani spesialis tanaman anggrek. Analisis foto anggrek ini.
Tentukan apakah tanaman tersebut sehat atau sakit.
Jika terdeteksi penyakit/hama:
- Sebutkan nama penyakit/masalahnya
- Sebutkan gejala visual yang Anda lihat di foto
- Berikan penjelasan penyebabnya secara singkat
- Berikan langkah penanganan/solusi praktis dan obat yang direkomendasikan.

Gunakan bahasa Indonesia yang jelas, sopan, dan terstruktur dengan baik (gunakan bullet points).
```

---

### 3.3. Analisis Klimatologi & Kontrol Otomatis (`/analyze-greenhouse`)
- **File**: `main.py` (baris ~870-919)
- **Model**: `gemini-3.5-flash-lite`
- **Output Format**: JSON murni (`response_mime_type: "application/json"`)

#### Prompt Mentah:
```python
prompt = (
    f"Anda adalah sistem analisis klimatologi & nutrisi otomatis untuk greenhouse budidaya tanaman anggrek.\n"
    f"Berikut adalah data sensor saat ini:\n"
    f"- Suhu Udara: {metrics.air_temperature}°C\n"
    f"- Kelembapan Udara: {metrics.air_humidity}%\n"
    f"- Intensitas Cahaya (Lux): {metrics.lux} Lux\n"
    f"- TDS Air Penyiraman: {metrics.tds} ppm\n"
    f"- Meja 1 (Tanah): Suhu {metrics.meja1.suhu}°C, Moisture {metrics.meja1.kelembapan}%, EC {metrics.meja1.ec}, pH {metrics.meja1.ph}\n"
    f"- Meja 2 (Tanah): Suhu {metrics.meja2.suhu}°C, Moisture {metrics.meja2.kelembapan}%, EC {metrics.meja2.ec}, pH {metrics.meja2.ph}\n"
    f"- Meja 3 (Tanah): Suhu {metrics.meja3.suhu}°C, Moisture {metrics.meja3.kelembapan}%, EC {metrics.meja3.ec}, pH {metrics.meja3.ph}\n\n"
    f"Aturan Kondisi Optimal Anggrek:\n"
    f"1. Iklim Udara: Suhu udara optimal ~25°C. Jika suhu > 27°C, nyalakan Kipas Exhaust (1).\n"
    f"2. Kelembapan Tanah (Moisture): Optimal 60% - 80%.\n"
    f"3. EC Tanah (Nutrisi): Optimal 1.0 - 1.5 mS/cm. pH Tanah: Optimal 5.5 - 6.5.\n"
    f"4. Kualitas Air (TDS): Optimal 150-300 ppm. Jika >400 ppm (terlalu pekat); jika <100 ppm (kurang nutrisi).\n"
    f"5. Cahaya (Lux): Optimal 2000-5000 Lux.\n"
    f"6. Sistem Otomasi Aktuator:\n"
    f"   - exhaust_fan (Kipas Sirkulasi Udara): 1 jika suhu > 27°C, selain itu 0.\n"
    f"   - penyiraman_air (Pompa Siram Air): 1 jika Moisture tanah < 60%, selain itu 0.\n"
    f"   - penyiraman_pupuk (Pompa Nutrisi): 1 jika TDS Air < 100 ppm ATAU EC Meja rata-rata < 1.0, selain itu 0.\n"
    f"   - mist_ruangan (Pelembap Ruangan): 1 jika Kelembapan Udara < 70% ATAU Suhu Udara > 29°C, selain itu 0.\n\n"
    f"Tugas Anda:\n"
    f"1. Analisis kondisi suhu & kelembapan udara secara singkat.\n"
    f"2. Analisis kondisi tanah (suhu, moisture, EC, pH) pada ketiga meja secara singkat.\n"
    f"3. Analisis nilai TDS dan ketersediaan air (Water Level).\n"
    f"4. Analisis intensitas cahaya (Lux) secara singkat.\n"
    f"5. Berikan rekomendasi perawatan tanaman anggrek yang sesuai secara terpadu.\n"
    f"6. Tentukan status aktuator (1 atau 0) untuk 'exhaust_fan', 'penyiraman_air', 'penyiraman_pupuk', dan 'mist_ruangan'.\n\n"
    f"Anda WAJIB mengembalikan respon dalam format JSON yang valid dengan struktur berikut:\n"
    f"{{\n"
    f"  \"status_udara\": \"analisis udara\",\n"
    f"  \"status_tanah\": \"analisis kondisi tanah meja 1-3\",\n"
    f"  \"status_nutrisi\": \"analisis air (TDS & Level)\",\n"
    f"  \"status_cahaya\": \"analisis cahaya (Lux)\",\n"
    f"  \"rekomendasi\": \"rekomendasi perawatan terpadu\",\n"
    f"  \"actions\": {{\n"
    f"    \"exhaust_fan\": 1 atau 0,\n"
    f"    \"penyiraman_air\": 1 atau 0,\n"
    f"    \"penyiraman_pupuk\": 1 atau 0,\n"
    f"    \"mist_ruangan\": 1 atau 0\n"
    f"  }}\n"
    f"}}\n"
    f"Pastikan respon adalah JSON murni, jangan sertakan markdown block (seperti ```json ... ```)."
)
```

---

## 4. Code Mentah Pemanggilan & Function Calling

### 4.1. Inisialisasi Model & Obrolan (`main.py`)
```python
import google.generativeai as genai
from PIL import Image
import io
import base64

# Konfigurasi Global
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Pembuatan Instance Chat dengan Tools (Function Calling)
model = genai.GenerativeModel(
    model_name='gemini-3.5-flash-lite',
    system_instruction=system_instruction,
    tools=[set_greenhouse_thresholds, query_database_stats, get_weather_forecast]
)

# Rekonstruksi Riwayat Obrolan
gemini_history = []
for msg in request.history:
    gemini_history.append({
        "role": "user" if msg.role == "user" else "model",
        "parts": [msg.content]
    })

# Inisialisasi Chat Session
chat = model.start_chat(history=gemini_history, enable_automatic_function_calling=True)

# Eksekusi Pengiriman Pesan (Multimodal Support)
if len(message_parts) == 1 and isinstance(message_parts[0], str):
    response = chat.send_message(message_parts[0])
else:
    response = chat.send_message(message_parts)
```

### 4.2. Definisi Tools / Function Calling (`main.py`)

#### A. Tool Pengaturan Threshold PLC (`set_greenhouse_thresholds`)
```python
def set_greenhouse_thresholds(
    suhu_siang: float, 
    suhu_malam: float, 
    hum_low: float, 
    tds_sp: float, 
    soil_temp: float, 
    soil_moist: float
) -> str:
    """Mengatur atau mengubah nilai batas (threshold) aktuator otomatis (suhu, kelembapan, tds, dll).
    Panggil fungsi ini secara otomatis JIKA pengguna secara tersurat meminta bantuan untuk mengubah, mengatur, atau menyetel parameter/threshold greenhouse.
    """
    global mqtt_client_instance
    if not mqtt_client_instance:
        return "Gagal: MQTT Client belum terhubung ke broker."
    
    payload_dict = {
        "Suhu_Siang": suhu_siang,
        "Suhu_Malam": suhu_malam,
        "Hum_Low": hum_low,
        "TDS_Sp": tds_sp,
        "Soil_Temp": soil_temp,
        "Soil_moist": soil_moist
    }
    try:
        mqtt_client_instance.publish(TOPIC_SP_SENSOR_SUB, json.dumps(payload_dict))
        return f"Berhasil mengirim pengaturan threshold ke sistem IoT: {json.dumps(payload_dict)}"
    except Exception as e:
        return f"Gagal mengatur threshold karena error: {str(e)}"
```

#### B. Tool Kueri Statistik & Konsumsi (`query_database_stats`)
```python
def query_database_stats(
    hours: Optional[int] = None,
    target_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """Mengambil dan menghitung statistik sensor (suhu, kelembapan, lux, TDS) serta riwayat dan durasi aktif aktuator (kipas exhaust, pompa air, pompa pupuk, mist) dari database Supabase."""
    # Memfilter rentang waktu WIB -> UTC
    # Mengambil log dari actuator_logs & sensor_logs via Supabase pagination
    # Menghitung durasi aktif berurutan terpanjang (streak) dan total menit menyala
    # Menghitung estimasi konsumsi volume air: (50 ml / 45 detik x 60 pot = 4 Liter/menit)
    # Mengembalikan string terformat sebagai referensi reasoning Gemini AI
```

#### C. Tool Cuaca Satelit (`get_weather_forecast`)
```python
def get_weather_forecast(lat: float = -6.2088, lon: float = 106.8456) -> str:
    """Mengambil prakiraan cuaca (suhu, curah hujan) untuk 3 hari ke depan menggunakan Open-Meteo API."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,rain_sum&timezone=auto"
    req = urllib.request.Request(url, headers={'User-Agent': 'OrchidCare-Greenhouse-IoT-App/1.0'})
    # Parsing JSON temperatur, curah hujan, dan kemungkinan hujan untuk dianalisis oleh AI
```

---

### 4.3. Pemanggilan dari Sisi Frontend (`public/app.js`)
```javascript
// Pengiriman pesan dari antarmuka web ke endpoint /chat
const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        session_id: currentSessionId,
        message: msg,
        image: attachedImg,     // Base64 string foto daun jika ada
        history: chatHistory    // Array [{role: 'user'|'model', content: string}]
    })
});
const data = await res.json();
const responseText = data.response;

// Render Typewriter Effect di antarmuka chat
let i = 0;
let currentText = "";
const typeInterval = setInterval(() => {
    currentText += responseText.charAt(i);
    el.innerHTML = (typeof marked !== 'undefined') ? marked.parse(currentText) : currentText;
    msgs.scrollTop = msgs.scrollHeight;
    i++;
    if (i >= responseText.length) clearInterval(typeInterval);
}, 10);
```

---

## 5. Ringkasan Skema Alur Kerja (Workflow)

```text
[ Pengguna ] 
     │ (Pertanyaan Teks / Upload Foto Anggrek)
     ▼
[ Frontend: app.js ] ──> POST /chat (session_id, message, image, history)
     │
     ▼
[ Backend: main.py ]
     ├─ Injeksi Konteks Real-Time (Waktu WIB, latest_telemetry, latest_actuators)
     ├─ Model: gemini-3.5-flash-lite + system_instruction
     │
     ├─ [Function Calling Evaluator]:
     │    ├─ Butuh ubah setpoint?       ──> Jalankan set_greenhouse_thresholds() ──> MQTT Publish PLC
     │    ├─ Tanya riwayat / konsumsi?  ──> Jalankan query_database_stats()      ──> Supabase DB Query
     │    └─ Tanya cuaca besok?         ──> Jalankan get_weather_forecast()      ──> Open-Meteo API
     │
     ├─ Sintesis Jawaban Akhir (Gemini Chat)
     ├─ Simpan Log ke Tabel Supabase (chat_logs)
     │
     ▼
[ Respon JSON: { status: "success", response: "..." } ]
     │
     ▼
[ Frontend: Typewriter Markdown Render ]
```
