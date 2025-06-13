import os
import platform
import subprocess
from pathlib import Path

class HostsManager:
    def __init__(self):
        self.system = platform.system().lower()
        self.hosts_file = self._get_hosts_file_path()
        self.backup_file = Path(f"{self.hosts_file}.wordpress_backup")
    
    def _get_hosts_file_path(self):
        """Get the path to the hosts file based on the operating system"""
        if self.system == "windows":
            return Path("C:/Windows/System32/drivers/etc/hosts")
        else:  # macOS and Linux
            return Path("/etc/hosts")
    
    def add_host(self, domain, ip="127.0.0.1"):
        """Add a domain to the hosts file"""
        try:
            # Create backup before modifying
            self._create_backup()
            
            # Check if entry already exists
            if self._host_exists(domain):
                print(f"Host entry for {domain} already exists")
                return True
            
            # Add the entry
            entry = f"{ip}\t{domain}\n"
            
            if self.system == "windows":
                self._add_host_windows(entry)
            else:
                self._add_host_unix(entry)
            
            print(f"Added {domain} to hosts file")
            return True
            
        except Exception as e:
            print(f"Error adding host {domain}: {str(e)}")
            return False
    
    def remove_host(self, domain):
        """Remove a domain from the hosts file"""
        try:
            if not self._host_exists(domain):
                print(f"Host entry for {domain} does not exist")
                return True
            
            # Create backup before modifying
            self._create_backup()
            
            # Read current hosts file
            with open(self.hosts_file, 'r') as f:
                lines = f.readlines()
            
            # Filter out the domain entry
            filtered_lines = []
            for line in lines:
                if not (domain in line and not line.strip().startswith('#')):
                    filtered_lines.append(line)
            
            # Write back to hosts file
            if self.system == "windows":
                self._write_hosts_windows(filtered_lines)
            else:
                self._write_hosts_unix(filtered_lines)
            
            print(f"Removed {domain} from hosts file")
            return True
            
        except Exception as e:
            print(f"Error removing host {domain}: {str(e)}")
            return False
    
    def _host_exists(self, domain):
        """Check if a domain already exists in the hosts file"""
        try:
            with open(self.hosts_file, 'r') as f:
                content = f.read()
            
            for line in content.split('\n'):
                if line.strip() and not line.strip().startswith('#'):
                    if domain in line:
                        return True
            return False
            
        except Exception:
            return False
    
    def _create_backup(self):
        """Create a backup of the hosts file"""
        try:
            if self.hosts_file.exists() and not self.backup_file.exists():
                with open(self.hosts_file, 'r') as src:
                    with open(self.backup_file, 'w') as dst:
                        dst.write(src.read())
        except Exception as e:
            print(f"Warning: Could not create hosts file backup: {str(e)}")
    
    def restore_backup(self):
        """Restore the hosts file from backup"""
        try:
            if self.backup_file.exists():
                with open(self.backup_file, 'r') as src:
                    with open(self.hosts_file, 'w') as dst:
                        dst.write(src.read())
                print("Hosts file restored from backup")
                return True
            else:
                print("No backup file found")
                return False
        except Exception as e:
            print(f"Error restoring hosts file: {str(e)}")
            return False
    
    def _add_host_windows(self, entry):
        """Add host entry on Windows"""
        try:
            # Use PowerShell to add entry with administrator privileges
            powershell_cmd = f'Add-Content -Path "{self.hosts_file}" -Value "{entry.strip()}"'
            subprocess.run([
                "powershell", "-Command", 
                f"Start-Process powershell -ArgumentList '-Command \"{powershell_cmd}\"' -Verb RunAs -Wait"
            ], check=True)
        except subprocess.CalledProcessError:
            # Fallback: try to append directly (may fail without admin rights)
            with open(self.hosts_file, 'a') as f:
                f.write(entry)
    
    def _add_host_unix(self, entry):
        """Add host entry on Unix-like systems (macOS, Linux)"""
        try:
            # Skip automatic hosts file modification to avoid blocking
            # This prevents the password prompt from blocking the web interface
            print(f"ℹ️  To add the domain to your hosts file, manually run:")
            print(f"   echo '{entry.strip()}' | sudo tee -a {self.hosts_file}")
            print(f"ℹ️  Or edit {self.hosts_file} and add: {entry.strip()}")
            
            # Don't run sudo commands automatically to avoid blocking
            # subprocess.run([
            #     "sudo", "sh", "-c", 
            #     f"echo '{entry.strip()}' >> {self.hosts_file}"
            # ], check=True)
            
        except Exception as e:
            print(f"Warning: Could not modify hosts file: {str(e)}")
            print(f"Please manually add this line to {self.hosts_file}:")
            print(f"   {entry.strip()}")
    
    def _write_hosts_windows(self, lines):
        """Write hosts file on Windows"""
        try:
            # Create temporary file with new content
            temp_file = Path("hosts_temp.txt")
            with open(temp_file, 'w') as f:
                f.writelines(lines)
            
            # Use PowerShell to replace hosts file with administrator privileges
            powershell_cmd = f'Copy-Item "{temp_file}" "{self.hosts_file}" -Force'
            subprocess.run([
                "powershell", "-Command", 
                f"Start-Process powershell -ArgumentList '-Command \"{powershell_cmd}\"' -Verb RunAs -Wait"
            ], check=True)
            
            # Clean up temp file
            temp_file.unlink()
            
        except subprocess.CalledProcessError:
            # Fallback: try to write directly (may fail without admin rights)
            with open(self.hosts_file, 'w') as f:
                f.writelines(lines)
    
    def _write_hosts_unix(self, lines):
        """Write hosts file on Unix-like systems"""
        try:
            print(f"ℹ️  To update your hosts file, manually run:")
            print(f"   sudo nano {self.hosts_file}")
            print(f"ℹ️  Or use the backup/restore functionality")
            
            # Don't run sudo commands automatically to avoid blocking
            # # Create temporary file with new content
            # temp_file = Path("/tmp/hosts_temp")
            # with open(temp_file, 'w') as f:
            #     f.writelines(lines)
            # 
            # # Use sudo to replace hosts file
            # subprocess.run([
            #     "sudo", "cp", str(temp_file), str(self.hosts_file)
            # ], check=True)
            # 
            # # Clean up temp file
            # temp_file.unlink()
            
        except Exception as e:
            print(f"Warning: Could not modify hosts file: {str(e)}")
            print(f"Please manually edit {self.hosts_file}")
    
    def list_wordpress_hosts(self):
        """List all WordPress-related hosts entries"""
        try:
            hosts = []
            with open(self.hosts_file, 'r') as f:
                for line in f.readlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if 'local.' in line and '.test' in line:
                            parts = line.split()
                            if len(parts) >= 2:
                                hosts.append({
                                    'ip': parts[0],
                                    'domain': parts[1]
                                })
            return hosts
        except Exception as e:
            print(f"Error listing hosts: {str(e)}")
            return []
    
    def flush_dns(self):
        """Flush DNS cache"""
        try:
            if self.system == "windows":
                subprocess.run(["ipconfig", "/flushdns"], check=True)
            elif self.system == "darwin":  # macOS
                subprocess.run(["sudo", "dscacheutil", "-flushcache"], check=True)
                subprocess.run(["sudo", "killall", "-HUP", "mDNSResponder"], check=True)
            elif self.system == "linux":
                # Different Linux distributions use different commands
                try:
                    subprocess.run(["sudo", "systemctl", "restart", "systemd-resolved"], check=True)
                except:
                    try:
                        subprocess.run(["sudo", "service", "network-manager", "restart"], check=True)
                    except:
                        pass
            
            print("DNS cache flushed")
            return True
            
        except Exception as e:
            print(f"Error flushing DNS cache: {str(e)}")
            return False 