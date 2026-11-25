import gc
import time
import json
import network
import socket
import dht
import urequests
from machine import Pin, ADC
import ai_model

# ================= KONFIGURASI WI-FI & CLOUD =================
SSID = "SKOMDA SISWA"
PASSWORD = ""

SUPABASE_URL = "https://jhkeatsnboshufjutpzy.supabase.co/rest/v1/greenhouse?id=eq.1"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Impoa2VhdHNuYm9zaHVmanV0cHp5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTU1ODYyNDQsImV4cCI6MjExMTE2MjI0NH0.FlplmWO-Tx9i-_Vub839li2PU0JsSgMBALsT3Hm9XW8"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": "Bearer " + SUPABASE_KEY,
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# ================= KONFIGURASI PIN ESP32 =================
DHT_PIN = 4
LDR_PIN = 34
SOIL_PIN = 35

SOIL_DRY = 3500
SOIL_WET = 1200

RELAY_POMPA_PIN = 18
RELAY_KIPAS_PIN = 19
RELAY_LAMPU_PIN = 23
RELAY_ACTIVE_LOW = False

# Inisialisasi Hardware
dht_sensor = dht.DHT11(Pin(DHT_PIN))

adc_ldr = ADC(Pin(LDR_PIN))
adc_ldr.atten(ADC.ATTN_11DB)
adc_ldr.width(ADC.WIDTH_12BIT)

adc_soil = ADC(Pin(SOIL_PIN))
adc_soil.atten(ADC.ATTN_11DB)
adc_soil.width(ADC.WIDTH_12BIT)

relay_pompa = Pin(RELAY_POMPA_PIN, Pin.OUT)
relay_kipas = Pin(RELAY_KIPAS_PIN, Pin.OUT)
relay_lampu = Pin(RELAY_LAMPU_PIN, Pin.OUT)


def set_relay(dev, state_on):
    """Mengatur relay dengan mempertimbangkan logika ACTIVE_LOW."""
    val = 1 if state_on else 0
    if RELAY_ACTIVE_LOW:
        val = 0 if state_on else 1
    dev.value(val)


# Matikan semua relay saat boot
set_relay(relay_pompa, False)
set_relay(relay_kipas, False)
set_relay(relay_lampu, False)

# ================= STATE SISTEM & HISTORY =================
state = {
    "tanaman": "monstera",
    "suhu": 26,
    "kelembapan": 65,
    "tanah": 50,
    "cahaya": 55,
    "pompa": 0,
    "kipas": 0,
    "lampu": 0,
    "system_running": 1,
    "control_mode": "ai",
    "th_soil": 45,
    "th_temp": 30,
    "th_light": 40,
}

history = {
    "tanah": [],
    "suhu": [],
    "kelembapan": [],
    "cahaya": [],
}
MAX_HIST = 20

_last_dht_ms = 0


def read_sensors():
    """Membaca DHT11, Soil Moisture, dan LDR dengan aman."""
    global _last_dht_ms
    now = time.ticks_ms()

    if time.ticks_diff(now, _last_dht_ms) >= 2000 or _last_dht_ms == 0:
        try:
            dht_sensor.measure()
            state["suhu"] = dht_sensor.temperature()
            state["kelembapan"] = dht_sensor.humidity()
            _last_dht_ms = now
        except Exception as e:
            print("DHT11 read error:", e)

    # Soil Moisture (%)
    raw_soil = adc_soil.read()
    soil_pct = (SOIL_DRY - raw_soil) * 100 // (SOIL_DRY - SOIL_WET)
    if soil_pct < 0:
        soil_pct = 0
    elif soil_pct > 100:
        soil_pct = 100
    state["tanah"] = soil_pct

    # LDR (%)
    raw_ldr = adc_ldr.read()
    light_pct = raw_ldr * 100 // 4095
    if light_pct < 0:
        light_pct = 0
    elif light_pct > 100:
        light_pct = 100
    state["cahaya"] = light_pct


def push_history():
    for k in ("tanah", "suhu", "kelembapan", "cahaya"):
        arr = history[k]
        arr.append(state[k])
        if len(arr) > MAX_HIST:
            arr.pop(0)


def eval_automation():
    """Menentukan status pompa, kipas, dan lampu berdasarkan mode AI atau Slider."""
    if int(state["system_running"]) != 1:
        p, k, l = 0, 0, 0
    elif state["control_mode"] == "slider":
        p = 1 if state["tanah"] < int(state["th_soil"]) else 0
        k = 1 if state["suhu"] > int(state["th_temp"]) else 0
        l = 1 if state["cahaya"] < int(state["th_light"]) else 0
    else:
        p, k, l = ai_model.prediksi_ai(
            state["tanaman"],
            state["suhu"],
            state["kelembapan"],
            state["tanah"],
            state["cahaya"],
        )

    state["pompa"] = p
    state["kipas"] = k
    state["lampu"] = l

    set_relay(relay_pompa, p == 1)
    set_relay(relay_kipas, k == 1)
    set_relay(relay_lampu, l == 1)


# ================= WI-FI & SUPABASE SYNC =================
wlan = network.WLAN(network.STA_IF)


def connect_wifi():
    wlan.active(True)
    if wlan.isconnected():
        return True
    print("Menghubungkan ke Wi-Fi:", SSID)
    wlan.connect(SSID, PASSWORD)
    for _ in range(30):
        if wlan.isconnected():
            print("Wi-Fi Terhubung! IP:", wlan.ifconfig()[0])
            return True
        time.sleep_ms(500)
    print("Gagal terhubung ke Wi-Fi")
    return False


def supabase_get():
    """Tarik pengaturan terbaru dari Supabase."""
    if not wlan.isconnected():
        return
    res = None
    try:
        res = urequests.get(SUPABASE_URL, headers=SUPABASE_HEADERS)
        if res.status_code == 200:
            rows = res.json()
            if isinstance(rows, list) and len(rows) > 0:
                row = rows[0]
                for key in ("tanaman", "system_running", "control_mode", "th_soil", "th_temp", "th_light"):
                    if key in row and row[key] is not None:
                        state[key] = row[key]
        else:
            print("Supabase GET status:", res.status_code)
    except Exception as e:
        print("Supabase GET error:", e)
    finally:
        if res:
            res.close()
        gc.collect()


def supabase_patch(payload):
    """Kirim PATCH data ke Supabase."""
    if not wlan.isconnected():
        return
    res = None
    try:
        res = urequests.patch(SUPABASE_URL, headers=SUPABASE_HEADERS, data=json.dumps(payload))
        if res.status_code not in (200, 204):
            print("Supabase PATCH status:", res.status_code)
    except Exception as e:
        print("Supabase PATCH error:", e)
    finally:
        if res:
            res.close()
        gc.collect()


def sync_cloud():
    """Siklus sinkronisasi dua arah dengan Supabase."""
    supabase_get()
    read_sensors()
    push_history()
    eval_automation()
    supabase_patch({
        "suhu": state["suhu"],
        "kelembapan": state["kelembapan"],
        "tanah": state["tanah"],
        "cahaya": state["cahaya"],
        "pompa": state["pompa"],
        "kipas": state["kipas"],
        "lampu": state["lampu"],
    })


# ================= WEB SERVER LOKAL (STREAMING CHUNK) =================
HTML_PAGE = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32 Smart Greenhouse</title>
<style>
:root{--bg:#0b1310;--card:#121f1a;--bdr:#253d33;--txt:#ecfdf5;--mut:#94b3a6;--pri:#10b981;--dan:#ef4444}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--txt);padding:16px}
.wrap{max-width:960px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.card{background:var(--card);border:1px solid var(--bdr);border-radius:14px;padding:14px}
.row{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.val{font-size:1.7rem;font-weight:800;margin:4px 0}
.mut{color:var(--mut);font-size:.82rem}
select,input,button{background:#182a23;color:var(--txt);border:1px solid var(--bdr);border-radius:8px;padding:8px 10px;font-size:.9rem}
button{cursor:pointer;font-weight:700}
.pri{background:var(--pri);color:#042f2e;border:none}
.dan{background:var(--dan);color:#fff;border:none}
.rbox{background:#182a23;border:1px solid var(--bdr);border-radius:10px;padding:10px;text-align:center}
.rbox.on{border-color:var(--pri);background:rgba(16,185,129,.14)}
svg{width:100%;height:34px;display:block}
.hide{display:none}
</style>
</head>
<body>
<div class="wrap">
  <div class="card row">
    <div><h2>🌿 ESP32 Smart Greenhouse</h2><div class="mut">Web Lokal + Sinkronisasi Cloud Supabase</div></div>
    <select id="plant"></select>
  </div>
  <div class="grid4">
    <div class="card"><div class="mut">💧 Tanah</div><div class="val" id="vSoil">--%</div><svg id="sSoil"></svg></div>
    <div class="card"><div class="mut">🌡️ Suhu</div><div class="val" id="vTemp">--°C</div><svg id="sTemp"></svg></div>
    <div class="card"><div class="mut">💨 Kelembapan</div><div class="val" id="vHum">--%</div><svg id="sHum"></svg></div>
    <div class="card"><div class="mut">☀️ Cahaya</div><div class="val" id="vLight">--%</div><svg id="sLight"></svg></div>
  </div>
  <div class="card">
    <div class="row" style="margin-bottom:10px">
      <strong>⚙️ Kontrol Otomasi</strong>
      <span id="runBadge" class="mut">--</span>
    </div>
    <div class="grid3" style="margin-bottom:10px">
      <div class="rbox" id="bPompa">🚿 Pompa<br><b id="rPompa">OFF</b></div>
      <div class="rbox" id="bKipas">🌀 Kipas<br><b id="rKipas">OFF</b></div>
      <div class="rbox" id="bLampu">💡 Lampu<br><b id="rLampu">OFF</b></div>
    </div>
    <div class="row" style="margin-bottom:10px">
      <button class="pri" onclick="upd({system_running:1})">▶ START</button>
      <button class="dan" onclick="upd({system_running:0})">■ STOP</button>
      <button id="btnMode" style="flex:1" onclick="toggleMode()">Mode: AI</button>
    </div>
    <div id="sliders" class="hide" style="display:flex;flex-direction:column;gap:8px">
      <label class="mut">Tanah (&lt;<span id="lS">45</span>%) <input type="range" id="iS" min="10" max="90" style="width:100%"></label>
      <label class="mut">Suhu (&gt;<span id="lT">30</span>°C) <input type="range" id="iT" min="15" max="40" style="width:100%"></label>
      <label class="mut">Cahaya (&lt;<span id="lL">40</span>%) <input type="range" id="iL" min="5" max="95" style="width:100%"></label>
    </div>
  </div>
  <div class="card">
    <strong style="display:block;margin-bottom:8px">✨ Tanya AI (Gemini)</strong>
    <div class="row" style="margin-bottom:8px">
      <input type="password" id="gKey" placeholder="Gemini API Key" style="flex:1">
      <button onclick="saveKey()">Simpan Key</button>
    </div>
    <div class="row" style="margin-bottom:8px">
      <input type="text" id="qAi" placeholder="Tanya kondisi tanaman..." style="flex:1">
      <button class="pri" onclick="askAi()">Kirim</button>
    </div>
    <div id="aAi" class="mut" style="white-space:pre-wrap">Siap membantu perawatan tanaman.</div>
  </div>
</div>
<script>
const PLANTS=["aglaonema","alocasia","anggrek_bulan","anthurium","begonia_rex","calathea","fittonia","kaktus_mini","kamboja_jepang","keladi_hias","krisan_mini","lidah_buaya","lidah_mertua","maranta","mawar_mini","monstera","pakis_boston","peace_lily","peperomia","philodendron","pilea","sirih_gading","spider_plant","sukulen_echeveria","tillandsia"];
const sel=document.getElementById("plant");
PLANTS.forEach(p=>{const o=document.createElement("option");o.value=p;o.textContent=p.replace(/_/g," ").toUpperCase();sel.appendChild(o);});
let cur={};
function spark(id,arr,col){
  const el=document.getElementById(id);if(!arr||arr.length<2){el.innerHTML="";return;}
  const mn=Math.min(...arr),mx=Math.max(...arr),rg=mx-mn||1;
  const pts=arr.map((v,i)=>`${(i/(arr.length-1))*100},${30-((v-mn)/rg)*26}`).join(" ");
  el.innerHTML=`<polyline fill="none" stroke="${col}" stroke-width="2" points="${pts}"/>`;
}
function render(d){
  cur=d;sel.value=d.tanaman;
  document.getElementById("vSoil").textContent=d.tanah+"%";
  document.getElementById("vTemp").textContent=d.suhu+"°C";
  document.getElementById("vHum").textContent=d.kelembapan+"%";
  document.getElementById("vLight").textContent=d.cahaya+"%";
  if(d.history){
    spark("sSoil",d.history.tanah,"#10b981");
    spark("sTemp",d.history.suhu,"#f59e0b");
    spark("sHum",d.history.kelembapan,"#38bdf8");
    spark("sLight",d.history.cahaya,"#eab308");
  }
  [["Pompa",d.pompa],["Kipas",d.kipas],["Lampu",d.lampu]].forEach(([n,v])=>{
    document.getElementById("b"+n).className="rbox"+(v?" on":"");
    document.getElementById("r"+n).textContent=v?"ON":"OFF";
  });
  document.getElementById("runBadge").textContent=d.system_running?"BERJALAN":"BERHENTI";
  const isS=d.control_mode==="slider";
  document.getElementById("btnMode").textContent=isS?"Mode: SLIDER":"Mode: AI";
  document.getElementById("sliders").className=isS?"":"hide";
  document.getElementById("iS").value=d.th_soil;document.getElementById("lS").textContent=d.th_soil;
  document.getElementById("iT").value=d.th_temp;document.getElementById("lT").textContent=d.th_temp;
  document.getElementById("iL").value=d.th_light;document.getElementById("lL").textContent=d.th_light;
}
async function load(){try{const r=await fetch("/api/status");render(await r.json());}catch(e){}}
async function upd(p){await fetch("/api/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});load();}
sel.onchange=()=>upd({tanaman:sel.value});
function toggleMode(){upd({control_mode:cur.control_mode==="ai"?"slider":"ai"});}
[["iS","lS","th_soil"],["iT","lT","th_temp"],["iL","lL","th_light"]].forEach(([i,l,k])=>{
  const el=document.getElementById(i);
  el.oninput=()=>document.getElementById(l).textContent=el.value;
  el.onchange=()=>upd({[k]:Number(el.value)});
});
document.getElementById("gKey").value=localStorage.getItem("gh_gemini_key")||"";
function saveKey(){localStorage.setItem("gh_gemini_key",document.getElementById("gKey").value.trim());}
async function askAi(){
  const k=document.getElementById("gKey").value.trim(),q=document.getElementById("qAi").value.trim(),out=document.getElementById("aAi");
  if(!k||!q){out.textContent="Isi API Key & pertanyaan dulu.";return;}
  out.textContent="Memproses...";
  const prompt=`Asisten tanaman greenhouse. Jawab singkat Bahasa Indonesia tanpa markdown. Tanaman:${cur.tanaman}, Tanah:${cur.tanah}%, Suhu:${cur.suhu}C, Lembap:${cur.kelembapan}%, Cahaya:${cur.cahaya}%. Tanya:${q}`;
  try{
    const r=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${encodeURIComponent(k)}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({contents:[{parts:[{text:prompt}]}]})});
    const j=await r.json();out.textContent=(j.candidates?.[0]?.content?.parts?.[0]?.text||"Gagal").replace(/[*#`]/g,"");
  }catch(e){out.textContent="Error: "+e.message;}
}
load();setInterval(load,4000);
</script>
</body>
</html>"""


def send_chunked(conn, data_str):
    """Mengirim data besar via memoryview per 1024 byte agar aman untuk RAM ESP32."""
    raw = data_str.encode("utf-8")
    mv = memoryview(raw)
    total = len(mv)
    sent = 0
    while sent < total:
        end = sent + 1024
        if end > total:
            end = total
        conn.sendall(mv[sent:end])
        sent = end
    del mv
    del raw
    gc.collect()


def handle_http(conn):
    try:
        conn.settimeout(2.0)
        req = conn.recv(2048)
        if not req:
            return
        req_str = req.decode("utf-8", "ignore")
        first_line = req_str.split("\r\n", 1)[0]
        parts = first_line.split(" ")
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]

        if method == "GET" and path == "/api/status":
            body = json.dumps({
                "tanaman": state["tanaman"],
                "suhu": state["suhu"],
                "kelembapan": state["kelembapan"],
                "tanah": state["tanah"],
                "cahaya": state["cahaya"],
                "pompa": state["pompa"],
                "kipas": state["kipas"],
                "lampu": state["lampu"],
                "system_running": state["system_running"],
                "control_mode": state["control_mode"],
                "th_soil": state["th_soil"],
                "th_temp": state["th_temp"],
                "th_light": state["th_light"],
                "history": history,
            })
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
            send_chunked(conn, body)

        elif method == "POST" and path == "/api/update":
            idx = req_str.find("\r\n\r\n")
            body_str = req_str[idx + 4:] if idx != -1 else "{}"
            try:
                data = json.loads(body_str)
            except Exception:
                data = {}
            patch_payload = {}
            for key in ("tanaman", "system_running", "control_mode", "th_soil", "th_temp", "th_light"):
                if key in data:
                    state[key] = data[key]
                    patch_payload[key] = data[key]

            eval_automation()
            patch_payload["pompa"] = state["pompa"]
            patch_payload["kipas"] = state["kipas"]
            patch_payload["lampu"] = state["lampu"]
            supabase_patch(patch_payload)

            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"ok\":true}")

        else:
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
            send_chunked(conn, HTML_PAGE)
    except Exception as e:
        print("HTTP error:", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        gc.collect()


def main():
    connect_wifi()
    read_sensors()
    push_history()
    eval_automation()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 80))
    srv.listen(4)
    srv.settimeout(0.25)
    print("Web Server Lokal aktif pada port 80")

    last_sync_ms = time.ticks_ms()

    while True:
        # 1. Layani request Web Server Lokal (non-blocking timeout)
        try:
            conn, _ = srv.accept()
            handle_http(conn)
        except OSError:
            pass

        # 2. Sinkronisasi Cloud Supabase setiap 5 detik
        now = time.ticks_ms()
        if time.ticks_diff(now, last_sync_ms) >= 5000:
            if not wlan.isconnected():
                connect_wifi()
            sync_cloud()
            last_sync_ms = time.ticks_ms()


if __name__ == "__main__":
    main()
