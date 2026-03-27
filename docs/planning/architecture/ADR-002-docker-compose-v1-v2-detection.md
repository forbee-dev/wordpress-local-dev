# ADR-002: Docker Compose v1 to v2 Detection and Compatibility

**Date:** 2026-03-27
**Status:** Proposed
**Decision Makers:** Project maintainers
**Technical Story:** The codebase hardcodes `docker-compose` (v1 standalone binary) in all subprocess calls. Docker Compose v1 reached end-of-life in July 2023 and has been removed from Docker Desktop since v4.25 (late 2023). Modern systems only have `docker compose` (v2 plugin). The application fails entirely on these systems.

---

## Context

### Current State

The codebase invokes `docker-compose` as a subprocess command in multiple locations:

| File | Approximate Call Count | Operations |
|------|:---:|---|
| `utils/docker_manager.py` | 10 | ps, up, down, restart, logs, exec, run |
| `utils/database_manager.py` | 5 | exec (mysqldump, mysql) |
| `utils/project_manager.py` | 1 | up -d (in `_start_containers_with_setup`) |
| `utils/config_manager.py` | 11 | All Makefile template strings |
| `test_setup.py` | 1 | Version check |
| **Total** | **~28** | |

Every one of these calls uses the string `'docker-compose'` (v1 standalone binary syntax). The v1 binary was deprecated in April 2023 and removed from Docker Desktop in late 2023. As of March 2026:

- **macOS (Docker Desktop 4.25+):** Only `docker compose` (v2 plugin) is available by default. Users must manually install the legacy `docker-compose` binary via pip or brew.
- **Linux:** Package managers (`apt`, `dnf`) now install `docker-compose-plugin` which provides `docker compose` only. The standalone `docker-compose` binary is no longer maintained.
- **Windows (Docker Desktop):** Same as macOS -- v2 plugin only.

Users on modern Docker installations see errors like:
```
FileNotFoundError: [Errno 2] No such file or directory: 'docker-compose'
```

### Constraints

- Must work on macOS, Linux, and Windows.
- Some users may still have v1 installed (older Linux servers, CI environments).
- The detection should happen once and be reused everywhere -- not repeated in every subprocess call.
- Makefile templates also contain `docker-compose` strings and must be updated.
- The solution should be simple enough that it does not require a dependency (e.g., no Docker SDK for Python).

---

## Options Considered

### Option A: Do Nothing (Require v1)

Continue using `docker-compose` everywhere. Document that users must install the legacy binary.

**Pros:**
- Zero code changes.

**Cons:**
- Breaks for most modern Docker installations.
- Requires users to install a deprecated, unmaintained binary.
- Will become increasingly untenable as v1 disappears from package managers.

**Complexity:** None (status quo)

### Option B: Hard-Switch to v2 Only

Replace all `docker-compose` strings with `docker compose` (split into `['docker', 'compose', ...]`).

**Pros:**
- Simple find-and-replace.
- Aligns with the future -- v2 is the only maintained version.

**Cons:**
- Breaks for users who still have only v1 installed.
- No graceful fallback.
- Requires splitting command strings differently (`['docker', 'compose', 'up']` vs `['docker-compose', 'up']`).

**Complexity:** Low

### Option C: Detection Utility with Cached Result

Create a small utility module that detects which command is available on the system at startup, caches the result, and provides it to all callers. The detection logic:

1. Try `docker compose version` (v2 plugin).
2. If that fails, try `docker-compose --version` (v1 standalone).
3. Cache the result as a command prefix (either `['docker', 'compose']` or `['docker-compose']`).
4. Provide a helper function that callers use to build subprocess commands.

**Pros:**
- Works with both v1 and v2 -- maximum compatibility.
- Detection happens once, cached for the process lifetime.
- Clean API: callers get a command list prefix and just append their arguments.
- Makefile templates can use a variable for the compose command.
- Easy to remove v1 support later when it is truly dead.

**Cons:**
- Slightly more code than a hard switch.
- Must be integrated into all call sites (though this is also true for Option B).

**Complexity:** Low-Medium

### Option D: Wrapper Shell Script

Create a `docker-compose` shell script/shim that delegates to `docker compose` if v1 is not found. Place it on PATH.

**Pros:**
- Zero code changes in Python -- the shim makes `docker-compose` work regardless.

**Cons:**
- Cross-platform complexity (batch file for Windows, shell script for Unix).
- Must be installed/configured per system -- adds setup friction.
- Fragile: PATH manipulation is error-prone.
- Does not solve the Makefile template issue.
- Hides the real command being used, complicating debugging.

**Complexity:** Medium (cross-platform) with high fragility

---

## Decision Matrix

| Criteria              | A: Do Nothing | B: v2 Only | C: Detection Utility | D: Wrapper Script |
|-----------------------|:---:|:---:|:---:|:---:|
| Compatibility         | 2/5 | 3/5 | 5/5 | 4/5 |
| Maintainability       | 3/5 | 4/5 | 5/5 | 2/5 |
| Implementation speed  | 5/5 | 4/5 | 4/5 | 2/5 |
| Robustness            | 1/5 | 3/5 | 5/5 | 2/5 |
| Debuggability         | 3/5 | 4/5 | 5/5 | 2/5 |
| Future-proofing       | 1/5 | 5/5 | 5/5 | 3/5 |
| **Weighted Total**    | **2.5** | **3.8** | **4.8** | **2.5** |

---

## Recommendation

**Option C: Detection Utility with Cached Result**

### Rationale

Option C provides maximum compatibility with minimal complexity. The detection logic is approximately 40 lines of Python. It handles the real-world scenario where some team members or CI systems still have v1 while others have v2. When v1 is eventually extinct, removing support is a one-line change (remove the v1 fallback branch).

Option B (v2 only) is tempting for its simplicity, but it will break for users on older Linux servers or CI environments that still ship v1. Given that the detection utility is trivially simple, the compatibility benefit easily justifies the marginal extra code.

### Why Not the Others

- **Option A (Do Nothing):** The application is already broken on most modern Docker installations. This is not viable.
- **Option B (v2 Only):** Unnecessarily excludes users who still have v1. The cost of supporting both is negligible.
- **Option D (Wrapper Script):** Introduces cross-platform maintenance burden and fragility for no real benefit over Option C.

---

## Detailed Design

### New Module: `utils/docker_compose_detect.py`

```python
"""
Detect whether the system has Docker Compose v2 (plugin) or v1 (standalone).
Provides a cached command prefix for use in all subprocess calls.
"""

import subprocess
import logging
import shutil

logger = logging.getLogger(__name__)

_cached_compose_cmd = None
_cached_compose_version = None


def get_compose_command():
    """
    Return the Docker Compose command as a list suitable for subprocess calls.

    Returns:
        list: Either ['docker', 'compose'] (v2) or ['docker-compose'] (v1).

    Raises:
        RuntimeError: If neither v1 nor v2 is available.
    """
    global _cached_compose_cmd, _cached_compose_version

    if _cached_compose_cmd is not None:
        return list(_cached_compose_cmd)  # return a copy

    # Strategy 1: Try Docker Compose v2 (plugin)
    try:
        result = subprocess.run(
            ['docker', 'compose', 'version'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version_str = result.stdout.strip()
            _cached_compose_cmd = ['docker', 'compose']
            _cached_compose_version = version_str
            logger.info(f"Detected Docker Compose v2: {version_str}")
            return list(_cached_compose_cmd)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Strategy 2: Try Docker Compose v1 (standalone)
    if shutil.which('docker-compose'):
        try:
            result = subprocess.run(
                ['docker-compose', '--version'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_str = result.stdout.strip()
                _cached_compose_cmd = ['docker-compose']
                _cached_compose_version = version_str
                logger.info(f"Detected Docker Compose v1: {version_str}")
                return list(_cached_compose_cmd)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    raise RuntimeError(
        "Docker Compose not found. Please install Docker Desktop (includes Compose v2) "
        "or install docker-compose standalone. "
        "See: https://docs.docker.com/compose/install/"
    )


def get_compose_version():
    """Return the detected Docker Compose version string, or None if not yet detected."""
    if _cached_compose_cmd is None:
        get_compose_command()  # trigger detection
    return _cached_compose_version


def compose_command(*args):
    """
    Convenience function: return a full command list ready for subprocess.run().

    Usage:
        subprocess.run(compose_command('up', '-d'), cwd=project_path, ...)
        subprocess.run(compose_command('exec', '-T', 'mysql', 'mysqldump', ...), ...)
    """
    return get_compose_command() + list(args)


def reset_cache():
    """Reset the cached detection (useful for testing)."""
    global _cached_compose_cmd, _cached_compose_version
    _cached_compose_cmd = None
    _cached_compose_version = None
```

### Integration Pattern

Every file that currently calls `subprocess.run(['docker-compose', ...])` will be updated to use the utility:

```python
# Before (current code):
result = subprocess.run(
    ['docker-compose', 'up', '-d'],
    cwd=project_path, capture_output=True, text=True
)

# After (new code):
from utils.docker_compose_detect import compose_command

result = subprocess.run(
    compose_command('up', '-d'),
    cwd=project_path, capture_output=True, text=True
)
```

The `compose_command()` function returns either `['docker', 'compose', 'up', '-d']` or `['docker-compose', 'up', '-d']` depending on what was detected.

### File-by-File Changes

**`utils/docker_manager.py` (10 call sites):**

| Line(s) | Current Command | New Command |
|---------|-----------------|-------------|
| 19 | `['docker-compose', 'ps', '--format', 'json']` | `compose_command('ps', '--format', 'json')` |
| 53 | `['docker-compose', 'up', '-d']` | `compose_command('up', '-d')` |
| 99 | `['docker-compose', 'down']` | `compose_command('down')` |
| 121 | `['docker-compose', 'down']` | `compose_command('down')` |
| 132 | `['docker-compose', 'up', '-d']` | `compose_command('up', '-d')` |
| 153 | `['docker-compose', 'restart', container_name]` | `compose_command('restart', container_name)` |
| 174 | `['docker-compose', 'logs', ...]` | `compose_command('logs', ...)` |
| 429 | `['docker-compose', 'ps', '-q', service_name]` | `compose_command('ps', '-q', service_name)` |
| 458 | `['docker-compose', 'exec', '-T', ...]` | `compose_command('exec', '-T', ...)` |
| 495 | `f"docker-compose --profile cli run ..."` | Build as list using `compose_command(...)` |

**`utils/database_manager.py` (5 call sites):**

| Line(s) | Current Command | New Command |
|---------|-----------------|-------------|
| 214 | `['docker-compose', 'exec', '-T', 'mysql', 'mysqldump', ...]` | `compose_command('exec', '-T', 'mysql', 'mysqldump', ...)` |
| 231 | `['docker-compose', 'exec', '-T', 'mysql', 'mysqldump', ...]` | `compose_command('exec', '-T', 'mysql', 'mysqldump', ...)` |
| 253 | `['docker-compose', 'exec', '-T', 'mysql', 'mysql', ...]` | `compose_command('exec', '-T', 'mysql', 'mysql', ...)` |
| 317 | `['docker-compose', 'exec', '-T', 'mysql', 'mysql', ...]` | `compose_command('exec', '-T', 'mysql', 'mysql', ...)` |
| 416 | `['docker-compose', 'exec', '-T', 'mysql', 'mysql', ...]` | `compose_command('exec', '-T', 'mysql', 'mysql', ...)` |

**`utils/project_manager.py` (1 call site):**

| Line(s) | Current Command | New Command |
|---------|-----------------|-------------|
| 593 | `['docker-compose', 'up', '-d']` | `compose_command('up', '-d')` |

**`utils/wordpress_manager.py` (1 call site in subprocess, references in strings):**

| Line(s) | Current | New |
|---------|---------|-----|
| 285 | `['docker-compose', 'exec', '-T', 'mysql', ...]` | `compose_command('exec', '-T', 'mysql', ...)` |

**`utils/config_manager.py` -- Makefile templates (11 occurrences):**

The Makefile is generated code, not a Python subprocess call. Two approaches:

1. **Dynamic variable injection (recommended):** Add a `COMPOSE_CMD` variable at the top of the generated Makefile:
   ```makefile
   COMPOSE_CMD ?= docker compose
   ```
   Then replace all `@docker-compose` with `@$(COMPOSE_CMD)` in the template.

2. The Python code that generates the Makefile will call `get_compose_command()` and join it into the appropriate string:
   ```python
   from utils.docker_compose_detect import get_compose_command
   compose_str = ' '.join(get_compose_command())  # "docker compose" or "docker-compose"
   ```

Approach 1 is preferred because it allows the user to override the command in their Makefile without regenerating it.

**`test_setup.py` (1 call site):**

Update the Docker Compose version check to use the detection utility:
```python
from utils.docker_compose_detect import get_compose_command, get_compose_version
cmd = get_compose_command()
print(f"Docker Compose: {get_compose_version()}")
```

### Startup Integration

In `app.py`, detect the compose command early and log it:

```python
from utils.docker_compose_detect import get_compose_command, get_compose_version

# During startup
try:
    compose_cmd = get_compose_command()
    print(f"Docker Compose detected: {' '.join(compose_cmd)} ({get_compose_version()})")
except RuntimeError as e:
    print(f"WARNING: {e}")
    print("Some features will not work without Docker Compose.")
```

This gives immediate feedback on startup if Docker Compose is missing.

### WP CLI Special Case

The `run_wp_cli_command` method in `docker_manager.py` (line 495) currently builds a command string and uses `shlex.split()`:

```python
full_command = f"docker-compose --profile cli run --rm wpcli {command}"
result = subprocess.run(shlex.split(full_command), ...)
```

This must be refactored to build the command as a list:

```python
from utils.docker_compose_detect import compose_command
import shlex

cmd = compose_command('--profile', 'cli', 'run', '--rm', 'wpcli')
cmd.extend(shlex.split(command))  # split user's WP CLI command into args
result = subprocess.run(cmd, ...)
```

---

## Implementation Roadmap

### Phase 1: Create Detection Module (~0.5 days)
1. Create `utils/docker_compose_detect.py` with `get_compose_command()`, `compose_command()`, and `get_compose_version()`.
2. Add unit tests: mock v1-only, v2-only, both available, neither available.
3. Add startup detection log in `app.py`.

### Phase 2: Update Subprocess Calls (~1 day)
1. Update `utils/docker_manager.py` (10 sites).
2. Update `utils/database_manager.py` (5 sites).
3. Update `utils/project_manager.py` (1 site).
4. Update `utils/wordpress_manager.py` (1 site).
5. Update `test_setup.py` (1 site).
6. Manually test each operation: start, stop, restart, logs, db import/export, WP CLI.

### Phase 3: Update Generated Files (~0.5 days)
1. Update `utils/config_manager.py` Makefile template to use `COMPOSE_CMD` variable.
2. Optionally add a migration endpoint to regenerate Makefiles for existing projects.
3. Update generated README templates.

### Phase 4: Deprecation Notice (~future)
1. Log a deprecation warning when v1 is detected:
   ```
   WARNING: Docker Compose v1 detected. v1 is deprecated and no longer maintained.
   Please upgrade to Docker Compose v2: https://docs.docker.com/compose/install/
   ```
2. Set a target date (e.g., 6 months) to drop v1 support entirely.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| v2 `docker compose` has subtle behavioral differences from v1 | Low | Medium | Docker Compose v2 is backward-compatible for the commands we use (up, down, exec, ps, logs, run). Test all operations on v2. |
| Detection runs before Docker daemon is started | Medium | Low | `get_compose_command()` checks the binary exists, not that the daemon is running. Daemon availability is checked separately at container start time. |
| Cached result becomes stale if user installs/removes Docker mid-session | Very Low | Low | `reset_cache()` is available. Application restart also resets. Not a practical concern. |
| Makefile regeneration breaks existing projects | Low | Medium | Use `COMPOSE_CMD ?=` (conditional assignment) so existing Makefiles with hardcoded `docker-compose` continue to work. Only new/regenerated Makefiles get the variable. |
| `--profile` flag behaves differently between v1 and v2 | Low | Low | The `--profile` flag was introduced in Docker Compose v1.28+ and works identically in v2. We already require profiles support. |

---

## Consequences

**Positive:**
- Application works on modern Docker installations (Docker Desktop 4.25+, recent Linux packages) where only v2 is available.
- Backward compatible with systems that still have v1.
- Single point of detection -- easy to maintain and reason about.
- Clear deprecation path for eventually dropping v1 support.
- Better error messages when Docker Compose is not installed at all.

**Negative:**
- All files with subprocess calls must be touched (one-time migration cost).
- Marginal increase in import complexity (one new import per file).

**Neutral:**
- No behavioral change for end users -- same Docker Compose operations, just invoked through the correct binary.
- Existing generated Makefiles continue to work until regenerated.

---

## ADR Record

**Decision:** Create a `utils/docker_compose_detect.py` module that detects Docker Compose v2 (`docker compose`) or v1 (`docker-compose`) once at startup, caches the result, and provides a `compose_command()` helper. All ~28 subprocess call sites across 5 files will be updated to use this helper instead of hardcoding `docker-compose`. Generated Makefiles will use a `COMPOSE_CMD` variable.

**Status:** Proposed

**Consequences:** The application will work on both legacy (v1) and modern (v2) Docker Compose installations. A future removal of v1 support becomes a one-line change in the detection module.
