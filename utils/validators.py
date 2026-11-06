"""Validation helpers shared by the API and the project managers.

Everything here returns ``True``/``False`` and never raises, so callers can
turn bad input into a 400 instead of a traceback.
"""

import re

PROJECT_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")

# One or more dot-separated hostname labels. No underscores, spaces or slashes.
_HOSTNAME_RE = re.compile(
    r"(?=.{1,253}\Z)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)

# Safe URL path segments (WordPress can live in /blog or /site/wp).
_SUBFOLDER_RE = re.compile(r"[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*")

# Docker Hub tags such as latest, 6.6, php8.3, 6.6-fpm. No whitespace, colon,
# slash or other characters that could break out of the YAML image line.
_WORDPRESS_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

_MAX_SUBFOLDER_LENGTH = 255


def is_valid_project_name(name):
    """Project names become directory names, Docker names and hosts entries."""
    return isinstance(name, str) and PROJECT_NAME_RE.fullmatch(name) is not None


def is_valid_hostname(host):
    """A bare hostname (no scheme, port, path or whitespace)."""
    return isinstance(host, str) and _HOSTNAME_RE.fullmatch(host) is not None


def is_valid_domain(domain):
    """Validate a full ``host`` or ``host/subfolder`` project domain.

    Both parts are checked: a valid host followed by an unsafe path would
    otherwise reach generated nginx/Makefile content.
    """
    if not isinstance(domain, str) or not domain:
        return False
    host, separator, subfolder = domain.partition("/")
    if not is_valid_hostname(host):
        return False
    if not separator:
        return True
    return bool(subfolder) and is_valid_subfolder(subfolder)


def is_valid_subfolder(subfolder):
    """Allow an empty value or one or more safe path segments."""
    if subfolder in (None, ""):
        return True
    if (
        not isinstance(subfolder, str)
        or len(subfolder) > _MAX_SUBFOLDER_LENGTH
        or not _SUBFOLDER_RE.fullmatch(subfolder)
    ):
        return False
    return all(segment not in (".", "..") for segment in subfolder.split("/"))


def is_valid_wordpress_version(version):
    """Allow tags such as ``latest``, ``6.6``, ``php8.3`` or ``6.6-fpm``.

    The value is written into ``docker-compose.yml`` verbatim, so anything that
    could break out of the YAML line (newlines, spaces, colons) must be rejected.
    """
    return isinstance(version, str) and _WORDPRESS_VERSION_RE.fullmatch(version) is not None
