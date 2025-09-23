"""
Utility functions for notebook rendering and testing.

This module contains reusable utility functions for browser management,
error handling, retry logic, and result tracking used by the notebook
rendering system.
"""

import time
import logging
from typing import Any

logger = logging.getLogger("notebook-renderer")


# =====================
# Retry and Error Handling Utilities
# =====================


def retry_with_backoff(
    func,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Any:
    """
    Retry a function with exponential backoff.

    This utility function encapsulates the common retry pattern used throughout
    the codebase, with configurable attempts, delays, and exception handling.

    Args:
        func: The function to execute (should be a callable with no arguments)
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds between retries (default: 1.0)
        backoff_factor: Multiplier for delay between attempts (default: 2.0)
        exceptions: Tuple of exception types to catch and retry (default: (Exception,))

    Returns:
        The return value of the successful function call

    Raises:
        The last exception if all retry attempts fail

    Example:
        result = retry_with_backoff(
            lambda: some_flaky_operation(),
            max_attempts=5,
            base_delay=0.5,
            exceptions=(TimeoutError, ConnectionError)
        )
    """
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            if attempt == max_attempts - 1:
                # Last attempt failed, re-raise the exception
                raise

            # Calculate delay with exponential backoff
            delay = base_delay * (backoff_factor**attempt)
            logger.warning(
                f"Attempt {attempt + 1}/{max_attempts} failed: {e}. Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


def classify_error(error: Exception, context: str = "") -> str:
    """
    Classify an error into categories for consistent handling.

    This function analyzes exceptions and classifies them into standard
    categories to enable consistent error handling across the codebase.

    Args:
        error: The exception to classify
        context: Optional context string for logging (e.g., function name)

    Returns:
        str: Error category - one of: 'browser_crash', 'timeout', 'navigation',
             'ui_element', 'execution', 'unknown'

    Example:
        category = classify_error(e, "save_notebook")
        if category == 'browser_crash':
            restart_browser()
        elif category == 'timeout':
            increase_timeout()
    """
    error_msg = str(error).lower()
    error_type = str(type(error)).lower()

    # Browser crash indicators
    if any(
        keyword in error_msg
        for keyword in [
            "target crashed",
            "browser context closed",
            "connection closed",
            "browser has been closed",
            "page has been closed",
        ]
    ):
        return "browser_crash"

    # Timeout indicators
    if "timeout" in error_type or "timeout" in error_msg:
        return "timeout"

    # Navigation/loading issues
    if any(
        keyword in error_msg
        for keyword in [
            "navigation",
            "net::",
            "failed to load",
            "connection refused",
            "dns",
            "resolve",
            "network",
        ]
    ):
        return "navigation"

    # UI element not found/accessible
    if any(
        keyword in error_msg
        for keyword in [
            "element not found",
            "selector",
            "locator",
            "element is not",
            "not visible",
            "not attached",
            "not enabled",
        ]
    ):
        return "ui_element"

    # Cell execution specific issues
    if any(
        keyword in error_msg
        for keyword in ["kernel", "execution", "cell", "jupyter", "notebook"]
    ):
        return "execution"

    return "unknown"


def should_retry_error(error: Exception, attempt: int, max_attempts: int) -> bool:
    """
    Determine if an error should trigger a retry based on error type and attempt count.

    This function implements the retry logic based on error classification,
    helping to decide whether to retry an operation or fail immediately.

    Args:
        error: The exception that occurred
        attempt: Current attempt number (0-based)
        max_attempts: Maximum number of attempts allowed

    Returns:
        bool: True if the operation should be retried, False otherwise

    Example:
        if should_retry_error(e, attempt, 3):
            continue  # retry
        else:
            break  # give up
    """
    if attempt >= max_attempts - 1:
        return False  # No more attempts left

    error_category = classify_error(error)

    # Always retry browser crashes (browser can be restarted)
    if error_category == "browser_crash":
        return True

    # Retry timeouts and UI element issues (transient)
    if error_category in ["timeout", "ui_element"]:
        return True

    # Retry navigation issues for first few attempts
    if error_category == "navigation" and attempt < 2:
        return True

    # Don't retry execution errors (likely code issues)
    if error_category == "execution":
        return False

    # Retry unknown errors for first attempt only
    if error_category == "unknown" and attempt < 1:
        return True

    return False


# =====================
# Browser Management Utilities
# =====================


def create_browser_with_config(
    playwright_instance, headless: bool = True, slow_mo: int = 2000
) -> Any:
    """
    Create a browser instance with enhanced memory management configuration.

    This function creates a Chromium browser with optimized settings for
    notebook rendering, including memory management and performance tweaks.

    Args:
        playwright_instance: The Playwright instance to use for browser creation
        headless: Whether to run browser in headless mode (default: True)
        slow_mo: Slow motion delay in milliseconds (default: 2000)

    Returns:
        Browser instance configured for notebook rendering

    Note:
        This function encapsulates browser creation logic that can be reused
        when restarting browsers after crashes or memory issues.
    """
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

    return playwright_instance.chromium.launch(
        headless=headless, slow_mo=slow_mo, args=browser_args
    )


def cleanup_browser_memory() -> None:
    """
    Perform memory cleanup operations between notebook executions.

    This function attempts to free memory and perform garbage collection
    to prevent memory accumulation during long test runs.

    Returns:
        None

    Note:
        This is called periodically during notebook processing to maintain
        system stability during long-running test sessions.
    """
    import gc

    gc.collect()
    time.sleep(1)  # Allow system to complete cleanup


def log_browser_status(
    browser_crashes: int, notebook_idx: int, total_notebooks: int
) -> None:
    """
    Log current browser status and crash statistics.

    This function provides visibility into browser health during test execution,
    helping to identify patterns in browser crashes and memory issues.

    Args:
        browser_crashes: Number of browser crashes encountered so far
        notebook_idx: Current notebook index (0-based)
        total_notebooks: Total number of notebooks to process

    Returns:
        None

    Example:
        log_browser_status(2, 15, 50)  # 2 crashes, processing notebook 16/50
    """
    if browser_crashes > 0:
        logger.info(
            f"📊 Browser status: {browser_crashes} crashes, processing {notebook_idx + 1}/{total_notebooks}"
        )
    else:
        logger.info(
            f"📊 Browser status: healthy, processing {notebook_idx + 1}/{total_notebooks}"
        )


def should_restart_browser(browser_crashes: int, max_crashes: int = 3) -> bool:
    """
    Determine if the browser should be restarted based on crash count.

    This function implements the policy for when to restart the browser
    to recover from memory issues or repeated crashes.

    Args:
        browser_crashes: Current number of browser crashes
        max_crashes: Maximum crashes before restart (default: 3)

    Returns:
        bool: True if browser should be restarted, False otherwise

    Example:
        if should_restart_browser(crash_count):
            restart_browser()
    """
    return browser_crashes >= max_crashes


# =====================
# Result Tracking Utilities
# =====================


def create_result_entry(notebook_name: str, status: str, duration: float) -> dict:
    """
    Create a standardized result entry for notebook execution tracking.

    This function creates a consistent result dictionary format for tracking
    notebook execution outcomes and timing information.

    Args:
        notebook_name: Name/path of the notebook
        status: Execution status ('COMPLETE' or 'FAIL')
        duration: Execution duration in seconds

    Returns:
        dict: Standardized result entry with 'name', 'status', and 'duration' keys

    Example:
        result = create_result_entry("my_notebook.ipynb", "COMPLETE", 45.2)
    """
    return {"name": notebook_name, "status": status, "duration": duration}


def format_duration(duration_seconds: float) -> str:
    """
    Format duration in seconds to a human-readable "Xm Ys" format.

    This function converts duration from seconds to a readable format
    used in summary reports and logging.

    Args:
        duration_seconds: Duration in seconds (float)

    Returns:
        str: Formatted duration string (e.g., "2m 30s")

    Example:
        formatted = format_duration(150.5)  # Returns "2m 30s"
    """
    minutes = int(duration_seconds // 60)
    seconds = int(duration_seconds % 60)
    return f"{minutes}m {seconds}s"


def log_notebook_progress(
    notebook_idx: int, total_notebooks: int, notebook_name: str
) -> None:
    """
    Log progress information for notebook processing.

    This function provides consistent progress logging across the application,
    showing current position in the processing queue.

    Args:
        notebook_idx: Current notebook index (0-based)
        total_notebooks: Total number of notebooks to process
        notebook_name: Name of the current notebook

    Returns:
        None

    Example:
        log_notebook_progress(4, 20, "analysis.ipynb")  # Processing notebook 5/20
    """
    logger.info(
        f"Processing notebook {notebook_idx + 1}/{total_notebooks}: {notebook_name}"
    )
