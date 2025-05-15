import glob
from pathlib import Path
import pytest
import sys
import re
import pandas as pd
import sys
from playwright.sync_api import sync_playwright, TimeoutError
import pathlib, sys, time
import socket


_MAIN = "main.ipynb"

# Maintain exclusion list only for academy and tech tutorials
# Add to exclude use cases which are upgraded to latest but cannot be tested
NOTEBOOKS_DIRECTORY = Path("notebooks")
DATA_PREPROCESSING_NOTEBOOKS = [
    "var-benchmark/data_generator.ipynb",  # Timeout
]

NOTEBOOKS_WTIH_ALT_CONNECTORS = [
    f"auto-cube/{_MAIN}",  # requires user csv input
    f"auto-cube/main-advanced.ipynb",  # requires user csv input
    f"var-benchmark/{_MAIN}",  # requires data generation (large data volume)
    f"directquery-vector/{_MAIN}",  # Direct Query notebook
    f"directquery-intro/{_MAIN}",  # Direct Query notebook
    f"virtual-hierarchies/{_MAIN}",  # Direct Query notebook
]

ATOTI_UNLOCKED_NOTEBOOKS = [
    "security-implementation/01-Basic-authentication.ipynb",
    "security-implementation/02-OIDC-Auth0.ipynb",
    "security-implementation/03-OIDC-Google.ipynb",
    "security-implementation/04-LDAP.ipynb",
    f"security-implementation/{_MAIN}",
    f"internationalization/{_MAIN}",
]

# some notebooks may have dependencies conflict with the latest Atoti version
# to be listed here if it cannot be tested but is still upgraded
NOTEBOOKS_WITH_ERRORS = []

NOTEBOOKS_ACADEMY = ["introduction-to-atoti/main.ipynb"]  # error on purpose

INVALID_NAMED_NOTEBOOKS = ["Untitled"]

NOTEBOOKS_TO_SKIP = sorted(
    DATA_PREPROCESSING_NOTEBOOKS
    + NOTEBOOKS_WITH_ERRORS
    + NOTEBOOKS_WTIH_ALT_CONNECTORS
    + ATOTI_UNLOCKED_NOTEBOOKS
    + NOTEBOOKS_ACADEMY
    + INVALID_NAMED_NOTEBOOKS
)

# Gather the list of notebooks under the project directory
nb_list = [
    nb_path.replace("\\", "/")
    for nb_path in glob.glob(f"./*/**/*.ipynb", recursive=True)
    if not "ipynb_checkpoints" in nb_path
]

# 1. Exclude the list of notebooks added in this script
# 2. Exclude the list of non-maintained notebooks generated from the README program
#    https://github.com/activeviam/bd-atoti-gallery/tree/main/readme-generator
exclusion_list = pd.read_csv("./tests/test_exclusion.txt", header=None)[0].to_list()
notebooks = [
    nb_path
    for nb_path in nb_list
    if not any(exclude_nb in str(nb_path) for exclude_nb in NOTEBOOKS_TO_SKIP)
    and not any(exclude_nb in str(nb_path) for exclude_nb in exclusion_list)
]

notebooks.sort()
for notebook in notebooks:
    print(notebook)


JUPYTER_LAB_URL = "http://localhost:8888/lab/tree/"


# def wait_for_jupyter(host="127.0.0.1", port=8888, timeout=60):
#     start = time.time()
#     while time.time() - start < timeout:
#         try:
#             with socket.create_connection((host, port), timeout=1):
#                 return
#         except OSError:
#             time.sleep(0.5)
#     raise RuntimeError("Timed out waiting for JupyterLab")


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
        print("⚠️ ‘Shut Down All Kernels…’ not present, skipping shutdown")

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
    failures = []
    with sync_playwright() as pw:
        # wait_for_jupyter()
        browser = pw.chromium.launch(headless=True, slow_mo=1000)
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
