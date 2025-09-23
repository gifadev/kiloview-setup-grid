import os
import re
import time
import random
import json
from typing import Iterable, List
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

# ===================== CONFIG =====================
IP_STREAM              = os.getenv("IP_DEVICES")                      # contoh: "192.168.144.220"
RTSP_PORT              = int(os.getenv("RTSP_PORT") or 6604)
BASE_URL               = f"http://{IP_STREAM}/808gps"

USERNAME               = os.getenv("USERNAME")
PASSWORD               = os.getenv("PASSWORD")

DEFAULT_STREAM         = int(os.getenv("DEFAULT_STREAM") or 1)

ENDPOINT_URL           = os.getenv("ENDPOINT_URL")
POST_TIMEOUT           = float(os.getenv("POST_TIMEOUT") or 20.0)
POST_MAX_RETRY         = int(os.getenv("POST_MAX_RETRY") or 1)
DRY_RUN                = (os.getenv("DRY_RUN") or "false").lower() in ("1", "true", "yes")

CLIENT_BATCH_SIZE      = int(os.getenv("CLIENT_BATCH_SIZE") or 3)
SLEEP_BETWEEN_BATCH    = float(os.getenv("SLEEP_BETWEEN_BATCH") or 0.5)
INITIAL_BACKOFF        = float(os.getenv("INITIAL_BACKOFF") or 0.8)
BACKOFF_CAP            = float(os.getenv("BACKOFF_CAP") or 5.0)
MAX_FALLBACK_SPLIT     = int(os.getenv("MAX_FALLBACK_SPLIT") or 1)

# Strategi penamaan untuk field "name" yang dikirim ke server:
# - "simple" (default): pakai cam_name langsung (SUPAYA COCOK DENGAN SOURCE DI SERVER)
# - "full": pakai "key/did - cam_name (chX)" seperti versi lama
NAME_MODE              = (os.getenv("NAME_MODE") or "simple").lower()

def load_camera_map() -> dict:
    """
    CAMERA_MAP_PATH JSON format contoh:
    {
      "014882506144": [
        {"name": "Car Camera 1", "channel": 0},
        {"name": "Car Camera 2", "channel": 1},
        {"name": "Body Worn",    "channel": 7}
      ]
    }
    """
    path = os.getenv("CAMERA_MAP_PATH")
    if not path:
        raise RuntimeError("CAMERA_MAP_PATH belum di-set di .env")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    cmap = {}
    for key, items in raw.items():
        cmap[key] = [(item["name"], int(item["channel"])) for item in items]
    return cmap

CAMERA_MAP = load_camera_map()

# ===================== HELPERS =====================
def ensure_env():
    missing = []
    for k in ("IP_DEVICES", "USERNAME", "PASSWORD", "ENDPOINT_URL"):
        if not os.getenv(k):
            missing.append(k)
    if missing:
        raise RuntimeError(f"ENV wajib belum di-set: {', '.join(missing)}")

def chunked(iterable: Iterable, size: int):
    batch = []
    for x in iterable:
        batch.append(x)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch

def safe_name(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()

def make_session() -> requests.Session:
    s = requests.Session()
    # Retry HANYA untuk GET; JANGAN untuk POST
    retries_get_only = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(["GET"])
    )
    adapter = HTTPAdapter(max_retries=retries_get_only, pool_connections=4, pool_maxsize=4)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

def _sleep_with_jitter(base: float):
    time.sleep(base + random.uniform(0, base * 0.35))

# ===================== CORE (CMSV8) =====================
def login(session: requests.Session) -> str:
    url = f"{BASE_URL}/StandardApiAction_login.action"
    r = session.get(url, params={"account": USERNAME, "password": PASSWORD}, timeout=8)
    r.raise_for_status()
    data = r.json()
    js = data.get("JSESSIONID") or data.get("jsession")
    if data.get("result") != 0 or not js:
        raise RuntimeError(f"Login gagal: {data}")
    return js

def query_online_by(session: requests.Session, jsession: str, *, dev: str = None, vehi: str = None) -> List[str]:
    url = f"{BASE_URL}/StandardApiAction_getDeviceOlStatus.action"
    params = {"jsession": jsession, "status": 1}
    if dev:
        params["devIdno"] = dev
    if vehi:
        params["vehiIdno"] = vehi
    r = session.get(url, params=params, timeout=8)
    r.raise_for_status()
    data = r.json()
    if data.get("result") != 0:
        return []
    onlines = data.get("onlines", []) or []
    return [it["did"] for it in onlines if str(it.get("online", 0)) == "1" and it.get("did")]

def fallback_status(session: requests.Session, jsession: str, key: str) -> List[str]:
    url = f"{BASE_URL}/StandardApiAction_getDeviceStatus.action"
    for param_name in ("devIdno", "vehiIdno"):
        r = session.get(url, params={"jsession": jsession, param_name: key}, timeout=8)
        r.raise_for_status()
        d = r.json()
        if d.get("result") == 0 and d.get("status"):
            dids = []
            for it in d["status"]:
                if it.get("id") and it.get("ol", 0) == 1:
                    dids.append(it["id"])
            if dids:
                return dids
    return []

def get_online_devices(session: requests.Session, jsession: str, key: str) -> List[str]:
    dids = query_online_by(session, jsession, dev=key)
    if dids:
        return dids
    dids = query_online_by(session, jsession, vehi=key)
    if dids:
        return dids
    return fallback_status(session, jsession, key)

def build_rtsp(jsession: str, devidno: str, channel: int, stream: int = DEFAULT_STREAM) -> str:
    return (
        f"rtsp://{IP_STREAM}:{RTSP_PORT}/3/3"
        f"?AVType=1&jsession={jsession}&DevIDNO={devidno}"
        f"&Channel={channel}&Stream={stream}"
    )

def choose_display_name(cam_name: str, key: str, did: str, ch: int) -> str:
    """
    Tentukan 'name' yang dikirim ke server.
    - simple: pakai cam_name (agar cocok dengan nama "Source" yang sudah ada di server)
    - full:   pakai "key/did - cam_name (chX)" (gaya lama)
    """
    if NAME_MODE == "full":
        return safe_name(f"{key}/{did} - {cam_name} (ch{ch})")
    # default simple
    return safe_name(cam_name)

# ===================== POSTER =====================
def _post_once(session: requests.Session, url: str, payload: dict, timeout: float) -> tuple[bool, str, int]:
    try:
        headers = {
            "Content-Type": "application/json",
            "Connection": "close",
            "Accept": "*/*",
        }
        r = session.post(url, json=payload, timeout=timeout, headers=headers)
        ok = 200 <= r.status_code < 300
        body = (r.text or "")[:1000]
        return ok, body, r.status_code
    except Exception as e:
        return False, f"EXC:{e}", -1

def post_set_urls(session: requests.Session, items: List[dict]) -> bool:
    """Kirim batch kecil; kalau gagal 5xx/EXC, fallback per-item."""
    if DRY_RUN:
        print(f"[DRY] Akan POST {len(items)} item ke {ENDPOINT_URL}")
        return True

    payload = {"set_urls": items}
    attempt = 0
    backoff = INITIAL_BACKOFF

    while True:
        attempt += 1
        ok, body, code = _post_once(session, ENDPOINT_URL, payload, POST_TIMEOUT)
        if ok:
            print(f"[OK] POST set_urls={len(items)} status={code}")
            return True

        print(f"[ERR] POST batch size={len(items)} status={code} body={body!r}")

        # Fallback: 5xx/EXC dan batch > 1 → kirim per-item
        if (500 <= code < 600 or code == -1) and len(items) > 1 and MAX_FALLBACK_SPLIT >= 1:
            print("[INFO] Fallback: kirim per-item untuk isolasi URL bermasalah...")
            all_ok = True
            for it in items:
                ok1, body1, code1 = _post_once(session, ENDPOINT_URL, {"set_urls": [it]}, POST_TIMEOUT)
                if ok1:
                    print(f"  [OK] {it.get('name')} status={code1}")
                else:
                    print(f"  [ERR] {it.get('name')} status={code1} body={body1!r}")
                    all_ok = False
                _sleep_with_jitter(0.25)
            return all_ok

        if attempt > POST_MAX_RETRY:
            print("[ERR] Gagal POST setelah retry.")
            return False

        print(f"[INFO] Retry dalam {min(backoff, BACKOFF_CAP):.1f}s ...")
        _sleep_with_jitter(min(backoff, BACKOFF_CAP))
        backoff *= 2.0

# ===================== MAIN =====================
def main():
    ensure_env()
    with make_session() as s:
        # 1) Login CMSV8
        jsession = login(s)
        print(f"[OK] Login sukses. JSESSIONID={jsession}")

        # 2) Bangun daftar set_urls
        payload_items: List[dict] = []
        total_links = 0
        sent_names = set()  # hindari nama duplikat (opsional)

        for key, cam_list in CAMERA_MAP.items():
            try:
                online_devs = get_online_devices(s, jsession, key)
            except Exception as e:
                print(f"[WARN] Gagal ambil device '{key}': {e}")
                online_devs = []

            if not online_devs:
                print(f"\n[{key}] (device online: 0) — skip")
                continue

            print(f"\n[{key}] (device online: {len(online_devs)})")
            for did in online_devs:
                print(f"  DevIDNO={did}")
                for cam_name, ch in cam_list:
                    rtsp = build_rtsp(jsession, devidno=did, channel=ch, stream=DEFAULT_STREAM)

                    # === PENTING: pakai nama yang server kenal ===
                    nice_name = choose_display_name(cam_name, key, did, ch)

                    # Hindari duplikasi nama (opsional)
                    if nice_name in sent_names:
                        print(f"    [SKIP] Duplicate name '{nice_name}' untuk {key}/{did} ch{ch}")
                        continue
                    sent_names.add(nice_name)

                    print(f"    {nice_name} -> {rtsp}")
                    payload_items.append({"name": nice_name, "url": rtsp})
                    total_links += 1

        print(f"\n[INFO] Total RTSP yang dikumpulkan: {total_links}")

        # 3) Kirim ke endpoint /run PER 3 ITEM (CLIENT_BATCH_SIZE)
        if not payload_items:
            print("[INFO] Tidak ada item untuk dikirim.")
            return

        sent = 0
        all_ok = True
        for batch in chunked(payload_items, CLIENT_BATCH_SIZE):
            ok = post_set_urls(s, batch)
            if ok:
                sent += len(batch)
            else:
                all_ok = False
            _sleep_with_jitter(SLEEP_BETWEEN_BATCH)

        if all_ok:
            print(f"[DONE] Semua terkirim. Total: {sent}")
        else:
            print(f"[DONE*] Sebagian terkirim. Berhasil: {sent}/{len(payload_items)}")

if __name__ == "__main__":
    main()

