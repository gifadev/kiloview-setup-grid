# core/auth.py
from playwright.sync_api import Page
from .utils import goto_login, wait_for_url_not_contains, wait_for_any_selector
from .ui_selectors import SEL_USER, SEL_PASS, SEL_BTN_LOGIN, DASHBOARD_PROBES

def login(page: Page, base_url: str, username: str, password: str):
    goto_login(page, base_url)
    page.fill(SEL_USER, username)
    page.fill(SEL_PASS, password)
    page.click(SEL_BTN_LOGIN)
    wait_for_url_not_contains(page, "/login", timeout_ms=30_000)

def wait_for_dashboard(page: Page):
    wait_for_any_selector(page, DASHBOARD_PROBES, timeout_ms=20_000)
