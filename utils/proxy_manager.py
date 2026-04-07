"""Shared reverse-proxy manager for WordPress Local Dev.

Manages a single nginx reverse-proxy container (``wp_local_proxy``) that
listens on ports 80/443 and routes traffic by ``Host`` header to the correct
project's per-project nginx container.

Lifecycle hooks:
    - ``on_project_start``  -- connect proxy to project network, write config, reload
    - ``on_project_stop``   -- remove config, disconnect network, reload
    - ``on_project_delete`` -- same as stop
    - ``regenerate_config`` -- rebuild all configs from project config.json files
"""

import json
import subprocess
import datetime
from pathlib import Path

from .docker_compose_detect import compose_command


class ProxyManager:
    """Manages the shared nginx reverse-proxy container."""

    PROXY_CONTAINER = "wp_local_proxy"

    def __init__(self, base_dir, projects_dir):
        self.base_dir = Path(base_dir)
        self.projects_dir = Path(projects_dir)
        self.proxy_dir = self.base_dir / "reverse-proxy"
        self.conf_dir = self.proxy_dir / "conf.d"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_proxy_running(self):
        """Start the shared proxy if not already running.

        Also verifies that host port bindings (80/443) are intact — Docker
        Desktop restarts can leave the container "running" but without the
        port mappings, making all sites unreachable.

        Returns True when the proxy is confirmed running, False on failure.
        """
        if not self.proxy_dir.exists():
            print("reverse-proxy/ directory not found")
            return False

        # Check if already running AND ports are bound
        needs_recreate = False
        already_running = False
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f",
                 "{{.State.Running}} {{(index (index .NetworkSettings.Ports \"80/tcp\") 0).HostPort}}",
                 self.PROXY_CONTAINER],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) >= 2 and parts[0] == "true" and parts[1]:
                    already_running = True
                elif parts[0] == "true":
                    # Running but ports not bound — needs recreate
                    print("Proxy is running but port bindings are lost — recreating...")
                    needs_recreate = True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Purge stale configs before (re)starting -- prevents nginx from
        # refusing to start when a project's containers are not running.
        self._purge_stale_configs()

        if already_running and not needs_recreate:
            return True

        # (Re)create it via docker compose up, which ensures correct port
        # bindings even when the container existed but lost its mappings.
        if needs_recreate:
            print("Recreating shared reverse proxy with port bindings...")
        else:
            print("Starting shared reverse proxy...")

        try:
            start = subprocess.run(
                compose_command("up", "-d", "--force-recreate") if needs_recreate
                else compose_command("up", "-d"),
                cwd=self.proxy_dir,
                capture_output=True, text=True, timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"Failed to start proxy: {exc}")
            return False

        if start.returncode == 0:
            print("Shared reverse proxy started on ports 80/443")
            # After (re)creating the proxy, reconnect to all running projects'
            # networks so their configs can resolve the upstream hostnames.
            self._reconnect_all_networks()
            return True

        print(f"Failed to start proxy: {start.stderr}")
        return False

    def regenerate_config(self):
        """Regenerate all proxy configs from project config.json files and reload nginx."""
        self.conf_dir.mkdir(parents=True, exist_ok=True)

        # Clear old configs
        for f in self.conf_dir.glob("*.conf"):
            f.unlink()

        # Generate one config per running project
        for project_dir in sorted(self.projects_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            config_file = project_dir / "config.json"
            if not config_file.exists():
                continue
            try:
                config = json.loads(config_file.read_text())
                project_name = config.get("name", project_dir.name)
                if self._is_project_running(project_dir):
                    self._write_project_conf(project_name, config)
            except Exception as exc:
                print(f"Skipping {project_dir.name}: {exc}")

        self._reload_nginx()

    def on_project_start(self, project_name, config):
        """Called after project containers start successfully."""
        self.ensure_proxy_running()

        # Connect proxy to the project's Docker network
        network_name = f"{project_name.lower()}_wordpress_network"
        try:
            result = subprocess.run(
                ["docker", "network", "connect", network_name, self.PROXY_CONTAINER],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if "already exists" not in stderr:
                    print(f"Warning: could not connect proxy to {network_name}: {stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"Warning: network connect failed for {network_name}: {exc}")

        # Write config for this project and reload
        self._write_project_conf(project_name, config)
        self._reload_nginx()

    def on_project_stop(self, project_name):
        """Called after project containers stop."""
        # Disconnect from the project network (may fail if network already gone)
        network_name = f"{project_name.lower()}_wordpress_network"
        try:
            subprocess.run(
                ["docker", "network", "disconnect", network_name, self.PROXY_CONTAINER],
                capture_output=True, text=True, timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Remove config and reload
        conf_file = self.conf_dir / f"{project_name}.conf"
        if conf_file.exists():
            conf_file.unlink()
        self._reload_nginx()

    def on_project_delete(self, project_name):
        """Called when a project is deleted (delegates to on_project_stop)."""
        self.on_project_stop(project_name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reconnect_all_networks(self):
        """Connect the proxy to every running project's Docker network.

        Called after proxy (re)creation to restore connectivity to projects
        that were already running before the proxy was recreated.
        """
        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            config_file = project_dir / "config.json"
            if not config_file.exists():
                continue
            if not self._is_project_running(project_dir):
                continue
            try:
                config = json.loads(config_file.read_text())
                project_name = config.get("name", project_dir.name)
                network_name = f"{project_name.lower()}_wordpress_network"
                subprocess.run(
                    ["docker", "network", "connect", network_name, self.PROXY_CONTAINER],
                    capture_output=True, text=True, timeout=15,
                )
            except Exception:
                pass

    def _purge_stale_configs(self):
        """Remove proxy configs for projects whose containers are not running.

        This prevents nginx from failing to start/reload when an upstream host
        (e.g. ``tvmatchen_nginx``) is unresolvable because its containers were
        stopped outside normal lifecycle hooks (crash, reboot, manual docker stop).
        """
        if not self.conf_dir.exists():
            return

        removed = []
        for conf_file in self.conf_dir.glob("*.conf"):
            project_name = conf_file.stem  # e.g. "tvmatchen" from "tvmatchen.conf"
            project_dir = self.projects_dir / project_name
            if not project_dir.is_dir() or not self._is_project_running(project_dir):
                conf_file.unlink()
                removed.append(project_name)

        if removed:
            print(f"Purged stale proxy configs: {', '.join(removed)}")
            self._reload_nginx()

    def _is_project_running(self, project_path):
        """Return True if at least one container in the project is running."""
        try:
            result = subprocess.run(
                compose_command("ps", "--format", "json"),
                cwd=project_path,
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return False
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    container = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if container.get("State") == "running":
                    return True
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _write_project_conf(self, project_name, config):
        """Write an nginx server-block config for one project."""
        self.conf_dir.mkdir(parents=True, exist_ok=True)

        domain = config.get("domain", "")
        # Strip any subfolder from the domain (e.g. "local.tvmatchen.nu/betting" -> "local.tvmatchen.nu")
        domain = domain.split("/")[0]
        if not domain:
            return

        enable_ssl = config.get("enable_ssl", True)
        nginx_container = f"{project_name}_nginx"
        now = datetime.datetime.now().isoformat()

        lines = [
            f"# Auto-generated by WordPress Local Dev",
            f"# Project: {project_name} | Domain: {domain} | Generated: {now}",
            "",
        ]

        # Use Docker's embedded DNS resolver and a variable for proxy_pass so
        # that nginx resolves the upstream at *request* time, not at config-load
        # time.  This prevents "host not found in upstream" errors that block
        # nginx from starting/reloading when the project container is not (yet)
        # running.
        if enable_ssl:
            # HTTP -> HTTPS redirect
            lines += [
                "server {",
                "    listen 80;",
                f"    server_name {domain};",
                "    return 301 https://$host$request_uri;",
                "}",
                "",
                "server {",
                "    listen 443 ssl;",
                "    http2 on;",
                f"    server_name {domain};",
                "",
                "    resolver 127.0.0.11 valid=10s ipv6=off;",
                "",
                f"    ssl_certificate /etc/nginx/project-ssl/{project_name}/ssl/cert.pem;",
                f"    ssl_certificate_key /etc/nginx/project-ssl/{project_name}/ssl/key.pem;",
                "    ssl_protocols TLSv1.2 TLSv1.3;",
                "    ssl_ciphers HIGH:!aNULL:!MD5;",
                "",
                "    client_max_body_size 100M;",
                "",
                "    location / {",
                f"        set $upstream http://{nginx_container}:80;",
                "        proxy_pass $upstream;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "        proxy_set_header X-Forwarded-Proto https;",
                "    }",
                "}",
            ]
        else:
            lines += [
                "server {",
                "    listen 80;",
                f"    server_name {domain};",
                "    resolver 127.0.0.11 valid=10s ipv6=off;",
                "    client_max_body_size 100M;",
                "    location / {",
                f"        set $upstream http://{nginx_container}:80;",
                "        proxy_pass $upstream;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "        proxy_set_header X-Forwarded-Proto http;",
                "    }",
                "}",
            ]

        conf_file = self.conf_dir / f"{project_name}.conf"
        conf_file.write_text("\n".join(lines) + "\n")

    def _reload_nginx(self):
        """Reload nginx config without downtime. Silently ignored if proxy is not running."""
        try:
            # Test configuration first
            test = subprocess.run(
                ["docker", "exec", self.PROXY_CONTAINER, "nginx", "-t"],
                capture_output=True, text=True, timeout=10,
            )
            if test.returncode != 0:
                print(f"nginx config test failed: {test.stderr}")
                return

            result = subprocess.run(
                ["docker", "exec", self.PROXY_CONTAINER, "nginx", "-s", "reload"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                print(f"nginx reload failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Proxy container is not running -- nothing to reload
            pass
