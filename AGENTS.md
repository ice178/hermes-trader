# Repository Guidelines

## Project Structure & Module Organization
The Python package lives in `src/hermes_trading/`, organized by domain: connectors to exchanges sit in `connectors/`, candle and liquidity utilities in `candles.py` and `liquidity.py`, trading orchestration in `trading.py`, and signal logic under `signals/`. Top-level scripts such as `scan_month_signals.py` demonstrate how to combine these pieces for historical scans. Test coverage mirrors the package tree in `tests/`, with focused suites like `tests/test_signals.py` validating indicator behaviour.

## Agent Workflow
Read `README.md` before starting, then check `tasks/INDEX.md` and read the relevant task file before changing code. For a non-trivial change without a task file, propose creating one from `tasks/templates/task.md`. Do not implement broad or ambiguous work until the scope, acceptance criteria, and test plan are clear.

Prefer small, focused diffs. Keep the task file and `tasks/INDEX.md` current after meaningful progress, without logging every minor action. Add or update tests whenever behavior changes. Record decisions with lasting architectural consequences in `docs/adr/`; routine implementation choices belong in the task file.

Before finishing, update the task status or handoff and summarize the files changed, commands and tests run, and remaining risks. Never put credentials, private data, or generated logs and backtest artifacts in task files.

## Build, Test, and Development Commands
Create a virtual environment targeting Python 3.10+, then install editable dependencies with `pip install -e .`. Run the full test suite via `pytest` from the project root; pytest auto-discovers `tests/`. For exploratory runs against live data, execute `python src/scan_month_signals.py` to stream Binance futures candles and print trade summaries. While iterating on detectors, target the signal suite with `pytest tests/test_signals.py -k price_action` to confirm pattern regressions early.

## Coding Style & Naming Conventions
Follow PEP 8 defaults: four-space indentation, `snake_case` for functions, and `PascalCase` for classes such as `BinanceConnector`. Existing modules rely heavily on type hints and dataclasses; new code should preserve annotations for public APIs and keep constructors side-effect free. Keep docstrings short and functional, mirroring the concise style in `trading.py`. Avoid in-line constants—promote shared values to module-level names when reused.

## Testing Guidelines
Write new tests alongside code in `tests/`, naming files `test_<feature>.py` and functions `test_<condition>_<expectation>()`, as seen in `test_price_action_signal_detects_patterns_on_levels`. Prefer parametrized pytest cases for connector edge conditions and ensure levels precede candles when crafting fixtures. Run `pytest -k <keyword>` locally while iterating, then `pytest` before opening a pull request to confirm regressions are caught early.

## Commit & Pull Request Guidelines
Commit history favours short, imperative summaries (`fix: pin bar detection`, `test: ensure levels precede candles`). Use that tone, optionally prefixing the scope with `fix:`, `feat:`, or `test:` when helpful. Each pull request should describe the behavioural change, reference relevant issues, and note any live-exchange impacts. Include screenshots or sample command output when changes affect user-facing scripts, and confirm pytest results in the PR description.

## Secrets & Exchange Configuration
Connector classes default to public market-data access, but trading flows require API credentials. Source keys from environment variables or a local `.env` excluded from version control, then pass them into connector constructors (e.g., `BinanceConnector(api_key, secret)`). Never commit keys, and reset credentials if accidental exposure occurs.
