# Problem Brief: Infrastructure Hardening

## Context
The WordPress Local Dev Environment is a Flask-based tool for managing local WordPress projects via Docker. A full code review surfaced 18 issues across security, architecture, functionality, and reliability.

## Problem Statement
The infrastructure has several bugs and design gaps that limit usability (only one project can run at a time due to port collisions), cause runtime crashes (`fix_php_upload_limits` AttributeError), store wrong metadata (`created_at` saves CWD), and use deprecated tooling (`docker-compose` v1).

## Goals
1. Fix all runtime-breaking bugs (crash, wrong data)
2. Enable multiple projects to run simultaneously (unique port allocation)
3. Migrate from deprecated `docker-compose` v1 to `docker compose` v2
4. Add missing subprocess timeouts to prevent hangs
5. Clean up duplicated code and unused imports
6. Improve reliability of database imports for large files

## Non-Goals
- Redesigning the web UI
- Adding new features
- Changing the modular architecture (it's good)
- WordPress project-level changes

## Success Criteria
- All 18 review items resolved
- Multiple projects can start simultaneously without port conflicts
- No runtime crashes on any API endpoint
- All subprocess calls have timeouts
