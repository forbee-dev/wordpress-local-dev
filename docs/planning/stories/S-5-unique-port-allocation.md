# S-5: Unique Port Allocation Per Project

## Priority: High
## Effort: L
## Dependencies: None (can run in parallel with S-2, S-3, S-4)
## Files:
- `utils/port_allocator.py` (new file)
- `utils/docker_manager.py`
- `utils/project_manager.py`
- `utils/config_manager.py`

## Description

Every project currently receives the same five ports (HTTP=80, HTTPS=443, MySQL=3306,
phpMyAdmin=8080, Redis=6379) in its `.env` file. Only one project can run at a time;
starting a second project causes Docker to fail with "port already in use" — the most
common operational complaint from users of this tool.

This story implements the port allocation strategy specified in
`docs/planning/architecture/ADR-001-unique-port-allocation-per-project.md`:
sequential port blocks derived from a per-project integer index, starting at base 10000
with a stride of 10.

**Port scheme:**
```
Project Index N: HTTP = 10000 + (N*10), HTTPS = +1, MySQL = +2, phpMyAdmin = +3, Redis = +4
Project 1:  HTTP=10010, HTTPS=10011, MySQL=10012, phpMyAdmin=10013, Redis=10014
Project 2:  HTTP=10020, HTTPS=10021, MySQL=10022, phpMyAdmin=10023, Redis=10024
```

**Backward compatibility:** Existing projects keep their current `.env` files
(ports 80/443/3306/8080/6379). They have no `port_index` in `config.json` and
continue working. New projects always get unique high-numbered ports.

### New file: `utils/port_allocator.py`

Create a `PortAllocator` class with:

- `BASE_PORT = 10000`, `PORTS_PER_PROJECT = 10`, `MAX_PROJECTS = 99`
- `SERVICE_OFFSETS = {'http': 0, 'https': 1, 'mysql': 2, 'phpmyadmin': 3, 'redis': 4}`
- `get_ports_for_index(index) -> dict` — Returns the port mapping dict for a given index.
- `get_used_indices() -> set` — Scans all project `config.json` files for existing `port_index` values.
- `allocate_next_index() -> int` — First-fit from 1..MAX_PROJECTS avoiding used indices.
- `is_port_available(port) -> bool` — Socket check on 127.0.0.1 (advisory only, not blocking).

Full class design is in ADR-001. The code shown there can be used as the starting point.

### Changes to `utils/docker_manager.py` — `create_docker_compose()`

The method currently generates `.env` with hardcoded port values:
```
HTTP_PORT=80
HTTPS_PORT=443
MYSQL_PORT=3306
PHPMYADMIN_PORT=8080
REDIS_PORT=6379
```

Add an optional `ports` parameter:
```python
def create_docker_compose(self, project_path, project_name, wordpress_version,
                          domain, enable_ssl, enable_redis, ports=None):
```

When `ports` is provided (a dict with keys `HTTP_PORT`, `HTTPS_PORT`, `MYSQL_PORT`,
`PHPMYADMIN_PORT`, `REDIS_PORT`), write those values to `.env`. When `ports` is `None`
(backward-compatible default), use the existing hardcoded values. This keeps all
existing callers that do not yet pass ports working without changes.

### Changes to `utils/project_manager.py` — `create_project()`

Before calling `docker_manager.create_docker_compose()`, instantiate `PortAllocator`
and allocate ports:

```python
from utils.port_allocator import PortAllocator

allocator = PortAllocator(self.projects_dir)
port_index = allocator.allocate_next_index()
ports = allocator.get_ports_for_index(port_index)
```

Store `port_index` and `ports` in the config dict before saving:
```python
config['port_index'] = port_index
config['ports'] = ports
```

Pass `ports` to `create_docker_compose()`:
```python
self.docker_manager.create_docker_compose(
    project_path, project_name, wordpress_version,
    domain, enable_ssl, enable_redis, ports=ports
)
```

### Changes to `utils/config_manager.py` — `create_makefile()`

The `start` target in the Makefile prints the phpMyAdmin URL with a hardcoded port 8080:
```makefile
@echo "phpMyAdmin is running at: http://localhost:${PHPMYADMIN_PORT}"
```

This already uses the env variable `${PHPMYADMIN_PORT}`, so no change is strictly needed
for the Makefile to show the correct port at runtime. However, confirm the variable
reference is consistent with the `.env` file key name — it should be.

No other changes needed in `config_manager.py` for this story.

## Acceptance Criteria

- [ ] Given a first project is created, then its `config.json` contains `"port_index": 1` and `"ports": {"HTTP_PORT": 10010, "HTTPS_PORT": 10011, "MySQL_PORT": 10012, "PHPMYADMIN_PORT": 10013, "REDIS_PORT": 10014}`.
- [ ] Given a first project is created, then its `.env` file contains `HTTP_PORT=10010` (not `80`).
- [ ] Given a second project is created, then it receives `port_index: 2` and ports starting at 10020.
- [ ] Given two projects exist with indices 1 and 2, when a third project is created, then it receives index 3 (no collision).
- [ ] Given a project is deleted and its index freed, when a new project is created, then the freed index is reused (first-fit).
- [ ] Given both projects are started, then Docker does not error with "port already in use".
- [ ] Given an existing project (no `port_index` in config.json), when the application runs, then it continues to work on its current ports (no forced migration).
- [ ] Given `allocate_next_index()` is called when all 99 indices are used, then it raises `RuntimeError`.
- [ ] `PortAllocator` can be instantiated with any `Path` and does not require Docker to be running.

## Implementation Notes

- `get_used_indices()` must handle `config.json` files that do not have a `port_index` key
  (existing projects) gracefully — skip them with `config.get('port_index')`.
- The `ports` dict keys written to `.env` must match exactly what the `docker-compose.yml`
  template references (`${HTTP_PORT}`, `${HTTPS_PORT}`, etc.). Verify by inspecting the
  existing `.env` template in `create_docker_compose()`.
- Concurrent project creation race: Flask's development server is single-threaded.
  Production WSGI servers (gunicorn) may use multiple workers but project creation is
  a rare operation. For now, no file lock is required. A threading lock can be added
  in a follow-up if needed.
- `is_port_available()` is advisory: if a port is in use by an unrelated process, log a
  warning but still proceed. Docker will report the real error at `docker-compose up` time.
- The `update_domain` path in `project_manager.py` calls `create_docker_compose()` again.
  It does not yet pass ports. That call must read the existing `port_index` from config
  and pass the correct ports dict, otherwise it will overwrite the `.env` with default
  ports 80/443. Fix this within this story:
  ```python
  existing_ports = allocator.get_ports_for_index(config['port_index']) if config.get('port_index') else None
  self.docker_manager.create_docker_compose(..., ports=existing_ports)
  ```
- Database migration: No.
- New environment variables: No.
- Breaking changes: None for existing projects. New projects will use non-standard ports;
  the web UI update (displaying these ports) is a separate story (S-9).
