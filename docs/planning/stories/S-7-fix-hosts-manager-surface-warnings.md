# S-7: Fix HostsManager to Surface Warnings to the UI

## Priority: Medium
## Effort: S
## Dependencies: None (can run in parallel with all other stories)
## Files:
- `utils/hosts_manager.py`
- `utils/project_manager.py`
- `app.py`

## Description

`HostsManager.add_host()` silently does nothing on Unix (macOS/Linux). The `_add_host_unix()`
method prints instructions to the server console but returns without modifying the hosts file
(the actual `sudo` call is commented out to avoid blocking the web server with a password prompt).
The caller — `project_manager.create_project()` line 116 — receives `True` regardless
and treats this as a success.

The result: a project is created, containers start, but the domain
`local.PROJECT.test` does not resolve because no hosts entry was added. The user sees
a "site not found" error with no explanation.

The fix is a structured return value from `add_host()` that distinguishes between
"entry added automatically" and "manual action required". The caller can then include
this information in the project creation response, so the UI can show a banner like:
"Project created — add this line to /etc/hosts to access your site."

### Changes to `utils/hosts_manager.py`

Change `add_host()` return type from `bool` to `dict`:

```python
def add_host(self, domain, ip="127.0.0.1") -> dict:
    """
    Returns:
        {
            'success': bool,
            'modified': bool,          # True if the hosts file was actually written
            'manual_action_required': bool,  # True if the user must edit manually
            'instruction': str | None  # Shell command to run, if manual action needed
        }
    """
```

For the Unix path (`_add_host_unix`), return:
```python
{
    'success': True,
    'modified': False,
    'manual_action_required': True,
    'instruction': f"echo '{ip}\t{domain}' | sudo tee -a /etc/hosts"
}
```

For the Windows path, if the PowerShell call succeeds:
```python
{'success': True, 'modified': True, 'manual_action_required': False, 'instruction': None}
```

If the entry already exists, return:
```python
{'success': True, 'modified': False, 'manual_action_required': False, 'instruction': None}
```

### Changes to `utils/project_manager.py`

`create_project()` currently ignores the return value of `add_host()`. Update it to
capture the result and include the hosts instruction in the returned config when
`manual_action_required` is True:

```python
hosts_result = self.hosts_manager.add_host(domain.split('/')[0])
if hosts_result.get('manual_action_required'):
    config['hosts_instruction'] = hosts_result.get('instruction')
```

Include `hosts_instruction` in the success response returned from `create_project()`.

### Changes to `app.py`

The `create_project` endpoint (around line 200) already returns
`jsonify({'success': True, 'project': config})`. The `hosts_instruction` key in `config`
will automatically flow through to the JSON response. No explicit change needed in the
endpoint handler, but verify the response does include the field when it is present.

## Acceptance Criteria

- [ ] Given a new project is created on macOS or Linux, when `add_host()` is called, then it returns a dict with `manual_action_required: true` and a non-empty `instruction` string.
- [ ] Given `add_host()` returns `manual_action_required: true`, when `create_project()` completes, then the returned dict contains `hosts_instruction` with the sudo command.
- [ ] Given the API `POST /api/create-project` response, then the JSON body includes `hosts_instruction` when running on Unix.
- [ ] Given a domain that already exists in the hosts file, when `add_host()` is called, then `manual_action_required` is `false` and `modified` is `false`.
- [ ] Given the `remove_host()` method, then it is NOT changed (its return type stays as-is).
- [ ] Existing callers of `add_host()` that only check truthiness (e.g. `if add_host(...)`) still work correctly because a non-empty dict is truthy.
- [ ] No existing test behaviour is broken.

## Implementation Notes

- The `add_host()` callers in `project_manager.py` include `update_domain()` (line 370).
  That call also ignores the return value. Update it the same way — capture the result and
  include `hosts_instruction` in the `update_domain` response dict.
- `remove_host()` does not need a dict return type. It still returns `True`/`False`.
- The `instruction` string for Unix should be the exact command the user can copy-paste
  into their terminal: `echo '127.0.0.1\tlocal.myproject.test' | sudo tee -a /etc/hosts`
- On Windows, `_add_host_windows()` uses PowerShell with UAC elevation. If the call
  succeeds, `modified=True`. If it falls back to the direct write (the `except` clause),
  also set `modified=True`. On Windows there is no `manual_action_required` scenario
  in the current implementation.
- Do not attempt to implement actual sudo-based hosts modification. The intentional
  choice to avoid blocking was correct; this story just adds visibility, not automation.
- Database migration: No.
- New environment variables: No.
- Breaking changes: `add_host()` return type changes from `bool` to `dict`. Any code
  that does `if add_host(...) == True` will break. Audit all callers. Currently there
  are two: `create_project()` and `update_domain()` — both ignore the return value,
  so no breakage.
