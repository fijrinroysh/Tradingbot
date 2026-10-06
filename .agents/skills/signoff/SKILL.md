---
name: signoff
description: Runs the automated functional test suite and provides a sign-off report before code merges.
---

# `signoff` Skill

Use this skill when the user types `/signoff` or asks you to run the test suite and provide a sign-off report before they merge a branch.

## Execution Steps:
1. Ensure the user is in the `Tradingbot` root directory.
2. Run the Mocked Unit Test suite using:
   `$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python.exe -m unittest discover -s tests`
3. If the unit tests pass, proceed to run the Live Integration Tests one by one using:
   `$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python.exe test_scripts\live_sp500_crosscheck.py`
   `$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python.exe test_scripts\live_integration_sheets.py`
   `$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python.exe test_scripts\live_integration_alpaca.py`
4. Analyze the output of all tests (both Mocked and Live).
5. If any test fails, clearly explain which test failed, why it failed based on the traceback, and propose a fix. Do NOT issue a sign-off.
6. If all Mocked and Live tests pass, generate a clear, professional Markdown artifact named `signoff_report.md` (set `UserFacing=true` and `RequestFeedback=false`) that lists the passing suites, confirms that core functional requirements AND live API connections (Alpaca, Sheets, Wikipedia) are validated, and provides the "🟢 QA Sign-Off Approved" stamp.

Always remind the user that they can now safely merge and push their code.
