# S-8: Cross-Platform and Deprecation Fixes (date command, utcnow, secret key, bare except)

## Priority: Low
## Effort: S
## Dependencies: None (can run in parallel with all other stories)
## Files:
- `utils/database_manager.py`
- `utils/ssl_generator.py`
- `utils/project_manager.py`
- `utils/config_manager.py`
- `app.py`

## Description

Four small quality issues, each a one-to-three line change, grouped into a single story
because they all touch different files with no dependencies on each other or on other stories.

### Fix 1 — R9: Cross-platform date command in database backup filename

**File:** `utils/database_manager.py` line 208

Current code:
```python
backup_filename = f"backup_before_import_{project_name}_{subprocess.run(['date', '+%Y%m%d_%H%M%S'], capture_output=True, text=True).stdout.strip()}.sql"
```

This forks a shell `date` process, which fails on Windows (no `date` command with Unix flags).
Replace with Python's datetime:

```python
from datetime import datetime
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_filename = f"backup_before_import_{project_name}_{timestamp}.sql"
```

`datetime` is already imported at the top of `database_manager.py` (line 6). No new import needed.

### Fix 2 — R10: Replace datetime.utcnow() deprecation in ssl_generator.py

**File:** `utils/ssl_generator.py` lines 166-168

Current code:
```python
).not_valid_before(
    datetime.datetime.utcnow()
).not_valid_after(
    datetime.datetime.utcnow() + datetime.timedelta(days=365)
```

`datetime.utcnow()` was deprecated in Python 3.12 and will be removed in a future version.
Replace with timezone-aware equivalents:

```python
import datetime as dt

now = dt.datetime.now(dt.timezone.utc)
).not_valid_before(now
).not_valid_after(now + dt.timedelta(days=365)
```

Note: the `cryptography` library's `x509` builder accepts timezone-aware datetimes.
Verify the installed cryptography version supports this (it does since cryptography >= 2.5).

### Fix 3 — R11: Replace hardcoded Flask secret key

**File:** `app.py` line 18

Current code:
```python
app.secret_key = 'wordpress-local-dev-secret-key'
```

A hardcoded secret key is a security risk: sessions could be forged if the key is leaked
or guessed. Replace with a randomly generated key at startup:

```python
import os
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24).hex()
```

This allows the secret key to be set via environment variable (for production/persistent
sessions), but falls back to a random key per-process (safe for local dev, where sessions
are ephemeral). The `os` module is already imported in `app.py`.

### Fix 4 — R12: Replace bare except clauses

**Files:** `utils/project_manager.py` lines 153, 640, 680; `utils/config_manager.py` lines 246, 265

Bare `except:` clauses catch `SystemExit`, `KeyboardInterrupt`, and `GeneratorExit` in
addition to regular exceptions, which can mask serious runtime problems.

Replace each bare `except:` with `except Exception as e:` and add a log line:

```python
# Before:
except:
    pass

# After:
except Exception as e:
    print(f"Warning: unexpected error: {e}")
```

Exact locations to fix:
- `project_manager.py` line 153 (in `list_projects` inner try): add `print(f"Warning: could not get status for project: {e}")`
- `project_manager.py` line 640 (in `_cleanup_failed_project`): add `print(f"Warning: cleanup failed: {e}")`
- `project_manager.py` line 680 (in `_ensure_ssl_certificates` inner try): add `print(f"Warning: SSL cert age check failed: {e}")`
- `config_manager.py` line 246 (in `read_project_config`): add `print(f"Warning: could not parse config.json: {e}")`
- `config_manager.py` line 265 (in `update_project_config`): add `print(f"Warning: could not write config.json: {e}")`

Also check `docker_manager.py` line 525 (`has_wpcli_service` bare `except:`):
```python
# Before:
except:
    return False

# After:
except Exception as e:
    print(f"Warning: could not read docker-compose.yml: {e}")
    return False
```

## Acceptance Criteria

- [ ] Given a database backup is triggered on Windows, when `_backup_database` runs, then no subprocess is spawned for the timestamp (the filename is generated via Python datetime).
- [ ] Given a project is created with SSL enabled on Python 3.12+, when `generate_ssl_cert` runs, then no `DeprecationWarning` about `utcnow()` is emitted.
- [ ] Given the Flask application is started twice in the same process, then `app.secret_key` is the same value both times (not regenerated per request).
- [ ] Given the Flask application is started in a fresh process with no `FLASK_SECRET_KEY` env var, then `app.secret_key` is a 48-character hex string (24 bytes).
- [ ] Given `FLASK_SECRET_KEY=mysecretkey` is set in the environment, then `app.secret_key` is `'mysecretkey'`.
- [ ] No bare `except:` clauses remain in `project_manager.py`, `config_manager.py`, or `docker_manager.py`.
- [ ] All replaced bare excepts include a print/log statement with the error.
- [ ] No lint errors introduced.

## Implementation Notes

- The `datetime` import in `ssl_generator.py` is currently `import datetime` (line 9),
  so the usage is `datetime.datetime.utcnow()`. After the fix, you can either:
  a) Keep `import datetime` and use `datetime.datetime.now(datetime.timezone.utc)`, or
  b) Change to `from datetime import datetime, timedelta, timezone` and use `datetime.now(timezone.utc)`.
  Either is correct — be consistent with the existing style in that file.
- The `os.urandom(24).hex()` call at module load time (outside a request context) is safe.
  It is called once when the module is imported, not on every request.
- The backup filename fix (Fix 1) is technically a one-liner that also removes an unnecessary
  `subprocess.run()` call inside `_backup_database`. This eliminates one unintended process
  fork and makes the code cleaner.
- Database migration: No.
- New environment variables: `FLASK_SECRET_KEY` (optional, for production overrides).
  Document this in the CLAUDE.md environment variables table.
- Breaking changes: Existing Flask sessions will be invalidated when the application
  restarts (because the random key changes). This is acceptable for a local dev tool
  where sessions are not expected to persist across restarts.
