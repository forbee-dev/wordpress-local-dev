"""Unit tests for project-manager update paths.

The managers are replaced with simple fakes so these tests never touch Docker,
nginx or the real hosts file.
"""

from utils.project_manager import ProjectManager


class FakeConfigManager:
    def __init__(self, config):
        self.config = dict(config)
        self.persisted = None
        self.nginx_subfolder = None

    def read_project_config(self, project_path):
        return dict(self.config)

    def update_project_config(self, project_path, updates):
        self.persisted = dict(updates)
        self.config.update(updates)

    def create_nginx_config(self, project_path, name, domain, enable_ssl, subfolder=''):
        self.nginx_subfolder = subfolder


class FakeHostsManager:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_host(self, host):
        self.added.append(host)
        return {'success': True}

    def remove_host(self, host):
        self.removed.append(host)


class FakeSSLGenerator:
    def __init__(self):
        self.generated = []

    def generate_ssl_cert(self, project_name, domain):
        self.generated.append((project_name, domain))


class FakeDockerManager:
    def __init__(self):
        self.stopped = []
        self.started = []
        self.compose_domain = None

    def stop_project(self, project_path):
        self.stopped.append(project_path)

    def create_docker_compose(self, project_path, name, version, domain, enable_ssl, enable_redis, ports=None):
        self.compose_domain = domain

    def start_project(self, project_path):
        self.started.append(project_path)
        return {'success': True}


def make_manager(tmp_path, **config_overrides):
    config = {
        'name': 'demo',
        'domain': 'local.demo.test',
        'subfolder': '',
        'wordpress_version': 'latest',
        'enable_ssl': True,
        'enable_redis': False,
    }
    config.update(config_overrides)

    manager = object.__new__(ProjectManager)
    manager.projects_dir = tmp_path
    (tmp_path / 'demo').mkdir()
    manager.config_manager = FakeConfigManager(config)
    manager.hosts_manager = FakeHostsManager()
    manager.ssl_generator = FakeSSLGenerator()
    manager.docker_manager = FakeDockerManager()
    return manager


def test_update_domain_persists_and_applies_subfolder(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.update_domain('demo', 'new.example.test/blog')

    assert result['success']
    assert manager.config_manager.persisted['domain'] == 'new.example.test/blog'
    assert manager.config_manager.persisted['subfolder'] == 'blog'
    assert manager.config_manager.nginx_subfolder == 'blog'
    assert manager.docker_manager.compose_domain == 'new.example.test/blog'
    assert manager.hosts_manager.added == ['new.example.test']
    assert manager.docker_manager.started


def test_update_domain_keeps_existing_subfolder(tmp_path):
    manager = make_manager(tmp_path, domain='old.example.test/blog', subfolder='blog')

    result = manager.update_domain('demo', 'new.example.test')

    assert result['success']
    assert manager.config_manager.persisted['domain'] == 'new.example.test/blog'
    assert manager.config_manager.nginx_subfolder == 'blog'


def test_update_domain_rejects_injection(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.update_domain('demo', 'evil.test/\nCOMPOSE_CMD = echo PWNED')

    assert not result['success']
    assert manager.config_manager.persisted is None


def test_update_project_config_noop_does_not_restart(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.update_project_config('demo', custom_domain='local.demo.test')

    assert result['success']
    assert result['updated_fields'] == []
    assert result['message'] == 'No configuration changes'
    assert manager.docker_manager.stopped == []
    assert manager.docker_manager.started == []


def test_update_project_config_rejects_duplicate_subfolder(tmp_path):
    manager = make_manager(tmp_path)

    result = manager.update_project_config(
        'demo', custom_domain='new.example.test/blog', subfolder='other'
    )

    assert not result['success']
    assert 'twice' in result['error'].lower()
    assert manager.config_manager.persisted is None
