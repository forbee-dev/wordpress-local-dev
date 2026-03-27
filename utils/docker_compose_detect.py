"""Docker Compose v1/v2 detection and command helpers.

Detects whether the system has Docker Compose v2 (``docker compose`` plugin)
or v1 (``docker-compose`` standalone binary) and provides helpers for
building subprocess command lists.
"""

import re
import shutil
import subprocess

__all__ = [
    "get_compose_command",
    "get_compose_version",
    "compose_command",
    "reset_cache",
]

_cached_compose_cmd: list[str] | None = None
_cached_compose_version: str | None = None


def _parse_version(text: str) -> str:
    """Extract a semver-like version string from command output."""
    match = re.search(r"(\d+\.\d+\.\d+[\w.-]*)", text)
    if match:
        return match.group(1)
    return text.strip()


def _detect() -> None:
    """Run the detection sequence and populate the module-level cache.

    Detection order:
    1. ``docker compose version`` (v2 plugin)
    2. ``docker-compose --version`` (v1 standalone)
    3. Raise ``RuntimeError`` if neither is available.
    """
    global _cached_compose_cmd, _cached_compose_version

    # --- Attempt 1: Docker Compose v2 (plugin) ---
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            _cached_compose_cmd = ["docker", "compose"]
            _cached_compose_version = _parse_version(result.stdout)
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # --- Attempt 2: Docker Compose v1 (standalone binary) ---
    if shutil.which("docker-compose") is not None:
        try:
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                _cached_compose_cmd = ["docker-compose"]
                _cached_compose_version = _parse_version(result.stdout)
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    raise RuntimeError(
        "Docker Compose not found. "
        "Install Docker Desktop from https://docs.docker.com/get-docker/"
    )


def get_compose_command() -> list[str]:
    """Return the base command list for invoking Docker Compose.

    Returns ``['docker', 'compose']`` for v2 or ``['docker-compose']`` for v1.
    The detection result is cached for the process lifetime.

    A *copy* of the cached list is returned so callers cannot mutate the cache.

    Raises:
        RuntimeError: If neither Docker Compose v2 nor v1 is available.
    """
    if _cached_compose_cmd is None:
        _detect()
    return list(_cached_compose_cmd)  # type: ignore[arg-type]


def get_compose_version() -> str:
    """Return the detected Docker Compose version string.

    Triggers detection if it has not been run yet.

    Raises:
        RuntimeError: If neither Docker Compose v2 nor v1 is available.
    """
    if _cached_compose_version is None:
        _detect()
    return _cached_compose_version  # type: ignore[return-value]


def compose_command(*args: str) -> list[str]:
    """Build a full command list ready for ``subprocess.run()``.

    Example::

        subprocess.run(compose_command('up', '-d'))
        # Equivalent to: ['docker', 'compose', 'up', '-d']  (on v2)

    Raises:
        RuntimeError: If neither Docker Compose v2 nor v1 is available.
    """
    return get_compose_command() + list(args)


def reset_cache() -> None:
    """Reset the in-memory detection cache.

    Useful in tests to force re-detection.
    """
    global _cached_compose_cmd, _cached_compose_version
    _cached_compose_cmd = None
    _cached_compose_version = None
