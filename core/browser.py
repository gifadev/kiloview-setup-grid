# core/browser.py
from pathlib import Path
from playwright.sync_api import sync_playwright
import os

def launch_browser(headless: bool = True, record_video: bool = False, out_dir: Path = Path("out")):
    out_dir.mkdir(parents=True, exist_ok=True)
    video_dir = out_dir / "videos"
    if record_video:
        video_dir.mkdir(parents=True, exist_ok=True)

    pw = sync_playwright().start()

    # pilih engine via env BROWSER (chromium|firefox|webkit), default chromium
    engine = (os.environ.get("BROWSER") or "chromium").lower()
    launcher = {"chromium": pw.chromium, "firefox": pw.firefox, "webkit": pw.webkit}.get(engine, pw.chromium)

    browser = launcher.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])

    ctx_kwargs = dict(
        viewport={"width": 1366, "height": 768},
        device_scale_factor=1,
        service_workers="block",      # hindari detach/error dari SW
        ignore_https_errors=True,
    )
    if record_video:
        ctx_kwargs["record_video_dir"] = str(video_dir)

    context = browser.new_context(**ctx_kwargs)
    page = context.new_page()
    return pw, browser, context, page
    