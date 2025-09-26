# SSL Certificate Setup Guide

## 🔐 Fix "Your connection is not private" Error

You're seeing this error because the mkcert local CA hasn't been installed in your system's trust store yet. Here are the solutions:

## 🚀 **Solution 1: Install mkcert CA (Recommended)**

### Step 1: Install the Local CA
```bash
# This requires sudo access to install the CA in your system trust store
mkcert -install
```

**Note:** You'll be prompted for your password. This is safe - mkcert only installs a local development CA.

### Step 2: Restart Your Browser
After installing the CA, restart your browser completely:
- **Chrome/Edge**: Close all windows and reopen
- **Firefox**: Close all windows and reopen  
- **Safari**: Close all windows and reopen

### Step 3: Test Your Site
Visit `https://local.example-site-2.test` - it should now work without warnings!

---

## 🔧 **Solution 2: Manual CA Installation (If mkcert -install fails)**

### For macOS:
```bash
# Find the CA file
CA_FILE="/Users/you/Library/Application Support/mkcert/rootCA.pem"

# Install manually
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$CA_FILE"
```

### For Linux:
```bash
# Copy CA to system certificates
sudo cp "/Users/you/Library/Application Support/mkcert/rootCA.pem" /usr/local/share/ca-certificates/mkcert.crt

# Update certificate store
sudo update-ca-certificates
```

### For Windows:
1. Open `certlm.msc` (Certificate Manager)
2. Go to "Trusted Root Certification Authorities" → "Certificates"
3. Right-click → "All Tasks" → "Import"
4. Import the file: `%USERPROFILE%\AppData\Local\mkcert\rootCA.pem`

---

## 🛠️ **Solution 3: Browser-Specific Trust (Quick Fix)**

### For Chrome/Edge:
1. Visit `https://local.example-site-2.test`
2. Click "Advanced" 
3. Click "Proceed to local.example-site-2.test (unsafe)"
4. The site will work, but you'll see a warning each time

### For Firefox:
1. Visit `https://local.example-site-2.test`
2. Click "Advanced"
3. Click "Accept the Risk and Continue"
4. The site will work, but you'll see a warning each time

### For Safari:
1. Visit `https://local.example-site-2.test`
2. Click "Show Details"
3. Click "visit this website"
4. Click "Visit Website"
5. The site will work, but you'll see a warning each time

---

## ✅ **Solution 4: Regenerate Certificates (Alternative)**

If the above doesn't work, regenerate the certificates:

```bash
# Stop the project
cd wordpress-projects/example-site-2
docker-compose down

# Regenerate SSL certificates
python -c "
from utils.ssl_generator import SSLGenerator
ssl_gen = SSLGenerator()
ssl_gen.generate_ssl_cert('example-site-2', 'local.example-site-2.test')
"

# Start the project
docker-compose up -d
```

---

## 🔍 **Verify Installation**

After installing the CA, verify it's working:

```bash
# Check if CA is installed
mkcert -CAROOT

# List trusted certificates (macOS)
security find-certificate -a -c "mkcert" /Library/Keychains/System.keychain
```

---

## 🎯 **Expected Result**

After proper installation, you should see:
- ✅ **Green lock icon** in browser address bar
- ✅ **No security warnings**
- ✅ **"Secure" connection status**
- ✅ **HTTPS working perfectly**

---

## 🆘 **Still Having Issues?**

If you're still seeing warnings:

1. **Clear browser cache** and restart browser
2. **Check system date/time** is correct
3. **Try incognito/private mode** to test
4. **Check firewall/antivirus** isn't blocking certificates

The mkcert approach is the best solution for local development as it provides real, trusted SSL certificates without any browser warnings!
