"""Regression tests for generated config files.

These cover the injection paths found in review: a domain or version reaching
generated Makefile/YAML text unvalidated.
"""

from pathlib import Path

import pytest

from utils.config_manager import ConfigManager
from utils.docker_manager import DockerManager


PORTS = {
    'HTTP_PORT': 8090,
    'HTTPS_PORT': 8443,
    'MYSQL_PORT': 3307,
    'PHPMYADMIN_PORT': 8091,
    'REDIS_PORT': 6380,
}


def test_makefile_rejects_domain_injection(tmp_path):
    with pytest.raises(ValueError):
        ConfigManager().create_makefile(
            tmp_path, 'demo', 'evil.test/\nCOMPOSE_CMD = echo PWNED'
        )


def test_makefile_rejects_unsafe_project_name(tmp_path):
    with pytest.raises(ValueError):
        ConfigManager().create_makefile(tmp_path, 'demo\nevil', 'local.demo.test')


def test_makefile_rejects_unsafe_db_filename(tmp_path):
    with pytest.raises(ValueError):
        ConfigManager().create_makefile(
            tmp_path, 'demo', 'local.demo.test',
            db_file_path=Path('/tmp/evil`whoami`.sql'),
        )


def test_makefile_does_not_pass_password_on_command_line(tmp_path):
    ConfigManager().create_makefile(
        tmp_path, 'demo', 'local.demo.test',
        db_file_path=Path('/tmp/dump.sql'),
    )
    content = (tmp_path / 'Makefile').read_text()

    assert '-p${DB_PASSWORD}' not in content
    assert 'MYSQL_PWD' in content
    assert 'export MYSQL_PWD := ${DB_PASSWORD}' in content


def test_compose_rejects_version_injection(tmp_path):
    with pytest.raises(ValueError):
        DockerManager().create_docker_compose(
            tmp_path, 'demo', 'latest\n    privileged: true',
            'local.demo.test', False, False, ports=PORTS,
        )
    assert not (tmp_path / 'docker-compose.yml').exists()


def test_compose_rejects_domain_injection(tmp_path):
    with pytest.raises(ValueError):
        DockerManager().create_docker_compose(
            tmp_path, 'demo', 'latest',
            'local.demo.test\nDOMAIN=evil.test', False, False, ports=PORTS,
        )


def test_compose_accepts_safe_values(tmp_path):
    DockerManager().create_docker_compose(
        tmp_path, 'demo', 'php8.3', 'local.demo.test/blog',
        False, False, ports=PORTS,
    )
    assert (tmp_path / 'docker-compose.yml').exists()
    assert 'image: wordpress:php8.3-fpm' in (tmp_path / 'docker-compose.yml').read_text()
