import os
from exclusion_utils import get_included_notebooks
import re
from playwright.sync_api import sync_playwright, TimeoutError
import sys

# Gather the list of notebooks under the project directory
notebooks = get_included_notebooks()

for notebook in notebooks:
    print(notebook)

JUPYTER_LAB_URL = "http://localhost:8888/lab/tree/"


def shutdown_and_restart_kernel(
    page,
    idle_timeout: int = 5000,
    dialog_timeout: int = 3000,
):
    # 1) Open Kernel → wait for the shutdown entry
    page.click('li.lm-MenuBar-item:has-text("Kernel")')
    shutdown_sel = (
        'li.lm-Menu-item[data-command="kernelmenu:shutdownAll"]:not(.lm-mod-disabled)'
    )
    try:
        page.wait_for_selector(shutdown_sel, timeout=dialog_timeout)
        page.click(shutdown_sel)
        print("  ▶️  Clicked “Shut Down All Kernels…”")

        # confirm dialog if it appears
        try:
            dlg = page.get_by_role("dialog")
            dlg.wait_for(state="visible", timeout=dialog_timeout)
            dlg.get_by_role("button", name="Shut Down All").click()
            print("  ✅ Confirmed shutdown")
        except TimeoutError:
            print("  ⚠️ No shutdown dialog appeared")

        page.wait_for_timeout(2_000)
    except TimeoutError:
        print("  ⚠️ ‘Shut Down All Kernels…’ not present, skipping shutdown")

    # 2) Open Kernel → wait for the restart entry
    page.click('li.lm-MenuBar-item:has-text("Kernel")')
    restart_sel = (
        'li.lm-Menu-item[data-command="kernelmenu:restart"]:not(.lm-mod-disabled)'
    )
    try:
        page.wait_for_selector(restart_sel, timeout=dialog_timeout)
        page.click(restart_sel)
        print("  ▶️  Clicked “Restart Kernel…”")

        page.wait_for_selector(
            'div.jp-Notebook-ExecutionIndicator[data-status="idle"]',
            state="attached",
            timeout=idle_timeout,
        )
        print("  🟢 Kernel is idle")

    except TimeoutError:
        print("  ⚠️ ‘Restart Kernel…’ not present, skipping restart")
        return


def click_restart_run_all(page):
    page.click('li.lm-MenuBar-item:has-text("Kernel")')
    page.get_by_role("menuitem", name="Restart Kernel and Run All Cells").click()


def run_all_code_cells_robust(
    page,
    start_timeout: int = 3000,  # how long to wait for a busy→idle transition to start
    idle_timeout: int = 600_000,  # how long to wait for the notebook to finish
):
    # 0) Focus the visible notebook panel
    page.wait_for_selector(
        "div.jp-NotebookPanel:not(.lm-mod-hidden)",
        state="visible",
    )
    page.click("div.jp-NotebookPanel:not(.lm-mod-hidden)")

    # 1) Collect only the visible code cells
    cells = page.locator(
        "div.jp-NotebookPanel:not(.lm-mod-hidden) .jp-Cell.jp-CodeCell"
    )
    total = sum(1 for i in range(cells.count()) if cells.nth(i).is_visible())
    print(f"  ▶️  Running {total} visible code cells…")

    run_index = 0
    for i in range(cells.count()):
        cell = cells.nth(i)
        if not cell.is_visible():
            continue
        run_index += 1
        print(f"     → Code cell {run_index}/{total}")

        # bring it into view & focus
        cell.scroll_into_view_if_needed()
        cell.evaluate("el => el.focus()")

        # run & advance
        page.keyboard.press("Shift+Enter")

        # 2) Short wait for busy (in case it actually fires)
        try:
            page.wait_for_selector(
                "div.jp-Notebook-ExecutionIndicator[data-status='busy']",
                state="attached",
                timeout=start_timeout,
            )
        except TimeoutError:
            # cell was too fast to ever go busy
            pass

        # 3) Always wait for idle before moving on
        try:
            page.wait_for_selector(
                "div.jp-Notebook-ExecutionIndicator[data-status='idle']",
                state="attached",
                timeout=idle_timeout,
            )
        except TimeoutError:
            print(f"⚠️  Code cell {run_index} did not return to idle in time")

    print("  💯 Run all cells completed")


def click_close_tab(page):
    page.click('li.lm-MenuBar-item:has-text("File")')
    item = page.get_by_role("menuitem", name="Close Tab")
    if item.is_visible() and item.is_enabled():
        item.click()
        print("  🙅 Close tab")
    else:
        print("  ⚠️ 'Close Tab' is disabled—nothing to do")


def run(nb, page):
    print(f"→ {nb}")
    page.goto(JUPYTER_LAB_URL + nb)
    shutdown_and_restart_kernel(page)
    run_all_code_cells_robust(page)

    # wait for notebook to be saved
    page.get_by_role("button", name=re.compile(r"Save and create checkpoint")).click()
    print("  💾 Notebook saved")

    click_close_tab(page)

    print(f"✔ {nb}")


def main():
    headless = os.getenv("PLAYWRIGHT_HEADLESS", "0") != "0"
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=1000)
        page = browser.new_page()
        for nb in notebooks:
            try:
                run(nb, page)
            except Exception as e:
                print(f"✖ Error on {nb}: {e}", file=sys.stderr)
                failures.append(nb)
        browser.close()

    if failures:
        print("Failed:", failures, file=sys.stderr)
        sys.exit(1)
    print("All notebooks ran successfully!")
    sys.exit(0)


if __name__ == "__main__":
    main()
