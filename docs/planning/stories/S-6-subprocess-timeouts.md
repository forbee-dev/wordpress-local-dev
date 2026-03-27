# S-6: Add Timeouts to All Subprocess Calls

## Priority: Medium
## Effort: S
## Dependencies: S-3 (the call sites in docker_manager.py and database_manager.py should be migrated to compose_command() first, to avoid touching the same lines twice)
## Files:
- `utils/docker_manager.py`
- `utils/database_manager.py`

## Description

Multiple `subprocess.run()` calls in these two files have no `timeout` parameter.
If Docker becomes unresponsive or a MySQL import stalls, the call blocks indefinitely,
hanging the Flask request thread and making the web interface appear frozen.

This story adds explicit `timeout` values to every `subprocess.run()` call in the two
affected files using a three-tier scheme chosen by operation type:

| Tier | Duration | Used for |
|------|----------|----------|
| Status | 30 seconds | `ps`, status checks |
| Operation | 120 seconds | `up`, `down`, `restart`, `logs`, `exec` for quick commands |
| Import | 600 seconds | `mysqldump`, `mysql` import/export (large databases) |

### `utils/docker_manager.py` — changes by method

| Method | Calls | Timeout tier |
|--------|-------|-------------|
| `get_project_status` | `compose_command('ps', ...)` | 30s (status) |
| `start_project` | `compose_command('up', '-d')` | 120s (operation) |
| `stop_project` | `compose_command('down')` | 120s (operation) |
| `restart_project` | both `down` and `up -d` | 120s each |
| `restart_container` | `compose_command('restart', ...)` | 120s |
| `get_project_logs` | `compose_command('logs', ...)` | 30s |
| `get_container_id` | `compose_command('ps', '-q', ...)` | 30s |
| `exec_command_in_container` | `compose_command('exec', ...)` | 120s |
| `run_wp_cli_command` | composed list | 120s |

### `utils/database_manager.py` — changes by method

| Method | Calls | Timeout tier |
|--------|-------|-------------|
| `_backup_database` (primary) | `mysqldump` via exec | 600s (import) |
| `_backup_database` (fallback) | `mysqldump` via exec | 600s |
| `_clear_database` | `mysql -e` | 120s (operation) |
| `_import_database_with_fallback` | `mysql` via exec | 600s |
| `_create_and_import_repaired_file` | `mysql` via exec | 600s |

### Handling `subprocess.TimeoutExpired`

For each call that currently has a bare `except Exception as e:` handler, add a specific
`except subprocess.TimeoutExpired:` clause before the generic handler that returns a
meaningful error:

```python
except subprocess.TimeoutExpired:
    return {'success': False, 'error': 'Operation timed out after Xs. Check Docker status.'}
```

For `database_manager.py` methods that do not return a dict (internal helpers), log the
timeout and re-raise or convert to a descriptive exception message that the caller
(`import_database`) will catch and include in the log output.

## Acceptance Criteria

- [ ] Given every `subprocess.run()` call in `docker_manager.py`, then each has a `timeout=` parameter.
- [ ] Given every `subprocess.run()` call in `database_manager.py`, then each has a `timeout=` parameter.
- [ ] Given `get_project_status` times out, when the status is requested, then the response is `{'status': 'error', 'error': 'Operation timed out...'}` (not a hanging request).
- [ ] Given a database import times out after 600 seconds, when the import endpoint is called, then the response includes a timeout error message in the `logs` array.
- [ ] Given no timeouts occur, then all existing operations continue to work identically (no regression).
- [ ] No new bare `except:` clauses are introduced.

## Implementation Notes

- Do NOT add `timeout` to the `subprocess.run()` call in `project_manager.py`
  `_start_containers_with_setup()` — that already has `timeout=120` on line 598.
  Verify and leave it as-is.
- The `copy_file_to_container` method uses `docker cp` (not docker-compose) — add
  `timeout=30` there too for completeness.
- For `get_project_logs`, a 30-second timeout is intentional. If the log fetch takes
  longer, the request has likely stalled. The caller handles the error gracefully.
- Database backup and import operations on large databases (e.g. 500MB SQL files) can
  legitimately take 5-10 minutes. 600 seconds (10 minutes) is the safe upper bound.
  If real-world usage shows this is too short, it can be increased — but any value is
  better than no limit.
- `subprocess.TimeoutExpired` is a subclass of `subprocess.SubprocessError`, which is
  a subclass of `Exception`. The existing `except Exception as e:` clauses will catch it,
  but it will produce a confusing error message. The specific handler gives a better UX.
- Database migration: No.
- New environment variables: No.
- Breaking changes: None.
