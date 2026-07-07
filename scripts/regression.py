import os
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect, sync_playwright


def note(message: str) -> None:
    print(message)


def click_nav(page, index: int) -> None:
    page.locator("nav.nav-list button").nth(index).click()
    page.wait_for_load_state("domcontentloaded")


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
        page.add_init_script(
            """
            window.localStorage.setItem('expmon-language', 'en');
            Object.keys(window.localStorage)
              .filter((key) => key.startsWith('expmon.order.'))
              .forEach((key) => window.localStorage.removeItem(key));
            ['mousedown', 'mousemove', 'mouseover', 'mouseup'].forEach((name) => {
              document.addEventListener(name, () => undefined);
            });
            """
        )
        page.goto(frontend_url, wait_until="domcontentloaded")

        expect(page.get_by_role("heading", name="Resource Dashboard")).to_be_visible()
        expect(page.locator("nav.nav-list").get_by_role("button", name="Run Detail")).to_have_count(0)
        note("PASS: default English dashboard and sidebar shape")

        host_cards = page.locator(".dashboard-host-grid [data-draggable-card='true']")
        if host_cards.count() >= 2:
            page.wait_for_timeout(500)
            host_cards.nth(0).scroll_into_view_if_needed()
            first_host_id = host_cards.nth(0).get_attribute("data-draggable-card-id")
            first_box = host_cards.nth(0).bounding_box()
            second_box = host_cards.nth(1).bounding_box()
            if first_box is None or second_box is None or first_host_id is None:
                raise AssertionError("dashboard host cards were not measurable for drag test")
            page.mouse.move(first_box["x"] + first_box["width"] / 2, first_box["y"] + first_box["height"] / 2)
            page.mouse.down()
            preview = page.locator("[data-drag-preview='true']")
            expect(preview).to_be_visible()
            panel_box = page.locator(".dashboard-host-panel").bounding_box()
            if panel_box is None:
                raise AssertionError("dashboard host panel was not measurable for drag preview test")
            page.mouse.move(panel_box["x"] + panel_box["width"] + 200, panel_box["y"] + panel_box["height"] + 200, steps=6)
            preview_box = preview.bounding_box()
            if preview_box is None:
                raise AssertionError("drag preview was not measurable")
            if preview_box["x"] < panel_box["x"] - 1 or preview_box["y"] < panel_box["y"] - 1:
                raise AssertionError("drag preview escaped above or left of the host panel")
            if preview_box["x"] + preview_box["width"] > panel_box["x"] + panel_box["width"] + 1:
                raise AssertionError("drag preview escaped right of the host panel")
            if preview_box["y"] + preview_box["height"] > panel_box["y"] + panel_box["height"] + 1:
                raise AssertionError("drag preview escaped below the host panel")
            page.mouse.up()
            expect(preview).to_have_count(0)

            host_cards.nth(0).scroll_into_view_if_needed()
            first_host_id = host_cards.nth(0).get_attribute("data-draggable-card-id")
            first_box = host_cards.nth(0).bounding_box()
            second_box = host_cards.nth(1).bounding_box()
            if first_box is None or second_box is None or first_host_id is None:
                raise AssertionError("dashboard host cards were not measurable for reorder test")
            page.mouse.move(first_box["x"] + first_box["width"] / 2, first_box["y"] + first_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(second_box["x"] + second_box["width"] / 2, second_box["y"] + second_box["height"] / 2, steps=12)
            page.mouse.up()
            expect(host_cards.nth(1)).to_have_attribute("data-draggable-card-id", first_host_id)

            returned_first_box = host_cards.nth(0).bounding_box()
            moved_first_box = host_cards.nth(1).bounding_box()
            if returned_first_box is None or moved_first_box is None:
                raise AssertionError("dashboard host cards were not measurable for drag rollback test")
            page.mouse.move(moved_first_box["x"] + moved_first_box["width"] / 2, moved_first_box["y"] + moved_first_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(returned_first_box["x"] + returned_first_box["width"] / 2, returned_first_box["y"] + returned_first_box["height"] / 2, steps=12)
            page.mouse.up()
            expect(host_cards.nth(0)).to_have_attribute("data-draggable-card-id", first_host_id)

            first_box = host_cards.nth(0).bounding_box()
            second_box = host_cards.nth(1).bounding_box()
            if first_box is None or second_box is None:
                raise AssertionError("dashboard host cards were not measurable for final reorder test")
            page.mouse.move(first_box["x"] + first_box["width"] / 2, first_box["y"] + first_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(second_box["x"] + second_box["width"] / 2, second_box["y"] + second_box["height"] / 2, steps=12)
            page.mouse.up()
            expect(host_cards.nth(1)).to_have_attribute("data-draggable-card-id", first_host_id)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            page.locator(".dashboard-host-grid [data-draggable-card='true']").nth(0).scroll_into_view_if_needed()
            expect(page.locator(".dashboard-host-grid [data-draggable-card='true']").nth(1)).to_have_attribute("data-draggable-card-id", first_host_id)
            note("PASS: dashboard cards drag reorder and persist")
        else:
            note("SKIP: dashboard card drag reorder, fewer than two host cards")

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
            page.wait_for_load_state("domcontentloaded")
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
            expect(page.get_by_role("button", name="Refresh Resources")).to_have_count(0)
            note("PASS: SSH test action rendered without manual resource refresh")
        else:
            note("SKIP: SSH test action, no remote SSH server configured")

        click_nav(page, 4)
        expect(page.get_by_role("heading", name="Config", exact=True)).to_be_visible()
        host_input = page.locator("label", has_text="Host ID").locator("input")
        original_host = host_input.input_value()
        host_input.fill("draft-host-not-saved")
        page.wait_for_timeout(4200)
        if host_input.input_value() != "draft-host-not-saved":
            raise AssertionError("config draft was overwritten by auto refresh")
        host_input.fill(original_host)
        note("PASS: config draft survives auto refresh")

        unmanaged_input = page.locator("label", has_text="Unmanaged process limit").locator("input")
        original_unmanaged = unmanaged_input.input_value()
        temporary_unmanaged = "81" if original_unmanaged != "81" else "82"
        unmanaged_input.fill(temporary_unmanaged)
        page.get_by_role("button", name="Save Config").click()
        expect(page.get_by_text("Collector config saved")).to_be_visible(timeout=10000)
        page.wait_for_timeout(700)
        if unmanaged_input.input_value() != temporary_unmanaged:
            raise AssertionError("saved config value did not remain in the UI")
        unmanaged_input.fill(original_unmanaged)
        page.get_by_role("button", name="Save Config").click()
        expect(page.get_by_text("Collector config saved")).to_be_visible(timeout=10000)
        note("PASS: config save round-trip")

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
