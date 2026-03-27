import json
import socket
from pathlib import Path


class PortAllocator:
    """Allocates unique port blocks for WordPress projects.

    Each project gets a contiguous block of PORTS_PER_PROJECT ports starting
    at BASE_PORT + (index * PORTS_PER_PROJECT).  The index (1..MAX_PROJECTS)
    is persisted in each project's config.json under the 'port_index' key so
    that it survives restarts and re-reads.
    """

    BASE_PORT = 10000
    PORTS_PER_PROJECT = 10
    MAX_PROJECTS = 99
    SERVICE_OFFSETS = {
        'HTTP_PORT': 0,
        'HTTPS_PORT': 1,
        'MYSQL_PORT': 2,
        'PHPMYADMIN_PORT': 3,
        'REDIS_PORT': 4,
    }

    def __init__(self, projects_dir):
        self.projects_dir = Path(projects_dir)

    def get_ports_for_index(self, index):
        """Return port mapping dict for a given project index (1-99)."""
        base = self.BASE_PORT + (index * self.PORTS_PER_PROJECT)
        return {key: base + offset for key, offset in self.SERVICE_OFFSETS.items()}

    def get_used_indices(self):
        """Scan all project config.json files for existing port_index values."""
        used = set()
        if not self.projects_dir.exists():
            return used
        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            config_file = project_dir / 'config.json'
            if not config_file.exists():
                continue
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                idx = config.get('port_index')
                if idx is not None:
                    used.add(idx)
            except Exception:
                continue
        return used

    def allocate_next_index(self):
        """First-fit allocation from 1..MAX_PROJECTS."""
        used = self.get_used_indices()
        for i in range(1, self.MAX_PROJECTS + 1):
            if i not in used:
                return i
        raise RuntimeError(
            f"All {self.MAX_PROJECTS} port slots are in use. "
            "Delete a project to free a slot."
        )

    def is_port_available(self, port):
        """Advisory check if a port is available on localhost."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                return result != 0  # 0 means connected (port in use)
        except Exception:
            return True  # Assume available on error
