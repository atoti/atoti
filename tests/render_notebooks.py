import glob
from pathlib import Path
import pytest
import sys
import re
import pandas as pd
import sys
from playwright.sync_api import sync_playwright, TimeoutError
import pathlib, sys, time


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

notebooks = [
    "02-technical-guides/introductory-tutorial/main.ipynb",
    "02-technical-guides/table-creation-and-data-loads/main.ipynb",
]

notebooks.sort()
for notebook in notebooks:
    print(notebook)


JUPYTER_LAB_URL = "http://localhost:8888/lab/tree/"


def shutdown_all_kernels(page):
    # 1) Click the "Kernel" menubar entry
    page.click('li.lm-MenuBar-item:has-text("Kernel")')

    # 2) Locate the "Shut Down All Kernels…" item
    item = page.get_by_role("menuitem", name="Shut Down All Kernels…")

    # If it’s visible AND enabled, click; otherwise skip
    if item.is_visible() and item.is_enabled():
        item.click()
        # 3) Confirm the dialog
        confirm = page.get_by_role("button", name="Shut Down All")
        if confirm.is_visible() and confirm.is_enabled():
            confirm.click()
        # allow time for kernels to shut down
        page.wait_for_timeout(5000)
        print("  ✅ Shut down all kernels")
    else:
        print("  ⚠️ Shut down all kernels is disabled, skipping")


def click_restart_run_all(page):
    page.click('li.lm-MenuBar-item:has-text("Kernel")')
    page.get_by_role("menuitem", name="Restart Kernel and Run All Cells").click()


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
    shutdown_all_kernels(page)
    click_restart_run_all(page)

    print("  🏃 Running all cells")

    # wait for kernel to start executing
    page.wait_for_selector(
        "div.jp-Notebook-ExecutionIndicator[data-status='busy']",
        state="attached",
        timeout=60000,  # 1 min to start executing
    )
    print("  🔧 Kernel is executing")

    # wait for kernel to finish executing
    page.wait_for_selector(
        "div.jp-Notebook-ExecutionIndicator[data-status='idle']",
        state="attached",
        timeout=600000,  # 10 minutes of execution time per notebook
    )
    print("  💯 Run all cells completed")

    # wait for notebook to be saved
    page.get_by_role("button", name=re.compile(r"Save and create checkpoint")).click()
    print("  💾 Notebook saved")

    click_close_tab(page)

    print(f"✔ {nb}")


def main():
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=1000)
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
