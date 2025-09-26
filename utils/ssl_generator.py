import os
import subprocess
import platform
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime
import shutil

class SSLGenerator:
    def __init__(self):
        self.ssl_dir = Path("ssl")
        self.ssl_dir.mkdir(exist_ok=True)
        self.projects_dir = Path("wordpress-projects")
        self.mkcert_available = self._check_mkcert_available()
    
    def _check_mkcert_available(self):
        """Check if mkcert is available on the system"""
        try:
            result = subprocess.run(['mkcert', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _check_mkcert_ca_installed(self):
        """Check if mkcert local CA is installed in system trust store"""
        try:
            # Check if mkcert can find its CA root (indicates CA is installed)
            result = subprocess.run(['mkcert', '-CAROOT'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                ca_root = result.stdout.strip()
                ca_file = Path(ca_root) / "rootCA.pem"
                return ca_file.exists()
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _install_mkcert_ca(self):
        """Attempt to install mkcert local CA in system trust store"""
        try:
            print("🔐 Installing mkcert local CA in system trust store...")
            print("ℹ️  This requires sudo access to add the CA to your system")
            
            result = subprocess.run(['mkcert', '-install'], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("✅ mkcert local CA installed successfully!")
                print("ℹ️  SSL certificates will now be automatically trusted by browsers")
                return True
            else:
                print(f"⚠️  Failed to install mkcert CA: {result.stderr}")
                print("ℹ️  You can install it manually by running: mkcert -install")
                return False
                
        except subprocess.TimeoutExpired:
            print("⚠️  mkcert -install timed out")
            return False
        except Exception as e:
            print(f"⚠️  Error installing mkcert CA: {str(e)}")
            return False
    
    def generate_ssl_cert(self, project_name, domain):
        """Generate SSL certificate for a domain"""
        try:
            project_ssl_dir = self.projects_dir / project_name / "ssl"
            project_ssl_dir.mkdir(exist_ok=True)
            
            cert_file = project_ssl_dir / "cert.pem"
            key_file = project_ssl_dir / "key.pem"
            
            # Try mkcert first (preferred method for trusted certificates)
            if self.mkcert_available:
                # Check if mkcert CA is installed, if not try to install it
                if not self._check_mkcert_ca_installed():
                    print("🔐 mkcert local CA not found in system trust store")
                    print("ℹ️  Attempting to install mkcert local CA...")
                    self._install_mkcert_ca()
                
                return self._generate_with_mkcert(project_ssl_dir, domain)
            else:
                return self._generate_self_signed_cert(project_ssl_dir, domain)
            
        except Exception as e:
            print(f"Error generating SSL certificate: {str(e)}")
            return False
    
    def _generate_with_mkcert(self, project_ssl_dir, domain):
        """Generate SSL certificate using mkcert (trusted by browsers)"""
        try:
            print(f"🔐 Generating trusted SSL certificate using mkcert for {domain}")
            
            # Create temporary directory for mkcert
            temp_dir = project_ssl_dir / "temp"
            temp_dir.mkdir(exist_ok=True)
            
            # Generate certificate with mkcert
            # Include common local domains
            domains = [domain, f"*.{domain}", "localhost", "127.0.0.1"]
            
            result = subprocess.run([
                'mkcert', '-cert-file', 'cert.pem', '-key-file', 'key.pem'
            ] + domains, 
            cwd=temp_dir, 
            capture_output=True, 
            text=True, 
            timeout=30)
            
            if result.returncode == 0:
                # Move files to project ssl directory
                shutil.move(temp_dir / "cert.pem", project_ssl_dir / "cert.pem")
                shutil.move(temp_dir / "key.pem", project_ssl_dir / "key.pem")
                
                # Clean up temp directory
                shutil.rmtree(temp_dir)
                
                print(f"✅ Trusted SSL certificate generated successfully for {domain}")
                print(f"ℹ️  Certificate is automatically trusted by browsers (no warnings)")
                return True
            else:
                print(f"❌ mkcert failed: {result.stderr}")
                # Fallback to self-signed
                return self._generate_self_signed_cert(project_ssl_dir, domain)
                
        except Exception as e:
            print(f"❌ mkcert error: {str(e)}")
            # Fallback to self-signed
            return self._generate_self_signed_cert(project_ssl_dir, domain)
    
    def _generate_self_signed_cert(self, project_ssl_dir, domain):
        """Generate self-signed SSL certificate (fallback method)"""
        try:
            print(f"🔐 Generating self-signed SSL certificate for {domain}")
            
            cert_file = project_ssl_dir / "cert.pem"
            key_file = project_ssl_dir / "key.pem"
            
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            
            # Generate certificate
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Local"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Development"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "WordPress Local Dev"),
                x509.NameAttribute(NameOID.COMMON_NAME, domain),
            ])
            
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.utcnow()
            ).not_valid_after(
                datetime.datetime.utcnow() + datetime.timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(domain),
                    x509.DNSName(f"*.{domain}"),
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                ]),
                critical=False,
            ).sign(private_key, hashes.SHA256())
            
            # Write certificate to file
            with open(cert_file, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            # Write private key to file
            with open(key_file, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            print(f"✅ Self-signed SSL certificate generated for {domain}")
            print(f"⚠️  Browser will show security warning - click 'Advanced' and 'Proceed'")
            self._add_to_trust_store(cert_file, domain)
            
            return True
            
        except Exception as e:
            print(f"❌ Error generating self-signed certificate: {str(e)}")
            return False
    
    def _add_to_trust_store(self, cert_file, domain):
        """Add certificate to system trust store"""
        try:
            system = platform.system().lower()
            
            # Skip system trust store installation in development mode
            # This avoids blocking the process waiting for admin password
            print(f"ℹ️  SSL certificate generated for {domain}")
            print(f"ℹ️  Certificate location: {cert_file}")
            print(f"ℹ️  To trust the certificate system-wide, manually run:")
            
            if system == "darwin":  # macOS
                print(f"   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain {cert_file}")
                # Don't run sudo commands automatically to avoid blocking
                # subprocess.run([
                #     "sudo", "security", "add-trusted-cert", 
                #     "-d", "-r", "trustRoot", 
                #     "-k", "/Library/Keychains/System.keychain", 
                #     str(cert_file)
                # ], check=False, capture_output=True)
                
            elif system == "linux":
                trust_dir = Path("/usr/local/share/ca-certificates")
                if trust_dir.exists():
                    cert_name = f"wordpress-local-{domain}.crt"
                    print(f"   sudo cp {cert_file} {trust_dir}/{cert_name}")
                    print(f"   sudo update-ca-certificates")
                    # Don't run sudo commands automatically
                    # subprocess.run([
                    #     "sudo", "cp", str(cert_file), 
                    #     str(trust_dir / cert_name)
                    # ], check=False, capture_output=True)
                    # subprocess.run([
                    #     "sudo", "update-ca-certificates"
                    # ], check=False, capture_output=True)
                    
            elif system == "windows":
                print(f"   Import {cert_file} into Windows Certificate Store")
                # Don't run admin commands automatically
                # subprocess.run([
                #     "certlm.msc", "/s", str(cert_file)
                # ], check=False, capture_output=True)
                
        except Exception as e:
            print(f"Warning: Could not add certificate to system trust store: {str(e)}")
            print("You may need to manually trust the certificate in your browser.")
    
    def remove_ssl_cert(self, project_name, domain):
        """Remove SSL certificate for a domain"""
        try:
            project_ssl_dir = self.projects_dir / project_name / "ssl"
            if project_ssl_dir.exists():
                for file in project_ssl_dir.glob("*"):
                    file.unlink()
            
            # Try to remove from system trust store
            self._remove_from_trust_store(domain)
            
            return True
            
        except Exception as e:
            print(f"Error removing SSL certificate: {str(e)}")
            return False
    
    def _remove_from_trust_store(self, domain):
        """Remove certificate from system trust store"""
        try:
            system = platform.system().lower()
            
            if system == "darwin":  # macOS
                # Remove from macOS keychain (this is complex, skipping for now)
                pass
                
            elif system == "linux":
                # Remove from Linux trust store
                trust_dir = Path("/usr/local/share/ca-certificates")
                cert_name = f"wordpress-local-{domain}.crt"
                cert_path = trust_dir / cert_name
                if cert_path.exists():
                    subprocess.run([
                        "sudo", "rm", str(cert_path)
                    ], check=False, capture_output=True)
                    subprocess.run([
                        "sudo", "update-ca-certificates"
                    ], check=False, capture_output=True)
                    
            elif system == "windows":
                # Remove from Windows trust store (complex, skipping for now)
                pass
                
        except Exception as e:
            print(f"Warning: Could not remove certificate from system trust store: {str(e)}")
    
    def setup_mkcert(self):
        """Help user set up mkcert for trusted SSL certificates"""
        print("🔐 Setting up mkcert for trusted SSL certificates...")
        print()
        
        if self.mkcert_available:
            print("✅ mkcert is already installed and available")
            print("ℹ️  To install the local CA (trusted by browsers), run:")
            print("   mkcert -install")
            print("   (This requires sudo access to add the CA to your system)")
            return True
        else:
            print("❌ mkcert is not installed")
            print()
            print("📦 To install mkcert:")
            print("   macOS: brew install mkcert")
            print("   Linux: https://github.com/FiloSottile/mkcert#installation")
            print("   Windows: https://github.com/FiloSottile/mkcert#installation")
            print()
            print("🔧 After installation, run:")
            print("   mkcert -install")
            print("   (This installs a local CA trusted by browsers)")
            print()
            print("ℹ️  With mkcert, SSL certificates will be automatically trusted")
            print("   by browsers without security warnings!")
            return False 