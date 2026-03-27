# S-3: Migrate docker-compose Subprocess Calls — Core Files

## Priority: High
## Effort: M
## Dependencies: S-2 (detection module must exist first)
## Files:
- `utils/docker_manager.py`
- `utils/database_manager.py`
- `utils/project_manager.py`

## Description

Replace every hardcoded `'docker-compose'` string in the three core utility files with
calls to `compose_command()` from `utils/docker_compose_detect.py` (created in S-2).
This makes the application functional on systems where only Docker Compose v2 is available.

This story covers the Python subprocess call sites only. Generated Makefile templates
are handled in S-4. The `app.py` startup detection log is handled in S-5.

### Call sites to migrate

**`utils/docker_manager.py` — 10 sites:**

| Method | Current | Replace with |
|--------|---------|--------------|
| `get_project_status` | `['docker-compose', 'ps', '--format', 'json']` | `compose_command('ps', '--format', 'json')` |
| `start_project` | `['docker-compose', 'up', '-d']` | `compose_command('up', '-d')` |
| `stop_project` | `['docker-compose', 'down']` | `compose_command('down')` |
| `restart_project` (stop) | `['docker-compose', 'down']` | `compose_command('down')` |
| `restart_project` (start) | `['docker-compose', 'up', '-d']` | `compose_command('up', '-d')` |
| `restart_container` | `['docker-compose', 'restart', container_name]` | `compose_command('restart', container_name)` |
| `get_project_logs` | `['docker-compose', 'logs', ...]` | `compose_command('logs', f'--tail={tail_lines}')` |
| `get_container_id` | `['docker-compose', 'ps', '-q', service_name]` | `compose_command('ps', '-q', service_name)` |
| `exec_command_in_container` | `['docker-compose', 'exec', '-T', ...]` | `compose_command('exec', '-T', container_name) + command` |
| `run_wp_cli_command` | `f"docker-compose --profile cli run ..."` then `shlex.split()` | Build as list (see notes) |

**`utils/database_manager.py` — 5 sites:**

| Method | Current | Replace with |
|--------|---------|--------------|
| `_backup_database` (primary) | `['docker-compose', 'exec', '-T', 'mysql', 'mysqldump', ...]` | `compose_command('exec', '-T', 'mysql', 'mysqldump', ...)` |
| `_backup_database` (fallback) | `['docker-compose', 'exec', '-T', 'mysql', 'mysqldump', ...]` | `compose_command('exec', '-T', 'mysql', 'mysqldump', ...)` |
| `_clear_database` | `['docker-compose', 'exec', '-T', 'mysql', 'mysql', ...]` | `compose_command('exec', '-T', 'mysql', 'mysql', ...)` |
| `_import_database_with_fallback` | `['docker-compose', 'exec', '-T', 'mysql', 'mysql', ...]` | `compose_command('exec', '-T', 'mysql', 'mysql', ...)` |
| `_create_and_import_repaired_file` | `['docker-compose', 'exec', '-T', 'mysql', 'mysql', ...]` | `compose_command('exec', '-T', 'mysql', 'mysql', ...)` |

**`utils/project_manager.py` — 1 site:**

| Method | Current | Replace with |
|--------|---------|--------------|
| `_start_containers_with_setup` line 592 | `['docker-compose', 'up', '-d']` | `compose_command('up', '-d')` |

## Acceptance Criteria

- [ ] Given Docker Compose v2 only, when a project is started via the API, then containers start without `FileNotFoundError`.
- [ ] Given Docker Compose v2 only, when a project is stopped, then the command succeeds.
- [ ] Given Docker Compose v2 only, when logs are fetched, then logs are returned.
- [ ] Given Docker Compose v2 only, when a database is imported, then the mysql subprocess runs correctly.
- [ ] Given Docker Compose v1 only, when any of the above operations are performed, then they continue to work (no regression).
- [ ] The WP CLI command in `run_wp_cli_command` is built as a list (not a formatted string passed to `shlex.split`).
- [ ] No `'docker-compose'` string literal remains in any of the three files (verified by grep).
- [ ] All three files have `from utils.docker_compose_detect import compose_command` at the top.

## Implementation Notes

**WP CLI special case** (`docker_manager.py` `run_wp_cli_command`):

Current code:
```python
full_command = f"docker-compose --profile cli run --rm wpcli {command}"
result = subprocess.run(shlex.split(full_command), ...)
```

Replace with:
```python
from utils.docker_compose_detect import compose_command
import shlex

cmd = compose_command('--profile', 'cli', 'run', '--rm', 'wpcli')
cmd.extend(shlex.split(command))   # split the WP CLI sub-command into args
result = subprocess.run(cmd, ...)
```

This preserves correct shell quoting for WP CLI arguments while eliminating the
string-built command.

**Import placement**: Add `from utils.docker_compose_detect import compose_command`
at the top of each file alongside the existing imports.

**`exec_command_in_container`** current code builds the list manually:
```python
cmd = ['docker-compose', 'exec', '-T', container_name] + command
```
Replace with:
```python
cmd = compose_command('exec', '-T', container_name) + command
```

**No timeout changes in this story**: subprocess timeouts are addressed in S-6.
Do not add `timeout=` parameters here — that is intentionally scoped to S-6 to
keep diffs reviewable.

- Database migration: No.
- New environment variables: No.
- Breaking changes: None for end users. Internal command list format changes but
  the Docker Compose operations are identical.
