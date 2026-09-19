import os
import io
import json
import time
import base64
import asyncio
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

# Load file .env jika ada
load_dotenv()

# Konfigurasi Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("PERINGATAN: GEMINI_API_KEY tidak ditemukan di environment variables. Silakan atur di file .env")

# Konfigurasi MQTT Topics dari Environment Variables
TOPIC_TELEMETRY = os.getenv("TOPIC_TELEMETRY", "esp32/dht11/telemetry")
TOPIC_SOIL = os.getenv("TOPIC_SOIL", "inianggrek/soil")
TOPIC_TDS = os.getenv("TOPIC_TDS", "inianggrek/tds")
TOPIC_PYRA = os.getenv("TOPIC_PYRA", "inianggrek/pyra")
TOPIC_THPR = os.getenv("TOPIC_THPR", "inianggrek/thpr")

TOPIC_CONTROL_MODE = os.getenv("TOPIC_CONTROL_MODE", "inianggrek/control/mode")
TOPIC_CONTROL_SPRAY = os.getenv("TOPIC_CONTROL_SPRAY", "inianggrek/control/spray")
TOPIC_CONTROL_MURNI = os.getenv("TOPIC_CONTROL_MURNI", "inianggrek/control/murni")
TOPIC_CONTROL_NUTRISI = os.getenv("TOPIC_CONTROL_NUTRISI", "inianggrek/control/nutrisi")
TOPIC_CONTROL_EXHAUST = os.getenv("TOPIC_CONTROL_EXHAUST", "inianggrek/control/exhaust")
TOPIC_THRESHOLDS = os.getenv("TOPIC_THRESHOLDS", "inianggrek/thresholds")

TOPIC_SP_SENSOR_PUB = os.getenv("TOPIC_SP_SENSOR_PUB", "inianggrek/sp/outsensor")
TOPIC_SP_SENSOR_SUB = os.getenv("TOPIC_SP_SENSOR_SUB", "inianggrek/sp/sensor")
TOPIC_SP_SENSOR_REC = os.getenv("TOPIC_SP_SENSOR_REC", "inianggrek/sp/stsensor")

TOPIC_SP_NUTRISI_PUB = os.getenv("TOPIC_SP_NUTRISI_PUB", "inianggrek/sp/outnutrisi")
TOPIC_SP_NUTRISI_SUB = os.getenv("TOPIC_SP_NUTRISI_SUB", "inianggrek/sp/nutrisi")
TOPIC_SP_NUTRISI_REC = os.getenv("TOPIC_SP_NUTRISI_REC", "inianggrek/sp/stnutrisi")

TOPIC_SP_DURASI_PUB = os.getenv("TOPIC_SP_DURASI_PUB", "inianggrek/sp/outdurasi")
TOPIC_SP_DURASI_SUB = os.getenv("TOPIC_SP_DURASI_SUB", "inianggrek/sp/durasi")
TOPIC_SP_DURASI_REC = os.getenv("TOPIC_SP_DURASI_REC", "inianggrek/sp/stdurasi")

# Konfigurasi Topik MQTT (Status dari PLC)
TOPIC_STATUS_MODE = os.getenv("TOPIC_STATUS_MODE", "inianggrek/control/modeout")
TOPIC_STATUS_SPRAY = os.getenv("TOPIC_STATUS_SPRAY", "inianggrek/control/outspray")
TOPIC_STATUS_MURNI = os.getenv("TOPIC_STATUS_MURNI", "inianggrek/control/outmurni")
TOPIC_STATUS_NUTRISI = os.getenv("TOPIC_STATUS_NUTRISI", "inianggrek/control/outnutrisi")
TOPIC_STATUS_EXHAUST = os.getenv("TOPIC_STATUS_EXHAUST", "inianggrek/control/outexhaust")

TOPIC_RECEIPT_MODE = os.getenv("TOPIC_RECEIPT_MODE", "inianggrek/control")
TOPIC_RECEIPT_SPRAY = os.getenv("TOPIC_RECEIPT_SPRAY", "inianggrek/control/spraystatus")
TOPIC_RECEIPT_MURNI = os.getenv("TOPIC_RECEIPT_MURNI", "inianggrek/control/murnistatus")
TOPIC_RECEIPT_NUTRISI = os.getenv("TOPIC_RECEIPT_NUTRISI", "inianggrek/control/nutrisistatus")
TOPIC_RECEIPT_EXHAUST = os.getenv("TOPIC_RECEIPT_EXHAUST", "inianggrek/control/exhauststatus")


app = FastAPI(title="Orchid Health Diagnosis API")

LOGGING_INTERVAL_SECONDS = 60

class LogIntervalRequest(BaseModel):
    interval: int

@app.get("/log-interval")
async def get_log_interval():
    return {"interval": LOGGING_INTERVAL_SECONDS}

@app.post("/set-log-interval")
async def set_log_interval(req: LogIntervalRequest):
    global LOGGING_INTERVAL_SECONDS
    LOGGING_INTERVAL_SECONDS = req.interval
    return {"status": "success", "interval": LOGGING_INTERVAL_SECONDS}

# Setup Supabase
from supabase import create_client, Client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error initializing Supabase: {e}")

import paho.mqtt.client as mqtt
import threading

# Global state for latest telemetry from ESP32 & PLC
latest_telemetry = {
    "last_update": 0,
    "air_temperature": 25.0,
    "air_humidity": 74.0,
    "lux": 4500,
    "tds": 210,
    "solar": 150,
    "rssi": 0,
    "meja1": {"suhu": 23.5, "kelembapan": 71, "ec": 1.2, "ph": 6.5},
    "meja2": {"suhu": 23.8, "kelembapan": 68, "ec": 1.1, "ph": 6.2},
    "meja3": {"suhu": 24.1, "kelembapan": 75, "ec": 1.4, "ph": 6.7},
}

latest_setpoints = {
    "sensor": {},
    "nutrisi": {},
    "durasi": {}
}

latest_actuators = {
    "exhaust_fan": 0,
    "penyiraman_air": 0,
    "penyiraman_pupuk": 0,
    "mist_ruangan": 0,
    "mode": "auto"
}

def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("Connected to HiveMQ Cloud!")
        # ----------------------------------------------------------------------------------
        # UBAH NAMA TOPIK DI SINI: Sesuaikan dengan topik MQTT yang dipublish oleh PLC Anda
        # ----------------------------------------------------------------------------------
        client.subscribe(TOPIC_TELEMETRY)
        client.subscribe(TOPIC_SOIL)
        client.subscribe(TOPIC_TDS)
        client.subscribe(TOPIC_PYRA)
        client.subscribe(TOPIC_THPR)
        
        # Subscribe ke status setpoint dari PLC
        client.subscribe(TOPIC_SP_SENSOR_PUB)
        client.subscribe(TOPIC_SP_SENSOR_REC)
        client.subscribe(TOPIC_SP_NUTRISI_PUB)
        client.subscribe(TOPIC_SP_NUTRISI_REC)
        client.subscribe(TOPIC_SP_DURASI_PUB)
        client.subscribe(TOPIC_SP_DURASI_REC)
        
        # Subscribe ke status aktuator
        client.subscribe(TOPIC_STATUS_MODE)
        client.subscribe(TOPIC_STATUS_SPRAY)
        client.subscribe(TOPIC_STATUS_MURNI)
        client.subscribe(TOPIC_STATUS_NUTRISI)
        client.subscribe(TOPIC_STATUS_EXHAUST)
        
        client.subscribe(TOPIC_RECEIPT_MODE)
        client.subscribe(TOPIC_RECEIPT_SPRAY)
        client.subscribe(TOPIC_RECEIPT_MURNI)
        client.subscribe(TOPIC_RECEIPT_NUTRISI)
        client.subscribe(TOPIC_RECEIPT_EXHAUST)
    else:
        print(f"Failed to connect to MQTT broker. Return code: {reason_code}")

def on_mqtt_message(client, userdata, msg):
    global latest_telemetry
    global latest_setpoints
    global latest_actuators
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())
        print(f"MQTT Message received on {topic}: {payload}")
        latest_telemetry["last_update"] = time.time()
        
        if topic == TOPIC_TELEMETRY:
            if "suhu" in payload: latest_telemetry["air_temperature"] = float(payload["suhu"])
            if "kelembapan" in payload: latest_telemetry["air_humidity"] = float(payload["kelembapan"])
            if "lux" in payload: latest_telemetry["lux"] = float(payload["lux"])
            elif "solar" in payload: latest_telemetry["lux"] = float(payload["solar"])
            if "tds" in payload: latest_telemetry["tds"] = float(payload["tds"])
            if "rssi" in payload: latest_telemetry["rssi"] = int(payload["rssi"])
            
        elif topic == TOPIC_TDS:
            if "TDS" in payload: latest_telemetry["tds"] = float(payload["TDS"])
            
        elif topic == TOPIC_PYRA:
            if "Pyrano" in payload: latest_telemetry["lux"] = float(payload["Pyrano"])
            
        elif topic == TOPIC_THPR:
            if "thp_suhu" in payload: latest_telemetry["air_temperature"] = round(float(payload["thp_suhu"]) / 10.0, 1)
            if "thp_hum" in payload: latest_telemetry["air_humidity"] = round(float(payload["thp_hum"]) / 10.0, 1)
            
        elif topic == TOPIC_SOIL:
            # Parsing Data Meja 1
            if "m1_suhu" in payload: latest_telemetry["meja1"]["suhu"] = round(float(payload["m1_suhu"]) / 10.0, 1)
            if "m1_kelembapan" in payload: latest_telemetry["meja1"]["kelembapan"] = round(float(payload["m1_kelembapan"]) / 10.0, 1)
            if "m1_EC" in payload: latest_telemetry["meja1"]["ec"] = round(float(payload["m1_EC"]) / 10.0, 1)
            if "m1_pH" in payload: latest_telemetry["meja1"]["ph"] = round(float(payload["m1_pH"]) / 10.0, 1)
            
            # Parsing Data Meja 2
            if "m2_suhu" in payload: latest_telemetry["meja2"]["suhu"] = round(float(payload["m2_suhu"]) / 10.0, 1)
            if "m2_kelembapan" in payload: latest_telemetry["meja2"]["kelembapan"] = round(float(payload["m2_kelembapan"]) / 10.0, 1)
            if "m2_EC" in payload: latest_telemetry["meja2"]["ec"] = round(float(payload["m2_EC"]) / 10.0, 1)
            if "m2_pH" in payload: latest_telemetry["meja2"]["ph"] = round(float(payload["m2_pH"]) / 10.0, 1)
            
            # Parsing Data Meja 3
            if "m3_suhu" in payload: latest_telemetry["meja3"]["suhu"] = round(float(payload["m3_suhu"]) / 10.0, 1)
            if "m3_kelembapan" in payload: latest_telemetry["meja3"]["kelembapan"] = round(float(payload["m3_kelembapan"]) / 10.0, 1)
            if "m3_EC" in payload: latest_telemetry["meja3"]["ec"] = round(float(payload["m3_EC"]) / 10.0, 1)
            if "m3_pH" in payload: latest_telemetry["meja3"]["ph"] = round(float(payload["m3_pH"]) / 10.0, 1)
            
        elif topic in [TOPIC_SP_SENSOR_PUB, TOPIC_SP_SENSOR_REC]:
            latest_setpoints["sensor"] = payload
            
        elif topic in [TOPIC_SP_NUTRISI_PUB, TOPIC_SP_NUTRISI_REC]:
            latest_setpoints["nutrisi"] = payload
            
        elif topic in [TOPIC_SP_DURASI_PUB, TOPIC_SP_DURASI_REC]:
            latest_setpoints["durasi"] = payload
            
        elif topic == TOPIC_STATUS_MODE:
            latest_actuators["mode"] = "auto" if payload.get("Mode", False) else "manual"
            
        elif topic == TOPIC_STATUS_SPRAY:
            latest_actuators["mist_ruangan"] = 1 if payload.get("Spray", False) else 0
            
        elif topic == TOPIC_STATUS_MURNI:
            latest_actuators["penyiraman_air"] = 1 if payload.get("Murni", False) else 0
            
        elif topic == TOPIC_STATUS_NUTRISI:
            latest_actuators["penyiraman_pupuk"] = 1 if payload.get("Nutrisi", False) else 0
            
        elif topic == TOPIC_STATUS_EXHAUST:
            latest_actuators["exhaust_fan"] = 1 if payload.get("Fan", False) else 0
            
    except Exception as e:
        print(f"Error parsing MQTT message: {e}")

mqtt_client_instance = None

def start_mqtt_client():
    global mqtt_client_instance
    mqtt_host = os.getenv("MQTT_HOST")
    mqtt_port = int(os.getenv("MQTT_PORT", 8883))
    mqtt_user = os.getenv("MQTT_USERNAME")
    mqtt_pass = os.getenv("MQTT_PASSWORD")

    if not mqtt_host:
        print("MQTT_HOST not configured in .env")
        return

    # Use paho-mqtt v2 callback style compatible
    client = mqtt.Client(client_id="fastapi_backend", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    
    # Gunakan enkripsi TLS (SSL) hanya jika port menggunakan 8883
    if mqtt_port == 8883:
        client.tls_set() 
        
    # Gunakan username/password hanya jika didefinisikan di .env
    if mqtt_user and mqtt_pass:
        client.username_pw_set(mqtt_user, mqtt_pass)
        
    client.on_connect = on_mqtt_connect
    client.on_message = on_mqtt_message
    
    try:
        client.connect(mqtt_host, mqtt_port, 60)
        client.loop_start()
        mqtt_client_instance = client
    except Exception as e:
        print(f"Error connecting to MQTT: {e}")

async def log_telemetry_to_supabase():
    while True:
        await asyncio.sleep(LOGGING_INTERVAL_SECONDS)
        if supabase:
            try:
                data = {
                    "air_temperature": latest_telemetry.get("air_temperature"),
                    "air_humidity": latest_telemetry.get("air_humidity"),
                    "lux": latest_telemetry.get("lux"),
                    "tds": latest_telemetry.get("tds"),
                    "m1_suhu": latest_telemetry.get("meja1", {}).get("suhu"),
                    "m1_humid": latest_telemetry.get("meja1", {}).get("kelembapan"),
                    "m1_ec": latest_telemetry.get("meja1", {}).get("ec"),
                    "m1_ph": latest_telemetry.get("meja1", {}).get("ph"),
                    "m2_suhu": latest_telemetry.get("meja2", {}).get("suhu"),
                    "m2_humid": latest_telemetry.get("meja2", {}).get("kelembapan"),
                    "m2_ec": latest_telemetry.get("meja2", {}).get("ec"),
                    "m2_ph": latest_telemetry.get("meja2", {}).get("ph"),
                    "m3_suhu": latest_telemetry.get("meja3", {}).get("suhu"),
                    "m3_humid": latest_telemetry.get("meja3", {}).get("kelembapan"),
                    "m3_ec": latest_telemetry.get("meja3", {}).get("ec"),
                    "m3_ph": latest_telemetry.get("meja3", {}).get("ph")
                }
                supabase.table("sensor_logs").insert(data).execute()
                
                # Log aktuator ke tabel terpisah
                actuator_data = {
                    "exhaust_fan": latest_actuators.get("exhaust_fan", 0),
                    "penyiraman_air": latest_actuators.get("penyiraman_air", 0),
                    "penyiraman_pupuk": latest_actuators.get("penyiraman_pupuk", 0),
                    "mist_ruangan": latest_actuators.get("mist_ruangan", 0),
                    "mode": latest_actuators.get("mode", "auto")
                }
                supabase.table("actuator_logs").insert(actuator_data).execute()
                
            except Exception as e:
                print(f"Error logging telemetry to Supabase: {e}")

background_tasks_set = set()

@app.on_event("startup")
async def startup_event():
    start_mqtt_client()
    task = asyncio.create_task(log_telemetry_to_supabase())
    background_tasks_set.add(task)
    task.add_done_callback(background_tasks_set.discard)

async def auto_off_actuator(payload_data: dict, device: str, delay: int = 3):
    await asyncio.sleep(delay)
    if mqtt_client_instance:
        try:
            if device == "mist_ruangan":
                topic = TOPIC_CONTROL_SPRAY
                payload = {"Spray": False}
            elif device == "penyiraman_air":
                topic = TOPIC_CONTROL_MURNI
                payload = {"Murni": False}
            elif device == "penyiraman_pupuk":
                topic = TOPIC_CONTROL_NUTRISI
                payload = {"Nutrisi": False}
            else:
                return
                
            mqtt_client_instance.publish(topic, json.dumps(payload))
            print(f"Auto-OFF sent for {device} after {delay}s")
        except Exception as e:
            print(f"Error publishing auto-OFF for {device}: {e}")

# Middleware CORS agar frontend bisa mengakses API secara eksternal jika dideploy terpisah
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (gambar background, dll) dari direktori project
app.mount("/static", StaticFiles(directory=os.path.dirname(os.path.abspath(__file__))), name="static")

# Route untuk menampilkan halaman utama (Frontend)
@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(index_path):
        return "<h3>File index.html tidak ditemukan.</h3>"
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

# Endpoint untuk mendiagnosis gambar anggrek
@app.post("/diagnose")
async def diagnose_orchid(file: UploadFile = File(...)):
    # 1. Validasi tipe file
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Format gambar harus JPEG, PNG, atau WebP")
    
    # 2. Pastikan API key sudah diatur
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=500, 
            detail="API Key Gemini belum dikonfigurasi. Silakan buat file .env dan isi GEMINI_API_KEY."
        )

    try:
        # 3. Baca data gambar ke PIL Image
        image_data = await file.read()
        image = Image.open(io.BytesIO(image_data))
        
        # 4. Inisialisasi model Gemini 3.5 Flash Lite (tersedia & berjalan di API key ini)
        model = genai.GenerativeModel('gemini-3.5-flash-lite')
        
        prompt = (
            "Anda adalah pakar botani spesialis tanaman anggrek. Analisis foto anggrek ini.\n"
            "Tentukan apakah tanaman tersebut sehat atau sakit.\n"
            "Jika terdeteksi penyakit/hama:\n"
            "- Sebutkan nama penyakit/masalahnya\n"
            "- Sebutkan gejala visual yang Anda lihat di foto\n"
            "- Berikan penjelasan penyebabnya secara singkat\n"
            "- Berikan langkah penanganan/solusi praktis dan obat yang direkomendasikan.\n\n"
            "Gunakan bahasa Indonesia yang jelas, sopan, dan terstruktur dengan baik (gunakan bullet points)."
        )
        
        # Kirim ke model
        response = model.generate_content([prompt, image])
        
        return {
            "status": "success",
            "diagnosis": response.text
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan saat memproses gambar: {str(e)}")

import datetime

class SetpointSensor(BaseModel):
    Suhu_Siang: float
    Suhu_Malam: float
    Hum_low: float
    TDS_Sp: float
    Soil_Temp: float
    Soil_moist: float

class SetpointNutrisi(BaseModel):
    Senin: bool
    Selasa: bool
    Rabu: bool
    Kamis: bool
    Jumat: bool
    Sabtu: bool
    Minggu: bool
    Jam: int

class SetpointDurasi(BaseModel):
    mist_on: int
    mist_off: int
    murni_on: int
    murni_off: int
    nutrisi_on: int
    nutrisi_off: int

# Model Input untuk Data Sensor Greenhouse yang Lengkap
class SoilSensor(BaseModel):
    suhu: float
    kelembapan: float
    ec: float
    ph: float

class ActuatorActions(BaseModel):
    exhaust_fan: int
    penyiraman_air: int
    penyiraman_pupuk: int
    mist_ruangan: int

class GreenhouseMetrics(BaseModel):
    air_temperature: float
    air_humidity: float
    lux: float             # Lux Light Level
    tds: float             # Total Dissolved Solids (ppm)
    meja1: SoilSensor
    meja2: SoilSensor
    meja3: SoilSensor
    mode: str = "auto"     # "auto" atau "manual"
    manual_actions: Optional[ActuatorActions] = None

# Model untuk Obrolan Chat Dokter Anggrek
class ChatMessage(BaseModel):
    role: str              # "user" atau "model"
    content: str

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    image: Optional[str] = None
    history: list[ChatMessage] = []

# Penyimpanan Data Logger di memori
sensor_logs = [
    {
        "timestamp": (datetime.datetime.now() - datetime.timedelta(hours=4)).strftime("%d-%m-%Y %H:%M:%S"),
        "air_temperature": 24.5,
        "air_humidity": 75.0,
        "lux": 1800.0,
        "tds": 220.0,
        "meja1": {"suhu": 23.2, "kelembapan": 68.0, "ec": 1.2, "ph": 6.5},
        "meja2": {"suhu": 23.5, "kelembapan": 69.0, "ec": 1.1, "ph": 6.2},
        "meja3": {"suhu": 23.1, "kelembapan": 67.0, "ec": 1.3, "ph": 6.7},
        "actions": {"exhaust_fan": 0, "penyiraman_air": 0, "penyiraman_pupuk": 0, "mist_ruangan": 0},
        "rekomendasi": "Kondisi greenhouse sangat optimal untuk pertumbuhan anggrek. Suhu udara sejuk dan kelembapan udara terjaga dengan baik."
    },
    {
        "timestamp": (datetime.datetime.now() - datetime.timedelta(hours=3)).strftime("%d-%m-%Y %H:%M:%S"),
        "air_temperature": 28.5,
        "air_humidity": 68.0,
        "lux": 3600.0,
        "tds": 220.0,
        "meja1": {"suhu": 24.8, "kelembapan": 65.0, "ec": 1.2, "ph": 6.5},
        "meja2": {"suhu": 25.1, "kelembapan": 64.0, "ec": 1.1, "ph": 6.2},
        "meja3": {"suhu": 24.5, "kelembapan": 66.0, "ec": 1.3, "ph": 6.7},
        "actions": {"exhaust_fan": 1, "penyiraman_air": 0, "penyiraman_pupuk": 0, "mist_ruangan": 1},
        "rekomendasi": "Suhu udara melampaui batas optimal (28.5°C) dan intensitas cahaya matahari tinggi (3600 Lux). Kipas exhaust diaktifkan untuk sirkulasi udara."
    },
    {
        "timestamp": (datetime.datetime.now() - datetime.timedelta(hours=2)).strftime("%d-%m-%Y %H:%M:%S"),
        "air_temperature": 25.8,
        "air_humidity": 72.0,
        "lux": 2500.0,
        "tds": 210.0,
        "meja1": {"suhu": 24.0, "kelembapan": 55.0, "ec": 1.2, "ph": 6.5},
        "meja2": {"suhu": 24.2, "kelembapan": 53.0, "ec": 1.1, "ph": 6.2},
        "meja3": {"suhu": 23.8, "kelembapan": 56.0, "ec": 1.3, "ph": 6.7},
        "actions": {"exhaust_fan": 0, "penyiraman_air": 1, "penyiraman_pupuk": 0, "mist_ruangan": 0},
        "rekomendasi": "Kelembapan tanah rata-rata berada di bawah batas optimal. Pompa siram meja diaktifkan untuk menyiram media tanam anggrek agar kelembapan kembali ke rentang optimal 60-80%."
    },
    {
        "timestamp": (datetime.datetime.now() - datetime.timedelta(hours=1)).strftime("%d-%m-%Y %H:%M:%S"),
        "air_temperature": 25.0,
        "air_humidity": 74.0,
        "lux": 4500.0,
        "tds": 210.0,
        "meja1": {"suhu": 23.5, "kelembapan": 71.0, "ec": 1.2, "ph": 6.5},
        "meja2": {"suhu": 23.8, "kelembapan": 68.0, "ec": 1.1, "ph": 6.2},
        "meja3": {"suhu": 24.1, "kelembapan": 75.0, "ec": 1.4, "ph": 6.7},
        "actions": {"exhaust_fan": 0, "penyiraman_air": 0, "penyiraman_pupuk": 0, "mist_ruangan": 0},
        "rekomendasi": "Seluruh parameter klimatologi, tanah, dan air saat ini berada dalam kondisi ideal."
    }
]

# Endpoint untuk menganalisis data sensor klimatologi lengkap greenhouse
@app.post("/analyze-metrics")
async def analyze_greenhouse_metrics(metrics: GreenhouseMetrics):
    # Pastikan API key sudah diatur
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=500, 
            detail="API Key Gemini belum dikonfigurasi. Silakan buat file .env dan isi GEMINI_API_KEY."
        )

    try:
        model = genai.GenerativeModel('gemini-3.5-flash-lite')
        
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
        
        # Panggil Gemini dengan response_mime_type untuk memastikan keluaran berupa JSON valid
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        result_json = json.loads(response.text)
        
        # Tentukan tindakan akhir yang dicatat (berdasarkan mode)
        final_actions = {}
        if metrics.mode == "manual" and metrics.manual_actions:
            final_actions = {
                "exhaust_fan": metrics.manual_actions.exhaust_fan,
                "penyiraman_air": metrics.manual_actions.penyiraman_air,
                "penyiraman_pupuk": metrics.manual_actions.penyiraman_pupuk,
                "mist_ruangan": metrics.manual_actions.mist_ruangan
            }
        else:
            final_actions = result_json.get("actions", {})

        # Update latest_actuators global state agar dicatat oleh Supabase logger
        global latest_actuators
        latest_actuators.update(final_actions)
        latest_actuators["mode"] = metrics.mode

        # Update latest telemetry global state agar data dashboard sinkron dengan custom dummy
        latest_telemetry["air_temperature"] = metrics.air_temperature
        latest_telemetry["air_humidity"] = metrics.air_humidity
        latest_telemetry["tds"] = metrics.tds
        latest_telemetry["lux"] = metrics.lux
        latest_telemetry["meja1"]["suhu"] = metrics.meja1.suhu
        latest_telemetry["meja1"]["kelembapan"] = metrics.meja1.kelembapan
        latest_telemetry["meja1"]["ec"] = metrics.meja1.ec
        latest_telemetry["meja1"]["ph"] = metrics.meja1.ph
        latest_telemetry["meja2"]["suhu"] = metrics.meja2.suhu
        latest_telemetry["meja2"]["kelembapan"] = metrics.meja2.kelembapan
        latest_telemetry["meja2"]["ec"] = metrics.meja2.ec
        latest_telemetry["meja2"]["ph"] = metrics.meja2.ph
        latest_telemetry["meja3"]["suhu"] = metrics.meja3.suhu
        latest_telemetry["meja3"]["kelembapan"] = metrics.meja3.kelembapan
        latest_telemetry["meja3"]["ec"] = metrics.meja3.ec
        latest_telemetry["meja3"]["ph"] = metrics.meja3.ph

        # Catat ke dalam Data Logger
        new_log = {
            "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
            "air_temperature": metrics.air_temperature,
            "air_humidity": metrics.air_humidity,
            "lux": metrics.lux,
            "tds": metrics.tds,
            "meja1": {"suhu": metrics.meja1.suhu, "kelembapan": metrics.meja1.kelembapan, "ec": metrics.meja1.ec, "ph": metrics.meja1.ph},
            "meja2": {"suhu": metrics.meja2.suhu, "kelembapan": metrics.meja2.kelembapan, "ec": metrics.meja2.ec, "ph": metrics.meja2.ph},
            "meja3": {"suhu": metrics.meja3.suhu, "kelembapan": metrics.meja3.kelembapan, "ec": metrics.meja3.ec, "ph": metrics.meja3.ph},
            "actions": final_actions,
            "rekomendasi": result_json.get("rekomendasi", "Hasil analisis klimatologi greenhouse.")
        }
        sensor_logs.append(new_log)
        
        # Batasi log maksimal 100 entri terakhir
        if len(sensor_logs) > 100:
            sensor_logs.pop(0)
            
        # Cek apakah PLC offline (tidak ada data lebih dari 60 detik)
        plc_offline = (time.time() - latest_telemetry.get("last_update", 0)) > 60

        # Jika mode auto dan PLC aktif, kirim command MQTT secara otomatis ke aktuator
        if metrics.mode == "auto" and mqtt_client_instance and not plc_offline:
            try:
                mqtt_client_instance.publish(TOPIC_CONTROL_MODE, json.dumps({"Mode": False}))
                if final_actions.get("mist_ruangan", 0) == 1:
                    mqtt_client_instance.publish(TOPIC_CONTROL_SPRAY, json.dumps({"Spray": True}))
                if final_actions.get("penyiraman_air", 0) == 1:
                    mqtt_client_instance.publish(TOPIC_CONTROL_MURNI, json.dumps({"Murni": True}))
                if final_actions.get("penyiraman_pupuk", 0) == 1:
                    mqtt_client_instance.publish(TOPIC_CONTROL_NUTRISI, json.dumps({"Nutrisi": True}))
                if final_actions.get("exhaust_fan", 0) == 1:
                    mqtt_client_instance.publish(TOPIC_CONTROL_EXHAUST, json.dumps({"Fan": True}))
                
                # Trigger auto off after 3 seconds for water/mist devices
                for device, state in final_actions.items():
                    if state == 1 and device in ["penyiraman_air", "penyiraman_pupuk", "mist_ruangan"]:
                        asyncio.create_task(auto_off_actuator(final_actions, device, 3))
            except Exception as e:
                print(f"Error publishing auto command: {e}")

        return result_json
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan saat menganalisis data sensor: {str(e)}")

# Endpoint untuk mengambil data log riwayat parameter greenhouse
@app.get("/get-logs")
async def get_logs():
    if supabase:
        try:
            # Mengambil 50 data terbaru dari supabase
            response = supabase.table("sensor_logs").select("*").order("created_at", desc=True).limit(50).execute()
            act_response = supabase.table("actuator_logs").select("*").order("created_at", desc=True).limit(50).execute()
            act_list = act_response.data
            
            # Format output agar sesuai dengan bentuk "sensor_logs" yang diharapkan frontend
            formatted_logs = []
            import datetime
            for row in reversed(response.data): 
                # Waktu di Supabase adalah format ISO 8601 UTC (2026-08-25T15:23:45+00:00).
                # Kita ubah ke zona waktu lokal (WIB = UTC+7) dan ambil jam:menit:detik
                ts_str = row.get("created_at", "")
                
                # Cari act_row yang waktunya cocok (di menit yang sama)
                prefix = ts_str[:16] if ts_str else ""
                act_row = {}
                for a in act_list:
                    if a.get("created_at", "").startswith(prefix):
                        act_row = a
                        break

                ts = ts_str
                if "T" in ts:
                    try:
                        # Parse UTC string ke datetime object
                        utc_dt = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                        # Tambah 7 jam untuk WIB
                        local_dt = utc_dt + datetime.timedelta(hours=7)
                        # Format ke string jam:menit:detik
                        ts = local_dt.strftime("%H:%M:%S")
                    except Exception:
                        ts = ts.split("T")[1][:8]
                        
                formatted_logs.append({
                    "timestamp": ts,
                    "air_temperature": row.get("air_temperature"),
                    "air_humidity": row.get("air_humidity"),
                    "lux": row.get("lux"),
                    "tds": row.get("tds"),
                    "meja1": {"suhu": row.get("m1_suhu"), "kelembapan": row.get("m1_humid"), "ec": row.get("m1_ec"), "ph": row.get("m1_ph")},
                    "meja2": {"suhu": row.get("m2_suhu"), "kelembapan": row.get("m2_humid"), "ec": row.get("m2_ec"), "ph": row.get("m2_ph")},
                    "meja3": {"suhu": row.get("m3_suhu"), "kelembapan": row.get("m3_humid"), "ec": row.get("m3_ec"), "ph": row.get("m3_ph")},
                    "actions": {
                        "exhaust_fan": act_row.get("exhaust_fan", 0),
                        "penyiraman_air": act_row.get("penyiraman_air", 0),
                        "penyiraman_pupuk": act_row.get("penyiraman_pupuk", 0),
                        "mist_ruangan": act_row.get("mist_ruangan", 0)
                    }
                })
            return {"status": "success", "logs": formatted_logs}
        except Exception as e:
            print(f"Error fetching logs from Supabase: {e}")
            
    return {"status": "success", "logs": sensor_logs}

# Endpoint untuk obrolan interaktif konsultasi anggrek (chatbot terbatas konteks anggrek)

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
        "Hum_low": hum_low,
        "TDS_Sp": tds_sp,
        "Soil_Temp": soil_temp,
        "Soil_moist": soil_moist
    }
    try:
        mqtt_client_instance.publish(TOPIC_SP_SENSOR_SUB, json.dumps(payload_dict))
        return f"Berhasil mengirim pengaturan threshold ke sistem IoT: {json.dumps(payload_dict)}"
    except Exception as e:
        return f"Gagal mengatur threshold karena error: {str(e)}"

@app.post("/chat")
async def chat_orchid(request: ChatRequest):
    # Pastikan API key sudah diatur
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=500, 
            detail="API Key Gemini belum dikonfigurasi. Silakan buat file .env dan isi GEMINI_API_KEY."
        )

    try:
        # Gunakan system_instruction untuk membatasi ke topik anggrek saja
        # Injeksi kondisi live
        live_telemetry_str = json.dumps(latest_telemetry)
        live_actuator_str = json.dumps(latest_actuators)
        
        system_instruction = (
            "Anda adalah Dokter Anggrek AI, pakar botani spesialis tanaman anggrek terintegrasi dengan sistem IoT Greenhouse.\n\n"
            f"KONDISI GREENHOUSE SAAT INI (REAL-TIME):\n- Data Sensor: {live_telemetry_str}\n- Status Aktuator: {live_actuator_str}\n\n"
            "Tugas Anda:\n"
            "1. Menjawab pertanyaan pengguna tentang anggrek (perawatan, penyakit, hama, pemupukan, dll).\n"
            "2. Anda BOLEH membaca dan menganalisis KONDISI GREENHOUSE SAAT INI di atas jika pengguna bertanya tentang keadaan greenhouse (contoh: 'Berapa suhu sekarang?', 'Apakah GH aman?').\n"
            "3. Jika Anda menilai kondisinya tidak wajar (misal suhu >35C atau <20C, kelembapan terlalu rendah), sarankan solusi atau perubahan batas suhu.\n"
            "4. Jika pengguna meminta Anda untuk menyetel, mengubah, atau menerapkan parameter (misalnya 'atur parameter ke suhu 28', 'bantu setel parameter yang ideal'), Anda memiliki ALAT (Function Calling) bernama `set_greenhouse_thresholds` untuk mengubahnya secara langsung! Eksekusi alat tersebut dengan angka yang tepat untuk Suhu Siang, Suhu Malam, Hum low, TDS, dll sesuai standar anggrek (seperti Phalaenopsis atau Dendrobium) atau sesuai angka permintaan pengguna.\n\n"
            "PENTING: Anda hanya boleh membahas hal seputar anggrek dan kendali Greenhouse. Tolak pertanyaan di luar itu dengan sopan."
        )
        
        model = genai.GenerativeModel(
            model_name='gemini-3.5-flash-lite',
            system_instruction=system_instruction,
            tools=[set_greenhouse_thresholds]
        )
        
        # Konversi history ke format API SDK Gemini
        gemini_history = []
        for msg in request.history:
            gemini_history.append({
                "role": "user" if msg.role == "user" else "model",
                "parts": [msg.content]
            })
            
        chat = model.start_chat(history=gemini_history, enable_automatic_function_calling=True)

        # Siapkan payload pesan (bisa berupa teks saja atau multimodal dengan gambar PIL)
        message_parts = []
        pil_image = None
        if request.image:
            try:
                # Format request.image bisa berupa data URI: data:image/png;base64,... atau raw base64
                img_data_str = request.image
                if "," in img_data_str:
                    img_data_str = img_data_str.split(",", 1)[1]
                img_bytes = base64.b64decode(img_data_str)
                pil_image = Image.open(io.BytesIO(img_bytes))
                message_parts.append(pil_image)
            except Exception as img_err:
                print(f"Error decoding chat image: {img_err}")

        text_prompt = request.message.strip() if request.message else ""
        if not text_prompt and pil_image:
            text_prompt = "Tolong periksa dan analisis kondisi tanaman anggrek pada foto ini. Apakah tanaman ini sehat atau mengalami penyakit/hama? Berikan penjelasan gejala dan solusi penanganannya."

        if text_prompt:
            message_parts.append(text_prompt)

        # Kirim ke Gemini Chat
        if len(message_parts) == 1 and isinstance(message_parts[0], str):
            response = chat.send_message(message_parts[0])
        else:
            response = chat.send_message(message_parts)
        
        if supabase:
            try:
                sid = request.session_id if request.session_id else "default"
                # Coba simpan dengan kolom session_id asli
                log_user_msg = request.message if request.message else "[Foto Anggrek Terlampir]"
                try:
                    supabase.table("chat_logs").insert({"session_id": sid, "role": "user", "message": log_user_msg}).execute()
                    supabase.table("chat_logs").insert({"session_id": sid, "role": "model", "message": response.text}).execute()
                except Exception:
                    # Fallback jika kolom session_id belum dibuat di tabel: encode session_id di dalam JSON message
                    u_msg = json.dumps({"sid": sid, "text": log_user_msg})
                    m_msg = json.dumps({"sid": sid, "text": response.text})
                    supabase.table("chat_logs").insert({"role": "user", "message": u_msg}).execute()
                    supabase.table("chat_logs").insert({"role": "model", "message": m_msg}).execute()
            except Exception as e:
                print(f"Error logging chat to Supabase: {e}")
        
        return {
            "status": "success",
            "response": response.text
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan pada chatbot: {str(e)}")

@app.delete("/chat-history/{session_id}")
async def delete_chat_history(session_id: str):
    if not supabase:
        raise HTTPException(status_code=500, detail="Database tidak tersedia")
    try:
        try:
            supabase.table("chat_logs").delete().eq("session_id", session_id).execute()
            return {"status": "success", "message": "Riwayat chat berhasil dihapus"}
        except Exception:
            pass
            
        res = supabase.table("chat_logs").select("id, message").execute()
        ids_to_delete = []
        for row in res.data:
            msg_raw = row.get("message", "")
            if msg_raw.startswith('{"sid":'):
                try:
                    parsed = json.loads(msg_raw)
                    if parsed.get("sid") == session_id:
                        ids_to_delete.append(row["id"])
                except Exception:
                    pass
        
        if ids_to_delete:
            for row_id in ids_to_delete:
                supabase.table("chat_logs").delete().eq("id", row_id).execute()
                
        return {"status": "success", "message": "Riwayat chat berhasil dihapus (fallback)"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menghapus riwayat chat: {str(e)}")

@app.get("/recent-chats")
async def get_recent_chats(client_id: str = None):
    if not supabase:
        return {"status": "success", "data": []}
    
    try:
        # Coba query dengan kolom session_id jika ada
        try:
            query = supabase.table("chat_logs").select("session_id, message, created_at").eq("role", "user")
            if client_id:
                query = query.like("session_id", f"{client_id}%")
            res = query.order("created_at", desc=False).execute()
            sessions = {}
            for row in res.data:
                sid = row.get("session_id")
                if sid and sid not in sessions:
                    title = row.get("message", "")[:32]
                    if len(row.get("message", "")) > 32: title += "..."
                    sessions[sid] = {
                        "session_id": sid,
                        "title": title,
                        "created_at": row.get("created_at")
                    }
            if sessions:
                sorted_sessions = sorted(list(sessions.values()), key=lambda x: x.get("created_at", ""), reverse=True)
                return {"status": "success", "data": sorted_sessions}
        except Exception:
            pass

        # Fallback: Ambil pesan dari chat_logs dan parse sesi terkelompok
        res = supabase.table("chat_logs").select("id, role, message, created_at").order("created_at", desc=False).limit(200).execute()
        sessions = {}
        for row in res.data:
            msg_raw = row.get("message", "")
            role = row.get("role", "")
            created_at = row.get("created_at", "")
            
            sid = None
            text = msg_raw
            # Deteksi apakah pesan ter-encode dengan session JSON
            if msg_raw.startswith('{"sid":'):
                try:
                    parsed = json.loads(msg_raw)
                    sid = parsed.get("sid")
                    text = parsed.get("text", "")
                except Exception:
                    pass

            if sid:
                # Sesi modern berbasis session_id
                if client_id and not sid.startswith(client_id):
                    continue # Lewati jika bukan milik client ini
                if role == "user" and sid not in sessions:
                    title = text[:32]
                    if len(text) > 32: title += "..."
                    sessions[sid] = {
                        "session_id": sid,
                        "title": title,
                        "created_at": created_at
                    }
            else:
                # Pesan lama legacy tanpa session_id
                if not client_id: # Hanya tampilkan legacy jika client_id tidak difilter (atau untuk retro-compatibility)
                    if role == "user" and "legacy-session" not in sessions:
                        title = text[:32]
                        if len(text) > 32: title += "..."
                        sessions["legacy-session"] = {
                            "session_id": "legacy-session",
                            "title": title,
                            "created_at": created_at
                        }

        sorted_sessions = sorted(list(sessions.values()), key=lambda x: x.get("created_at", ""), reverse=True)
        return {"status": "success", "data": sorted_sessions}
    except Exception as e:
        print(f"Error fetching recent chats: {e}")
        return {"status": "success", "data": []}

@app.get("/chat-history/{session_id}")
async def get_chat_history(session_id: str):
    if not supabase:
        return {"status": "success", "data": []}
    
    try:
        # Coba query dengan kolom session_id asli
        try:
            res = supabase.table("chat_logs").select("role, message").eq("session_id", session_id).order("created_at", desc=False).execute()
            if res.data:
                return {"status": "success", "data": res.data}
        except Exception:
            pass

        # Fallback query: filter pesan berdasarkan session_id yang ter-encode di JSON message
        res = supabase.table("chat_logs").select("id, role, message, created_at").order("created_at", desc=False).limit(300).execute()
        history = []
        for row in res.data:
            msg_raw = row.get("message", "")
            role = row.get("role", "")
            if msg_raw.startswith('{"sid":'):
                try:
                    parsed = json.loads(msg_raw)
                    if parsed.get("sid") == session_id:
                        history.append({"role": role, "message": parsed.get("text", "")})
                except Exception:
                    pass
            elif session_id == "legacy-session":
                history.append({"role": role, "message": msg_raw})

        return {"status": "success", "data": history}
    except Exception as e:
        print(f"Error fetching chat history: {e}")
        return {"status": "success", "data": []}

class ControlRequest(BaseModel):
    device: str
    state: int
    payload_data: dict

@app.post("/control-actuator")
async def control_actuator(req: ControlRequest, background_tasks: BackgroundTasks):
    global mqtt_client_instance
    if not mqtt_client_instance:
        raise HTTPException(status_code=500, detail="MQTT Client not connected")
    
    # Cek apakah PLC offline
    if (time.time() - latest_telemetry.get("last_update", 0)) > 60:
        raise HTTPException(status_code=503, detail="PLC Offline, command not sent.")
    
    try:
        if req.device == "mode_switch":
            topic = TOPIC_CONTROL_MODE
            payload = json.dumps({"Mode": bool(req.state)})
        elif req.device == "mist_ruangan":
            topic = TOPIC_CONTROL_SPRAY
            payload = json.dumps({"Spray": bool(req.payload_data.get("Spray", False))})
        elif req.device == "penyiraman_air":
            topic = TOPIC_CONTROL_MURNI
            payload = json.dumps({"Murni": bool(req.payload_data.get("Murni", False))})
        elif req.device == "penyiraman_pupuk":
            topic = TOPIC_CONTROL_NUTRISI
            payload = json.dumps({"Nutrisi": bool(req.payload_data.get("Nutrisi", False))})
        elif req.device == "exhaust_fan":
            topic = TOPIC_CONTROL_EXHAUST
            payload = json.dumps({"Fan": bool(req.payload_data.get("Fan", False))})
        else:
            topic = f"inianggrek/control/{req.device}"
            payload = json.dumps({"status": req.state})

        mqtt_client_instance.publish(topic, payload)

        return {"status": "success", "message": f"Command sent to {topic}", "payload": payload}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send MQTT command: {str(e)}")

# Endpoint untuk mengambil data sensor terbaru dari MQTT
@app.get("/latest-telemetry")
async def get_latest_telemetry():
    return latest_telemetry

@app.post("/publish-thresholds")
async def publish_thresholds(req: dict):
    global mqtt_client_instance
    if not mqtt_client_instance:
        raise HTTPException(status_code=500, detail="MQTT Client not connected")
    
    # Publikasikan langsung data konfigurasi (sebagai JSON string) ke MQTT broker
    topic = TOPIC_THRESHOLDS
    payload = json.dumps(req)
    
    try:
        mqtt_client_instance.publish(topic, payload)
        return {"status": "success", "message": f"Thresholds sent to {topic}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send MQTT command: {str(e)}")

@app.post("/setpoint/sensor")
async def setpoint_sensor(req: SetpointSensor):
    global mqtt_client_instance
    if not mqtt_client_instance:
        raise HTTPException(status_code=500, detail="MQTT Client not connected")
    payload = json.dumps(req.model_dump() if hasattr(req, "model_dump") else req.dict())
    try:
        mqtt_client_instance.publish(TOPIC_SP_SENSOR_SUB, payload)
        return {"status": "success", "message": f"Setpoint sent to {TOPIC_SP_SENSOR_SUB}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send MQTT command: {str(e)}")

@app.post("/setpoint/nutrisi")
async def setpoint_nutrisi(req: SetpointNutrisi):
    global mqtt_client_instance
    if not mqtt_client_instance:
        raise HTTPException(status_code=500, detail="MQTT Client not connected")
    payload = json.dumps(req.model_dump() if hasattr(req, "model_dump") else req.dict())
    try:
        mqtt_client_instance.publish(TOPIC_SP_NUTRISI_SUB, payload)
        return {"status": "success", "message": f"Setpoint sent to {TOPIC_SP_NUTRISI_SUB}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send MQTT command: {str(e)}")

@app.post("/setpoint/durasi")
async def setpoint_durasi(req: SetpointDurasi):
    global mqtt_client_instance
    if not mqtt_client_instance:
        raise HTTPException(status_code=500, detail="MQTT Client not connected")
    payload = json.dumps(req.model_dump() if hasattr(req, "model_dump") else req.dict())
    try:
        mqtt_client_instance.publish(TOPIC_SP_DURASI_SUB, payload)
        return {"status": "success", "message": f"Setpoint sent to {TOPIC_SP_DURASI_SUB}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send MQTT command: {str(e)}")

@app.get("/setpoints")
async def get_setpoints():
    return latest_setpoints

if __name__ == "__main__":
    import uvicorn
    # Jalankan server FastAPI secara lokal pada port 8000
    print("Menjalankan server di http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
