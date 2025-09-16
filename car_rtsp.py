#!/usr/bin/env python3
# cmsv8_rtsp_to_endpoint.py

import os
import re
import time
from typing import Dict, List, Tuple, Iterable
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

# ===================== CONFIG =====================
IP_STREAM        = os.getenv("IP_DEVICES")          # contoh: "172.15.4.252"
RTSP_PORT        = int(os.getenv("RTSP_PORT") or 6604)
BASE_URL         = f"http://{IP_STREAM}/808gps"

USERNAME         = os.getenv("USERNAME")
PASSWORD         = os.getenv("PASSWORD")

DEFAULT_STREAM   = int(os.getenv("DEFAULT_STREAM") or 1)

# Endpoint tujuan:
ENDPOINT_URL     = os.getenv("ENDPOINT_URL")
BATCH_SIZE       = int(os.getenv("POST_BATCH_SIZE") or 50)
POST_TIMEOUT     = float(os.getenv("POST_TIMEOUT") or 10.0)
POST_MAX_RETRY   = int(os.getenv("POST_MAX_RETRY") or 2)
DRY_RUN          = (os.getenv("DRY_RUN") or "false").lower() in ("1", "true", "yes")

# Peta kamera: key bisa DevIDNO atau vehiIdno (plat)
CAMERA_MAP: Dict[str, List[Tuple[str, int]]] = {
    # "B2222KJA": [
    #     ("Depan", 0),
    #     ("Kabin", 1),
    #     ("Kanan", 2),
    #     ("Kiri", 3),
    # ],
    "14882506144": [
        ("Car Camera 1", 0),
        ("Car Camera 2", 1),
        ("Car Camera 3", 2),
        ("Car Camera 4", 3),
        ("Car Camera 5", 4),
        ("Car Camera 6", 5),
        ("Car Camera 7", 6),
        ("Car Camera 8", 7),
    ],
}

# ===================== HELPERS =====================
def ensure_env():
    missing = []
    for k in ("IP_DEVICES", "USERNAME", "PASSWORD"):
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
    # Retry GET (login / query) agar lebih tahan terhadap fluktuasi jaringan
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"])
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

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

# ===================== POSTER =====================
def post_set_urls(session: requests.Session, items: List[dict]) -> bool:
    """Kirim batch ke ENDPOINT_URL dalam format {'set_urls': [...]} dengan retry sederhana."""
    if DRY_RUN:
        print(f"[DRY] Akan POST {len(items)} item ke {ENDPOINT_URL}")
        return True

    attempt = 0
    while True:
        attempt += 1
        try:
            r = session.post(ENDPOINT_URL, json={"set_urls": items}, timeout=POST_TIMEOUT)
            if 200 <= r.status_code < 300:
                print(f"[OK] POST set_urls={len(items)} status={r.status_code}")
                return True
            else:
                print(f"[ERR] POST status={r.status_code} body={r.text[:300]}")
        except Exception as e:
            print(f"[ERR] Exception POST: {e}")

        if attempt > POST_MAX_RETRY:
            print("[ERR] Gagal POST setelah retry.")
            return False
        sleep_s = min(2.0 * attempt, 5.0)
        print(f"[INFO] Retry dalam {sleep_s:.1f}s ...")
        time.sleep(sleep_s)

# ===================== MAIN =====================
def main():
    ensure_env()
    with make_session() as s:
        # 1) Login
        jsession = login(s)
        print(f"[OK] Login sukses. JSESSIONID={jsession}")

        # 2) Bangun daftar set_urls
        payload_items: List[dict] = []
        total_links = 0

        for key, cam_list in CAMERA_MAP.items():
            if isinstance(cam_list, dict):
                cam_list = list(cam_list.items())

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
                    nice_name = safe_name(f"{key}/{did} - {cam_name} (ch{ch})")
                    print(f"    {nice_name} -> {rtsp}")
                    payload_items.append({"name": nice_name, "url": rtsp})
                    total_links += 1

        print(f"\n[INFO] Total RTSP yang dihasilkan: {total_links}")

        # 3) Kirim ke endpoint /run per-batch
        if not payload_items:
            print("[INFO] Tidak ada item untuk dikirim.")
            return

        sent = 0
        all_ok = True
        for batch in chunked(payload_items, BATCH_SIZE):
            ok = post_set_urls(s, batch)
            if ok:
                sent += len(batch)
            all_ok = all_ok and ok

        if all_ok:
            print(f"[DONE] Semua terkirim. Total: {sent}")
        else:
            print(f"[DONE*] Sebagian terkirim. Berhasil: {sent}/{len(payload_items)}")

if __name__ == "__main__":
    main()
