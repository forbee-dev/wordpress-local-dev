# Git Repository Setup Guide

This guide explains how to configure Git authentication to avoid password prompts when creating WordPress projects.

## 🔐 Authentication Methods

### Option 1: SSH Keys (Recommended for Private Repos)

**Setup SSH keys once, then use SSH URLs for all repositories:**

1. **Generate SSH key** (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

2. **Add SSH key to ssh-agent:**
   ```bash
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519
   ```

3. **Add SSH key to GitHub/GitLab:**
   ```bash
   # Copy public key to clipboard
   cat ~/.ssh/id_ed25519.pub | pbcopy  # macOS
   # Or manually copy the content of ~/.ssh/id_ed25519.pub
   ```
   
   Then paste it in:
   - **GitHub**: Settings → SSH and GPG keys → New SSH key
   - **GitLab**: Preferences → SSH Keys → Add new key
   - **Bitbucket**: Account settings → SSH keys → Add key

4. **Test SSH connection:**
   ```bash
   ssh -T git@github.com
   ssh -T git@gitlab.com
   ssh -T git@bitbucket.org
   ```

5. **Use SSH URLs in WordPress Local Dev:**
   ```
   git@github.com:username/repository.git
   git@gitlab.com:username/repository.git
   git@bitbucket.org:username/repository.git
   ```

### Option 2: Personal Access Tokens (HTTPS)

**For GitHub private repositories using HTTPS:**

1. **Create Personal Access Token:**
   - GitHub: Settings → Developer settings → Personal access tokens → Generate new token
   - Select scopes: `repo` (for private repos) or `public_repo` (for public repos)

2. **Use token in HTTPS URL:**
   ```
   https://USERNAME:TOKEN@github.com/username/repository.git
   ```

3. **Or configure Git credential helper:**
   ```bash
   git config --global credential.helper store
   # Then clone once manually to store credentials
   ```

### Option 3: Public Repositories

**For public repositories, use standard HTTPS URLs:**
```
https://github.com/username/repository.git
https://gitlab.com/username/repository.git
```

## 📂 Repository Structure

The WordPress Local Dev environment now intelligently handles various repository structures:

### Structure 1: Full WordPress Project
```
project-name/
├── repository/            # 🔗 Your entire repository (intact)
│   ├── wp-content/
│   │   ├── themes/
│   │   │   └── your-theme/
│   │   ├── plugins/
│   │   │   └── your-plugin/
│   │   └── uploads/
│   ├── composer.json      # ✅ Preserved exactly as-is
│   ├── composer.lock      # ✅ Preserved exactly as-is
│   ├── package.json       # ✅ Preserved exactly as-is
│   ├── webpack.config.js  # ✅ Preserved exactly as-is
│   ├── .gitignore         # ✅ Preserved exactly as-is
│   ├── vendor/            # ✅ Preserved exactly as-is
│   ├── node_modules/      # ✅ Preserved exactly as-is
│   └── .git/              # ✅ Preserved exactly as-is
├── wp-content/            # 🔗 Symlink to repository/wp-content/
├── docker-compose.yml
├── Makefile
└── ...other project files
```

### Structure 2: Theme Repository
```
project-name/
├── repository/            # 🔗 Your entire theme repository (intact)  
│   ├── style.css         # ✅ Preserved exactly as-is
│   ├── index.php         # ✅ Preserved exactly as-is
│   ├── functions.php     # ✅ Preserved exactly as-is
│   ├── composer.json     # ✅ Preserved exactly as-is
│   ├── package.json      # ✅ Preserved exactly as-is
│   ├── webpack.config.js # ✅ Preserved exactly as-is
│   ├── .gitignore        # ✅ Preserved exactly as-is
│   ├── vendor/           # ✅ Preserved exactly as-is
│   ├── node_modules/     # ✅ Preserved exactly as-is
│   ├── .git/             # ✅ Preserved exactly as-is
│   └── assets/           # ✅ Preserved exactly as-is
├── wp-content/
│   └── themes/
│       └── theme-name/   # 🔗 Symlink to repository/
├── docker-compose.yml
└── ...other project files
```

### Structure 3: Plugin Repository
```
project-name/
├── repository/            # 🔗 Your entire plugin repository (intact)
│   ├── plugin-name.php   # ✅ Preserved exactly as-is
│   ├── composer.json     # ✅ Preserved exactly as-is
│   ├── vendor/           # ✅ Preserved exactly as-is
│   ├── .gitignore        # ✅ Preserved exactly as-is
│   ├── .git/             # ✅ Preserved exactly as-is
│   ├── readme.txt        # ✅ Preserved exactly as-is
│   ├── assets/           # ✅ Preserved exactly as-is
│   └── includes/         # ✅ Preserved exactly as-is
├── wp-content/
│   └── plugins/
│       └── plugin-name/  # 🔗 Symlink to repository/
├── docker-compose.yml
└── ...other project files
```

### Automatically Preserved Files
The system now preserves ALL important development files:

**📦 Dependency Management:**
- `composer.json`, `composer.lock` (PHP dependencies)
- `package.json`, `package-lock.json`, `yarn.lock` (Node.js dependencies)
- `vendor/` directory (Composer packages)
- `node_modules/` directory (NPM packages)

**🔧 Build Tools:**
- `webpack.config.js`, `gulpfile.js`, `Gruntfile.js`
- `tsconfig.json` (TypeScript)
- `.stylelintrc`, `.eslintrc` (Linting)

**🔄 Version Control:**
- `.git/` directory (for ongoing development)
- `.gitignore`, `.gitattributes`

**⚙️ Configuration:**
- `.env.example`, `.env.local`
- `.editorconfig`
- `wp-config.php`, `wp-config-sample.php`

**📚 Documentation:**
- `README.md`, `CHANGELOG.md`, `LICENSE`

**🚫 Excluded Files:**
Only system files are excluded:
- `.DS_Store` (macOS)
- `Thumbs.db` (Windows)

## 🚫 Avoiding Password Prompts

The WordPress Local Dev environment now:

1. **Disables interactive prompts** using `GIT_TERMINAL_PROMPT=0`
2. **Sets timeout** to 60 seconds for clone operations
3. **Provides helpful error messages** for authentication failures
4. **Shows clear instructions** for fixing authentication issues

## 🔧 Troubleshooting

### "Authentication failed" error
- **For private repos**: Use SSH URLs with properly configured SSH keys
- **For HTTPS**: Use Personal Access Token in the URL
- **Check permissions**: Ensure you have access to the repository

### "Repository not found" error
- **Check URL**: Verify the repository URL is correct
- **Check permissions**: Ensure the repository exists and you have access
- **Private repos**: Make sure you're authenticated properly

### Clone timeout
- **Check network**: Ensure stable internet connection
- **Large repos**: Consider using `--depth 1` for shallow clones (automatically done)
- **Slow connection**: The system will timeout after 60 seconds

## 💡 Best Practices

1. **Use SSH for private repositories** - More secure and convenient
2. **Use HTTPS for public repositories** - Simple and works everywhere
3. **Test authentication first** - Clone repositories manually before using in WordPress Local Dev
4. **Keep tokens secure** - Don't share Personal Access Tokens
5. **Use descriptive repository names** - Makes project management easier

## 🎯 Quick Setup Commands

**Setup SSH key (one-time):**
```bash
# Generate key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Copy public key (add to GitHub/GitLab)
cat ~/.ssh/id_ed25519.pub | pbcopy

# Test connection
ssh -T git@github.com
```

**Clone test (verify before using in WordPress Local Dev):**
```bash
# Test SSH
git clone git@github.com:username/repository.git test-clone

# Test HTTPS with token
git clone https://username:token@github.com/username/repository.git test-clone

# Clean up
rm -rf test-clone
```

## 📞 Need Help?

If you're still experiencing issues:

1. **Test Git clone manually** in terminal first
2. **Check SSH key configuration** with `ssh -T git@github.com`
3. **Verify repository permissions** in GitHub/GitLab/Bitbucket
4. **Use public repository** for testing initially
5. **Check our troubleshooting guide** in the main documentation 