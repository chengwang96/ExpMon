import os
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect, sync_playwright


def note(message: str) -> None:
    print(message)


def click_nav(page, index: int) -> None:
    page.locator("nav.nav-list button").nth(index).click()
    page.wait_for_load_state("networkidle")


def first_enabled(locator):
    for index in range(locator.count()):
        item = locator.nth(index)
        if not item.is_disabled():
            return item
    return None


def main() -> None:
    frontend_url = os.environ.get("EXPMON_FRONTEND_URL", "http://127.0.0.1:5173")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script("window.localStorage.setItem('expmon-language', 'en')")
        page.goto(frontend_url, wait_until="networkidle")

        expect(page.get_by_role("heading", name="Resource Dashboard")).to_be_visible()
        expect(page.locator("nav.nav-list").get_by_role("button", name="Run Detail")).to_have_count(0)
        note("PASS: default English dashboard and sidebar shape")

        refresh_button = page.get_by_role("button", name="Refresh")
        refresh_button.click()
        expect(refresh_button).to_have_class(re.compile(r"\bis-refreshing\b"))
        note("PASS: manual refresh animation state")

        page.get_by_role("button", name="中文").click()
        expect(page.get_by_role("heading", name="资源总览")).to_be_visible()
        expect(page.get_by_text("Resource Dashboard")).to_have_count(0)
        page.get_by_role("button", name="EN").click()
        expect(page.get_by_role("heading", name="Resource Dashboard")).to_be_visible()
        note("PASS: language toggle")

        click_nav(page, 3)
        expect(page.get_by_role("button", name="CPU-only", exact=True)).to_be_visible()
        run_rows = page.locator(".run-table-row")
        if run_rows.count() == 0:
            expect(page.get_by_text("No runs")).to_be_visible()
            note("SKIP: run detail checks, no runs in current snapshot")
        else:
            run_rows.first.click()
            page.wait_for_load_state("networkidle")
            expect(page.get_by_role("heading", name="Run Detail")).to_be_visible()
            expect(page.get_by_role("button", name="Back to Runs")).to_be_visible()
            note("PASS: run row opens detail")

            subcharts = page.locator(".resource-subchart")
            if subcharts.count() > 0:
                titles = " | ".join(page.locator(".resource-subchart .metric-subchart-title strong").all_inner_texts())
                if not re.search(r"CPU / Memory|Disk I/O|GPU", titles):
                    raise AssertionError(f"unexpected resource subchart titles: {titles}")
                note(f"PASS: resource subcharts ({titles})")
            else:
                expect(page.get_by_text("No resource samples")).to_be_visible()
                note("SKIP: resource subcharts, selected run has no resource samples")

            expect(page.locator(".log-toolbar")).to_be_visible()
            expect(page.locator("input[placeholder='Search logs']")).to_be_visible()
            note("PASS: log search/filter toolbar")

            page.get_by_role("button", name="Back to Runs").click()
            expect(page.get_by_role("button", name="CPU-only", exact=True)).to_be_visible()
            note("PASS: back to Runs")

            delete_button = first_enabled(page.locator("button[title='Delete finished run record']"))
            if delete_button is None:
                note("SKIP: delete confirmation, no deletable finished run in current snapshot")
            else:
                delete_button.click()
                page.wait_for_selector(".confirm-dialog", timeout=3000)
                expect(page.locator(".confirm-dialog")).to_contain_text(re.compile("Delete run record|删除任务记录"))
                page.keyboard.press("Escape")
                page.wait_for_selector(".confirm-dialog", state="detached", timeout=3000)
                note("PASS: delete run confirmation")

        click_nav(page, 2)
        expect(page.get_by_role("heading", name="Projects")).to_be_visible()
        push_buttons = page.locator("button:has-text('Git push')")
        if push_buttons.count() == 0 or push_buttons.first.is_disabled():
            note("SKIP: Git push confirmation, selected/current project is not a Git repository")
        else:
            push_buttons.first.click()
            page.wait_for_selector(".confirm-dialog", timeout=3000)
            expect(page.locator(".confirm-dialog")).to_contain_text("Run git push?")
            page.keyboard.press("Escape")
            page.wait_for_selector(".confirm-dialog", state="detached", timeout=3000)
            note("PASS: Git push confirmation")

        click_nav(page, 1)
        expect(page.get_by_role("heading", name="Host / SSH Servers")).to_be_visible()
        if page.get_by_role("button", name="Test Connection").count() > 0:
            expect(page.get_by_role("button", name="Refresh Resources").first).to_be_visible()
            note("PASS: SSH test action rendered")
        else:
            note("SKIP: SSH test action, no remote SSH server configured")

        page.set_viewport_size({"width": 390, "height": 900})
        click_nav(page, 0)
        expect(page.get_by_role("heading", name="Resource Dashboard")).to_be_visible()
        note("PASS: mobile dashboard renders")

        browser.close()


if __name__ == "__main__":
    try:
        main()
    except PlaywrightTimeoutError as error:
        raise SystemExit(f"TIMEOUT: {error}") from error
