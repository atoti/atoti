---
name: Python bug report
about: Report a bug concerning the Python library
labels: ":bug: bug"
---

<!--
Thank you for reporting a bug! Please make sure you have searched for similar issues.

By opening an issue, you agree with atoti's terms of use and privacy policy available at https://www.atoti.io/terms and https://www.atoti.io/privacy-policy
-->

## Steps to reproduce

<!--
Include a code sample and dataset with the issue.
If possible, indicate which cell triggers the error.
-->

## Actual Result

<!--
Include the error message if you have one.
-->

## Expected Result

## Environment

<!--
Add any other versions relevant to your issue.

You may run the following Python (>= 3.8) code:

import platform
import sys

from importlib.metadata import version

import atoti

print(f"""
- atoti: {version("atoti")}
- Python: {platform.python_version()}
- Operating system: {sys.platform}
""")

-->

- atoti:
- Python:
- Operating System:

## Logs (if relevant)

<!--
You can get your full session logs by calling: `session.logs_path.read_text(encoding="utf8")`.
Include them between HTML tags like that <details><pre>{paste logs here}</pre></details>.
-->
