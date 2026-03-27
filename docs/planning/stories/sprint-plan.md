# Sprint Plan: Infrastructure Hardening

**Goal**: Eliminate the three classes of production-grade failures — runtime crashes,
broken Docker Compose compatibility on modern systems, and port conflicts that prevent
running multiple projects simultaneously — while clearing accumulated code quality debt.

**Duration**: 1 sprint (estimated 3-5 focused agent sessions)
**Requirements source**: `docs/planning/requirements/infrastructure-hardening.md`
**Architecture decisions**: ADR-001 (port allocation), ADR-002 (docker-compose detection)

---

## Story Map

### Must Have (P0) — blocking production use

| # | Story | Effort | Dependencies | Requirements |
|---|-------|--------|-------------|-------------|
| S-1 | Fix Runtime Crashes (fix_php_upload_limits + created_at) | XS | None | R1, R2 |
| S-2 | Create Docker Compose Detection Module | S | None | R4 |
| S-3 | Migrate docker-compose Calls — Core Files | M | S-2 | R4 |
| S-5 | Unique Port Allocation Per Project | L | None | R3 |

### Should Have (P1) — significant usability or stability improvement

| # | Story | Effort | Dependencies | Requirements |
|---|-------|--------|-------------|-------------|
| S-4 | Migrate docker-compose — Makefile Templates and app.py Startup | S | S-2, S-3 | R4 |
| S-6 | Add Timeouts to All Subprocess Calls | S | S-3 | R5 |
| S-7 | Fix HostsManager to Surface Warnings to UI | S | None | R8 |

### Nice to Have (P2) — code quality and low-risk fixes

| # | Story | Effort | Dependencies | Requirements |
|---|-------|--------|-------------|-------------|
| S-8 | Cross-Platform and Deprecation Fixes | S | None | R9, R10, R11, R12 |
| S-9 | Remove Duplicate Validation and Unused Imports from app.py | S | S-4, S-8 (same file, coordinate) | R6, R7 |

---

## Dependency Graph

```
S-1  (standalone — touches only project_manager.py)
S-2  (standalone — new file only)
S-5  (standalone — new file + docker_manager.py + project_manager.py)
S-7  (standalone — hosts_manager.py + project_manager.py + app.py)
S-8  (standalone — 5 files, no cross-story deps)

S-2 --> S-3 --> S-4
              S-3 --> S-6

S-4, S-8 --> S-9   (coordinate: all touch app.py)
```

### Critical path
**S-2 → S-3 → S-4** is the longest sequential chain and gates the Docker Compose v2
compatibility fix. S-3 is the heaviest story (10 call sites in docker_manager.py alone).
Start S-2 first.

### Parallelism opportunities
These stories have no mutual dependencies and touch disjoint files — they can be
assigned to separate agents simultaneously:
- **S-1** (project_manager.py only)
- **S-2** (new file)
- **S-5** (new file + docker_manager.py + project_manager.py — but note S-5 and S-3 both modify docker_manager.py; sequence S-3 before S-5 or merge into one pass)
- **S-7** (hosts_manager.py)
- **S-8** (database_manager.py, ssl_generator.py, project_manager.py, config_manager.py, app.py — none overlap with S-1 or S-2)

**Important sequencing constraint:** S-3 and S-5 both modify `docker_manager.py` and
`project_manager.py`. Do not run them in parallel. Complete S-3 first, then S-5.
Alternatively, a single agent can implement both in one pass.

---

## File Ownership Map

| File | Stories that modify it |
|------|----------------------|
| `utils/project_manager.py` | S-1, S-3, S-5, S-7, S-8 |
| `utils/docker_manager.py` | S-3, S-5, S-6, S-8 |
| `utils/database_manager.py` | S-3 (via compose_command import), S-6, S-8 |
| `utils/config_manager.py` | S-4, S-8 |
| `utils/hosts_manager.py` | S-7 |
| `utils/ssl_generator.py` | S-8 |
| `app.py` | S-4, S-7, S-8, S-9 |
| `utils/docker_compose_detect.py` | S-2 (creates) |
| `utils/port_allocator.py` | S-5 (creates) |

Recommended agent assignment order to avoid conflicts:
1. **Agent A**: S-2 (new file, no conflicts possible)
2. **Agent B** (parallel with A): S-1, S-7, S-8 (non-overlapping files within this set)
3. **Agent C** (after S-2): S-3, then S-6 (S-6 depends on S-3 touching the same lines)
4. **Agent D** (after S-3): S-5 (shares docker_manager.py with S-3)
5. **Agent E** (after S-3, S-8): S-4, then S-9

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| S-3 and S-5 conflict on docker_manager.py | High (if parallelised) | Medium | Sequence S-3 before S-5. Enforce in agent assignment. |
| Port allocation breaks update_domain (which calls create_docker_compose again) | Medium | High | S-5 notes this edge case — the implementer must read the existing port_index from config and pass it back. |
| compose_command() import causes circular import | Low | Medium | No circular dependency exists; docker_compose_detect.py imports only stdlib modules. |
| Removing validate_and_repair_database (S-9) breaks upload endpoint | Medium | High | Verify the upload endpoint path in app.py before deleting. DatabaseManager already handles all repair cases. |
| 600s DB timeout (S-6) is too long for UI | Low | Low | The import endpoint is async-ish from the user's POV (the UI polls). A very long import is still better than a hung thread. |

---

## Definition of Done (Sprint-level)

- [ ] All P0 stories (S-1, S-2, S-3, S-5) merged and manually smoke-tested
- [ ] P1 stories (S-4, S-6, S-7) merged
- [ ] No remaining `'docker-compose'` string literals in Python subprocess call sites (grep check)
- [ ] No bare `except:` clauses in `project_manager.py`, `config_manager.py`, `docker_manager.py`
- [ ] A new project can be created and started when Docker Compose v2 is the only binary available
- [ ] Two projects can be started simultaneously without port conflicts (spot-check with two projects)
- [ ] `POST /api/fix-upload-limits/<name>` returns HTTP 200 (was HTTP 500 before S-1)
- [ ] P2 stories (S-8, S-9) merged before sprint close
- [ ] No new lint or type errors introduced (run `python -m py_compile` on all modified files)

---

## Story File Index

| File | Story |
|------|-------|
| `docs/planning/stories/S-1-fix-runtime-crashes.md` | R1 + R2 |
| `docs/planning/stories/S-2-docker-compose-detection-module.md` | R4 (module) |
| `docs/planning/stories/S-3-migrate-docker-compose-calls-core.md` | R4 (call sites) |
| `docs/planning/stories/S-4-migrate-docker-compose-makefile-and-startup.md` | R4 (Makefile + startup) |
| `docs/planning/stories/S-5-unique-port-allocation.md` | R3 |
| `docs/planning/stories/S-6-subprocess-timeouts.md` | R5 |
| `docs/planning/stories/S-7-fix-hosts-manager-surface-warnings.md` | R8 |
| `docs/planning/stories/S-8-cross-platform-and-deprecation-fixes.md` | R9, R10, R11, R12 |
| `docs/planning/stories/S-9-remove-duplicate-validation-and-unused-imports.md` | R6, R7 |
