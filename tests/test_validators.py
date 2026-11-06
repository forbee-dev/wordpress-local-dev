from utils.validators import (
    is_valid_domain,
    is_valid_hostname,
    is_valid_project_name,
    is_valid_subfolder,
    is_valid_wordpress_version,
)


def test_project_names():
    assert is_valid_project_name('my-site_2')
    assert not is_valid_project_name('..')
    assert not is_valid_project_name('../etc')
    assert not is_valid_project_name('foo\n')
    assert not is_valid_project_name('')


def test_hostnames():
    assert is_valid_hostname('local.example.test')
    assert is_valid_hostname('localhost')
    assert not is_valid_hostname('example.test:8080')
    assert not is_valid_hostname('exa mple.test')
    assert not is_valid_hostname('-example.test')
    assert not is_valid_hostname('example..test')


def test_domains():
    assert is_valid_domain('local.example.test')
    assert is_valid_domain('local.example.test/blog')
    assert is_valid_domain('local.example.test/site/wp')
    assert not is_valid_domain('evil.test\n1.2.3.4 injected')
    assert not is_valid_domain('evil.test; rm -rf /')
    assert not is_valid_domain('local.example.test/')
    assert not is_valid_domain('local.example.test/../../etc')
    assert not is_valid_domain('local.example.test/.')
    assert not is_valid_domain('local.example.test/%2e%2e')
    assert not is_valid_domain('')


def test_subfolders():
    assert is_valid_subfolder('')
    assert is_valid_subfolder(None)
    assert is_valid_subfolder('blog')
    assert is_valid_subfolder('site/wp')
    assert not is_valid_subfolder('../etc')
    assert not is_valid_subfolder('site/../wp')
    assert not is_valid_subfolder('.')
    assert not is_valid_subfolder('a b')
    assert not is_valid_subfolder('a;b')
    assert not is_valid_subfolder('a' * 256)


def test_wordpress_versions():
    for version in ('latest', '6.6', '6.6.1', 'php8.3', '6.6-fpm', 'wordpress_6.6'):
        assert is_valid_wordpress_version(version)
    for version in (
        '',
        None,
        'latest\n    privileged: true',
        'latest 6.6',
        'latest:6.6',
        '../6.6',
        'a' * 65,
    ):
        assert not is_valid_wordpress_version(version)
