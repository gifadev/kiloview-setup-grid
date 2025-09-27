import os
import re
import time
import random
import json
from typing import Iterable, List, Tuple
from pathlib import Path
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# ===================== ENV =====================
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

CLIENT_BATCH_SIZE      = int(os.getenv("CLIENT_BATCH_SIZE") or 3)  # TETAP 3 sesuai requirement
SLEEP_BETWEEN_BATCH    = float(os.getenv("SLEEP_BETWEEN_BATCH") or 0.5)
INITIAL_BACKOFF        = float(os.getenv("INITIAL_BACKOFF") or 0.8)
BACKOFF_CAP            = float(os.getenv("BACKOFF_CAP") or 5.0)
MAX_FALLBACK_SPLIT     = int(os.getenv("MAX_FALLBACK_SPLIT") or 1)

# Loop & session
RESCAN_INTERVAL_SECONDS = int(os.getenv("RESCAN_INTERVAL_SECONDS") or 20)   # default 20 detik
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS") or 1200) # default 20 menit
STARTUP_GRACE_SECONDS   = int(os.getenv("STARTUP_GRACE_SECONDS") or 0)      # opsional; 0=tanpa grace
ALWAYS_LOGIN_EACH_LOOP  = (os.getenv("ALWAYS_LOGIN_EACH_LOOP") or "false").lower() in ("1","true","yes")

# Cache: simpan di folder yang sama dengan file .py ini
_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE = _SCRIPT_DIR / "last_sent.json"
PERSIST_CACHE_PATH = os.getenv("PERSIST_CACHE_PATH") or str(DEFAULT_CACHE)

# Penamaan "name" yang dikirim ke server:
# - "simple": pakai cam_name langsung (cocok dengan Source di server)
# - "full"  : "key/did - cam_name (chX)"
NAME_MODE = (os.getenv("NAME_MODE") or "simple").lower()

def load_camera_map() -> dict:
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

# ===== Cache persist =====
def _load_cache() -> dict:
    p = Path(PERSIST_CACHE_PATH)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        return {}
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return {}

def _save_cache(cache: dict):
    p = Path(PERSIST_CACHE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)

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
    # path "rtmp://.../3/3" sesuai pola yang kamu pakai
    return (
        f"rtmp://{IP_STREAM}:{RTSP_PORT}/3/3"
        f"?AVType=1&jsession={jsession}&DevIDNO={devidno}"
        f"&Channel={channel}&Stream={stream}"
    )

def choose_display_name(cam_name: str, key: str, did: str, ch: int) -> str:
    if NAME_MODE == "full":
        return safe_name(f"{key}/{did} - {cam_name} (ch{ch})")
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

def post_set_urls(session: requests.Session, items: List[dict]) -> Tuple[bool, List[dict]]:
    """
    Kirim batch kecil; kalau gagal 5xx/EXC, fallback per-item.
    RETURN:
      - all_ok: bool
      - succeeded_items: list[dict] yang sukses terkirim (untuk update cache presisi)
    """
    if DRY_RUN:
        print(f"[DRY] Akan POST {len(items)} item ke {ENDPOINT_URL}")
        return True, list(items)

    payload = {"set_urls": items}
    attempt = 0
    backoff = INITIAL_BACKOFF

    while True:
        attempt += 1
        ok, body, code = _post_once(session, ENDPOINT_URL, payload, POST_TIMEOUT)
        if ok:
            print(f"[OK] POST set_urls={len(items)} status={code}")
            return True, list(items)

        print(f"[ERR] POST batch size={len(items)} status={code} body={body!r}")

        # Fallback: 5xx/EXC dan batch > 1 → kirim per-item
        if (500 <= code < 600 or code == -1) and len(items) > 1 and MAX_FALLBACK_SPLIT >= 1:
            print("[INFO] Fallback: kirim per-item untuk isolasi URL bermasalah...")
            succeeded = []
            for it in items:
                ok1, body1, code1 = _post_once(session, ENDPOINT_URL, {"set_urls": [it]}, POST_TIMEOUT)
                if ok1:
                    print(f"  [OK] {it.get('name')} status={code1}")
                    succeeded.append(it)
                else:
                    print(f"  [ERR] {it.get('name')} status={code1} body={body1!r}")
                _sleep_with_jitter(0.25)
            return (len(succeeded) == len(items)), succeeded

        if attempt > POST_MAX_RETRY:
            print("[ERR] Gagal POST setelah retry.")
            return False, []

        print(f"[INFO] Retry dalam {min(backoff, BACKOFF_CAP):.1f}s ...")
        _sleep_with_jitter(min(backoff, BACKOFF_CAP))
        backoff *= 2.0

# ===================== SNAPSHOT & DIFF =====================
def collect_snapshot(session: requests.Session, jsession: str) -> List[dict]:
    """Kembalikan list item {name,url} untuk SEMUA device online saat ini."""
    items = []
    for key, cam_list in CAMERA_MAP.items():
        try:
            online_devs = get_online_devices(session, jsession, key)
        except Exception as e:
            print(f"[WARN] Gagal ambil device '{key}': {e}")
            online_devs = []

        if not online_devs:
            continue

        for did in online_devs:
            for cam_name, ch in cam_list:
                url = build_rtsp(jsession, devidno=did, channel=ch, stream=DEFAULT_STREAM)
                name = choose_display_name(cam_name, key, did, ch)
                items.append({"name": name, "url": url})
    return items

def diff_delta(snapshot: List[dict], cache: dict) -> List[dict]:
    """Ambil item yang baru/berubah dibanding cache {name:url}."""
    delta = []
    for it in snapshot:
        nm, url = it["name"], it["url"]
        if cache.get(nm) != url:
            delta.append(it)
    return delta

# ===================== LOOP MODE =====================
def loop_resilient():
    ensure_env()
    if STARTUP_GRACE_SECONDS > 0:
        print(f"[BOOT] Grace period {STARTUP_GRACE_SECONDS}s …")
        time.sleep(STARTUP_GRACE_SECONDS)

    cache = _load_cache()
    with make_session() as s:
        jsession = None
        js_birth = datetime.min

        while True:
            # 1) Login
            try:
                if ALWAYS_LOGIN_EACH_LOOP:
                    new_js = login(s)
                    if jsession is None:
                        print(f"[OK] Login (loop). JSESSIONID={new_js}")
                    elif new_js != jsession:
                        print(f"[OK] Login (loop). JSESSIONID berubah: {jsession} -> {new_js}")
                    else:
                        print("[OK] Login (loop). JSESSIONID tetap sama.")
                    jsession = new_js
                    js_birth = datetime.utcnow()
                else:
                    need_login = (jsession is None) or \
                                 ((datetime.utcnow() - js_birth).total_seconds() > SESSION_MAX_AGE_SECONDS)
                    if need_login:
                        jsession = login(s)
                        js_birth = datetime.utcnow()
                        print(f"[OK] Login. JSESSIONID={jsession}")
            except Exception as e:
                print(f"[ERR] Login gagal: {e}. Coba lagi {RESCAN_INTERVAL_SECONDS}s.")
                time.sleep(RESCAN_INTERVAL_SECONDS)
                continue

            # 2) Snapshot saat ini
            try:
                snap = collect_snapshot(s, jsession)
            except Exception as e:
                print(f"[ERR] Collect snapshot gagal: {e}")
                time.sleep(RESCAN_INTERVAL_SECONDS)
                continue

            if not snap:
                print("[INFO] Belum ada device online.")
                time.sleep(RESCAN_INTERVAL_SECONDS)
                continue

            # 3) Delta vs cache
            delta = diff_delta(snap, cache)
            if not delta:
                print("[INFO] Tidak ada perubahan URL/name. Skip kirim.")
                time.sleep(RESCAN_INTERVAL_SECONDS)
                continue

            # 4) Kirim delta PER 3 item (tetap batch=3)
            sent = 0
            for batch in chunked(delta, CLIENT_BATCH_SIZE):
                all_ok, succeeded = post_set_urls(s, batch)
                if succeeded:
                    for it in succeeded:
                        cache[it["name"]] = it["url"]  # update cache utk yang sukses
                    sent += len(succeeded)
                _sleep_with_jitter(SLEEP_BETWEEN_BATCH)

            if sent > 0:
                _save_cache(cache)
                print(f"[OK] Delta terkirim: {sent}/{len(delta)} & cache updated.")
            else:
                print(f"[WARN] Tidak ada item delta yang sukses terkirim kali ini.")

            time.sleep(RESCAN_INTERVAL_SECONDS)

# ===================== RUN =====================
def main():
    loop_resilient()

if __name__ == "__main__":
    main()
