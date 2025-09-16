# get_rtmp.py
import subprocess
import time
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime

# ===================== Utils ADB =====================
def run_adb_command(command, timeout=15):
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return "", str(e)

def adb_shell(cmd, timeout=15):
    return run_adb_command(f"adb shell {cmd}", timeout=timeout)

# ===================== Cari RTMP di layar =====================
RTMP_RE = re.compile(r'rtmps?://[^\s"\'<>)\]]+', re.I)

RESOURCE_IDS_PRIORITAS = [
    # "com.ybws.newmlive:id/play_url",
    # "com.ybws.newmlive:id/stream_url",
]

def dump_ui_xml():
    adb_shell("uiautomator dump --compressed /sdcard/uidump.xml")
    xml, _ = run_adb_command("adb exec-out cat /sdcard/uidump.xml")
    return xml

def parse_rtmp_from_xml(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    if RESOURCE_IDS_PRIORITAS:
        for node in root.iter("node"):
            rid = (node.get("resource-id") or "").strip()
            if rid in RESOURCE_IDS_PRIORITAS:
                txt = (node.get("text") or "") + " " + (node.get("content-desc") or "")
                m = RTMP_RE.search(txt)
                if m:
                    return m.group(0)

    for node in root.iter("node"):
        txt = (node.get("text") or "") + " " + (node.get("content-desc") or "")
        m = RTMP_RE.search(txt)
        if m:
            return m.group(0)
    return None

def find_rtmp_in_screen(max_retries=4, scroll_attempts=2, scroll_pixels=900):
    for attempt in range(1, max_retries + 1):
        xml = dump_ui_xml()
        link = parse_rtmp_from_xml(xml)
        if link:
            return link

        for _ in range(scroll_attempts):
            _ = adb_shell("input swipe 500 1600 500 600 250")
            time.sleep(0.4)
            xml = dump_ui_xml()
            link = parse_rtmp_from_xml(xml)
            if link:
                return link

        time.sleep(0.6)
    return None

# ===================== Public API =====================
def fetch_rtmp(
    package: str = "com.ybws.newmlive",
    do_login_taps: bool = True,
    max_retries: int = 5,
    scroll_attempts: int = 3,
) -> str | None:
    """
    Jalankan flow ADB dan kembalikan link RTMP jika ditemukan, else None.
    """
    # Force stop & start app
    adb_shell(f"am force-stop {package}")
    stdout, _ = run_adb_command(f'adb shell cmd package resolve-activity --brief {package}')
    if stdout:
        activity = stdout.splitlines()[-1]
        adb_shell(f"am start -n {activity}")
    time.sleep(3)

    # Ketukan untuk login (opsional)
    if do_login_taps:
        adb_shell("input tap 540 1440"); time.sleep(1)
        adb_shell("input tap 510 360");  time.sleep(1)
        adb_shell("input tap 900 570");  time.sleep(1)
        adb_shell("input tap 664 450");  time.sleep(1)
        adb_shell("input tap 656 336");  time.sleep(1)

    # Cari link RTMP di layar
    link = find_rtmp_in_screen(max_retries=max_retries, scroll_attempts=scroll_attempts)
    return link

# ===================== CLI (opsional) =====================
def main():
    print("Mencari link RTMP...")
    link = fetch_rtmp()
    if link:
        print(f"[+] Link RTMP {link}")
    else:
        print("[-] Belum menemukan RTMP.")

if __name__ == "__main__":
    main()
