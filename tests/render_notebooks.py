import argparse
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
JUPYTER_LAB_URL = os.getenv("JUPYTER_LAB_URL", "http://localhost:8888/lab/tree/")
HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "1") != "0"
SLOW_MO = int(os.getenv("PLAYWRIGHT_SLOWMO", "2000"))
SHUTDOWN_DIALOG_TIMEOUT = 3000  # ms to wait for shutdown dialog
RESTART_DIALOG_TIMEOUT = 3000  # ms to wait for restart dialog
RESTART_IDLE_TIMEOUT = 5000  # ms to wait for kernel idle after restart
RUN_START_TIMEOUT = 1000  # ms to wait for cell to go busy
RUN_IDLE_TIMEOUT = 600000  # ms to wait for cell to go idle after execution

# =====================
# Selectors
# =====================
KERNEL_MENU = 'li.lm-MenuBar-item:has-text("Kernel")'
FILE_MENU = 'li.lm-MenuBar-item:has-text("File")'
SHUTDOWN_ALL_KERNELS = (
    'li.lm-Menu-item[data-command="kernelmenu:shutdownAll"]:not(.lm-mod-disabled)'
)
RESTART_KERNEL = (
    'li.lm-Menu-item[data-command="kernelmenu:restart"]:not(.lm-mod-disabled)'
)
SAVE_NOTEBOOK = 'li.lm-Menu-item[data-command="docmanager:save"] .lm-Menu-itemLabel:has-text("Save Notebook")'
NOTEBOOK_PANEL = "div.jp-NotebookPanel"
VISIBLE_NOTEBOOK_PANEL = "div.jp-NotebookPanel:not(.lm-mod-hidden)"
HIDDEN_NOTEBOOK_PANEL = "div.jp-NotebookPanel.lm-mod-hidden"
CODE_CELLS = "div.jp-NotebookPanel:not(.lm-mod-hidden) .jp-Cell.jp-CodeCell"
EXECUTION_INDICATOR_BUSY = "div.jp-Notebook-ExecutionIndicator[data-status='busy']"
EXECUTION_INDICATOR_IDLE = "div.jp-Notebook-ExecutionIndicator[data-status='idle']"
INPUT_PROMPT = ".jp-InputArea-prompt"

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


def classify_error(error_msg: str) -> str:
    """Classify error types for consistent handling."""
    if "Target crashed" in error_msg or "Browser context closed" in error_msg:
        return "crash"
    elif "TimeoutError" in error_msg or "timeout" in error_msg.lower():
        return "timeout"
    else:
        return "other"


def check_execution_started(page: Page, cells, run_index: int) -> tuple[bool, float]:
    """Check if cell execution started and return status and execution time."""
    try:
        page.wait_for_selector(EXECUTION_INDICATOR_BUSY, state="attached", timeout=5000)
        return True, None
    except TimeoutError:
        # Check execution count in prompt to see if cell completed quickly
        try:
            current_cell = cells.nth(run_index)
            execution_count = current_cell.locator(INPUT_PROMPT).text_content()
            if execution_count and any(c.isdigit() for c in execution_count):
                return True, time.time()
        except Exception:
            pass
        return False, None


def get_notebook_timeout(page: Page, base_timeout: int) -> int:
    """Get adjusted timeout based on notebook type."""
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


def activate_notebook_panel(page: Page, nb: str) -> None:
    """Ensure notebook panel is visible and activated."""
    page.wait_for_selector(NOTEBOOK_PANEL, state="attached", timeout=30000)
    visible_panels = page.locator(VISIBLE_NOTEBOOK_PANEL)

    if visible_panels.count() == 0:
        logger.info(f"  📋 No visible panels, trying to activate tab for {nb}")
        notebook_filename = nb.split("/")[-1]

        # Try to find matching tab
        tabs = page.locator('.lm-TabBar-tab[title*=".ipynb"]')
        for i in range(tabs.count()):
            tab = tabs.nth(i)
            title = tab.get_attribute("title") or ""
            if notebook_filename in title:
                logger.info(f"  🎯 Found matching tab: {title[:50]}...")
                tab.click(timeout=5000)
                page.wait_for_timeout(2000)
                return

        # Fallback: click first available notebook tab
        notebook_tabs = page.locator(".lm-TabBar-tab.lm-mod-closable")
        if notebook_tabs.count() > 0:
            logger.info("  🔄 Fallback: clicking first available notebook tab")
            notebook_tabs.first.click(timeout=5000)
            page.wait_for_timeout(2000)

    # Verify we have a visible panel
    if page.locator(VISIBLE_NOTEBOOK_PANEL).count() == 0:
        page.wait_for_selector(VISIBLE_NOTEBOOK_PANEL, timeout=10000)

    logger.info(f"  ✅ Notebook panel activated for {nb}")


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
    return pw.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO, args=browser_args)


def shutdown_kernel(page: Page, dialog_timeout: int = SHUTDOWN_DIALOG_TIMEOUT) -> None:
    """Attempt to shut down all running kernels in the current JupyterLab session."""
    page.click(KERNEL_MENU)
    try:
        page.wait_for_selector(SHUTDOWN_ALL_KERNELS, timeout=dialog_timeout)
        page.click(SHUTDOWN_ALL_KERNELS)
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
    """Restart the notebook kernel and wait for it to become idle."""
    page.click(KERNEL_MENU)
    try:
        page.wait_for_selector(RESTART_KERNEL, timeout=dialog_timeout)
        page.click(RESTART_KERNEL)
        logger.info("  ▶️  Clicked 'Restart Kernel…'")
        page.wait_for_selector(
            EXECUTION_INDICATOR_IDLE, state="attached", timeout=idle_timeout
        )
        logger.info("  🟢 Kernel is idle")
    except TimeoutError:
        logger.warning("  ⚠️ 'Restart Kernel…' not present, skipping restart")


def run_all_code_cells(
    page: Page, idle_timeout: int, start_timeout: int = RUN_START_TIMEOUT
) -> None:
    """Execute all visible code cells in the notebook."""
    for attempt in range(3):
        try:
            page.wait_for_selector(NOTEBOOK_PANEL, state="attached", timeout=10000)
            visible_panel = page.locator(VISIBLE_NOTEBOOK_PANEL)

            if visible_panel.count() == 0:
                hidden_panel = page.locator(HIDDEN_NOTEBOOK_PANEL).first
                if hidden_panel.count() > 0:
                    panel_id = hidden_panel.get_attribute("id")
                    if panel_id:
                        tab = page.locator(
                            f'.lm-TabBar-tab[aria-describedby="{panel_id}"]'
                        )
                        if tab.count() > 0:
                            tab.click(timeout=5000)
                            page.wait_for_timeout(1000)

            page.wait_for_selector(
                VISIBLE_NOTEBOOK_PANEL, state="visible", timeout=5000
            )
            break
        except TimeoutError:
            if attempt == 2:
                logger.error(
                    "❌ Notebook panel not found or not activatable after 3 attempts"
                )
                raise
            logger.warning(f"⚠️  Notebook panel not ready, retry {attempt + 1}/3")
            page.wait_for_timeout(2000)

    page.click(VISIBLE_NOTEBOOK_PANEL)

    try:
        page.wait_for_selector(CODE_CELLS, state="attached", timeout=10000)
        cells = page.locator(CODE_CELLS)
        total = cells.count()
        if total == 0:
            logger.error("❌ No code cells found in notebook")
            return
    except Exception as e:
        logger.error(f"❌ Failed to find code cells: {e}")
        return

    logger.info(f"  ▶️  Running {total} code cells…")
    consecutive_failures = 0
    current_timeout = get_notebook_timeout(page, idle_timeout)

    for run_index in range(total):
        if consecutive_failures >= 3:
            logger.error(
                f"❌ Aborting execution after {consecutive_failures} consecutive failures"
            )
            break

        try:
            cell = cells.nth(run_index)
            cell.wait_for(state="attached", timeout=15000)
            cell.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            cell.evaluate("el => el.focus()")

            start_time = time.time()
            page.keyboard.press("Shift+Enter")

            execution_started, quick_time = check_execution_started(
                page, cells, run_index
            )
            if not execution_started:
                logger.warning(
                    f"⚠️  Cell {run_index + 1} execution may not have started"
                )
                consecutive_failures += 1
                continue
            if quick_time is None:
                try:
                    page.wait_for_selector(
                        EXECUTION_INDICATOR_IDLE,
                        state="attached",
                        timeout=current_timeout,
                    )
                    execution_time = time.time() - start_time
                except TimeoutError:
                    execution_time = time.time() - start_time
                    logger.warning(
                        f"⚠️  Cell {run_index + 1} timeout after {execution_time:.1f}s"
                    )
                    consecutive_failures += 1
                    continue
            else:
                execution_time = quick_time - start_time

            logger.info(
                f"     → Code cell {run_index + 1}/{total}: Completed in {execution_time:.1f}s"
            )
            consecutive_failures = 0

        except Exception as e:
            error_type = classify_error(str(e))
            if error_type == "crash":
                logger.error(f"🔥 Browser crash detected at cell {run_index + 1}")
                raise
            logger.error(f"❌ Error in cell {run_index + 1}: {e}")
            consecutive_failures += 1

    logger.info("  💯 Run all cells completed")


def close_tab(page: Page) -> None:
    """Close the currently active notebook tab in JupyterLab."""
    handle_file_changed_dialog(page)
    page.click('li.lm-MenuBar-item:has-text("File")')
    try:
        item = page.get_by_role("menuitem", name="Close Tab")
        item.click()
        logger.info("  🙅 Close tab")
    except Exception:
        logger.warning("  ⚠️ 'Close Tab' is not available, nothing to do")


def save_notebook(page: Page, nb: str) -> None:
    """Save the current notebook using multiple fallback strategies."""
    handle_file_changed_dialog(page)

    strategies = [
        (
            "File menu",
            lambda: [
                page.click('li.lm-MenuBar-item:has-text("File")', timeout=15000),
                page.wait_for_selector(SAVE_NOTEBOOK, state="visible", timeout=15000),
                page.locator(SAVE_NOTEBOOK).focus(),
                page.click(SAVE_NOTEBOOK, timeout=15000),
            ],
        ),
        ("keyboard shortcut", lambda: page.keyboard.press("Control+s")),
        (
            "command palette",
            lambda: [
                page.keyboard.press("Control+Shift+c"),
                page.wait_for_timeout(1000),
                page.keyboard.type("Save Notebook"),
                page.wait_for_timeout(500),
                page.keyboard.press("Enter"),
            ],
        ),
    ]

    for strategy_name, action in strategies:
        try:
            if strategy_name != "File menu":
                logger.info(f"  🔄 Trying {strategy_name} fallback")
            action()
            page.wait_for_timeout(3000)
            logger.info(f"  💾 Notebook saved via {strategy_name}")
            page.keyboard.press("Escape")  # Dismiss any leftover dialogs
            return
        except Exception as e:
            logger.warning(f"  ⚠️ {strategy_name.title()} save failed for {nb}: {e}")

    logger.error(f"  ❌ All save strategies failed for {nb}")


def run_notebook(nb: str, page: Page, idle_timeout: int) -> float:
    """Open a notebook, restart kernel, run cells, save and close. Returns execution time."""
    logger.info(f"→ {nb}")
    nb_start_time = time.time()
    try:
        navigation_successful = False
        navigation_attempts = 5
        for attempt in range(navigation_attempts):
            try:
                page.goto(JUPYTER_LAB_URL + nb, timeout=90000, wait_until="load")
                page.wait_for_timeout(2000)  # Allow page to stabilize
                navigation_successful = True
                break
            except TimeoutError:
                if attempt == navigation_attempts - 1:
                    logger.error(
                        f"❌ Navigation failed after {navigation_attempts} attempts"
                    )
                    raise
                logger.warning(
                    f"  ⚠️ Navigation timeout attempt {attempt + 1}/{navigation_attempts}, retrying..."
                )
                page.wait_for_timeout(3000)
            except Exception as e:
                if "Target crashed" in str(e):
                    logger.error(f"🔥 Browser crash during navigation to {nb}")
                    raise
                if attempt == navigation_attempts - 1:
                    raise
                logger.warning(f"  ⚠️ Navigation error attempt {attempt + 1}: {e}")
                page.wait_for_timeout(3000)

        if not navigation_successful:
            raise Exception("Navigation failed after all attempts")

        try:
            activate_notebook_panel(page, nb)
        except Exception as e:
            logger.error(f"❌ Failed to activate notebook panel for {nb}: {e}")
            raise

        try:
            shutdown_kernel(page)
        except Exception as e:
            logger.warning(f"⚠️  Kernel shutdown failed for {nb}: {e}")

        try:
            restart_kernel(page)
        except Exception as e:
            logger.error(f"❌ Kernel restart failed for {nb}: {e}")
            raise

        try:
            run_all_code_cells(page, idle_timeout=idle_timeout)
        except Exception as e:
            if "Target crashed" in str(e) or "Browser context closed" in str(e):
                logger.error(f"🔥 Browser crash during cell execution in {nb}")
                raise
            logger.error(f"❌ Cell execution failed for {nb}: {e}")

        try:
            save_notebook(page, nb)
        except Exception as e:
            logger.warning(f"⚠️  Save failed for {nb}: {e}")

        try:
            close_tab(page)
        except Exception as e:
            logger.warning(f"⚠️  Close tab failed for {nb}: {e}")

        try:
            page.evaluate("() => { if (window.gc) window.gc(); }")
        except Exception:
            pass

        nb_duration = time.time() - nb_start_time
        logger.info(
            f"✔ {nb} (Duration: {int(nb_duration // 60)}m {int(nb_duration % 60)}s)"
        )
        return nb_duration

    except Exception as e:
        error_type = classify_error(str(e))
        icon = (
            "🔥" if error_type == "crash" else "⏰" if error_type == "timeout" else "❌"
        )
        logger.error(f"{icon} {error_type.title()} on {nb}: {e}")
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
        7200000 if "long-running" in normalized_targets else RUN_IDLE_TIMEOUT
    )

    total_start_time = time.time()
    results: List[dict] = []
    failures: List[str] = []
    browser_crashes = 0
    max_browser_crashes = 3  # Restart browser after this many crashes

    def should_restart_browser():
        return browser_crashes >= max_browser_crashes

    with sync_playwright() as pw:
        browser = create_browser(pw)

        try:
            notebook_count = len(notebooks)
            notebook_idx = 0

            while notebook_idx < notebook_count:
                nb = notebooks[notebook_idx]
                logger.info(f"Processing notebook {notebook_idx + 1}/{notebook_count}")

                if should_restart_browser():
                    logger.warning(
                        f"🔄 Restarting browser after {browser_crashes} crashes"
                    )
                    browser.close()
                    import gc

                    gc.collect()
                    time.sleep(5)
                    browser = create_browser(pw)
                    browser_crashes = 0
                page_attempts = 3

                for page_attempt in range(page_attempts):
                    try:
                        with browser.new_page() as page:
                            page.set_default_timeout(180000)
                            page.set_extra_http_headers({"Cache-Control": "no-cache"})

                            duration = run_notebook(
                                nb, page, idle_timeout=run_idle_timeout
                            )
                            results.append(
                                {"name": nb, "status": "COMPLETE", "duration": duration}
                            )
                            break

                    except Exception as e:
                        error_msg = str(e)
                        error_type = classify_error(error_msg)

                        if error_type == "crash":
                            browser_crashes += 1
                            logger.error(
                                f"🔥 Browser crash on {nb} (crash #{browser_crashes})"
                            )
                            retry_delay = 3
                        elif error_type == "timeout":
                            logger.error(f"⏰ Timeout on {nb}: {error_msg}")
                            retry_delay = 2
                        else:
                            logger.error(f"❌ Error on {nb}: {error_msg}")
                            results.append(
                                {"name": nb, "status": "FAIL", "duration": 0}
                            )
                            failures.append(nb)
                            break

                        if page_attempt < page_attempts - 1:
                            logger.info(
                                f"🔄 Retrying {nb} after {error_type} (attempt {page_attempt + 2}/{page_attempts})"
                            )
                            time.sleep(retry_delay)
                            continue
                        else:
                            results.append(
                                {"name": nb, "status": "FAIL", "duration": 0}
                            )
                            failures.append(nb)
                            break

                notebook_idx += 1

                if notebook_idx % 5 == 0:
                    logger.info("🧹 Performing memory cleanup")
                    import gc

                    gc.collect()
                    time.sleep(1)

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
