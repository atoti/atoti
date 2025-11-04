import argparse
import gc
import os
import sys
import time
import logging
from typing import List
from utils.exclusion_utils import (
    resolve_target_notebooks,
    add_and_validate_target_args,
)
from playwright.sync_api import sync_playwright, TimeoutError, Page

# =====================
# Configuration
# =====================
CONFIG = {
    "jupyter_url": os.getenv("JUPYTER_LAB_URL", "http://localhost:8888/lab/tree/"),
    "headless": os.getenv("PLAYWRIGHT_HEADLESS", "1") != "0",
    "slow_mo": int(os.getenv("PLAYWRIGHT_SLOWMO", "2000")),
    "timeouts": {
        "dialog": 3000,
        "restart_idle": 5000,
        "run_start": 1000,
        "run_idle": 600000,
        "page_load": 90000,
        "cell_attach": 15000,
        "panel_visible": 30000,
    },
}

# =====================
# Selectors
# =====================
SELECTORS = {
    "menus": {
        "kernel": 'li.lm-MenuBar-item:has-text("Kernel")',
        "file": 'li.lm-MenuBar-item:has-text("File")',
    },
    "kernel_actions": {
        "shutdown_all": 'li.lm-Menu-item[data-command="kernelmenu:shutdownAll"]:not(.lm-mod-disabled)',
        "restart": 'li.lm-Menu-item[data-command="kernelmenu:restart"]:not(.lm-mod-disabled)',
    },
    "notebook": {
        "panel": "div.jp-NotebookPanel",
        "visible_panel": "div.jp-NotebookPanel:not(.lm-mod-hidden)",
        "code_cells": "div.jp-NotebookPanel:not(.lm-mod-hidden) .jp-Cell.jp-CodeCell",
        "exec_busy": "div.jp-Notebook-ExecutionIndicator[data-status='busy']",
        "exec_idle": "div.jp-Notebook-ExecutionIndicator[data-status='idle']",
        "input_prompt": ".jp-InputArea-prompt",
    },
}

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
def handle_file_changed_dialog(page: Page) -> None:
    """Handle potential file changed dialog that appears before save/close operations."""
    try:
        dialog = page.locator('dialog[aria-label*="File Changed"]')
        if dialog.is_visible(timeout=1000):
            logger.info("  🔔 File changed dialog detected, dismissing...")
            overwrite_btn = dialog.get_by_role("button", name="Overwrite")
            if overwrite_btn.is_visible():
                overwrite_btn.click()
                page.wait_for_timeout(1000)
    except Exception:
        pass


def execute_cell_with_timing(page: Page, cell, run_index: int, timeout: int) -> float:
    """Execute a single cell and return execution time."""
    cell.wait_for(state="attached", timeout=CONFIG["timeouts"]["cell_attach"])
    cell.scroll_into_view_if_needed()
    page.wait_for_timeout(100)  # Reduced from 500ms to 100ms
    cell.evaluate("el => el.focus()")

    start_time = time.time()
    page.keyboard.press("Shift+Enter")

    # Check if execution started - balanced timeout for fast vs normal cells
    try:
        page.wait_for_selector(
            SELECTORS["notebook"]["exec_busy"],
            state="attached",
            timeout=800,  # 800ms - fast enough to catch quick cells, slow enough for normal ones
        )
        # Wait for completion
        page.wait_for_selector(
            SELECTORS["notebook"]["exec_idle"], state="attached", timeout=timeout
        )
    except TimeoutError:
        # Fast cell completed before busy indicator appeared - check execution count
        execution_count = cell.locator(
            SELECTORS["notebook"]["input_prompt"]
        ).text_content()
        if execution_count and any(c.isdigit() for c in execution_count):
            return time.time() - start_time
        # If no execution count, it's a real timeout
        execution_time = time.time() - start_time
        logger.warning(f"⚠️  Cell {run_index + 1} timeout after {execution_time:.1f}s")
        raise

    return time.time() - start_time


def setup_notebook_panel(page: Page, nb: str, base_timeout: int) -> int:
    """Activate notebook panel and return adjusted timeout based on notebook type."""
    page.wait_for_selector(
        SELECTORS["notebook"]["visible_panel"],
        state="visible",
        timeout=CONFIG["timeouts"]["panel_visible"],
    )
    logger.info(f"  ✅ Notebook panel activated for {nb}")

    # Get adjusted timeout based on notebook type
    notebook_name = page.url.split("/")[-1] if page.url else ""
    intensive_keywords = [
        "market-risk",
        "bucket-analysis",
        "stressed-var",
        "xva",
        "irrbb",
        "cvar-optimizer",
        "price-elasticity",
    ]
    if any(keyword in notebook_name for keyword in intensive_keywords):
        return min(900000, base_timeout * 5)
    return min(base_timeout, 600000)  # 10 minutes absolute maximum


def cleanup_memory(page: Page = None) -> None:
    """Centralized memory cleanup with optional page-level garbage collection."""
    if page:
        try:
            page.evaluate("() => { if (window.gc) window.gc(); }")
        except Exception:
            pass
    gc.collect()


def create_browser(pw):
    """Create browser with enhanced memory management and optimized settings."""
    browser_args = [
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-gpu",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--max_old_space_size=8192",  # Increased memory limit
        "--memory-pressure-off",  # Disable memory pressure notifications
        "--disable-features=TranslateUI",  # Disable unnecessary features
        "--disable-ipc-flooding-protection",
    ]
    return pw.chromium.launch(
        headless=CONFIG["headless"], slow_mo=CONFIG["slow_mo"], args=browser_args
    )


def restart_kernel_with_shutdown(page: Page) -> None:
    """Shutdown all kernels then restart current kernel and wait for idle."""
    dialog_timeout = CONFIG["timeouts"]["dialog"]
    idle_timeout = CONFIG["timeouts"]["restart_idle"]

    # First shutdown all kernels
    page.click(SELECTORS["menus"]["kernel"])
    try:
        page.wait_for_selector(
            SELECTORS["kernel_actions"]["shutdown_all"], timeout=dialog_timeout
        )
        page.click(SELECTORS["kernel_actions"]["shutdown_all"])
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

    # Then restart the kernel
    page.click(SELECTORS["menus"]["kernel"])
    try:
        page.wait_for_selector(
            SELECTORS["kernel_actions"]["restart"], timeout=dialog_timeout
        )
        page.click(SELECTORS["kernel_actions"]["restart"])
        logger.info("  ▶️  Clicked 'Restart Kernel…'")
        page.wait_for_selector(
            SELECTORS["notebook"]["exec_idle"], state="attached", timeout=idle_timeout
        )
        logger.info("  🟢 Kernel is idle")
    except TimeoutError:
        logger.warning("  ⚠️ 'Restart Kernel…' not present, skipping restart")


def run_all_code_cells(
    page: Page, idle_timeout: int, start_timeout: int = None
) -> None:
    """Execute all visible code cells in the notebook."""
    if start_timeout is None:
        start_timeout = CONFIG["timeouts"]["run_start"]
    page.wait_for_selector(
        SELECTORS["notebook"]["visible_panel"], state="visible", timeout=10000
    )
    page.click(SELECTORS["notebook"]["visible_panel"])

    try:
        page.wait_for_selector(
            SELECTORS["notebook"]["code_cells"], state="attached", timeout=10000
        )
        cells = page.locator(SELECTORS["notebook"]["code_cells"])
        total = cells.count()
        if total == 0:
            logger.error("❌ No code cells found in notebook")
            return
    except Exception as e:
        logger.error(f"❌ Failed to find code cells: {e}")
        return

    logger.info(f"  ▶️  Running {total} code cells…")
    consecutive_failures = 0
    current_timeout = idle_timeout

    for run_index in range(total):
        if consecutive_failures >= 3:
            logger.error(
                f"❌ Aborting execution after {consecutive_failures} consecutive failures"
            )
            break

        try:
            cell = cells.nth(run_index)
            execution_time = execute_cell_with_timing(
                page, cell, run_index, current_timeout
            )
            logger.info(
                f"     → Code cell {run_index + 1}/{total}: Completed in {execution_time:.1f}s"
            )
            consecutive_failures = 0

        except Exception as e:
            error_msg = str(e)
            if "Target crashed" in error_msg or "Browser context closed" in error_msg:
                logger.error(f"🔥 Browser crash detected at cell {run_index + 1}")
                raise
            logger.error(f"❌ Error in cell {run_index + 1}: {e}")
            consecutive_failures += 1

    logger.info("  💯 Run all cells completed")


def cleanup_notebook(page: Page, nb: str) -> None:
    """Save and close the current notebook."""
    handle_file_changed_dialog(page)

    # Save notebook
    page.keyboard.press("Control+s")
    page.wait_for_timeout(2000)  # Allow save to complete
    logger.info("  💾 Notebook saved")

    # Close tab
    handle_file_changed_dialog(page)
    page.click(SELECTORS["menus"]["file"])
    try:
        item = page.get_by_role("menuitem", name="Close Tab")
        item.click()
        logger.info("  🙅 Close tab")
    except Exception:
        logger.warning("  ⚠️ 'Close Tab' is not available, nothing to do")


def run_notebook(nb: str, page: Page, idle_timeout: int) -> float:
    """Open a notebook, restart kernel, run cells, save and close. Returns execution time."""
    logger.info(f"→ {nb}")
    nb_start_time = time.time()
    try:
        page.goto(
            CONFIG["jupyter_url"] + nb,
            timeout=CONFIG["timeouts"]["page_load"],
            wait_until="load",
        )
        page.wait_for_timeout(2000)

        current_timeout = setup_notebook_panel(page, nb, idle_timeout)

        try:
            restart_kernel_with_shutdown(page)
        except Exception:
            logger.warning(f"⚠️  Kernel restart failed for {nb}")
        run_all_code_cells(page, idle_timeout=current_timeout)

        try:
            cleanup_notebook(page, nb)
        except Exception:
            logger.warning(f"⚠️  Cleanup failed for {nb}")

        cleanup_memory(page)

        nb_duration = time.time() - nb_start_time
        logger.info(
            f"✔ {nb} (Duration: {int(nb_duration // 60)}m {int(nb_duration % 60)}s)"
        )
        return nb_duration

    except Exception as e:
        error_msg = str(e)
        if "Target crashed" in error_msg or "Browser context closed" in error_msg:
            icon, error_type = "🔥", "crash"
        elif "TimeoutError" in error_msg or "timeout" in error_msg.lower():
            icon, error_type = "⏰", "timeout"
        else:
            icon, error_type = "❌", "other"
        logger.error(f"{icon} {error_type.title()} on {nb}: {e}")
        try:
            cleanup_notebook(page, nb)
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
    """Launch browser, run all notebook tests, collect results, and print a summary."""
    parser = argparse.ArgumentParser(
        description="Render target notebooks with Playwright."
    )
    args = add_and_validate_target_args(parser)
    notebooks = resolve_target_notebooks(args.target)
    logger.info(f"Found {len(notebooks)} notebooks to render:")
    for notebook in notebooks:
        logger.info(f"  - {notebook}")

    # Set timeout based on target groups
    normalized_targets = [
        part.strip().lower().replace(" ", "-")
        for arg in args.target
        for part in arg.split(",")
        if part.strip()
    ]
    run_idle_timeout = (
        7200000
        if "long-running" in normalized_targets
        else CONFIG["timeouts"]["run_idle"]
    )

    total_start_time = time.time()
    results: List[dict] = []
    failures: List[str] = []

    with sync_playwright() as pw:
        browser = create_browser(pw)

        try:
            for idx, nb in enumerate(notebooks, 1):
                logger.info(f"Processing notebook {idx}/{len(notebooks)}")

                try:
                    with browser.new_page() as page:
                        page.set_default_timeout(180000)
                        page.set_extra_http_headers({"Cache-Control": "no-cache"})

                        duration = run_notebook(nb, page, idle_timeout=run_idle_timeout)
                        results.append(
                            {"name": nb, "status": "COMPLETE", "duration": duration}
                        )

                except Exception as e:
                    if "crash" in str(e).lower() or "target closed" in str(e).lower():
                        logger.error(f"🔥 Browser crash on {nb}, restarting...")
                        browser.close()
                        cleanup_memory()
                        time.sleep(2)
                        browser = create_browser(pw)
                    else:
                        logger.error(f"❌ Error on {nb}: {e}")

                    results.append({"name": nb, "status": "FAIL", "duration": 0})
                    failures.append(nb)

                # Efficient memory cleanup every 5 notebooks
                if idx % 5 == 0:
                    logger.info("🧹 Memory cleanup")
                    cleanup_memory()

        finally:
            browser.close()
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
