import os
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "screenshots"
SHOT_DIR.mkdir(exist_ok=True)


def main() -> None:
    frontend_url = os.environ.get("EXPMON_FRONTEND_URL", "http://127.0.0.1:5173")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.goto(frontend_url, wait_until="domcontentloaded")

        expect(page.get_by_text("Resource Dashboard")).to_be_visible()
        expect(page.get_by_role("button", name=re.compile("Local")).first).to_be_visible()
        expect(page.get_by_role("heading", name="GPU")).to_be_visible(timeout=30000)
        expect(page.get_by_role("heading", name="CPU cores")).to_be_visible()
        page.screenshot(path=str(SHOT_DIR / "dashboard.png"), full_page=True)

        nav = page.locator("nav")
        expect(nav.get_by_role("button", name="Run Detail")).to_have_count(0)
        nav.get_by_role("button", name="Runs").click()
        expect(page.get_by_role("button", name="CPU-only", exact=True)).to_be_visible()

        if page.locator(".run-table-row").count() > 0:
            page.locator(".run-table-row").first.click()
            expect(page.get_by_role("heading", name="Process Tree")).to_be_visible()
            page.get_by_role("button", name="Back to Runs").click()
            expect(page.get_by_role("button", name="CPU-only", exact=True)).to_be_visible()
        else:
            expect(page.get_by_text("No runs")).to_be_visible()
        page.screenshot(path=str(SHOT_DIR / "detail.png"), full_page=True)

        page.set_viewport_size({"width": 390, "height": 900})
        nav.get_by_role("button", name="Host / SSH").click()
        expect(page.get_by_role("heading", name=re.compile("Local"))).to_be_visible()
        expect(page.get_by_role("heading", name="SSH Servers", exact=True)).to_be_visible()
        page.screenshot(path=str(SHOT_DIR / "mobile-hosts.png"), full_page=True)

        browser.close()


if __name__ == "__main__":
    main()
