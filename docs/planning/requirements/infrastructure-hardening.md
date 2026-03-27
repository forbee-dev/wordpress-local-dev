# Requirements: Infrastructure Hardening

## R1: Fix Runtime Crash — fix_php_upload_limits
- **Priority:** High
- **File:** `app.py:618`, `utils/project_manager.py:701-704`
- **Issue:** `fix_php_upload_limits` is called from app.py but method is commented out in ProjectManager
- **Fix:** Add the method back (returning success since limits are auto-configured)

## R2: Fix created_at Metadata
- **Priority:** High
- **File:** `utils/project_manager.py:110`
- **Issue:** `created_at` stores `str(Path().resolve())` (CWD) instead of a timestamp
- **Fix:** Use `datetime.datetime.now().isoformat()`

## R3: Unique Port Allocation Per Project
- **Priority:** High
- **Files:** `utils/docker_manager.py` (create_docker_compose, .env generation)
- **Issue:** All projects use ports 80/443/3306/8080/6379 — only one can run
- **Fix:** Allocate unique port ranges per project. Strategy: base port from project index or hash. Store assigned ports in config.json.

## R4: Docker Compose v2 Migration
- **Priority:** Medium
- **Files:** All files using `docker-compose` command
- **Issue:** `docker-compose` (v1) is deprecated. Modern Docker uses `docker compose` (v2 plugin)
- **Fix:** Create a helper that detects available command and uses the right one. Replace all subprocess calls.

## R5: Add Subprocess Timeouts
- **Priority:** Medium
- **Files:** `utils/docker_manager.py`, `utils/database_manager.py`
- **Issue:** Several subprocess.run calls have no timeout — can block indefinitely
- **Fix:** Add timeout parameter to all subprocess calls (30s for status, 120s for operations, 600s for imports)

## R6: Remove Duplicated Validation Logic
- **Priority:** Low
- **File:** `app.py:41-140`
- **Issue:** `validate_and_repair_database` and `repair_database_file` duplicate DatabaseManager logic
- **Fix:** Remove from app.py and use DatabaseManager methods instead

## R7: Clean Unused Imports
- **Priority:** Low
- **File:** `app.py:1-12`
- **Issue:** `subprocess`, `platform`, `yaml`, `send_from_directory` imported but unused
- **Fix:** Remove them

## R8: Fix Hosts Manager to Surface Warnings
- **Priority:** Medium
- **File:** `utils/hosts_manager.py`
- **Issue:** `add_host` returns True on Unix even though it doesn't modify anything
- **Fix:** Return a result dict with `success` and `manual_action_required` flag so the UI can inform the user

## R9: Fix date Command in Backup (Cross-Platform)
- **Priority:** Medium
- **File:** `utils/database_manager.py:208`
- **Issue:** Uses shell `date` command (fails on Windows)
- **Fix:** Use `datetime.now().strftime('%Y%m%d_%H%M%S')`

## R10: Deprecation Warning — datetime.utcnow()
- **Priority:** Low
- **File:** `utils/ssl_generator.py:166-168`
- **Fix:** Use `datetime.datetime.now(datetime.timezone.utc)`

## R11: Hardcoded Flask Secret Key
- **Priority:** Low
- **File:** `app.py:18`
- **Fix:** Generate random key at startup with `os.urandom(24).hex()`

## R12: Bare except Clauses
- **Priority:** Low
- **Files:** `utils/project_manager.py:153,640,680`, `utils/config_manager.py:246,265`
- **Fix:** Replace with `except Exception as e:` and log the error
