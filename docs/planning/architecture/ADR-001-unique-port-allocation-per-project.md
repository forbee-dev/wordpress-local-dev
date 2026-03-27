# ADR-001: Unique Port Allocation Per Project

**Date:** 2026-03-27
**Status:** Proposed
**Decision Makers:** Project maintainers
**Technical Story:** All WordPress projects share identical port mappings (80, 443, 3306, 8080, 6379), preventing multiple projects from running simultaneously.

---

## Context

The WordPress Local Development Environment creates Docker Compose stacks for each project. Today, every project's `.env` file contains identical port mappings:

```
HTTP_PORT=80
HTTPS_PORT=443
MYSQL_PORT=3306
PHPMYADMIN_PORT=8080
REDIS_PORT=6379
```

This means only one project can have its containers running at a time. Starting a second project either fails with "port already in use" errors or silently steals the port from the first project. With 10 existing projects in production use (AffiliationCloud, bijoumysterybox, casimaru, casinobonukset, casinotop5, meetup, oncasitown, turtlebet, tvmatchen), this is a real operational pain point.

### Constraints

- Projects are created via the web UI at `localhost:5001` -- users must not need to manually choose ports.
- Existing projects (10 of them) already have `.env` files with hardcoded ports; they must continue working without forced migration.
- Port ranges should be predictable so developers can easily find phpMyAdmin, MySQL, etc. for any given project.
- Five ports per project: HTTP, HTTPS, MySQL, phpMyAdmin, Redis.
- Ports must not collide with the application itself (port 5001) or common system services.
- The system runs on macOS (primary), Linux, and Windows.

---

## Options Considered

### Option A: Do Nothing

Keep the current behavior. Only one project runs at a time.

**Pros:**
- Zero implementation effort.
- No migration risk.

**Cons:**
- Developers must stop one project before starting another -- a workflow killer when working across projects.
- Root cause of the most common user complaint.
- Scales poorly as project count grows.

**Complexity:** None (status quo)

### Option B: Sequential Port Blocks Based on Project Index

Assign each project a numeric index (1, 2, 3...) at creation time. Compute ports as a deterministic function of that index using a base offset and stride.

**Port scheme:**
```
Base offset: 10000
Stride per project: 10 ports (leaves room for future services)
Project index: stored in config.json as "port_index"

HTTP_PORT     = 10000 + (index * 10) + 0   (project 1 = 10010, project 2 = 10020)
HTTPS_PORT    = 10000 + (index * 10) + 1   (project 1 = 10011, project 2 = 10021)
MYSQL_PORT    = 10000 + (index * 10) + 2   (project 1 = 10012, project 2 = 10022)
PHPMYADMIN_PORT = 10000 + (index * 10) + 3 (project 1 = 10013, project 2 = 10023)
REDIS_PORT    = 10000 + (index * 10) + 4   (project 1 = 10014, project 2 = 10024)
```

**Pros:**
- Fully deterministic -- knowing the index is enough to compute all ports.
- Predictable pattern: once you know "project X is index 3", you know all its ports.
- No external state file needed beyond config.json per project.
- 10-port stride leaves headroom for adding services (Mailhog, Elasticsearch, etc.).

**Cons:**
- Ports like 10012 are not particularly memorable.
- If a project is deleted and re-created, index reuse must be handled carefully.
- Requires scanning all projects to find the next available index.

**Complexity:** Low-Medium

### Option C: Named Port Ranges with a Global Registry

Maintain a central `port-registry.json` file in the `wordpress-projects/` directory that maps project names to allocated port blocks. Each block is a contiguous range of 10 ports.

**Port scheme:**
```
Range: 10000-10999 (room for 100 projects)
Block size: 10
Allocation: first-fit from registry

port-registry.json:
{
  "next_block": 3,
  "allocations": {
    "tvmatchen": {"block": 1, "http": 10010, "https": 10011, ...},
    "meetup": {"block": 2, "http": 10020, "https": 10021, ...}
  }
}
```

**Pros:**
- Central source of truth prevents collisions even across concurrent operations.
- Easy to inspect: one file shows all port assignments.
- Supports port reclamation when projects are deleted.

**Cons:**
- Introduces a shared mutable file -- needs locking or atomic writes for safety.
- Extra file to maintain and keep in sync.
- If the registry is lost/corrupted, ports must be rebuilt from individual `.env` files.

**Complexity:** Medium

### Option D: Hash-Based Port Derivation from Project Name

Derive ports deterministically from the project name using a hash function, mapped into a port range.

```python
import hashlib
def get_port_block(project_name):
    h = int(hashlib.md5(project_name.encode()).hexdigest(), 16)
    block = (h % 90) + 1  # blocks 1-90, ports 10010-10909
    return block
```

**Pros:**
- No state file needed -- ports are always computable from the name alone.
- No sequential scanning.

**Cons:**
- Hash collisions are possible and must be handled (two project names mapping to the same block).
- Non-obvious mapping makes debugging harder ("why is meetup on port 10473?").
- Collision resolution reintroduces state management, negating the main benefit.

**Complexity:** Medium (due to collision handling)

---

## Decision Matrix

| Criteria              | A: Do Nothing | B: Sequential Blocks | C: Global Registry | D: Hash-Based |
|-----------------------|:---:|:---:|:---:|:---:|
| Scalability           | 1/5 | 4/5 | 5/5 | 4/5 |
| Maintainability       | 5/5 | 4/5 | 3/5 | 2/5 |
| Implementation speed  | 5/5 | 4/5 | 3/5 | 3/5 |
| Predictability        | 5/5 | 4/5 | 5/5 | 1/5 |
| Robustness            | 1/5 | 4/5 | 3/5 | 2/5 |
| Migration simplicity  | 5/5 | 4/5 | 3/5 | 4/5 |
| **Weighted Total**    | **3.3** | **4.0** | **3.5** | **2.7** |

---

## Recommendation

**Option B: Sequential Port Blocks Based on Project Index** -- with the Global Registry concept from Option C used as a lightweight enhancement.

### Rationale

Option B offers the best balance of simplicity, predictability, and robustness. The core insight is that a local development tool managing at most a few dozen projects does not need the sophistication of a hash-based allocator or a heavyweight registry. A simple monotonic counter stored per-project is sufficient.

However, we borrow one idea from Option C: on startup and during project creation, scan all existing project `.env` files to build an in-memory index of allocated ports. This eliminates the need for a separate registry file while still preventing collisions.

### Why Not the Others

- **Option A (Do Nothing):** Unacceptable -- this is the number one usability issue.
- **Option C (Global Registry):** The shared file introduces a coordination problem that does not pay for itself at this scale. The per-project `.env` already serves as the source of truth.
- **Option D (Hash-Based):** Collision handling complexity and poor debuggability outweigh the "no state" benefit, especially since we already have per-project state in `.env`.

---

## Detailed Design

### Port Allocation Scheme

```
Base: 10000
Stride: 10 (ports per project block)
Maximum projects: 99 (ports 10010 through 10999)

Project Index 1:  HTTP=10010, HTTPS=10011, MySQL=10012, phpMyAdmin=10013, Redis=10014
Project Index 2:  HTTP=10020, HTTPS=10021, MySQL=10022, phpMyAdmin=10023, Redis=10024
Project Index N:  HTTP=10000+(N*10), HTTPS=10000+(N*10)+1, ...
```

Port offsets within a block:
| Offset | Service     | Container Port |
|--------|-------------|----------------|
| +0     | HTTP        | 80             |
| +1     | HTTPS       | 443            |
| +2     | MySQL       | 3306           |
| +3     | phpMyAdmin  | 80             |
| +4     | Redis       | 6379           |
| +5..+9 | (reserved)  | future use     |

### Where to Store Port Index

The `port_index` integer is stored in each project's `config.json`:

```json
{
  "name": "tvmatchen",
  "port_index": 1,
  "ports": {
    "http": 10010,
    "https": 10011,
    "mysql": 10012,
    "phpmyadmin": 10013,
    "redis": 10014
  },
  ...
}
```

The `.env` file continues to be the runtime source of truth (Docker Compose reads it). The `config.json` stores the canonical index for reconstruction.

### Implementation: New PortAllocator Utility

Create `utils/port_allocator.py`:

```python
class PortAllocator:
    """Manages unique port allocation for WordPress projects"""

    BASE_PORT = 10000
    PORTS_PER_PROJECT = 10
    MAX_PROJECTS = 99

    SERVICE_OFFSETS = {
        'http': 0,
        'https': 1,
        'mysql': 2,
        'phpmyadmin': 3,
        'redis': 4,
    }

    def __init__(self, projects_dir):
        self.projects_dir = projects_dir

    def get_ports_for_index(self, index):
        """Compute all port mappings for a given project index"""
        base = self.BASE_PORT + (index * self.PORTS_PER_PROJECT)
        return {
            'HTTP_PORT': base + self.SERVICE_OFFSETS['http'],
            'HTTPS_PORT': base + self.SERVICE_OFFSETS['https'],
            'MYSQL_PORT': base + self.SERVICE_OFFSETS['mysql'],
            'PHPMYADMIN_PORT': base + self.SERVICE_OFFSETS['phpmyadmin'],
            'REDIS_PORT': base + self.SERVICE_OFFSETS['redis'],
        }

    def get_used_indices(self):
        """Scan all projects to find which indices are in use"""
        used = set()
        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            config_file = project_dir / 'config.json'
            if config_file.exists():
                config = json.load(open(config_file))
                idx = config.get('port_index')
                if idx is not None:
                    used.add(idx)
        return used

    def allocate_next_index(self):
        """Find and return the next available project index"""
        used = self.get_used_indices()
        for i in range(1, self.MAX_PROJECTS + 1):
            if i not in used:
                return i
        raise RuntimeError("Maximum project count reached (99)")

    def is_port_available(self, port):
        """Check if a specific port is available on the system"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) != 0
```

### Changes to Existing Files

**`utils/docker_manager.py` -- `create_docker_compose()` method (lines 347-362):**
- Accept a `ports` dict parameter instead of hardcoding port values.
- Write the allocated ports to `.env` instead of fixed 80/443/3306/8080/6379.

**`utils/project_manager.py` -- `create_project()` method:**
- Instantiate `PortAllocator`, call `allocate_next_index()`.
- Compute ports via `get_ports_for_index(index)`.
- Store `port_index` and `ports` in `config.json`.
- Pass ports to `docker_manager.create_docker_compose()`.

**`utils/config_manager.py` -- `create_readme()` and `create_makefile()`:**
- Reference `${PHPMYADMIN_PORT}` variable instead of hardcoded `8080`.

**`templates/index.html` and `static/js/app.js`:**
- Display allocated ports in the project card/detail view.
- Show "phpMyAdmin: http://localhost:10013" etc.

**`app.py` -- project list and status endpoints:**
- Include port information in API responses so the UI can display access URLs.

### Backward Compatibility: Existing Projects

Existing projects keep their current `.env` with ports 80/443/3306/8080/6379. They will continue to work exactly as before -- they simply will not have a `port_index` in `config.json`.

When `get_used_indices()` scans projects without a `port_index`, it skips them. This means new projects will get indices starting from 1.

A **voluntary migration command** (`/api/projects/<name>/migrate-ports`) can be added later to assign an index to an existing project, rewrite its `.env`, and restart its containers. This is not required for the initial implementation.

If an existing project (on port 80) and a new project (on port 10010) both run simultaneously, there is no conflict because they use entirely different port ranges.

### Collision Handling

1. **Index collision:** Prevented by scanning all `config.json` files before allocation.
2. **System port collision:** After computing ports from the index, optionally verify with `is_port_available()`. If a computed port is occupied by a non-project process, log a warning but proceed (Docker will report the actual error on `docker-compose up`).
3. **Deleted project reuse:** When a project is deleted, its index becomes available. `allocate_next_index()` uses first-fit, so indices are reused in order.

---

## Implementation Roadmap

### Phase 1: Core Port Allocation (~1-2 days)
1. Create `utils/port_allocator.py` with the `PortAllocator` class.
2. Modify `DockerManager.create_docker_compose()` to accept a `ports` dict.
3. Modify `ProjectManager.create_project()` to allocate ports via `PortAllocator`.
4. Store `port_index` and `ports` in `config.json`.
5. Verify new projects get unique ports and can run simultaneously.

### Phase 2: UI Integration (~1 day)
1. Add port information to API responses (`/api/projects`).
2. Display per-project access URLs (HTTP, HTTPS, phpMyAdmin) in the web interface.
3. Update project cards to show "phpMyAdmin: localhost:10013" instead of hardcoded 8080.

### Phase 3: Migration Tool (~0.5 days)
1. Add `/api/projects/<name>/migrate-ports` endpoint.
2. Add "Migrate All Projects" bulk action.
3. Migration: allocate index, rewrite `.env`, restart containers.

### Phase 4: Polish (~0.5 days)
1. Add port information to generated `README.md` and `Makefile`.
2. Add startup validation: warn if allocated ports are occupied by external processes.
3. Document the port scheme in project README.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Port range conflicts with other local services | Low | Medium | Base at 10000 avoids common services. Startup check warns if ports are in use. |
| Existing projects break during migration | Low | High | Migration is voluntary and opt-in. Existing `.env` files are untouched by default. |
| config.json corruption loses port_index | Low | Medium | Ports can be reconstructed from `.env` file. Add a `rebuild-port-index` utility. |
| 99-project limit reached | Very Low | Low | Increase `MAX_PROJECTS` and adjust stride. At this scale, consider a different architecture. |
| Two concurrent create requests race on index allocation | Low | Medium | File-based locking around `allocate_next_index()`, or Python threading lock since Flask runs single-threaded by default. |

---

## Consequences

**Positive:**
- Multiple WordPress projects can run simultaneously for the first time.
- Each project gets a predictable, unique set of ports.
- No breaking changes to existing projects.
- Port scheme leaves room for future services.

**Negative:**
- Developers must remember project-specific port numbers (mitigated by UI display).
- HTTP/HTTPS no longer on standard ports 80/443 (mitigated by nginx reverse proxy pattern, or by keeping the domain-based access via hosts file and port 80/443 for the "primary" active project).
- Slight increase in codebase complexity with new `PortAllocator` class.

**Neutral:**
- Existing projects continue working on their current ports until voluntarily migrated.

---

## ADR Record

**Decision:** Assign each new project a sequential index (1..99) and derive five unique ports from it using a base offset of 10000 and a stride of 10. Store the index in `config.json`; write computed ports to `.env`. Existing projects are unaffected until voluntarily migrated.

**Status:** Proposed

**Consequences:** Multiple projects can run simultaneously. New projects will be accessible on non-standard ports (e.g., `https://local.project.test:10011`). The web UI must display per-project port information clearly.
