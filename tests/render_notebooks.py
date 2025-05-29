import os
import sys
from exclusion_utils import get_included_notebooks
from playwright.sync_api import sync_playwright, TimeoutError

# List of notebooks to render, after applying exclusions
notebooks = get_included_notebooks()

for notebook in notebooks:
    print(notebook)

JUPYTER_LAB_URL = "http://localhost:8888/lab/tree/"


def shutdown_kernel(page, dialog_timeout: int = 3000):
    """
    Shut down all kernels in the current JupyterLab page.
    """
    page.click('li.lm-MenuBar-item:has-text("Kernel")')
    shutdown_sel = (
        'li.lm-Menu-item[data-command="kernelmenu:shutdownAll"]:not(.lm-mod-disabled)'
    )
    try:
        page.wait_for_selector(shutdown_sel, timeout=dialog_timeout)
        page.click(shutdown_sel)
        print("  ▶️  Clicked “Shut Down All Kernels…”")
        # Confirm dialog if it appears
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


def restart_kernel(page, idle_timeout: int = 5000, dialog_timeout: int = 3000):
    """
    Restart the kernel in the current JupyterLab page and wait for idle.
    """
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


def run_all_code_cells_robust(
    page, start_timeout: int = 1000, idle_timeout: int = 60000
):
    """
    Run all visible code cells in the current notebook robustly, waiting for idle after each.
    """
    # Focus the visible notebook panel
    page.wait_for_selector("div.jp-NotebookPanel:not(.lm-mod-hidden)", state="visible")
    page.click("div.jp-NotebookPanel:not(.lm-mod-hidden)")

    # Collect only the visible code cells
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

        # Bring it into view & focus
        cell.scroll_into_view_if_needed()
        cell.evaluate("el => el.focus()")

        # Run & advance
        page.keyboard.press("Shift+Enter")

        # Short wait for busy (in case it actually fires)
        try:
            page.wait_for_selector(
                "div.jp-Notebook-ExecutionIndicator[data-status='busy']",
                state="attached",
                timeout=start_timeout,
            )
            # print("       Kernel is busy, waiting for idle…")
        except TimeoutError:
            # print("       Kernel did not go busy, cell executed too quick")
            pass

        # Always wait for idle before moving on
        try:
            page.wait_for_selector(
                "div.jp-Notebook-ExecutionIndicator[data-status='idle']",
                state="attached",
                timeout=idle_timeout,
            )
            # print("       Kernel is now idle")
        except TimeoutError:
            print(f"⚠️  Code cell {run_index} did not return to idle in time")
    print("  💯 Run all cells completed")


def click_close_tab(page):
    """
    Click the close tab menu item to close the current notebook tab.
    """
    page.click('li.lm-MenuBar-item:has-text("File")')
    item = page.get_by_role("menuitem", name="Close Tab")
    if item.is_visible() and item.is_enabled():
        item.click()
        print("  🙅 Close tab")
    else:
        print("  ⚠️ 'Close Tab' is disabled—nothing to do")


def save_notebook(page, nb):
    """
    Save the current notebook using File > Save Notebook.
    """
    page.click('li.lm-MenuBar-item:has-text("File")')
    save_sel = 'li.lm-Menu-item[data-command="docmanager:save"]:not(.lm-mod-disabled)'
    page.wait_for_selector(save_sel, timeout=1000)
    page.click(save_sel)
    print("  💾 Notebook saved")


def run_notebook(nb, page):
    """
    Open, restart, run all cells, save, and close a notebook.
    """
    print(f"→ {nb}")
    page.goto(JUPYTER_LAB_URL + nb)
    shutdown_kernel(page)
    restart_kernel(page)
    run_all_code_cells_robust(page)
    save_notebook(page, nb)
    click_close_tab(page)
    print(f"✔ {nb}")


def main():
    """
    Main entry point: open browser, run all notebooks, handle failures.
    """
    headless = os.getenv("PLAYWRIGHT_HEADLESS", "0") != "0"
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=2000)
        page = browser.new_page()
        for nb in notebooks:
            try:
                run_notebook(nb, page)
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
