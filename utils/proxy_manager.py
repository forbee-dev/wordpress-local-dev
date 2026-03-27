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

        Returns True when the proxy is confirmed running, False on failure.
        """
        if not self.proxy_dir.exists():
            print("reverse-proxy/ directory not found")
            return False

        # Check if already running
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", self.PROXY_CONTAINER],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip() == "true":
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Start it
        print("Starting shared reverse proxy...")
        try:
            start = subprocess.run(
                compose_command("up", "-d"),
                cwd=self.proxy_dir,
                capture_output=True, text=True, timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"Failed to start proxy: {exc}")
            return False

        if start.returncode == 0:
            print("Shared reverse proxy started on ports 80/443")
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
        network_name = f"{project_name}_wordpress_network"
        try:
            subprocess.run(
                ["docker", "network", "connect", network_name, self.PROXY_CONTAINER],
                capture_output=True, text=True, timeout=15,
            )
            # Errors are expected when the proxy is already connected -- that is fine.
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Write config for this project and reload
        self._write_project_conf(project_name, config)
        self._reload_nginx()

    def on_project_stop(self, project_name):
        """Called after project containers stop."""
        # Disconnect from the project network (may fail if network already gone)
        network_name = f"{project_name}_wordpress_network"
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
                f"    ssl_certificate /etc/nginx/project-ssl/{project_name}/ssl/cert.pem;",
                f"    ssl_certificate_key /etc/nginx/project-ssl/{project_name}/ssl/key.pem;",
                "    ssl_protocols TLSv1.2 TLSv1.3;",
                "    ssl_ciphers HIGH:!aNULL:!MD5;",
                "",
                "    client_max_body_size 100M;",
                "",
                "    location / {",
                f"        proxy_pass http://{nginx_container}:80;",
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
                "    client_max_body_size 100M;",
                "    location / {",
                f"        proxy_pass http://{nginx_container}:80;",
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
            result = subprocess.run(
                ["docker", "exec", self.PROXY_CONTAINER, "nginx", "-s", "reload"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                print(f"nginx reload failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Proxy container is not running -- nothing to reload
            pass
