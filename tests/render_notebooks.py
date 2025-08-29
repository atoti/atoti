import argparse
import os
import sys
import time
import logging
from typing import List
from exclusion_utils import (
    resolve_target_notebooks,
    add_and_validate_target_args,
)
from playwright.sync_api import sync_playwright, TimeoutError, Page

# =====================
# Configuration
# =====================
JUPYTER_LAB_URL = os.getenv("JUPYTER_LAB_URL", "http://localhost:8888/lab/tree/")
HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "1") != "0"
SLOW_MO = int(os.getenv("PLAYWRIGHT_SLOWMO", "2000"))
SHUTDOWN_DIALOG_TIMEOUT = 3000  # ms to wait for shutdown dialog
RESTART_DIALOG_TIMEOUT = 3000  # ms to wait for restart dialog
RESTART_IDLE_TIMEOUT = 5000  # ms to wait for kernel idle after restart
RUN_START_TIMEOUT = 1000  # ms to wait for cell to go busy
RUN_IDLE_TIMEOUT = 600000  # ms to wait for cell to go idle after execution

# =====================
# Logging setup
# =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("notebook-renderer")


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
    idle_timeout: int,
    start_timeout: int = RUN_START_TIMEOUT,
) -> None:
    """
    Execute all visible code cells in the notebook, ensuring each cell completes
    before moving to the next.
    """
    page.wait_for_selector("div.jp-NotebookPanel:not(.lm-mod-hidden)", state="attached")
    page.click("div.jp-NotebookPanel:not(.lm-mod-hidden)")
    cells = page.locator(
        "div.jp-NotebookPanel:not(.lm-mod-hidden) .jp-Cell.jp-CodeCell"
    )
    # Get all code cells
    cell_count = cells.count()
    total = cell_count
    logger.info(f"  ▶️  Running {total} code cells…")

    for run_index in range(total):
        logger.info(f"     → Code cell {run_index + 1}/{total}")
        try:
            # Get the cell with retry logic
            cell = cells.nth(run_index)
            # Wait for cell to be available with timeout
            cell.wait_for(state="attached", timeout=30000)
            cell.scroll_into_view_if_needed()
            # Add a small delay to ensure cell is ready
            page.wait_for_timeout(500)
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
                # Enhanced timeout for computationally intensive notebooks
                current_idle_timeout = idle_timeout
                notebook_name = page.url.split("/")[-1] if page.url else ""
                if any(
                    keyword in notebook_name
                    for keyword in [
                        "market-risk",
                        "bucket-analysis",
                        "stressed-var",
                        "xva",
                        "irrbb",
                    ]
                ):
                    current_idle_timeout = min(
                        300000, idle_timeout * 3
                    )  # Up to 5 minutes for intensive cells
                    logger.info(
                        f"     ⏱️  Using extended timeout ({current_idle_timeout / 1000}s) for intensive computation"
                    )

                page.wait_for_selector(
                    "div.jp-Notebook-ExecutionIndicator[data-status='idle']",
                    state="attached",
                    timeout=current_idle_timeout,
                )
            except TimeoutError:
                logger.warning(
                    f"⚠️  Code cell {run_index + 1} did not return to idle in time"
                )

        except TimeoutError as e:
            logger.error(f"❌ Error accessing cell {run_index + 1}: {e}")
            # Try to continue with next cell
            continue
        except Exception as e:
            logger.error(f"❌ Unexpected error in cell {run_index + 1}: {e}")
            continue

    logger.info("  💯 Run all cells completed")


def close_tab(page: Page) -> None:
    """
    Close the currently active notebook tab in JupyterLab.
    """
    # Handle potential file changed dialog before closing tab
    try:
        dialog = page.locator('dialog[aria-label*="File Changed"]')
        if dialog.is_visible(timeout=1000):
            logger.info("  🔔 File changed dialog detected, dismissing...")
            # Click "Overwrite" to dismiss the dialog
            overwrite_btn = dialog.get_by_role("button", name="Overwrite")
            if overwrite_btn.is_visible():
                overwrite_btn.click()
                page.wait_for_timeout(1000)  # Wait for dialog to close
    except Exception:
        pass  # No dialog present

    page.click('li.lm-MenuBar-item:has-text("File")')
    try:
        item = page.get_by_role("menuitem", name="Close Tab")
        item.click()
        logger.info("  🙅 Close tab")
    except Exception:
        logger.warning("  ⚠️ 'Close Tab' is not available, nothing to do")


def save_notebook(page: Page, nb: str) -> None:
    """
    Save the current notebook using the JupyterLab File menu.
    """
    # Handle potential file changed dialog before saving
    try:
        dialog = page.locator('dialog[aria-label*="File Changed"]')
        if dialog.is_visible(timeout=1000):
            logger.info("  🔔 File changed dialog detected, dismissing...")
            # Click "Overwrite" to dismiss the dialog
            overwrite_btn = dialog.get_by_role("button", name="Overwrite")
            if overwrite_btn.is_visible():
                overwrite_btn.click()
                page.wait_for_timeout(1000)  # Wait for dialog to close
    except Exception:
        pass  # No dialog present

    try:
        page.click('li.lm-MenuBar-item:has-text("File")', timeout=30000)
        save_sel = 'li.lm-Menu-item[data-command="docmanager:save"] .lm-Menu-itemLabel:has-text("Save Notebook")'
        page.wait_for_selector(save_sel, state="visible", timeout=30000)
        # Focus on the save button before clicking
        page.locator(save_sel).focus()
        page.click(save_sel, timeout=30000)
        # Wait for save to complete with a shorter timeout
        page.wait_for_timeout(2000)
        logger.info("  💾 Notebook saved")
    except TimeoutError as e:
        logger.warning(f"  ⚠️ Save timeout for {nb}, trying keyboard shortcut: {e}")
        # Try keyboard shortcut as fallback
        try:
            page.keyboard.press("Control+s")
            page.wait_for_timeout(2000)
            logger.info("  💾 Notebook saved via keyboard shortcut")
        except Exception as fallback_e:
            logger.error(f"  ❌ Failed to save {nb}: {fallback_e}")
            raise


def run_notebook(nb: str, page: Page, idle_timeout: int) -> float:
    """
    Open a notebook, restart its kernel, run all code cells, save, and close the
    notebook. Returns execution duration in minutes, seconds.
    """
    logger.info(f"→ {nb}")
    nb_start_time = time.time()
    try:
        # Navigate to notebook with retries
        navigation_attempts = 3
        for attempt in range(navigation_attempts):
            try:
                page.goto(JUPYTER_LAB_URL + nb, timeout=60000, wait_until="load")
                break
            except TimeoutError:
                if attempt == navigation_attempts - 1:
                    raise
                logger.warning(
                    f"  ⚠️ Navigation timeout attempt {attempt + 1}, retrying..."
                )
                page.wait_for_timeout(2000)

        # Add a small delay to ensure page is fully loaded
        page.wait_for_timeout(1000)

        shutdown_kernel(page)
        restart_kernel(page)
        run_all_code_cells(page, idle_timeout=idle_timeout)
        save_notebook(page, nb)
        close_tab(page)

        # Force garbage collection and memory cleanup
        page.evaluate("() => { if (window.gc) window.gc(); }")

        nb_duration = time.time() - nb_start_time
        logger.info(
            f"✔ {nb} (Duration: {int(nb_duration // 60)}m {int(nb_duration % 60)}s)"
        )
        return nb_duration
    except Exception as e:
        logger.error(f"✖ Error on {nb}: {e}")
        # Try to clean up on error
        try:
            close_tab(page)
        except Exception:
            pass
        raise


def print_summary(results: List[dict]) -> None:
    """
    Print a formatted summary table of all notebook test results, including
    status and duration. Shows 'FAIL' for failed notebooks.
    """
    logger.info("\nSummary:")
    logger.info(f"{'Notebook':70} | {'Status':9} | {'Duration':10}")
    logger.info("-" * 102)
    for r in results:
        mins = int(r["duration"] // 60)
        secs = int(r["duration"] % 60)
        status = r["status"]
        logger.info(f"{r['name'][:70]:70} | {status:9} | {mins}m {secs}s")


# =====================
# Main execution
# =====================
def main() -> None:
    """
    Launch browser, run all notebook tests, collect results, and print a summary.
    Exit with error if any failures. Shows 'FAIL' in summary for failed notebooks.
    """
    parser = argparse.ArgumentParser(
        description="Render target notebooks with Playwright."
    )
    args = add_and_validate_target_args(parser)
    notebooks = resolve_target_notebooks(args.target)
    logger.info(f"Found {len(notebooks)} notebooks to render:")
    for notebook in notebooks:
        logger.info(f"  - {notebook}")

    # Normalize all target group names for consistent logic
    normalized_targets = []
    for arg in args.target:
        for part in arg.split(","):
            normalized = part.strip().lower().replace(" ", "-")
            if normalized:
                normalized_targets.append(normalized)
    run_idle_timeout = RUN_IDLE_TIMEOUT  # Use default
    if "long-running" in normalized_targets:
        run_idle_timeout = 7200000  # ms

    total_start_time = time.time()
    results: List[dict] = []
    failures: List[str] = []
    with sync_playwright() as pw:
        # Launch browser with additional memory management flags
        browser_args = [
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-gpu",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--max_old_space_size=4096",
        ]
        with pw.chromium.launch(
            headless=HEADLESS, slow_mo=SLOW_MO, args=browser_args
        ) as browser:
            notebook_count = len(notebooks)
            for idx, nb in enumerate(notebooks):
                logger.info(f"Processing notebook {idx + 1}/{notebook_count}")

                # Create new page for each notebook to prevent memory issues
                with browser.new_page() as page:
                    # Set page timeout
                    page.set_default_timeout(120000)  # 2 minutes

                    try:
                        duration = run_notebook(nb, page, idle_timeout=run_idle_timeout)
                        results.append(
                            {"name": nb, "status": "COMPLETE", "duration": duration}
                        )
                    except Exception as e:
                        # Check if this is a browser crash
                        if "Target crashed" in str(
                            e
                        ) or "Browser context closed" in str(e):
                            logger.error(f"🔥 Browser crashed on {nb}, skipping...")
                            results.append(
                                {"name": nb, "status": "FAIL", "duration": 0}
                            )
                            failures.append(nb)
                            # Force garbage collection and wait before continuing
                            import gc

                            gc.collect()
                            time.sleep(3)
                        else:
                            logger.error(f"Failed notebook {nb}: {str(e)}")
                            results.append(
                                {"name": nb, "status": "FAIL", "duration": 0}
                            )
                            failures.append(nb)

                    # Clean up after each notebook
                    try:
                        page.evaluate("() => { if (window.gc) window.gc(); }")
                    except Exception:
                        pass
    total_duration = time.time() - total_start_time
    print_summary(results)
    if failures:
        logger.error(f"Failed: {failures}")
        sys.exit(1)
    logger.info(
        f"All notebooks ran successfully! Total duration: {int(total_duration // 60)}m {int(total_duration % 60)}s."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
