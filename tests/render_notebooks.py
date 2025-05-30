import os
import sys
import time
import logging
from typing import List
from exclusion_utils import get_included_notebooks
from playwright.sync_api import sync_playwright, TimeoutError, Page

# =====================
# Configuration
# =====================
JUPYTER_LAB_URL = os.getenv("JUPYTER_LAB_URL", "http://localhost:8888/lab/tree/")
HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "0") != "0"
SLOW_MO = int(os.getenv("PLAYWRIGHT_SLOWMO", "2000"))
SHUTDOWN_DIALOG_TIMEOUT = 3000  # ms to wait for shutdown dialog
RESTART_IDLE_TIMEOUT = 5000  # ms to wait for kernel idle after restart
RESTART_DIALOG_TIMEOUT = 3000  # ms to wait for restart dialog
RUN_START_TIMEOUT = 1000  # ms to wait for cell to go busy
RUN_IDLE_TIMEOUT = 60000  # ms to wait for cell to return to idle
SAVE_TIMEOUT = 1000  # ms to wait for save menu item

# =====================
# Logging setup
# =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("notebook-renderer")

# =====================
# Notebook selection
# =====================
notebooks: List[str] = get_included_notebooks()
logger.info(f"Found {len(notebooks)} notebooks to test:")
for notebook in notebooks:
    logger.info(f"  - {notebook}")


# =====================
# Helper functions
# =====================
def shutdown_kernel(page: Page, dialog_timeout: int = SHUTDOWN_DIALOG_TIMEOUT) -> None:
    """
    Attempt to shut down all running kernels in the current JupyterLab session.
    """
    page.click('li.lm-MenuBar-item:has-text("Kernel")')
    shutdown_sel = (
        'li.lm-Menu-item[data-command="kernelmenu:shutdownAll"]:not(.lm-mod-disabled)'
    )
    try:
        page.wait_for_selector(shutdown_sel, timeout=dialog_timeout)
        page.click(shutdown_sel)
        logger.info("  ▶️  Clicked 'Shut Down All Kernels…'")
        try:
            dlg = page.get_by_role("dialog")
            dlg.wait_for(state="visible", timeout=dialog_timeout)
            dlg.get_by_role("button", name="Shut Down All").click()
            logger.info("  ✅ Confirmed shutdown")
        except TimeoutError:
            logger.warning("  ⚠️ No shutdown dialog appeared")
        page.wait_for_timeout(2000)
    except TimeoutError:
        logger.warning("  ⚠️ 'Shut Down All Kernels…' not present, skipping shutdown")


def restart_kernel(
    page: Page,
    idle_timeout: int = RESTART_IDLE_TIMEOUT,
    dialog_timeout: int = RESTART_DIALOG_TIMEOUT,
) -> None:
    """
    Restart the notebook kernel and wait for it to become idle.
    """
    page.click('li.lm-MenuBar-item:has-text("Kernel")')
    restart_sel = (
        'li.lm-Menu-item[data-command="kernelmenu:restart"]:not(.lm-mod-disabled)'
    )
    try:
        page.wait_for_selector(restart_sel, timeout=dialog_timeout)
        page.click(restart_sel)
        logger.info("  ▶️  Clicked 'Restart Kernel…'")
        page.wait_for_selector(
            'div.jp-Notebook-ExecutionIndicator[data-status="idle"]',
            state="attached",
            timeout=idle_timeout,
        )
        logger.info("  🟢 Kernel is idle")
    except TimeoutError:
        logger.warning("  ⚠️ 'Restart Kernel…' not present, skipping restart")
        return


def run_all_code_cells(
    page: Page,
    start_timeout: int = RUN_START_TIMEOUT,
    idle_timeout: int = RUN_IDLE_TIMEOUT,
) -> None:
    """
    Execute all visible code cells in the notebook, ensuring each cell completes
    before moving to the next.
    """
    page.wait_for_selector("div.jp-NotebookPanel:not(.lm-mod-hidden)", state="visible")
    page.click("div.jp-NotebookPanel:not(.lm-mod-hidden)")
    cells = page.locator(
        "div.jp-NotebookPanel:not(.lm-mod-hidden) .jp-Cell.jp-CodeCell"
    )
    total = sum(1 for i in range(cells.count()) if cells.nth(i).is_visible())
    logger.info(f"  ▶️  Running {total} visible code cells…")
    run_index = 0
    for i in range(cells.count()):
        cell = cells.nth(i)
        if not cell.is_visible():
            continue
        run_index += 1
        logger.info(f"     → Code cell {run_index}/{total}")
        cell.scroll_into_view_if_needed()
        cell.evaluate("el => el.focus()")
        page.keyboard.press("Shift+Enter")
        try:
            page.wait_for_selector(
                "div.jp-Notebook-ExecutionIndicator[data-status='busy']",
                state="attached",
                timeout=start_timeout,
            )
        except TimeoutError:
            pass
        try:
            page.wait_for_selector(
                "div.jp-Notebook-ExecutionIndicator[data-status='idle']",
                state="attached",
                timeout=idle_timeout,
            )
        except TimeoutError:
            logger.warning(f"⚠️  Code cell {run_index} did not return to idle in time")
    logger.info("  💯 Run all cells completed")


def close_tab(page: Page) -> None:
    """
    Close the currently active notebook tab in JupyterLab.
    """
    page.click('li.lm-MenuBar-item:has-text("File")')
    item = page.get_by_role("menuitem", name="Close Tab")
    if item.is_visible() and item.is_enabled():
        item.click()
        logger.info("  🙅 Close tab")
    else:
        logger.warning("  ⚠️ 'Close Tab' is disabled, nothing to do")


def save_notebook(page: Page, nb: str) -> None:
    """
    Save the current notebook using the JupyterLab File menu.
    """
    page.click('li.lm-MenuBar-item:has-text("File")')
    save_sel = 'li.lm-Menu-item[data-command="docmanager:save"]:not(.lm-mod-disabled)'
    page.wait_for_selector(save_sel, timeout=SAVE_TIMEOUT)
    page.click(save_sel)
    logger.info("  💾 Notebook saved")


def run_notebook(nb: str, page: Page) -> float:
    """
    Open a notebook, restart its kernel, run all code cells, save, and close the
    notebook. Returns execution duration in minutes, seconds.
    """
    logger.info(f"→ {nb}")
    nb_start_time = time.time()
    try:
        page.goto(JUPYTER_LAB_URL + nb)
        shutdown_kernel(page)
        restart_kernel(page)
        run_all_code_cells(page)
        save_notebook(page, nb)
        close_tab(page)
        nb_duration = time.time() - nb_start_time
        logger.info(
            f"✔ {nb} (Duration: {int(nb_duration // 60)}m {int(nb_duration % 60)}s)"
        )
        return nb_duration
    except Exception as e:
        logger.error(f"✖ Error on {nb}: {e}")
        raise


def print_summary(results: List[dict]) -> None:
    """
    Print a formatted summary table of all notebook test results, including
    status and duration.
    """
    logger.info("\nSummary:")
    logger.info(f"{'Notebook':60} | {'Status':8} | {'Duration':10}")
    logger.info("-" * 85)
    for r in results:
        mins = int(r["duration"] // 60)
        secs = int(r["duration"] % 60)
        logger.info(f"{r['name'][:60]:60} | {r['status']:8} | {mins}m {secs}s")


# =====================
# Main execution
# =====================
def main() -> None:
    """
    Launch browser, run all notebook tests, collect results, and print a summary.
    Exit with error if any failures.
    """
    total_start_time = time.time()
    results = []
    failures = []
    with sync_playwright() as pw:
        with pw.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO) as browser:
            with browser.new_page() as page:
                for nb in notebooks:
                    try:
                        duration = run_notebook(nb, page)
                        results.append(
                            {"name": nb, "status": "PASS", "duration": duration}
                        )
                    except Exception:
                        results.append({"name": nb, "status": "FAIL", "duration": 0})
                        failures.append(nb)
    total_duration = time.time() - total_start_time
    print_summary(results)
    total_minutes = int(total_duration // 60)
    total_seconds = int(total_duration % 60)
    if failures:
        logger.error(f"Failed: {failures}")
        sys.exit(1)
    logger.info(
        f"All notebooks ran successfully! Total duration: {total_minutes}m {total_seconds}s."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
