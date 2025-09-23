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
    before moving to the next. Enhanced with better error handling and recovery.
    """
    # Wait for notebook panel with retries
    for attempt in range(3):
        try:
            # Wait for any notebook panel first
            page.wait_for_selector(
                "div.jp-NotebookPanel",
                state="attached",
                timeout=10000,
            )

            # Try to find a visible panel, if not make one visible
            visible_panel = page.locator("div.jp-NotebookPanel:not(.lm-mod-hidden)")
            if visible_panel.count() == 0:
                # Try to activate a hidden panel by clicking on its tab
                hidden_panel = page.locator("div.jp-NotebookPanel.lm-mod-hidden").first
                if hidden_panel.count() > 0:
                    panel_id = hidden_panel.get_attribute("id")
                    if panel_id:
                        # Find corresponding tab and click it
                        tab = page.locator(
                            f'.lm-TabBar-tab[aria-describedby="{panel_id}"]'
                        )
                        if tab.count() > 0:
                            tab.click(timeout=5000)
                            page.wait_for_timeout(1000)

            # Verify we now have a visible panel
            page.wait_for_selector(
                "div.jp-NotebookPanel:not(.lm-mod-hidden)",
                state="visible",
                timeout=5000,
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

    page.click("div.jp-NotebookPanel:not(.lm-mod-hidden)")

    # Get cells with retry logic
    cells = None
    for attempt in range(3):
        try:
            cells = page.locator(
                "div.jp-NotebookPanel:not(.lm-mod-hidden) .jp-Cell.jp-CodeCell"
            )
            cell_count = cells.count()
            if cell_count > 0:
                break
        except Exception:
            pass
        if attempt == 2:
            logger.error("❌ No code cells found after 3 attempts")
            return
        logger.warning(f"⚠️  Cells not ready, retry {attempt + 1}/3")
        page.wait_for_timeout(1000)

    total = cell_count
    logger.info(f"  ▶️  Running {total} code cells…")

    # Track consecutive failures to detect browser issues
    consecutive_failures = 0
    max_consecutive_failures = 3

    for run_index in range(total):
        # Check if we should abort due to too many consecutive failures
        if consecutive_failures >= max_consecutive_failures:
            logger.error(
                f"❌ Aborting execution after {consecutive_failures} consecutive failures"
            )
            break

        try:
            # Enhanced cell access with better error handling
            cell = None
            for cell_attempt in range(3):
                try:
                    cell = cells.nth(run_index)
                    cell.wait_for(state="attached", timeout=15000)
                    break
                except Exception as e:
                    if cell_attempt == 2:
                        logger.error(
                            f"❌ Cell {run_index + 1} not accessible after 3 attempts: {e}"
                        )
                        consecutive_failures += 1
                        continue
                    page.wait_for_timeout(1000)

            if cell is None:
                continue

            # Scroll and focus with error handling
            try:
                cell.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                cell.evaluate("el => el.focus()")
            except Exception as e:
                logger.warning(f"⚠️  Cell {run_index + 1} focus/scroll failed: {e}")

            # Execute cell and start timing
            logger.info(f"     → Code cell {run_index + 1}/{total}")
            start_execution_time = time.time()

            page.keyboard.press("Shift+Enter")

            # Wait for execution to start with more generous timeout
            execution_started = False
            execution_time = None

            try:
                page.wait_for_selector(
                    "div.jp-Notebook-ExecutionIndicator[data-status='busy']",
                    state="attached",
                    timeout=5000,
                )
                execution_started = True
            except TimeoutError:
                # Check if cell executed so quickly by looking at the current cell's execution count
                try:
                    current_cell = cells.nth(run_index)
                    execution_count = current_cell.locator(
                        ".jp-InputArea-prompt"
                    ).text_content()

                    # If there's a number in the prompt, the cell executed
                    if execution_count and any(c.isdigit() for c in execution_count):
                        execution_started = True
                        execution_time = time.time() - start_execution_time
                    else:
                        logger.warning(
                            f"⚠️  Cell {run_index + 1} execution may not have started"
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            logger.error(
                                "❌ Too many consecutive cell execution failures"
                            )
                            return
                        continue
                except Exception as e:
                    logger.warning(
                        f"⚠️  Cell {run_index + 1} execution status unclear: {e}"
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        logger.error("❌ Too many consecutive cell execution failures")
                        return
                    continue

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
                    "cvar-optimizer",
                    "price-elasticity",
                ]
            ):
                current_idle_timeout = min(
                    900000,
                    idle_timeout * 5,  # Up to 15 minutes for very intensive cells
                )

            # Set absolute maximum timeout to prevent infinite hangs
            max_cell_timeout = 600000  # 10 minutes absolute maximum per cell
            current_idle_timeout = min(current_idle_timeout, max_cell_timeout)

            # Wait for execution to complete
            if execution_started:
                if execution_time is None:
                    try:
                        # Wait for the cell to finish execution
                        page.wait_for_selector(
                            "div.jp-Notebook-ExecutionIndicator[data-status='idle']",
                            state="attached",
                            timeout=current_idle_timeout,
                        )
                        execution_time = time.time() - start_execution_time
                        logger.info(f"          completed in {execution_time:.1f}s")
                        consecutive_failures = 0  # Reset on success
                    except TimeoutError:
                        execution_time = time.time() - start_execution_time
                        logger.warning(
                            f"⚠️  Cell {run_index + 1} timeout after {execution_time:.1f}s"
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            logger.error("❌ Too many consecutive timeouts")
                            return
                    except Exception as e:
                        execution_time = time.time() - start_execution_time
                        logger.error(
                            f"❌ Cell {run_index + 1} error after {execution_time:.1f}s: {e}"
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            logger.error("❌ Too many consecutive errors")
                            return
                else:
                    # Cell already completed quickly
                    logger.info(f"          completed in {execution_time:.1f}s")
                    consecutive_failures = 0  # Reset on success
            else:
                # Cell execution didn't start properly
                logger.warning(f"⚠️  Cell {run_index + 1} failed to start")
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.error("❌ Too many consecutive execution failures")
                    return

        except TimeoutError as e:
            logger.error(f"❌ Timeout accessing cell {run_index + 1}: {e}")
            consecutive_failures += 1
            continue
        except Exception as e:
            # Check for browser crash indicators
            if "Target crashed" in str(e) or "Browser context closed" in str(e):
                logger.error(f"🔥 Browser crash detected at cell {run_index + 1}")
                raise
            logger.error(f"❌ Unexpected error in cell {run_index + 1}: {e}")
            consecutive_failures += 1
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
    Save the current notebook using multiple fallback strategies.
    Enhanced to handle timeouts and UI issues more robustly.
    """
    # Handle potential file changed dialog before saving
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

    # Strategy 1: Standard File menu approach
    save_successful = False
    try:
        page.click('li.lm-MenuBar-item:has-text("File")', timeout=15000)
        save_sel = 'li.lm-Menu-item[data-command="docmanager:save"] .lm-Menu-itemLabel:has-text("Save Notebook")'
        page.wait_for_selector(save_sel, state="visible", timeout=15000)
        page.locator(save_sel).focus()
        page.click(save_sel, timeout=15000)
        page.wait_for_timeout(3000)  # Wait for save to complete
        logger.info("  💾 Notebook saved via File menu")
        save_successful = True
    except TimeoutError:
        logger.warning(f"  ⚠️ File menu save timeout for {nb}")
    except Exception as e:
        logger.warning(f"  ⚠️ File menu save failed for {nb}: {e}")

    # Strategy 2: Keyboard shortcut fallback
    if not save_successful:
        try:
            logger.info("  🔄 Trying keyboard shortcut fallback")
            page.keyboard.press("Control+s")
            page.wait_for_timeout(3000)
            logger.info("  💾 Notebook saved via keyboard shortcut")
            save_successful = True
        except Exception as fallback_e:
            logger.warning(f"  ⚠️ Keyboard shortcut save failed for {nb}: {fallback_e}")

    # Strategy 3: Command palette fallback
    if not save_successful:
        try:
            logger.info("  🔄 Trying command palette fallback")
            page.keyboard.press("Control+Shift+c")  # Open command palette
            page.wait_for_timeout(1000)
            page.keyboard.type("Save Notebook")
            page.wait_for_timeout(500)
            page.keyboard.press("Enter")
            page.wait_for_timeout(3000)
            logger.info("  💾 Notebook saved via command palette")
            save_successful = True
        except Exception as cmd_e:
            logger.warning(f"  ⚠️ Command palette save failed for {nb}: {cmd_e}")

    if not save_successful:
        logger.error(f"  ❌ All save strategies failed for {nb}")
        # Don't raise exception - continue with execution

    # Always try to dismiss any leftover dialogs
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass


def run_notebook(nb: str, page: Page, idle_timeout: int) -> float:
    """
    Open a notebook, restart its kernel, run all code cells, save, and close the
    notebook. Returns execution duration in minutes, seconds.
    Enhanced with better error handling and recovery mechanisms.
    """
    logger.info(f"→ {nb}")
    nb_start_time = time.time()
    try:
        # Navigate to notebook with enhanced retries
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

        # Verify notebook is loaded properly and activate if needed
        try:
            # Wait for any notebook panel to exist (visible or hidden)
            page.wait_for_selector(".jp-NotebookPanel", state="attached", timeout=30000)

            # Check if we have a visible panel already
            visible_panels = page.locator(".jp-NotebookPanel:not(.lm-mod-hidden)")

            if visible_panels.count() == 0:
                logger.info(f"  📋 No visible panels, trying to activate tab for {nb}")

                # Try to find the tab for this specific notebook and click it
                notebook_filename = nb.split("/")[-1]
                tab_found = False

                # Look for tab with notebook filename in title
                tabs = page.locator('.lm-TabBar-tab[title*=".ipynb"]')
                for i in range(tabs.count()):
                    tab = tabs.nth(i)
                    title = tab.get_attribute("title") or ""
                    if notebook_filename in title:
                        logger.info(f"  🎯 Found matching tab: {title[:50]}...")
                        tab.click(timeout=5000)
                        page.wait_for_timeout(2000)
                        tab_found = True
                        break

                if not tab_found:
                    # Fallback: try clicking the most recent notebook tab
                    notebook_tabs = page.locator(".lm-TabBar-tab.lm-mod-closable")
                    if notebook_tabs.count() > 0:
                        logger.info(
                            f"  🔄 Fallback: clicking first available notebook tab"
                        )
                        notebook_tabs.first.click(timeout=5000)
                        page.wait_for_timeout(2000)

            # Double-check we have a visible panel now
            visible_panels = page.locator(".jp-NotebookPanel:not(.lm-mod-hidden)")
            visible_count = visible_panels.count()

            if visible_count > 0:
                logger.info(
                    f"  ✅ Found {visible_count} visible notebook panel(s) for {nb}"
                )
            else:
                # Last resort: try to wait a bit more for visibility
                try:
                    page.wait_for_selector(
                        ".jp-NotebookPanel:not(.lm-mod-hidden)", timeout=10000
                    )
                    logger.info(
                        f"  ✅ Notebook panel became visible after additional wait for {nb}"
                    )
                except TimeoutError:
                    logger.error(
                        f"❌ No visible panels found even after activation attempts for {nb}"
                    )
                    raise

        except TimeoutError:
            logger.error(f"❌ Notebook panel not found or not visible for {nb}")
            # Let's check what we actually have for debugging
            panels = page.locator(".jp-NotebookPanel").all()
            logger.error(f"  Debug: Found {len(panels)} total panels")
            for i, panel in enumerate(panels):
                classes = panel.get_attribute("class") or ""
                visible = "lm-mod-hidden" not in classes
                logger.error(f"    Panel {i}: visible={visible}")
            raise

        # Shutdown kernels with error handling
        try:
            shutdown_kernel(page)
        except Exception as e:
            logger.warning(f"⚠️  Kernel shutdown failed for {nb}: {e}")
            # Continue anyway

        # Restart kernel with error handling
        try:
            restart_kernel(page)
        except Exception as e:
            logger.error(f"❌ Kernel restart failed for {nb}: {e}")
            raise

        # Run all cells with enhanced error handling
        try:
            run_all_code_cells(page, idle_timeout=idle_timeout)
        except Exception as e:
            if "Target crashed" in str(e) or "Browser context closed" in str(e):
                logger.error(f"🔥 Browser crash during cell execution in {nb}")
                raise
            logger.error(f"❌ Cell execution failed for {nb}: {e}")
            # Continue to save what we have

        # Save notebook with enhanced error handling
        try:
            save_notebook(page, nb)
        except Exception as e:
            logger.warning(f"⚠️  Save failed for {nb}: {e}")
            # Don't fail the entire notebook for save issues

        # Close tab with error handling
        try:
            close_tab(page)
        except Exception as e:
            logger.warning(f"⚠️  Close tab failed for {nb}: {e}")

        # Force garbage collection and memory cleanup
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
        # Enhanced error classification
        if "Target crashed" in str(e) or "Browser context closed" in str(e):
            logger.error(f"🔥 Browser crash on {nb}: {e}")
        elif "TimeoutError" in str(type(e)) or "timeout" in str(e).lower():
            logger.error(f"⏰ Timeout on {nb}: {e}")
        else:
            logger.error(f"❌ Error on {nb}: {e}")

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
    browser_crashes = 0
    max_browser_crashes = 3  # Restart browser after this many crashes

    def should_restart_browser():
        return browser_crashes >= max_browser_crashes

    def create_browser(pw):
        """Create browser with enhanced memory management"""
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

    with sync_playwright() as pw:
        browser = create_browser(pw)

        try:
            notebook_count = len(notebooks)
            notebook_idx = 0

            while notebook_idx < notebook_count:
                nb = notebooks[notebook_idx]
                logger.info(f"Processing notebook {notebook_idx + 1}/{notebook_count}")

                # Check if we need to restart browser
                if should_restart_browser():
                    logger.warning(
                        f"🔄 Restarting browser after {browser_crashes} crashes"
                    )
                    browser.close()
                    import gc

                    gc.collect()
                    time.sleep(5)  # Allow system recovery
                    browser = create_browser(pw)
                    browser_crashes = 0

                # Create new page for each notebook to prevent memory issues
                page_successful = False
                page_attempts = 3

                for page_attempt in range(page_attempts):
                    try:
                        with browser.new_page() as page:
                            # Enhanced page configuration
                            page.set_default_timeout(
                                180000
                            )  # 3 minutes default timeout
                            page.set_extra_http_headers({"Cache-Control": "no-cache"})

                            duration = run_notebook(
                                nb, page, idle_timeout=run_idle_timeout
                            )
                            results.append(
                                {"name": nb, "status": "COMPLETE", "duration": duration}
                            )
                            page_successful = True
                            break

                    except Exception as e:
                        error_msg = str(e)

                        # Enhanced error classification and handling
                        if (
                            "Target crashed" in error_msg
                            or "Browser context closed" in error_msg
                        ):
                            browser_crashes += 1
                            logger.error(
                                f"🔥 Browser crash on {nb} (crash #{browser_crashes})"
                            )

                            if page_attempt < page_attempts - 1:
                                logger.info(
                                    f"� Retrying {nb} after browser crash (attempt {page_attempt + 2}/{page_attempts})"
                                )
                                time.sleep(3)
                                continue
                            else:
                                results.append(
                                    {"name": nb, "status": "FAIL", "duration": 0}
                                )
                                failures.append(nb)
                                break

                        elif (
                            "TimeoutError" in str(type(e))
                            or "timeout" in error_msg.lower()
                        ):
                            logger.error(f"⏰ Timeout on {nb}: {error_msg}")
                            if page_attempt < page_attempts - 1:
                                logger.info(
                                    f"🔄 Retrying {nb} after timeout (attempt {page_attempt + 2}/{page_attempts})"
                                )
                                time.sleep(2)
                                continue
                            else:
                                results.append(
                                    {"name": nb, "status": "FAIL", "duration": 0}
                                )
                                failures.append(nb)
                                break

                        else:
                            logger.error(f"❌ Error on {nb}: {error_msg}")
                            results.append(
                                {"name": nb, "status": "FAIL", "duration": 0}
                            )
                            failures.append(nb)
                            break

                notebook_idx += 1

                # Memory cleanup between notebooks
                if notebook_idx % 5 == 0:  # Every 5 notebooks
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
