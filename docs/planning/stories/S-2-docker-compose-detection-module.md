# S-2: Create Docker Compose v1/v2 Detection Module

## Priority: High
## Effort: S
## Dependencies: None
## Files:
- `utils/docker_compose_detect.py` (new file)

## Description

The application hardcodes the string `'docker-compose'` (the v1 standalone binary) in
approximately 28 subprocess call sites across 5 files. Docker Compose v1 was removed
from Docker Desktop in late 2023; modern macOS/Linux/Windows systems only ship v2
(`docker compose`, space-separated, as a Docker plugin). The application is entirely
broken on these systems with `FileNotFoundError: [Errno 2] No such file or directory: 'docker-compose'`.

This story creates the detection module that all subsequent stories will consume.
It must be implemented before S-3, S-4, and S-5 which migrate the call sites.

The module lives at `utils/docker_compose_detect.py` and provides three public functions:

1. `get_compose_command()` — Returns `['docker', 'compose']` (v2) or `['docker-compose']` (v1).
   Detection result is cached for the process lifetime. Raises `RuntimeError` if neither is found.
2. `get_compose_version()` — Returns the version string detected, or triggers detection if not yet run.
3. `compose_command(*args)` — Convenience function: returns `get_compose_command() + list(args)`,
   ready to pass to `subprocess.run()`.
4. `reset_cache()` — Resets the in-memory cache (for use in tests).

Detection order:
1. Try `docker compose version` (v2). If exit code 0 → v2 confirmed, cache `['docker', 'compose']`.
2. Try `shutil.which('docker-compose')` then `docker-compose --version` (v1).
3. If both fail → raise `RuntimeError` with an install link.

The full module design is specified in
`docs/planning/architecture/ADR-002-docker-compose-v1-v2-detection.md`.
The code shown there can be used verbatim.

## Acceptance Criteria

- [ ] Given only Docker Compose v2 is installed, when `get_compose_command()` is called, then it returns `['docker', 'compose']`.
- [ ] Given only Docker Compose v1 is installed, when `get_compose_command()` is called, then it returns `['docker-compose']`.
- [ ] Given neither is installed, when `get_compose_command()` is called, then a `RuntimeError` is raised with a message containing the Docker install URL.
- [ ] Given `get_compose_command()` has already been called, when it is called a second time, then no subprocess is spawned (the cached result is returned).
- [ ] Given `reset_cache()` is called, when `get_compose_command()` is called next, then detection runs again.
- [ ] Given any environment, when `compose_command('up', '-d')` is called, then the return value is a list starting with either `['docker', 'compose', 'up', '-d']` or `['docker-compose', 'up', '-d']`.
- [ ] All subprocess calls in the module use `timeout=10`.
- [ ] The module has no external package dependencies beyond the Python standard library.

## Implementation Notes

- The detection subprocess calls must use `capture_output=True, text=True` so they do not
  pollute the terminal and do not block on stdin.
- Use `shutil.which('docker-compose')` before attempting to run it, to avoid a slow
  `FileNotFoundError` on PATH-less environments.
- The cache is module-level globals (`_cached_compose_cmd`, `_cached_compose_version`).
  This is safe because Flask runs in a single process (or multiple workers that each
  independently detect and cache — both outcomes are correct).
- `get_compose_command()` returns a copy of the cached list (`list(_cached_compose_cmd)`)
  so callers cannot mutate the cache.
- Do not import this module at the top of other utils modules at definition time; import
  it inside the function that needs it if you want to avoid circular imports, or import
  at the top of the file — either is fine since there are no circular dependencies.
- Database migration: No.
- New environment variables: No.
- Breaking changes: None (no existing code is modified in this story).
