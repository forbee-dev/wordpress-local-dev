// WordPress Local Development Environment - Frontend Application
class WordPressDevApp {
    constructor() {
        this.currentProject = null;
        this.init();
    }

    init() {
        this.loadWordPressVersions();
        this.loadProjects();
        this.bindEvents();
    }

    bindEvents() {
        // Form submission
        document.getElementById('createProjectForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.createProject();
        });

        // Modal close events
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.closeModal(e.target.closest('.modal'));
            });
        });

        // Message close
        document.querySelector('.message-close')?.addEventListener('click', () => {
            this.hideMessage();
        });

        // Project action buttons
        document.getElementById('startBtn')?.addEventListener('click', () => {
            this.startProject(this.currentProject);
        });

        document.getElementById('stopBtn')?.addEventListener('click', () => {
            this.stopProject(this.currentProject);
        });

        document.getElementById('logsBtn')?.addEventListener('click', () => {
            this.showLogs(this.currentProject);
        });

        document.getElementById('debugLogsBtn')?.addEventListener('click', () => {
            this.showDebugLogs(this.currentProject);
        });

        document.getElementById('deleteBtn')?.addEventListener('click', () => {
            this.deleteProject(this.currentProject);
        });

        document.getElementById('uploadDbBtn')?.addEventListener('click', () => {
            this.showUploadDbModal();
        });

        // Database upload form submission
        document.getElementById('dbUploadForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.uploadDatabase();
        });

        // Click outside modal to close
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.closeModal(modal);
                }
            });
        });
    }

    async loadWordPressVersions() {
        try {
            const select = document.getElementById('wordpress_version');
            select.innerHTML = '<option value="">Loading WordPress versions...</option>';
            
            const response = await fetch('/api/wordpress-versions');
            const versions = await response.json();
            
            select.innerHTML = '<option value="">Select WordPress version...</option>';
            
            versions.forEach(version => {
                const option = document.createElement('option');
                option.value = version.version;
                option.textContent = version.description;
                select.appendChild(option);
            });
            
            console.log(`Loaded ${versions.length} WordPress versions from Docker Hub`);
        } catch (error) {
            console.error('Error loading WordPress versions:', error);
            const select = document.getElementById('wordpress_version');
            select.innerHTML = '<option value="">Error loading versions - refresh page</option>';
            this.showMessage('Failed to load WordPress versions from Docker Hub', 'error');
        }
    }

    async loadProjects() {
        try {
            const response = await fetch('/api/projects');
            const projects = await response.json();
            
            this.renderProjects(projects);
        } catch (error) {
            console.error('Error loading projects:', error);
            this.showMessage('Failed to load projects', 'error');
        }
    }

    renderProjects(projects) {
        const container = document.getElementById('projectsList');
        
        if (projects.length === 0) {
            container.innerHTML = `
                <div class="no-projects">
                    <i class="fas fa-folder-open"></i>
                    <h3>No projects yet</h3>
                    <p>Create your first WordPress project using the form above!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = projects.map(project => this.createProjectCard(project)).join('');
        
        // Bind click events to project cards
        container.querySelectorAll('.project-card').forEach(card => {
            card.addEventListener('click', () => {
                const projectName = card.dataset.project;
                const project = projects.find(p => p.name === projectName);
                this.showProjectModal(project);
            });
        });
    }

    createProjectCard(project) {
        const status = project.status?.status || 'unknown';
        const statusClass = `status-${status}`;
        const statusText = this.getStatusText(status);
        
        const domain = project.domain || `local.${project.name}.test`;
        const protocol = project.enable_ssl ? 'https' : 'http';
        
        return `
            <div class="project-card" data-project="${project.name}">
                <h3><i class="fab fa-wordpress"></i> ${project.name}</h3>
                <p><strong>WordPress:</strong> ${project.wordpress_version}</p>
                <p><strong>Domain:</strong> <a href="${protocol}://${domain}" target="_blank" class="domain">${domain}</a></p>
                <p><strong>Status:</strong> <span class="status-badge ${statusClass}">${statusText}</span></p>
                ${project.subfolder ? `<p><strong>Subfolder:</strong> ${project.subfolder}</p>` : ''}
                <p class="project-features">
                    ${project.enable_ssl ? '<i class="fas fa-lock" title="SSL Enabled"></i>' : ''}
                    ${project.enable_redis ? '<i class="fas fa-memory" title="Redis Enabled"></i>' : ''}
                </p>
            </div>
        `;
    }

    getStatusText(status) {
        const statusMap = {
            'running': 'Running',
            'stopped': 'Stopped',
            'partial': 'Partial',
            'error': 'Error',
            'unknown': 'Unknown'
        };
        return statusMap[status] || 'Unknown';
    }

    async createProject() {
        const form = document.getElementById('createProjectForm');
        const formData = new FormData(form);

        this.showLoading();

        try {
            const response = await fetch('/api/create-project', {
                method: 'POST',
                body: formData // Send FormData directly for file upload
            });

            const result = await response.json();

            if (response.ok) {
                this.showMessage('Project created successfully!', 'success');
                form.reset();
                // Reset checkboxes to default checked state
                document.getElementById('enable_ssl').checked = true;
                document.getElementById('enable_redis').checked = true;
                
                // Reload projects list
                this.loadProjects();
            } else {
                this.showMessage(result.error || 'Failed to create project', 'error');
            }
        } catch (error) {
            console.error('Error creating project:', error);
            this.showMessage('Failed to create project. Please try again.', 'error');
        } finally {
            this.hideLoading();
        }
    }

    showProjectModal(project) {
        this.currentProject = project.name;
        
        document.getElementById('modalProjectName').textContent = project.name;
        document.getElementById('modalDomain').textContent = project.domain;
        
        const status = project.status?.status || 'unknown';
        const statusElement = document.getElementById('modalStatus');
        statusElement.textContent = this.getStatusText(status);
        statusElement.className = `status-badge status-${status}`;
        
        // Update button states based on status
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        
        if (status === 'running') {
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }

        this.showModal('projectModal');
    }

    async startProject(projectName) {
        if (!projectName) return;

        this.showLoading();
        
        try {
            const response = await fetch(`/api/projects/${projectName}/start`, {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (response.ok) {
                this.showMessage('Project started successfully!', 'success');
                this.loadProjects();
                this.closeModal(document.getElementById('projectModal'));
            } else {
                this.showMessage(result.error || 'Failed to start project', 'error');
            }
        } catch (error) {
            console.error('Error starting project:', error);
            this.showMessage('Failed to start project', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async stopProject(projectName) {
        if (!projectName) return;

        this.showLoading();
        
        try {
            const response = await fetch(`/api/projects/${projectName}/stop`, {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (response.ok) {
                this.showMessage('Project stopped successfully!', 'success');
                this.loadProjects();
                this.closeModal(document.getElementById('projectModal'));
            } else {
                this.showMessage(result.error || 'Failed to stop project', 'error');
            }
        } catch (error) {
            console.error('Error stopping project:', error);
            this.showMessage('Failed to stop project', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async deleteProject(projectName) {
        if (!projectName) return;

        if (!confirm(`Are you sure you want to delete the project "${projectName}"? This action cannot be undone.`)) {
            return;
        }

        this.showLoading();
        
        try {
            const response = await fetch(`/api/projects/${projectName}/delete`, {
                method: 'DELETE'
            });
            
            const result = await response.json();
            
            if (response.ok) {
                this.showMessage('Project deleted successfully!', 'success');
                this.loadProjects();
                this.closeModal(document.getElementById('projectModal'));
            } else {
                this.showMessage(result.error || 'Failed to delete project', 'error');
            }
        } catch (error) {
            console.error('Error deleting project:', error);
            this.showMessage('Failed to delete project', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async showLogs(projectName) {
        if (!projectName) return;

        this.showLoading();
        
        try {
            const response = await fetch(`/api/projects/${projectName}/logs`);
            const result = await response.json();
            
            if (response.ok) {
                document.getElementById('logsContent').textContent = result.logs || 'No logs available';
                this.showModal('logsModal');
            } else {
                this.showMessage(result.error || 'Failed to load logs', 'error');
            }
        } catch (error) {
            console.error('Error loading logs:', error);
            this.showMessage('Failed to load logs', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async showDebugLogs(projectName) {
        if (!projectName) return;

        this.currentProject = projectName;
        this.showModal('debugLogsModal');
        this.loadDebugLogs();

        // Start live streaming
        this.startLiveLogging();

        // Add event listeners for debug logs controls
        document.getElementById('refreshDebugLogsBtn')?.addEventListener('click', () => {
            this.loadDebugLogs();
        });

        document.getElementById('clearDebugLogsBtn')?.addEventListener('click', () => {
            this.clearDebugLogs();
        });

        document.getElementById('debugLogsLines')?.addEventListener('change', () => {
            this.loadDebugLogs();
        });

        // Add live streaming toggle
        document.getElementById('toggleLiveLogsBtn')?.addEventListener('click', () => {
            this.toggleLiveLogging();
        });
    }

    async loadDebugLogs(showLoadingOverlay = true) {
        if (!this.currentProject) return;

        if (showLoadingOverlay) {
            this.showLoading();
        }
        
        try {
            const lines = document.getElementById('debugLogsLines')?.value || 50;
            const response = await fetch(`/api/projects/${this.currentProject}/debug-logs?lines=${lines}`);
            const result = await response.json();
            
            if (response.ok) {
                const content = result.logs || 'No debug logs available';
                const debugLogsContent = document.getElementById('debugLogsContent');
                
                // Store current scroll position to maintain it during live updates
                const wasAtBottom = debugLogsContent.scrollTop >= (debugLogsContent.scrollHeight - debugLogsContent.clientHeight - 50);
                
                debugLogsContent.textContent = content;
                
                // Auto-scroll to bottom only if user was already at bottom or this is manual refresh
                if (wasAtBottom || showLoadingOverlay) {
                    debugLogsContent.scrollTop = debugLogsContent.scrollHeight;
                }
                
                // Color-code log levels
                this.colorCodeDebugLogs(debugLogsContent);
                
                // Update last refresh time
                if (!showLoadingOverlay) {
                    const timestamp = new Date().toLocaleTimeString();
                    const refreshStatus = document.getElementById('lastRefresh');
                    if (refreshStatus) {
                        refreshStatus.textContent = `Last updated: ${timestamp}`;
                    }
                }
            } else {
                if (showLoadingOverlay) {
                    this.showMessage(result.error || 'Failed to load debug logs', 'error');
                }
            }
        } catch (error) {
            console.error('Error loading debug logs:', error);
            if (showLoadingOverlay) {
                this.showMessage('Failed to load debug logs', 'error');
            }
        } finally {
            if (showLoadingOverlay) {
                this.hideLoading();
            }
        }
    }

    async clearDebugLogs() {
        if (!this.currentProject) return;

        if (!confirm('Are you sure you want to clear all debug logs? This action cannot be undone.')) {
            return;
        }

        this.showLoading();
        
        try {
            const response = await fetch(`/api/projects/${this.currentProject}/debug-logs/clear`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (response.ok) {
                this.showMessage('Debug logs cleared successfully!', 'success');
                this.loadDebugLogs(); // Refresh the logs view
            } else {
                this.showMessage(result.error || 'Failed to clear debug logs', 'error');
            }
        } catch (error) {
            console.error('Error clearing debug logs:', error);
            this.showMessage('Failed to clear debug logs', 'error');
        } finally {
            this.hideLoading();
        }
    }

    colorCodeDebugLogs(element) {
        const content = element.textContent;
        const lines = content.split('\n');
        
        const coloredLines = lines.map(line => {
            if (line.includes('[ERROR]') || line.includes('Fatal error') || line.includes('PHP Fatal error')) {
                return `<span style="color: #e74c3c; font-weight: bold;">${line}</span>`;
            } else if (line.includes('[WARNING]') || line.includes('PHP Warning') || line.includes('Warning:')) {
                return `<span style="color: #f39c12; font-weight: bold;">${line}</span>`;
            } else if (line.includes('[NOTICE]') || line.includes('PHP Notice') || line.includes('Notice:')) {
                return `<span style="color: #fff;">${line}</span>`;
            } else if (line.includes('[DEBUG]') || line.includes('DEBUG')) {
                return `<span style="color: #95a5a6;">${line}</span>`;
            } else {
                return line;
            }
        });
        
        element.innerHTML = coloredLines.join('\n');
    }

    startLiveLogging() {
        this.isLiveLogging = true;
        
        // Update button state
        const toggleBtn = document.getElementById('toggleLiveLogsBtn');
        if (toggleBtn) {
            toggleBtn.innerHTML = '<i class="fas fa-pause"></i> Pause Live';
            toggleBtn.classList.remove('btn-success');
            toggleBtn.classList.add('btn-warning');
        }

        // Start polling every 3 seconds
        this.liveLogInterval = setInterval(() => {
            if (this.isLiveLogging && this.currentProject) {
                this.loadDebugLogs(false); // Don't show loading overlay for auto-refresh
            }
        }, 3000);
    }

    stopLiveLogging() {
        this.isLiveLogging = false;
        
        // Update button state
        const toggleBtn = document.getElementById('toggleLiveLogsBtn');
        if (toggleBtn) {
            toggleBtn.innerHTML = '<i class="fas fa-play"></i> Start Live';
            toggleBtn.classList.remove('btn-warning');
            toggleBtn.classList.add('btn-success');
        }

        if (this.liveLogInterval) {
            clearInterval(this.liveLogInterval);
            this.liveLogInterval = null;
        }
    }

    toggleLiveLogging() {
        if (this.isLiveLogging) {
            this.stopLiveLogging();
        } else {
            this.startLiveLogging();
        }
    }

    showModal(modalId) {
        const modal = document.getElementById(modalId);
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    closeModal(modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
        
        // Stop live logging when debug logs modal is closed
        if (modal.id === 'debugLogsModal') {
            this.stopLiveLogging();
        }
    }

    showLoading() {
        document.getElementById('loadingOverlay').classList.remove('hidden');
    }

    hideLoading() {
        document.getElementById('loadingOverlay').classList.add('hidden');
    }

    showMessage(message, type = 'info') {
        const container = document.getElementById('messageContainer');
        const messageElement = container.querySelector('.message');
        const textElement = container.querySelector('.message-text');
        
        textElement.textContent = message;
        messageElement.className = `message ${type}`;
        container.classList.remove('hidden');
        
        // Auto hide after 5 seconds
        setTimeout(() => {
            this.hideMessage();
        }, 5000);
    }

    hideMessage() {
        document.getElementById('messageContainer').classList.add('hidden');
    }

    showUploadDbModal() {
        if (!this.currentProject) return;
        
        // Reset form
        document.getElementById('dbUploadForm').reset();
        document.getElementById('backupBeforeUpload').checked = true;
        
        this.showModal('dbUploadModal');
    }

    async uploadDatabase() {
        if (!this.currentProject) return;

        const form = document.getElementById('dbUploadForm');
        const formData = new FormData(form);
        const fileInput = document.getElementById('dbUploadFile');

        if (!fileInput.files.length) {
            this.showMessage('Please select a database file', 'error');
            return;
        }

        this.showLoading();

        try {
            const response = await fetch(`/api/projects/${this.currentProject}/upload-db`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok) {
                this.showMessage('Database uploaded and imported successfully!', 'success');
                this.closeModal(document.getElementById('dbUploadModal'));
                this.loadProjects(); // Refresh project list
            } else {
                this.showMessage(result.error || 'Failed to upload database', 'error');
            }
        } catch (error) {
            console.error('Error uploading database:', error);
            this.showMessage('Failed to upload database. Please try again.', 'error');
        } finally {
            this.hideLoading();
        }
    }

    // Auto-refresh projects every 30 seconds
    startAutoRefresh() {
        setInterval(() => {
            this.loadProjects();
        }, 30000);
    }
}

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const app = new WordPressDevApp();
    app.startAutoRefresh();
    
    // Add some additional styling for the no-projects state
    const style = document.createElement('style');
    style.textContent = `
        .no-projects {
            text-align: center;
            padding: 40px 20px;
            color: #7f8c8d;
            grid-column: 1 / -1;
        }
        
        .no-projects i {
            font-size: 3rem;
            margin-bottom: 20px;
            opacity: 0.5;
        }
        
        .no-projects h3 {
            margin-bottom: 10px;
            font-size: 1.2rem;
        }
        
        .project-features {
            margin-top: 10px;
        }
        
        .project-features i {
            margin-right: 8px;
            color: #27ae60;
        }
        
        .domain {
            color: inherit;
            text-decoration: none;
        }
        
        .domain:hover {
            text-decoration: underline;
        }
    `;
    document.head.appendChild(style);
}); 