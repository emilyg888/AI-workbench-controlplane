# Issues Pending Review

## Summary

| ID | Severity | Area | Issue | Recommended action | Status |
|---|---|---|---|---|---|
| ISSUE-001 | Medium | Docs | Tracked docs were renamed or replaced before housekeeping (`docs/design.md`, `docs/PLANES.md`, `docs/architecture_diagram.md` are deleted; related replacements with spaces in filenames are untracked). | Review whether the new doc filenames are intentional before finalizing the documentation layout. Prefer stable, link-friendly paths for active engineering docs. | Pending review |
| ISSUE-002 | Low | Repo hygiene | Ignored local artifacts exist in the working tree (`.coverage`, `.DS_Store`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, generated pycache files, DuckDB, and run outputs). | No commit action needed while ignored. Clean locally before packaging or handoff if a pristine directory is required. | Pending review |
| ISSUE-003 | Low | CI/CD | No CI workflow was found in the first-pass repo map. | Add a GitHub Actions workflow for pytest and ruff if this repo will be reviewed through pull requests. | Pending review |

## SIT Results

| Command | Result | Notes |
|---|---|---|
| `uv run pytest -q` | Passed | 182 tests passed on 2026-05-18. |
| `uv run ruff check .` | Passed | Ruff completed successfully on 2026-05-18. Initial sandbox run could not access the uv cache; the command passed after approved cache access. |

## Archived Code Review

| Original path | Archived path | Reason | Review needed? |
|---|---|---|---|
| N/A | N/A | No low-risk redundant code was archived during this pass. Ignored generated artifacts were left in place because they are already excluded from git. | No |

## Detailed Issues

### ISSUE-001 - Documentation Rename Review

- Severity: Medium
- Area: Docs
- Evidence: `git status --short` showed deleted tracked files at `docs/design.md`, `docs/PLANES.md`, and `docs/architecture_diagram.md`, plus untracked related files such as `docs/HL_design.md`, `docs/AI Workbench PLANES.md`, `docs/AI Workbench architecture_diagram.md`, and `docs/architecture.md`.
- Impact: Links and references can drift when active engineering docs are renamed, especially with spaces in filenames.
- Recommended action: Confirm which docs should remain canonical. Keep `design/architecture.md` as the engineering source of truth and use docs with spaces only for presentation or audience-specific material if needed.
- Status: Pending review

### ISSUE-002 - Ignored Local Artifacts

- Severity: Low
- Area: Repo hygiene
- Evidence: The workspace contains ignored local artifacts such as `.coverage`, `.DS_Store`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, `tests/__pycache__/`, `db/workbench.duckdb`, and generated run outputs.
- Impact: They are not currently a source-control risk because `.gitignore` excludes them, but they can clutter manual handoff directories.
- Recommended action: Leave them untracked during development. Remove local ignored artifacts only when preparing a clean distribution outside git.
- Status: Pending review

### ISSUE-003 - Missing CI Workflow

- Severity: Low
- Area: CI/CD
- Evidence: The first-pass file map did not show a `.github/workflows/` test workflow.
- Impact: Test and lint checks depend on local execution unless repository settings provide external CI elsewhere.
- Recommended action: Add a GitHub Actions workflow that runs `uv run pytest -q` and `uv run ruff check .`.
- Status: Pending review
