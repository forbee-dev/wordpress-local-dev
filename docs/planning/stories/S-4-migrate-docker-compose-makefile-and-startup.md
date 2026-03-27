# S-4: Migrate docker-compose References — Makefile Templates and app.py Startup

## Priority: Medium
## Effort: S
## Dependencies: S-2 (detection module), S-3 (core call sites — must be done to avoid merge conflicts on docker_manager)
## Files:
- `utils/config_manager.py`
- `app.py`

## Description

After S-3 migrates the Python subprocess calls, two remaining locations still reference
the old `docker-compose` command:

1. **Makefile template in `config_manager.py`** — The `create_makefile()` method generates
   a `Makefile` for each project. All 11 occurrences of `docker-compose` in the template
   string are hardcoded. Developers using these Makefiles on modern Docker will see
   `make: docker-compose: No such file or directory`.

2. **`app.py` startup** — The application should log which Docker Compose binary was detected
   on startup, giving immediate feedback when Docker Compose is missing entirely.

### Changes

**`utils/config_manager.py`** — `create_makefile()`:

Add a `COMPOSE_CMD` variable at the top of the generated Makefile content using
a conditional assignment (`?=`), then replace every `@docker-compose` with
`@$(COMPOSE_CMD)` in the template. This allows users to override the command
if needed, and means existing Makefiles (already generated for the 10 existing
projects) continue to work until regenerated:

```makefile
# Near top of generated Makefile, after the include .env line:
COMPOSE_CMD ?= docker compose
```

Then throughout the template:
```makefile
# Before:
@docker-compose up -d

# After:
@$(COMPOSE_CMD) up -d
```

The `create_makefile()` method signature and parameters do not change.
The `COMPOSE_CMD` default value (`docker compose`) is a safe default since v2
is the current standard. Users on v1 can override: `make start COMPOSE_CMD=docker-compose`.

**`app.py`** — startup detection:

After the `project_manager = ProjectManager()` instantiation block, add a startup
detection call that prints the detected command to the console:

```python
from utils.docker_compose_detect import get_compose_command, get_compose_version

try:
    _compose_cmd = get_compose_command()
    print(f"Docker Compose detected: {' '.join(_compose_cmd)} ({get_compose_version()})")
except RuntimeError as e:
    print(f"WARNING: {e}")
    print("Some features will not work without Docker Compose.")
```

This runs once when the Flask app module is loaded.

## Acceptance Criteria

- [ ] Given a newly created project, when its `Makefile` is inspected, then it contains `COMPOSE_CMD ?= docker compose` near the top.
- [ ] Given a newly created project Makefile, then no line contains the literal string `docker-compose` (only `$(COMPOSE_CMD)` references).
- [ ] Given an existing project whose Makefile was generated before this change, then `make start` still works (the old hardcoded `docker-compose` remains in their file until they regenerate).
- [ ] Given Docker Compose v2 is installed, when the Flask application starts, then the console prints a line like `Docker Compose detected: docker compose (Docker Compose version v2.x.x)`.
- [ ] Given Docker Compose v1 is installed, when the Flask application starts, then the console prints a line like `Docker Compose detected: docker-compose (docker-compose version 1.x.x)`.
- [ ] Given neither v1 nor v2 is installed, when the Flask application starts, then the console prints a WARNING line and the app continues to start (does not crash).
- [ ] No `'docker-compose'` string literal remains in `config_manager.py` within the Makefile template section.

## Implementation Notes

- The `?=` conditional assignment means `make start COMPOSE_CMD=docker-compose` overrides
  the default. This is the correct Make syntax for user-overridable variables.
- The `README.md` template in `config_manager.py` (`create_readme()`) also contains hardcoded
  `8080` phpMyAdmin port. Do not fix that here — it belongs in S-7 (port allocation UI).
- Do not modify `utils/wordpress_manager.py` in this story; check whether it contains
  any `docker-compose` references (it may have one at line 285 per ADR-002) and if so,
  add it to this story's scope — it is a small change (`compose_command('exec', ...)`)
  touching a separate file, so it can be done here without conflicting with S-3.
- The `app.py` import for `docker_compose_detect` should be placed after the existing
  `from utils.project_manager import ProjectManager` import, keeping the import block ordered.
- Database migration: No.
- New environment variables: No.
- Breaking changes: None. Existing Makefiles are untouched.
