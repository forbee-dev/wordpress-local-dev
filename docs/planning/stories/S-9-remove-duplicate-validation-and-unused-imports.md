# S-9: Remove Duplicate Database Validation Logic and Unused Imports from app.py

## Priority: Low
## Effort: S
## Dependencies: None (can run in parallel with S-1 through S-8, though it touches app.py — coordinate with S-4 and S-8 which also modify app.py to avoid merge conflicts)
## Files:
- `app.py`

## Description

Two independent code quality issues in `app.py`, grouped because they are both confined
to the same file and are low-risk cosmetic/structural improvements.

### Fix 1 — R6: Remove duplicated database validation logic

`app.py` contains two standalone functions at lines 41-140:
- `validate_and_repair_database(file_path)` (~40 lines)
- `repair_database_file(file_path, is_gzipped)` (~60 lines)

These functions duplicate logic that already exists in `DatabaseManager`:
- `DatabaseManager._read_database_file()` handles both plain and gzipped files with UTF-8 fallback.
- `DatabaseManager._create_and_import_repaired_file()` handles cleaning and rewriting corrupted files.

The `validate_and_repair_database()` function is called from within `app.py` during
the `/api/projects/<name>/upload-db` endpoint (and possibly the older
`/api/import-database/<name>` endpoint). Identify all callers, then replace each call
with a call to the appropriate `DatabaseManager` method through `project_manager.database_manager`.

If the DatabaseManager does not expose an equivalent standalone validation method,
the simplest approach is to remove the pre-validation step entirely from `app.py`
and rely on the fallback strategy already built into `database_manager.import_database()`,
which reads, retries, and auto-repairs during the import itself. This is the more correct
design: validate-during-import rather than validate-before-import.

Steps:
1. Confirm all callers of `validate_and_repair_database()` in `app.py`.
2. Remove the call to `validate_and_repair_database()` from those callers
   (the DatabaseManager's import method already handles malformed files).
3. Delete the `validate_and_repair_database()` function definition.
4. Delete the `repair_database_file()` function definition.
5. Remove the `is_gzipped_file()` standalone function at line 32 (also a duplicate of
   `DatabaseManager._is_gzipped_file()`).

### Fix 2 — R7: Remove unused imports

**File:** `app.py` lines 1-12

The following imports are present but the identifiers are not used anywhere in `app.py`:

| Import | Reason it is unused |
|--------|---------------------|
| `subprocess` | No direct subprocess calls in `app.py` after R6 fix |
| `platform` | Checked — not referenced in any endpoint or function |
| `yaml` | Not used anywhere in `app.py` |
| `send_from_directory` | Not used in any route |

Removing unused imports eliminates lint warnings (flake8 F401) and reduces the
chance that a future developer assumes these are available in scope.

Note: verify each import is truly unused AFTER applying Fix 1. If Fix 1 removes
the `gzip` usage from the standalone functions, `gzip` may also become unused in `app.py`.
Remove it if so.

## Acceptance Criteria

- [ ] Given `app.py` after this change, then `validate_and_repair_database` is not defined anywhere in the file.
- [ ] Given `app.py` after this change, then `repair_database_file` is not defined anywhere in the file.
- [ ] Given `app.py` after this change, then `is_gzipped_file` is not defined anywhere in the file.
- [ ] Given a database file upload via `POST /api/projects/<name>/upload-db`, then the import still succeeds (the endpoint works correctly after the duplicate code is removed).
- [ ] Given a corrupted database file is uploaded, then the import still attempts auto-repair (DatabaseManager handles this internally — no regression).
- [ ] Given `import subprocess` is removed from `app.py`, then no `NameError: name 'subprocess' is not defined` occurs at runtime.
- [ ] Running `python -m py_compile app.py` after this change produces no errors.
- [ ] None of `subprocess`, `platform`, `yaml`, `send_from_directory` appear in the import block of `app.py` after this change (unless any were found to be used after audit).

## Implementation Notes

- Before deleting anything, grep for every occurrence of `validate_and_repair_database`,
  `repair_database_file`, `is_gzipped_file`, `subprocess`, `platform`, `yaml`, and
  `send_from_directory` in `app.py` to confirm they are safe to remove.
- The `/api/projects/<name>/upload-db` endpoint (around line 540-600 in `app.py`) calls
  `validate_and_repair_database()`. After removing it, the endpoint should pass the raw
  uploaded file path directly to `project_manager.import_database()` or
  `project_manager.update_project_with_database()`, which already handle validation
  internally.
- The `gzip` import in `app.py` was only used by the now-deleted `validate_and_repair_database`
  and `repair_database_file` functions. Remove it.
- The `tempfile` import may still be used for the temp directory in file uploads — confirm
  before removing.
- Coordination note: S-4 adds two lines at the top of `app.py` (the compose detection
  import and startup call). S-8 modifies line 18 (secret key). S-9 removes lines 1-12
  (imports) and lines 32-140 (duplicate functions). These are non-overlapping regions.
  Apply S-4 and S-8 first, then S-9, or apply all three in a single pass — either works
  as long as the final file is correct.
- Database migration: No.
- New environment variables: No.
- Breaking changes: The `validate_and_repair_database()` function is removed from `app.py`.
  It was never part of the public API (no external callers). Internal callers are updated
  as part of this story.
