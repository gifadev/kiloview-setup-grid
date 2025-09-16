import time
from pathlib import Path
from playwright.sync_api import Error, Page
from .ui_selectors import SEL_USER

OUT_DIR = Path("out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def goto_login(page: Page, base_url: str):
    url = base_url.rstrip("/")
    print(f"[INFO] goto {url}")

    for attempt in range(2):
        try:
            page.goto(url, wait_until="commit", timeout=60_000)
            break
        except Error as e:
            msg = str(e)
            if "ERR_ABORTED" in msg or "frame was detached" in msg:
                print(f"[WARN] goto aborted (attempt {attempt+1}): {msg}")
                time.sleep(0.5)
                continue
            raise

    try:
        page.wait_for_selector(SEL_USER, timeout=20_000)
    except Error:
        page.screenshot(path=str(OUT_DIR / "after_goto_login.png"), full_page=True)
        raise

def wait_for_url_not_contains(page: Page, needle: str, timeout_ms: int = 30_000):
    page.wait_for_function(
        "url => !window.location.href.includes(url)",
        arg=needle,
        timeout=timeout_ms,
    )

def wait_for_any_selector(page: Page, selectors: list[str], timeout_ms: int = 15_000):
    """Lolos kalau salah satu selector muncul."""
    deadline = time.time() + (timeout_ms / 1000.0)
    last_err = None
    for sel in selectors:
        try:
            remain = max(1, int((deadline - time.time()) * 1000))
            page.wait_for_selector(sel, timeout=remain, state="visible")
            return sel
        except Error as e:
            last_err = e
            continue
    if last_err:
        raise last_err
