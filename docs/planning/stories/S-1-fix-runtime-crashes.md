# S-1: Fix Runtime Crashes (fix_php_upload_limits + created_at metadata)

## Priority: High
## Effort: XS
## Dependencies: None
## Files:
- `utils/project_manager.py`

## Description

Two separate bugs that can each be fixed in isolation but are both tiny and touch the same file.
They are grouped to avoid back-to-back diffs on `project_manager.py`.

**Bug 1 — R1: Runtime crash on fix_php_upload_limits**
`app.py` line 618 calls `project_manager.fix_php_upload_limits(project_name)`.
The method is commented out at the bottom of `project_manager.py` (lines 701-704).
Calling a non-existent method raises `AttributeError`, which causes the
`/api/fix-upload-limits/<project_name>` endpoint to always return HTTP 500.
The fix is to uncomment and restore the method. PHP upload limits are already
auto-configured at project creation time via `_create_php_config()` in DockerManager,
so the method body simply returns a success response.

**Bug 2 — R2: created_at stores the CWD instead of a timestamp**
`project_manager.py` line 110:
```python
'created_at': str(Path().resolve()),
```
`Path().resolve()` returns the process working directory (e.g. `/Users/tiago/Desktop/DEV/Local Dev`),
not a timestamp. Every project config records the wrong value. Fix: replace with
`datetime.datetime.now().isoformat()`. The `datetime` module is already imported
(line 7 of `project_manager.py` imports `time`; `datetime` must be added).

## Acceptance Criteria

- [ ] Given a running project, when `POST /api/fix-upload-limits/<project_name>` is called, then the response is HTTP 200 with `{"message": "..."}` (not HTTP 500).
- [ ] Given `fix_php_upload_limits` does not exist, when a request hits the endpoint, then `AttributeError` is NOT raised.
- [ ] Given a newly created project, when its `config.json` is read, then `created_at` is an ISO 8601 timestamp string (e.g. `"2026-03-27T10:45:00.123456"`), not a file path.
- [ ] Given existing projects (created before this fix), their `config.json` files are unaffected (no migration required).
- [ ] No lint errors introduced.

## Implementation Notes

- Add `import datetime` at the top of `project_manager.py` (currently only `time` is imported).
- Restored method signature must match the call in `app.py`:
  `def fix_php_upload_limits(self, project_name) -> dict`
- Return value must be `{'success': True, 'message': 'PHP upload limits are automatically configured (100MB)'}`.
- The method body needs no Docker/subprocess calls — PHP limits are written at container-creation time.
- Database migration: No. Existing `config.json` files keep their stale `created_at` values.
  A future migration story could backfill them, but that is out of scope here.
- No new environment variables required.
- No breaking changes.
