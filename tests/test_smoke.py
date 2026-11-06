"""Smoke tests that do not need Docker or network access."""

import app as webapp


def make_client():
    webapp.app.config.update(TESTING=True)
    return webapp.app.test_client()


def test_index_renders():
    response = make_client().get('/')
    assert response.status_code == 200
    assert b'WordPress' in response.data


def test_list_projects_is_json():
    response = make_client().get('/api/projects')
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_project_name_traversal_is_rejected():
    client = make_client()
    for url in ('/api/projects/../status', '/api/projects/%2e%2e/logs'):
        response = client.get(url)
        assert response.status_code == 400
        assert response.get_json()['error'] == 'Invalid project name'

    response = client.delete('/api/projects/../delete')
    assert response.status_code == 400


def test_wp_cli_missing_project_returns_json_400():
    response = make_client().post('/api/wp-cli/not-a-project', json={'command': 'help'})
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Project not found'


def test_untrusted_host_is_rejected():
    response = make_client().get('/', headers={'Host': 'evil.example.com'})
    assert response.status_code == 400


def test_cross_origin_write_is_rejected():
    response = make_client().post(
        '/api/create-project', data={}, headers={'Origin': 'https://evil.example.com'}
    )
    assert response.status_code == 403


def test_same_origin_write_is_allowed():
    response = make_client().post(
        '/api/create-project', data={}, headers={'Origin': 'http://127.0.0.1:5001'}
    )
    assert response.status_code == 400  # validation error, not a CSRF rejection


def test_invalid_custom_domain_is_rejected():
    response = make_client().post('/api/create-project', data={
        'project_name': 'smoke-test-invalid',
        'wordpress_version': 'latest',
        'custom_domain': 'evil.test; rm -rf /',
    })
    assert response.status_code == 400
    assert 'domain' in response.get_json()['error'].lower()


def test_invalid_subfolder_is_rejected():
    response = make_client().post('/api/create-project', data={
        'project_name': 'smoke-test-invalid',
        'wordpress_version': 'latest',
        'subfolder': '../../etc',
    })
    assert response.status_code == 400
    assert 'subfolder' in response.get_json()['error'].lower()


def test_upload_limit_returns_json_413():
    client = make_client()
    original = webapp.app.config['MAX_CONTENT_LENGTH']
    webapp.app.config['MAX_CONTENT_LENGTH'] = 1024
    try:
        response = client.post('/api/create-project', data={'blob': 'x' * 4096})
    finally:
        webapp.app.config['MAX_CONTENT_LENGTH'] = original
    assert response.status_code == 413
    assert 'too large' in response.get_json()['error'].lower()


def test_safe_upload_filename_strips_paths():
    assert webapp.safe_upload_filename('../../evil.sql') == 'evil.sql'
    assert webapp.safe_upload_filename(r'..\..\evil.sql') == 'evil.sql'
    assert webapp.safe_upload_filename('..') == ''
    assert webapp.safe_upload_filename('.') == ''
    assert webapp.safe_upload_filename('数据库.sql') == '数据库.sql'


def test_safe_upload_filename_neutralizes_shell_metacharacters():
    cleaned = webapp.safe_upload_filename('evil`whoami`;$(id).sql')
    for char in ('`', '$', ';'):
        assert char not in cleaned
    assert cleaned.endswith('.sql')


def test_safe_upload_filename_preserves_long_extension():
    cleaned = webapp.safe_upload_filename('a' * 400 + '.sql')
    assert cleaned.endswith('.sql')
    assert len(cleaned) <= 200


def test_invalid_wordpress_version_is_rejected_on_create():
    response = make_client().post('/api/create-project', data={
        'project_name': 'smoke-test-invalid',
        'wordpress_version': 'latest\n    privileged: true',
    })
    assert response.status_code == 400
    assert 'version' in response.get_json()['error'].lower()


def test_invalid_wordpress_version_is_rejected_on_update():
    response = make_client().post(
        '/api/projects/not-a-project/update-wordpress-version',
        json={'version': 'latest\n    privileged: true'},
    )
    assert response.status_code == 400
    assert 'version' in response.get_json()['error'].lower()


def test_fix_upload_limits_missing_project_returns_400():
    response = make_client().post('/api/fix-upload-limits/not-a-project')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Project not found'
