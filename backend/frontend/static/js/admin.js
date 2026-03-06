// ENCPServices - Admin Controller
const Admin = {
    currentView: 'dashboard',
    leads: [],
    estimates: [],
    projects: [],
    conversations: [],

    // ─── Initialization ───────────────────────────────────────────────

    init() {
        API.init();
        if (!API.token) {
            this.showLogin();
            return;
        }
        this.showAdmin();
        this.bindNavigation();
        this.bindSearch();
        this.bindModals();
        this.loadDashboard();
    },

    // ─── View Switching ───────────────────────────────────────────────

    showLogin() {
        this._hide('admin-container');
        this._show('admin-login-screen');
        this.bindLoginForm();
    },

    showAdmin() {
        this._hide('admin-login-screen');
        this._show('admin-container');
    },

    bindLoginForm() {
        const form = document.getElementById('admin-login-form');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('admin-email').value.trim();
            const password = document.getElementById('admin-password').value;
            const errorEl = document.getElementById('admin-login-error');

            if (!email || !password) {
                this._showError(errorEl, 'Please enter email and password.');
                return;
            }

            this._showError(errorEl, '');
            try {
                const data = await API.login(email, password);
                API.setToken(data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('encp_refresh', data.refresh_token);
                }
                this.showAdmin();
                this.bindNavigation();
                this.bindSearch();
                this.bindModals();
                this.loadDashboard();
            } catch (err) {
                this._showError(errorEl, err.message || 'Login failed.');
            }
        });
    },

    // ─── Navigation ───────────────────────────────────────────────────

    bindNavigation() {
        document.querySelectorAll('[data-view]').forEach((item) => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const view = item.dataset.view;
                this.navigateTo(view);
            });
        });

        // Logout
        const logoutBtn = document.getElementById('admin-logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                API.clearToken();
                window.location.reload();
            });
        }
    },

    navigateTo(view) {
        this.currentView = view;

        // Update sidebar active state
        document.querySelectorAll('[data-view]').forEach((el) => {
            el.classList.toggle('active', el.dataset.view === view);
        });

        // Hide all views, show selected
        document.querySelectorAll('.admin-view').forEach((el) => {
            el.style.display = 'none';
        });
        const viewEl = document.getElementById(`view-${view}`);
        if (viewEl) viewEl.style.display = '';

        // Load data for the view
        switch (view) {
            case 'dashboard': this.loadDashboard(); break;
            case 'leads': this.loadLeads(); break;
            case 'estimates': this.loadEstimates(); break;
            case 'projects': this.loadProjects(); break;
            case 'conversations': this.loadConversations(); break;
            case 'marketing': this.loadMarketing(); break;
            case 'blog': this.loadBlog(); break;
        }
    },

    // ─── Search ───────────────────────────────────────────────────────

    bindSearch() {
        const searchInput = document.getElementById('admin-search');
        if (!searchInput) return;

        let debounceTimer = null;
        searchInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const query = searchInput.value.trim();
                if (query.length >= 2) {
                    this.performSearch(query);
                } else {
                    this._hideSearchResults();
                }
            }, 300);
        });

        // Close search results on outside click
        document.addEventListener('click', (e) => {
            const searchArea = document.getElementById('search-area');
            if (searchArea && !searchArea.contains(e.target)) {
                this._hideSearchResults();
            }
        });
    },

    async performSearch(query) {
        const resultsEl = document.getElementById('search-results');
        if (!resultsEl) return;

        try {
            const data = await API.admin.search(query);
            const results = data.results || data || [];
            resultsEl.style.display = 'block';

            if (results.length === 0) {
                resultsEl.innerHTML = '<div class="search-no-results">No results found.</div>';
                return;
            }

            resultsEl.innerHTML = results.map((r) => `
                <div class="search-result-item" data-type="${this._escapeAttr(r.type || '')}" data-id="${this._escapeAttr(r.id || '')}">
                    <div class="search-result-name">${this._escapeHtml(r.name || r.title || 'Unknown')}</div>
                    <div class="search-result-type">${this._escapeHtml(r.type || '')}</div>
                    <div class="search-result-detail">${this._escapeHtml(r.detail || r.email || r.phone || '')}</div>
                </div>
            `).join('');

            resultsEl.querySelectorAll('.search-result-item').forEach((item) => {
                item.addEventListener('click', () => {
                    const type = item.dataset.type;
                    const id = item.dataset.id;
                    this._hideSearchResults();
                    if (type === 'lead') this.navigateTo('leads');
                    else if (type === 'estimate') this.navigateTo('estimates');
                    else if (type === 'project') this.navigateTo('projects');
                    else if (type === 'conversation') this.navigateTo('conversations');
                });
            });
        } catch (err) {
            console.error('Search failed:', err);
            resultsEl.innerHTML = '<div class="search-no-results">Search failed.</div>';
            resultsEl.style.display = 'block';
        }
    },

    _hideSearchResults() {
        const resultsEl = document.getElementById('search-results');
        if (resultsEl) resultsEl.style.display = 'none';
    },

    // ─── Dashboard ────────────────────────────────────────────────────

    async loadDashboard() {
        try {
            const data = await API.admin.dashboard();
            const metrics = data.metrics || data;

            // Populate stat cards using existing HTML elements
            this._setText('stat-leads-week', metrics.leads_this_week ?? '--');
            this._setText('stat-active-projects', metrics.active_projects ?? '--');
            this._setText('stat-conversion', metrics.conversion_rate != null ? metrics.conversion_rate + '%' : '--');
            this._setText('stat-conversations', metrics.conversations_30d ?? '--');

            // Load recent leads table
            try {
                const leadsData = await API.admin.getLeads({ limit: 5 });
                const leads = leadsData.leads || leadsData || [];
                this._renderRecentLeads(leads);
            } catch (e) { console.error('Recent leads failed:', e); }

            // Load active projects table
            try {
                const projData = await API.admin.getActiveProjects();
                const projects = projData.projects || projData || [];
                this._renderActiveProjects(projects);
            } catch (e) { console.error('Active projects failed:', e); }

        } catch (err) {
            console.error('Dashboard load failed:', err);
            this._showViewError('dashboard', 'Failed to load dashboard data.');
        }
    },

    _setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    },

    _renderRecentLeads(leads) {
        const container = document.getElementById('recent-leads-table');
        if (!container) return;

        if (leads.length === 0) {
            container.innerHTML = '<tr><td colspan="4" class="empty-state">No recent leads.</td></tr>';
            return;
        }

        container.innerHTML = leads.slice(0, 5).map((lead) => `
            <tr>
                <td>${this._escapeHtml(lead.name || '')}</td>
                <td>${this._escapeHtml(lead.source || '')}</td>
                <td><span class="status-badge status-${this._escapeAttr(lead.status || 'new')}">${this._escapeHtml(lead.status || 'new')}</span></td>
                <td>${lead.created_at ? this._formatDate(lead.created_at) : ''}</td>
            </tr>
        `).join('');
    },

    _renderActiveProjects(projects) {
        const container = document.getElementById('active-projects-table');
        if (!container) return;

        if (projects.length === 0) {
            container.innerHTML = '<tr><td colspan="4" class="empty-state">No active projects.</td></tr>';
            return;
        }

        container.innerHTML = projects.slice(0, 5).map((proj) => `
            <tr>
                <td>${this._escapeHtml(proj.description || proj.name || '')}</td>
                <td>${this._escapeHtml((proj.city || '') + (proj.state ? ', ' + proj.state : ''))}</td>
                <td><span class="stage-badge stage-${this._escapeAttr(proj.stage || '')}">${this._formatStage(proj.stage)}</span></td>
                <td>${proj.start_date ? this._formatDate(proj.start_date) : ''}</td>
            </tr>
        `).join('');
    },

    // ─── Leads ────────────────────────────────────────────────────────

    async loadLeads(params = {}) {
        const container = document.getElementById('leads-table-body');
        if (!container) return;

        try {
            const data = await API.admin.getLeads(params);
            this.leads = data.leads || data || [];

            if (this.leads.length === 0) {
                container.innerHTML = '<tr><td colspan="7" class="empty-state">No leads found.</td></tr>';
                return;
            }

            container.innerHTML = this.leads.map((lead) => `
                <tr data-lead-id="${this._escapeAttr(lead.id)}">
                    <td>${this._escapeHtml(lead.name || '')}</td>
                    <td>${this._escapeHtml(lead.email || '')}</td>
                    <td>${this._escapeHtml(lead.phone || '')}</td>
                    <td>${this._escapeHtml(lead.source || '')}</td>
                    <td>
                        <select class="lead-status-select" data-lead-id="${this._escapeAttr(lead.id)}">
                            ${['new', 'contacted', 'qualified', 'quoted', 'won', 'lost'].map((s) =>
                                `<option value="${s}" ${lead.status === s ? 'selected' : ''}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`
                            ).join('')}
                        </select>
                    </td>
                    <td>${lead.created_at ? this._formatDate(lead.created_at) : ''}</td>
                    <td>
                        <button class="btn-sm btn-edit" data-lead-id="${this._escapeAttr(lead.id)}">Edit</button>
                    </td>
                </tr>
            `).join('');

            // Bind status change
            container.querySelectorAll('.lead-status-select').forEach((sel) => {
                sel.addEventListener('change', async (e) => {
                    const leadId = e.target.dataset.leadId;
                    const newStatus = e.target.value;
                    let lossReason = null;

                    if (newStatus === 'lost') {
                        lossReason = prompt('Reason for loss (optional):');
                    }

                    try {
                        await API.admin.updateLeadStatus(leadId, newStatus, lossReason);
                    } catch (err) {
                        console.error('Failed to update lead status:', err);
                        alert('Failed to update status.');
                        this.loadLeads(params);
                    }
                });
            });

        } catch (err) {
            console.error('Failed to load leads:', err);
            container.innerHTML = '<tr><td colspan="7" class="empty-state">Failed to load leads.</td></tr>';
        }

        // Bind filter controls
        this._bindLeadFilters();
    },

    _bindLeadFilters() {
        const statusFilter = document.getElementById('leads-filter-status');
        const sourceFilter = document.getElementById('leads-filter-source');

        const applyFilters = () => {
            const params = {};
            if (statusFilter && statusFilter.value) params.status = statusFilter.value;
            if (sourceFilter && sourceFilter.value) params.source = sourceFilter.value;
            this.loadLeads(params);
        };

        if (statusFilter && !statusFilter.dataset.bound) {
            statusFilter.addEventListener('change', applyFilters);
            statusFilter.dataset.bound = 'true';
        }
        if (sourceFilter && !sourceFilter.dataset.bound) {
            sourceFilter.addEventListener('change', applyFilters);
            sourceFilter.dataset.bound = 'true';
        }
    },

    // ─── Estimates ────────────────────────────────────────────────────

    async loadEstimates(params = {}) {
        const container = document.getElementById('estimates-table-body');
        if (!container) return;

        try {
            const data = await API.admin.getEstimates(params);
            this.estimates = data.estimates || data || [];

            if (this.estimates.length === 0) {
                container.innerHTML = '<tr><td colspan="6" class="empty-state">No estimates found.</td></tr>';
                return;
            }

            container.innerHTML = this.estimates.map((est) => `
                <tr data-estimate-id="${this._escapeAttr(est.id)}">
                    <td>${this._escapeHtml(est.lead_name || est.customer_name || '')}</td>
                    <td>${this._escapeHtml(est.description || est.title || '')}</td>
                    <td>${this._formatCurrency(est.amount || est.total || 0)}</td>
                    <td>
                        <select class="estimate-status-select" data-estimate-id="${this._escapeAttr(est.id)}">
                            ${['draft', 'sent', 'viewed', 'accepted', 'rejected', 'expired'].map((s) =>
                                `<option value="${s}" ${est.status === s ? 'selected' : ''}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`
                            ).join('')}
                        </select>
                    </td>
                    <td>${est.created_at ? this._formatDate(est.created_at) : ''}</td>
                    <td>
                        <button class="btn-sm btn-edit" data-estimate-id="${this._escapeAttr(est.id)}">Edit</button>
                    </td>
                </tr>
            `).join('');

            // Bind status change
            container.querySelectorAll('.estimate-status-select').forEach((sel) => {
                sel.addEventListener('change', async (e) => {
                    const estId = e.target.dataset.estimateId;
                    const newStatus = e.target.value;
                    try {
                        await API.admin.updateEstimateStatus(estId, newStatus);
                    } catch (err) {
                        console.error('Failed to update estimate status:', err);
                        alert('Failed to update status.');
                        this.loadEstimates(params);
                    }
                });
            });

        } catch (err) {
            console.error('Failed to load estimates:', err);
            container.innerHTML = '<tr><td colspan="6" class="empty-state">Failed to load estimates.</td></tr>';
        }
    },

    // ─── Projects ─────────────────────────────────────────────────────

    async loadProjects(params = {}) {
        const container = document.getElementById('projects-container');
        if (!container) return;

        try {
            const data = await API.admin.getProjects(params);
            this.projects = data.projects || data || [];

            if (this.projects.length === 0) {
                container.innerHTML = '<p class="empty-state">No projects found.</p>';
                return;
            }

            const stages = ['scheduled', 'prep', 'in_progress', 'installation', 'grouting', 'inspection', 'completed'];

            container.innerHTML = this.projects.map((proj) => {
                const stageIdx = stages.indexOf(proj.stage || 'scheduled');
                const percent = stageIdx >= 0 ? Math.round(((stageIdx + 1) / stages.length) * 100) : 0;

                return `
                    <div class="project-card" data-project-id="${this._escapeAttr(proj.id)}">
                        <div class="project-header">
                            <h3 class="project-title">${this._escapeHtml(proj.name || proj.title || '')}</h3>
                            <span class="stage-badge stage-${this._escapeAttr(proj.stage || 'scheduled')}">${this._formatStage(proj.stage)}</span>
                        </div>
                        <div class="project-details">
                            <div class="project-customer">${this._escapeHtml(proj.customer_name || '')}</div>
                            <div class="project-address">${this._escapeHtml(proj.address || '')}</div>
                            ${proj.start_date ? `<div class="project-dates">Start: ${this._formatDate(proj.start_date)}</div>` : ''}
                            ${proj.estimated_value ? `<div class="project-value">${this._formatCurrency(proj.estimated_value)}</div>` : ''}
                        </div>
                        <div class="project-progress">
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${percent}%"></div>
                            </div>
                            <span class="progress-label">${percent}%</span>
                        </div>
                        <div class="project-stage-controls">
                            <label>Stage:</label>
                            <select class="project-stage-select" data-project-id="${this._escapeAttr(proj.id)}">
                                ${stages.map((s) =>
                                    `<option value="${s}" ${proj.stage === s ? 'selected' : ''}>${this._formatStage(s)}</option>`
                                ).join('')}
                            </select>
                        </div>
                    </div>
                `;
            }).join('');

            // Bind stage change
            container.querySelectorAll('.project-stage-select').forEach((sel) => {
                sel.addEventListener('change', async (e) => {
                    const projId = e.target.dataset.projectId;
                    const newStage = e.target.value;
                    try {
                        await API.admin.updateProjectStage(projId, newStage);
                        this.loadProjects(params);
                    } catch (err) {
                        console.error('Failed to update project stage:', err);
                        alert('Failed to update stage.');
                        this.loadProjects(params);
                    }
                });
            });

        } catch (err) {
            console.error('Failed to load projects:', err);
            container.innerHTML = '<p class="empty-state">Failed to load projects.</p>';
        }
    },

    // ─── Conversations ────────────────────────────────────────────────

    async loadConversations() {
        const listEl = document.getElementById('convo-list-items');
        if (!listEl) return;

        try {
            const data = await API.admin.conversations(50, 0);
            this.conversations = data.conversations || data || [];

            if (this.conversations.length === 0) {
                listEl.innerHTML = '<p class="empty-state">No conversations found.</p>';
                return;
            }

            listEl.innerHTML = this.conversations.map((conv) => `
                <div class="admin-conv-item" data-conv-id="${this._escapeAttr(conv.id)}">
                    <div class="admin-conv-user">${this._escapeHtml(conv.user_name || conv.email || 'Unknown')}</div>
                    <div class="admin-conv-preview">${this._escapeHtml((conv.last_message || '').substring(0, 80))}</div>
                    <div class="admin-conv-time">${conv.updated_at ? this._formatDate(conv.updated_at) : ''}</div>
                </div>
            `).join('');

            listEl.querySelectorAll('.admin-conv-item').forEach((item) => {
                item.addEventListener('click', () => {
                    const convId = item.dataset.convId;
                    this.viewConversation(convId);
                    listEl.querySelectorAll('.admin-conv-item').forEach((el) => {
                        el.classList.toggle('active', el.dataset.convId === convId);
                    });
                });
            });

        } catch (err) {
            console.error('Failed to load conversations:', err);
            listEl.innerHTML = '<p class="empty-state">Failed to load conversations.</p>';
        }
    },

    async viewConversation(convId) {
        const messagesEl = document.getElementById('convo-messages');
        if (!messagesEl) return;

        messagesEl.innerHTML = '<p class="loading">Loading messages...</p>';

        try {
            const data = await API.getMessages(convId);
            const messages = data.messages || data || [];

            if (messages.length === 0) {
                messagesEl.innerHTML = '<p class="empty-state">No messages in this conversation.</p>';
                return;
            }

            messagesEl.innerHTML = messages.map((msg) => `
                <div class="admin-message admin-message-${this._escapeAttr(msg.role || 'user')}">
                    <div class="admin-message-header">
                        <span class="admin-message-role">${this._escapeHtml(msg.role || 'user')}</span>
                        <span class="admin-message-time">${msg.timestamp ? this._formatDateTime(msg.timestamp) : ''}</span>
                    </div>
                    <div class="admin-message-content">${this._escapeHtml(msg.content || '')}</div>
                </div>
            `).join('');

            messagesEl.scrollTop = messagesEl.scrollHeight;
        } catch (err) {
            console.error('Failed to load conversation messages:', err);
            messagesEl.innerHTML = '<p class="empty-state">Failed to load messages.</p>';
        }
    },

    // ─── Modals ───────────────────────────────────────────────────────

    bindModals() {
        // Create Lead button
        const createLeadBtn = document.getElementById('create-lead-btn');
        if (createLeadBtn) {
            createLeadBtn.addEventListener('click', () => this.showModal('lead-modal'));
        }

        // Create Estimate button
        const createEstimateBtn = document.getElementById('create-estimate-btn');
        if (createEstimateBtn) {
            createEstimateBtn.addEventListener('click', () => this.showModal('estimate-modal'));
        }

        // Create Project button
        const createProjectBtn = document.getElementById('create-project-btn');
        if (createProjectBtn) {
            createProjectBtn.addEventListener('click', () => this.showModal('project-modal'));
        }

        // Close modal buttons
        document.querySelectorAll('.modal-close, .modal-cancel').forEach((btn) => {
            btn.addEventListener('click', () => {
                const modal = btn.closest('.modal-overlay');
                if (modal) this.hideModal(modal.id);
            });
        });

        // Close modal on backdrop click
        document.querySelectorAll('.modal-overlay').forEach((modal) => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this.hideModal(modal.id);
            });
        });

        // Lead form submit
        const leadForm = document.getElementById('lead-form');
        if (leadForm) {
            leadForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleCreateLead();
            });
        }

        // Estimate form submit
        const estimateForm = document.getElementById('estimate-form');
        if (estimateForm) {
            estimateForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleCreateEstimate();
            });
        }

        // Project form submit
        const projectForm = document.getElementById('project-form');
        if (projectForm) {
            projectForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleCreateProject();
            });
        }
    },

    showModal(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.style.display = 'flex';
            // Reset form inside
            const form = modal.querySelector('form');
            if (form) form.reset();
        }
    },

    hideModal(id) {
        const modal = document.getElementById(id);
        if (modal) modal.style.display = 'none';
    },

    async handleCreateLead() {
        const data = {
            name: document.getElementById('lead-name')?.value.trim() || '',
            email: document.getElementById('lead-email')?.value.trim() || '',
            phone: document.getElementById('lead-phone')?.value.trim() || '',
            source: document.getElementById('lead-source')?.value || '',
            notes: document.getElementById('lead-notes')?.value.trim() || '',
            address: document.getElementById('lead-address')?.value.trim() || '',
            service_type: document.getElementById('lead-service-type')?.value || '',
        };

        if (!data.name) {
            alert('Name is required.');
            return;
        }

        try {
            await API.admin.createLead(data);
            this.hideModal('lead-modal');
            this.loadLeads();
            if (this.currentView === 'dashboard') this.loadDashboard();
        } catch (err) {
            console.error('Failed to create lead:', err);
            alert('Failed to create lead: ' + err.message);
        }
    },

    async handleCreateEstimate() {
        const data = {
            lead_id: document.getElementById('estimate-lead-id')?.value || '',
            customer_name: document.getElementById('estimate-customer')?.value.trim() || '',
            description: document.getElementById('estimate-description')?.value.trim() || '',
            amount: parseFloat(document.getElementById('estimate-amount')?.value) || 0,
            notes: document.getElementById('estimate-notes')?.value.trim() || '',
            valid_until: document.getElementById('estimate-valid-until')?.value || '',
        };

        if (!data.customer_name && !data.lead_id) {
            alert('Customer name or lead is required.');
            return;
        }

        try {
            await API.admin.createEstimate(data);
            this.hideModal('estimate-modal');
            this.loadEstimates();
            if (this.currentView === 'dashboard') this.loadDashboard();
        } catch (err) {
            console.error('Failed to create estimate:', err);
            alert('Failed to create estimate: ' + err.message);
        }
    },

    async handleCreateProject() {
        const data = {
            name: document.getElementById('project-name')?.value.trim() || '',
            customer_name: document.getElementById('project-customer')?.value.trim() || '',
            address: document.getElementById('project-address')?.value.trim() || '',
            description: document.getElementById('project-description')?.value.trim() || '',
            estimated_value: parseFloat(document.getElementById('project-value')?.value) || 0,
            start_date: document.getElementById('project-start-date')?.value || '',
            stage: 'scheduled',
        };

        if (!data.name) {
            alert('Project name is required.');
            return;
        }

        try {
            await API.admin.createProject(data);
            this.hideModal('project-modal');
            this.loadProjects();
            if (this.currentView === 'dashboard') this.loadDashboard();
        } catch (err) {
            console.error('Failed to create project:', err);
            alert('Failed to create project: ' + err.message);
        }
    },

    // ─── Marketing ────────────────────────────────────────────────────

    async loadMarketing() {
        this._bindMarketingTabs();
        this.loadSeoTerms();
        this.loadReviews();
        this.loadContent();
        this._bindMarketingForms();
    },

    _bindMarketingTabs() {
        document.querySelectorAll('.marketing-tab').forEach((btn) => {
            if (btn.dataset.bound) return;
            btn.addEventListener('click', () => {
                document.querySelectorAll('.marketing-tab').forEach(b => {
                    b.classList.remove('active', 'btn-primary');
                    b.classList.add('btn-outline');
                });
                document.querySelectorAll('.marketing-panel').forEach(p => p.style.display = 'none');
                btn.classList.add('active', 'btn-primary');
                btn.classList.remove('btn-outline');
                const panel = document.getElementById('mtab-' + btn.dataset.mtab);
                if (panel) panel.style.display = '';
            });
            btn.dataset.bound = 'true';
        });
    },

    _bindMarketingForms() {
        // Add SEO term
        const addTermBtn = document.getElementById('btn-add-seo-term');
        if (addTermBtn && !addTermBtn.dataset.bound) {
            addTermBtn.addEventListener('click', () => this.addSeoTerm());
            addTermBtn.dataset.bound = 'true';
        }

        // Run SEO check
        const seoCheckBtn = document.getElementById('btn-seo-check');
        if (seoCheckBtn && !seoCheckBtn.dataset.bound) {
            seoCheckBtn.addEventListener('click', () => this.runSeoCheck());
            seoCheckBtn.dataset.bound = 'true';
        }

        // Generate review response
        const reviewGenBtn = document.getElementById('btn-generate-review');
        if (reviewGenBtn && !reviewGenBtn.dataset.bound) {
            reviewGenBtn.addEventListener('click', () => this.generateReview());
            reviewGenBtn.dataset.bound = 'true';
        }

        // Generate content
        const contentGenBtn = document.getElementById('btn-generate-content');
        if (contentGenBtn && !contentGenBtn.dataset.bound) {
            contentGenBtn.addEventListener('click', () => this.generateContent());
            contentGenBtn.dataset.bound = 'true';
        }

        // Sync GSC
        const syncGscBtn = document.getElementById('btn-sync-gsc');
        if (syncGscBtn && !syncGscBtn.dataset.bound) {
            syncGscBtn.addEventListener('click', () => this.syncGsc());
            syncGscBtn.dataset.bound = 'true';
        }
    },

    // SEO
    async loadSeoTerms() {
        const tbody = document.getElementById('seo-terms-body');
        if (!tbody) return;

        try {
            const data = await API.admin.marketing.seoDashboard();
            const rankings = data.rankings || [];

            // Update stat cards
            this._setText('seo-total-terms', data.total_terms || 0);
            this._setText('seo-terms-found', data.terms_found || 0);
            this._setText('seo-first-page', data.first_page || 0);
            this._setText('seo-total-clicks', data.total_clicks || 0);
            this._setText('seo-total-impressions', data.total_impressions || 0);
            this._setText('seo-avg-position', data.avg_position != null ? data.avg_position : '—');

            // GSC status
            const gscStatus = document.getElementById('gsc-status');
            if (gscStatus) {
                gscStatus.textContent = data.gsc_connected
                    ? 'Google Search Console connected'
                    : 'Google Search Console not configured — using scraping fallback';
            }

            if (rankings.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No SEO terms tracked yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rankings.map(r => `
                <tr>
                    <td>${this._escapeHtml(r.term)}</td>
                    <td>${this._escapeHtml(r.city)}</td>
                    <td>${r.position != null ? r.position : '—'}</td>
                    <td>${r.clicks || 0}</td>
                    <td>${r.impressions || 0}</td>
                    <td>${r.ctr ? (r.ctr * 100).toFixed(1) + '%' : '—'}</td>
                    <td>${r.last_checked ? this._formatDate(r.last_checked) : 'Never'}</td>
                    <td>
                        <button class="btn-sm btn-danger seo-delete-term" data-term-id="${this._escapeAttr(r.term_id)}">Delete</button>
                    </td>
                </tr>
            `).join('');

            tbody.querySelectorAll('.seo-delete-term').forEach(btn => {
                btn.addEventListener('click', async () => {
                    if (!confirm('Delete this search term?')) return;
                    try {
                        await API.admin.marketing.deleteSeoTerm(btn.dataset.termId);
                        this.loadSeoTerms();
                    } catch (e) { alert('Failed to delete: ' + e.message); }
                });
            });
        } catch (err) {
            console.error('Failed to load SEO terms:', err);
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Failed to load SEO data.</td></tr>';
        }
    },

    async addSeoTerm() {
        const term = document.getElementById('seo-term')?.value.trim();
        const city = document.getElementById('seo-city')?.value.trim();
        if (!term || !city) { alert('Enter both search term and city.'); return; }

        try {
            await API.admin.marketing.addSeoTerm({ term, city, state: 'FL' });
            document.getElementById('seo-term').value = '';
            document.getElementById('seo-city').value = '';
            this.loadSeoTerms();
        } catch (err) {
            alert('Failed to add term: ' + err.message);
        }
    },

    async runSeoCheck() {
        const btn = document.getElementById('btn-seo-check');
        if (btn) { btn.disabled = true; btn.textContent = 'Checking...'; }
        try {
            const result = await API.admin.marketing.runSeoCheck();
            alert(`SEO check complete! Checked ${result.checked || 0} terms. Source: ${result.source || 'scrape'}. ${(result.alerts || []).length} alerts.`);
            this.loadSeoTerms();
        } catch (err) {
            alert('SEO check failed: ' + err.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Run Check'; }
        }
    },

    async syncGsc() {
        const btn = document.getElementById('btn-sync-gsc');
        if (btn) { btn.disabled = true; btn.textContent = 'Syncing...'; }
        try {
            const result = await API.admin.marketing.syncGsc();
            if (result.error) {
                alert(result.error);
            } else {
                alert(`GSC sync complete! Matched ${result.matched || 0} of ${result.checked || 0} terms. GSC returned ${result.gsc_queries || 0} queries.`);
            }
            this.loadSeoTerms();
        } catch (err) {
            alert('GSC sync failed: ' + err.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Sync GSC'; }
        }
    },

    // Reviews
    async loadReviews() {
        const tbody = document.getElementById('reviews-body');
        if (!tbody) return;

        try {
            const data = await API.admin.marketing.getReviews();
            const responses = data.responses || [];

            if (responses.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No review responses yet.</td></tr>';
                return;
            }

            tbody.innerHTML = responses.map(r => `
                <tr>
                    <td>${this._escapeHtml(r.platform)}</td>
                    <td>${this._escapeHtml(r.reviewer_name)}</td>
                    <td>${r.rating}/5</td>
                    <td>${this._escapeHtml((r.ai_response || '').substring(0, 80))}...</td>
                    <td><span class="status-badge status-${this._escapeAttr(r.status)}">${this._escapeHtml(r.status)}</span></td>
                    <td>
                        ${r.status === 'draft' ? `<button class="btn-sm btn-success review-approve" data-id="${this._escapeAttr(r.id)}">Approve</button>` : ''}
                        ${r.status === 'approved' ? `<button class="btn-sm btn-primary review-post" data-id="${this._escapeAttr(r.id)}">Mark Posted</button>` : ''}
                    </td>
                </tr>
            `).join('');

            tbody.querySelectorAll('.review-approve').forEach(btn => {
                btn.addEventListener('click', async () => {
                    try { await API.admin.marketing.updateReview(btn.dataset.id, 'approved'); this.loadReviews(); }
                    catch (e) { alert('Failed: ' + e.message); }
                });
            });
            tbody.querySelectorAll('.review-post').forEach(btn => {
                btn.addEventListener('click', async () => {
                    try { await API.admin.marketing.updateReview(btn.dataset.id, 'posted'); this.loadReviews(); }
                    catch (e) { alert('Failed: ' + e.message); }
                });
            });
        } catch (err) {
            console.error('Failed to load reviews:', err);
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Failed to load reviews.</td></tr>';
        }
    },

    async generateReview() {
        const platform = document.getElementById('review-platform')?.value || '';
        const reviewer_name = document.getElementById('review-name')?.value.trim() || 'Customer';
        const rating = parseInt(document.getElementById('review-rating')?.value) || 5;
        const review_text = document.getElementById('review-text')?.value.trim() || '';

        if (!review_text) { alert('Enter the review text.'); return; }

        const btn = document.getElementById('btn-generate-review');
        if (btn) { btn.disabled = true; btn.textContent = 'Generating...'; }
        const resultEl = document.getElementById('review-result');

        try {
            const data = await API.admin.marketing.generateReview({ platform, reviewer_name, rating, review_text });
            const resp = data.review_response || data;
            if (resultEl) {
                resultEl.style.display = 'block';
                resultEl.innerHTML = `<strong>AI Response:</strong><br>${this._escapeHtml(resp.ai_response || '')}`;
            }
            this.loadReviews();
        } catch (err) {
            alert('Failed to generate: ' + err.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Generate Response'; }
        }
    },

    // Content
    async loadContent() {
        const tbody = document.getElementById('content-body');
        if (!tbody) return;

        try {
            const data = await API.admin.marketing.getContent();
            const items = data.content || [];

            if (items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No content generated yet.</td></tr>';
                return;
            }

            tbody.innerHTML = items.map(c => `
                <tr>
                    <td>${this._escapeHtml(c.content_type)}</td>
                    <td>${this._escapeHtml(c.platform)}</td>
                    <td>${this._escapeHtml(c.city)}</td>
                    <td>${this._escapeHtml((c.content_text || '').substring(0, 100))}...</td>
                    <td><span class="status-badge status-${this._escapeAttr(c.status)}">${this._escapeHtml(c.status)}</span></td>
                    <td>
                        ${c.status === 'draft' ? `<button class="btn-sm btn-success content-approve" data-id="${this._escapeAttr(c.id)}">Approve</button>` : ''}
                        ${c.status === 'approved' ? `<button class="btn-sm btn-primary content-post" data-id="${this._escapeAttr(c.id)}">Mark Posted</button>` : ''}
                    </td>
                </tr>
            `).join('');

            tbody.querySelectorAll('.content-approve').forEach(btn => {
                btn.addEventListener('click', async () => {
                    try { await API.admin.marketing.updateContent(btn.dataset.id, 'approved'); this.loadContent(); }
                    catch (e) { alert('Failed: ' + e.message); }
                });
            });
            tbody.querySelectorAll('.content-post').forEach(btn => {
                btn.addEventListener('click', async () => {
                    try { await API.admin.marketing.updateContent(btn.dataset.id, 'posted'); this.loadContent(); }
                    catch (e) { alert('Failed: ' + e.message); }
                });
            });
        } catch (err) {
            console.error('Failed to load content:', err);
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Failed to load content.</td></tr>';
        }
    },

    async generateContent() {
        const platform = document.getElementById('content-platform')?.value || 'instagram';
        const city = document.getElementById('content-city')?.value.trim() || '';
        const service = document.getElementById('content-service')?.value.trim() || '';
        const content_type = 'social_post';

        if (!city || !service) { alert('Enter city and service.'); return; }

        const btn = document.getElementById('btn-generate-content');
        if (btn) { btn.disabled = true; btn.textContent = 'Generating...'; }
        const resultEl = document.getElementById('content-result');

        try {
            const data = await API.admin.marketing.generateContent({ content_type, platform, city, service });
            const item = data.content || data;
            if (resultEl) {
                resultEl.style.display = 'block';
                resultEl.innerHTML = `<strong>Generated Content:</strong><br>${this._escapeHtml(item.content_text || '')}`;
            }
            this.loadContent();
        } catch (err) {
            alert('Failed to generate: ' + err.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Generate Post'; }
        }
    },

    // ─── Utilities ────────────────────────────────────────────────────

    _show(id) {
        const el = document.getElementById(id);
        if (el) el.style.display = '';
    },

    _hide(id) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    },

    _showError(el, msg) {
        if (el) {
            el.textContent = msg;
            el.style.display = msg ? 'block' : 'none';
        }
    },

    _showViewError(view, msg) {
        const container = document.getElementById(`view-${view}`);
        if (!container) return;
        let errEl = container.querySelector('.view-error');
        if (!errEl) {
            errEl = document.createElement('div');
            errEl.className = 'view-error';
            container.prepend(errEl);
        }
        errEl.textContent = msg;
        errEl.style.display = msg ? 'block' : 'none';
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    },

    _escapeAttr(text) {
        return (text || '').toString().replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },

    _formatCurrency(amount) {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount || 0);
    },

    _formatDate(isoString) {
        try {
            return new Date(isoString).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch { return ''; }
    },

    _formatDateTime(isoString) {
        try {
            const d = new Date(isoString);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
                   d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        } catch { return ''; }
    },

    _formatStage(stage) {
        if (!stage) return '';
        return stage.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    },

    _stagePercent(stage) {
        const stages = ['scheduled', 'prep', 'in_progress', 'installation', 'grouting', 'inspection', 'completed'];
        const idx = stages.indexOf(stage || 'scheduled');
        return idx >= 0 ? Math.round(((idx + 1) / stages.length) * 100) : 0;
    },

    // ─── Blog AI ─────────────────────────────────────────────────────

    async loadBlog() {
        this._blogBindEvents();
        await this._blogLoadSchedule();
        await this._blogLoadPosts();
    },

    _blogBound: false,
    _blogBindEvents() {
        if (this._blogBound) return;
        this._blogBound = true;

        document.getElementById('btn-generate-post')?.addEventListener('click', () => this._blogGenerate(false));
        document.getElementById('btn-generate-batch')?.addEventListener('click', () => this._blogGenerate(true));
        document.getElementById('btn-load-topics')?.addEventListener('click', () => this._blogLoadTopics());
        document.getElementById('blog-filter-status')?.addEventListener('change', () => this._blogLoadPosts());
        document.getElementById('btn-save-schedule')?.addEventListener('click', () => this._blogSaveSchedule());
    },

    _blogUpdateToggleVisual(enabled) {
        const box = document.getElementById('schedule-toggle-box');
        const label = document.getElementById('schedule-on-off');
        if (box) {
            box.style.borderColor = enabled ? '#27ae60' : '#ccc';
            box.style.background = enabled ? '#f0faf3' : 'transparent';
        }
        if (label) {
            label.textContent = enabled ? 'ON' : 'OFF';
            label.style.color = enabled ? '#27ae60' : '#999';
        }
    },

    async _blogLoadSchedule() {
        try {
            const s = await API.get('/blog/admin/schedule');
            const chk1 = document.getElementById('schedule-enabled');
            const chk2 = document.getElementById('schedule-enabled-inline');
            if (chk1) chk1.checked = s.enabled;
            if (chk2) chk2.checked = s.enabled;
            document.getElementById('schedule-posts-per-day').value = s.posts_per_day || 2;
            document.getElementById('schedule-hour').value = s.publish_hour || 8;
            document.getElementById('schedule-auto-publish').checked = s.auto_publish !== false;
            this._blogUpdateToggleVisual(s.enabled);
            const statusText = document.getElementById('schedule-status-text');
            if (s.enabled) {
                statusText.textContent = `${s.posts_per_day} posts/day at ${s.publish_hour}:00 UTC`;
                statusText.style.color = '#27ae60';
            } else {
                statusText.textContent = 'Disabled';
                statusText.style.color = 'var(--text-muted)';
            }
            if (s.last_run_at) {
                const lastRun = new Date(s.last_run_at);
                statusText.textContent += ` • Last: ${lastRun.toLocaleDateString()} (${s.posts_generated_today} posts)`;
            }
        } catch(e) { console.error('Schedule load error:', e); }
    },

    async _blogSaveSchedule() {
        const statusEl = document.getElementById('schedule-save-status');
        const inlineChk = document.getElementById('schedule-enabled-inline');
        const headerChk = document.getElementById('schedule-enabled');
        const enabled = inlineChk ? inlineChk.checked : (headerChk ? headerChk.checked : false);
        try {
            const data = {
                enabled: enabled,
                posts_per_day: parseInt(document.getElementById('schedule-posts-per-day').value),
                publish_hour: parseInt(document.getElementById('schedule-hour').value),
                auto_publish: document.getElementById('schedule-auto-publish').checked,
            };
            await API.patch('/blog/admin/schedule', data);
            statusEl.textContent = enabled ? 'Saved! Scheduler ON' : 'Saved! Scheduler OFF';
            statusEl.style.color = '#27ae60';
            await this._blogLoadSchedule();
            setTimeout(() => { statusEl.textContent = ''; }, 4000);
        } catch(e) {
            statusEl.textContent = 'Error: ' + (e.message || 'Failed');
            statusEl.style.color = '#e74c3c';
        }
    },

    async _blogLoadPosts() {
        const status = document.getElementById('blog-filter-status')?.value || '';
        try {
            const url = status ? `/blog/admin/posts?status=${status}` : '/blog/admin/posts';
            const data = await API.get(url);
            if (data.stats) {
                document.getElementById('blog-total').textContent = data.stats.total || 0;
                document.getElementById('blog-published').textContent = data.stats.published || 0;
                document.getElementById('blog-drafts').textContent = data.stats.drafts || 0;
                document.getElementById('blog-views').textContent = data.stats.total_views || 0;
            }
            const tbody = document.getElementById('blog-posts-body');
            if (!data.posts?.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;" class="text-muted">No posts yet. Generate your first post!</td></tr>';
                return;
            }
            tbody.innerHTML = data.posts.map(p => `
                <tr>
                    <td><a href="/blog/${p.slug}/" target="_blank" style="font-weight:600;">${this._escapeHtml(p.title)}</a></td>
                    <td>${p.category || '-'}</td>
                    <td>${p.city || '-'}</td>
                    <td><span class="status-badge status-${p.status}">${p.status}</span></td>
                    <td>${p.views || 0}</td>
                    <td>${p.created_at ? new Date(p.created_at).toLocaleDateString() : '-'}</td>
                    <td style="white-space:nowrap;">
                        <button class="btn btn-sm btn-outline" onclick="Admin._blogPreview('${p.slug}')">Preview</button>
                        ${p.status === 'draft' ? `<button class="btn btn-sm btn-primary" onclick="Admin._blogPublish('${p.id}')">Publish</button>` : ''}
                        ${p.status === 'published' ? `<button class="btn btn-sm btn-outline" onclick="Admin._blogArchive('${p.id}')">Archive</button>` : ''}
                        <button class="btn btn-sm" style="color:#e74c3c;" onclick="Admin._blogDelete('${p.id}')">Delete</button>
                    </td>
                </tr>
            `).join('');
        } catch(e) {
            console.error('Blog load error:', e);
        }
    },

    async _blogGenerate(batch) {
        const statusEl = document.getElementById('blog-gen-status');
        const topic = document.getElementById('blog-topic')?.value?.trim() || null;
        const city = document.getElementById('blog-city')?.value?.trim() || null;
        const service = document.getElementById('blog-service')?.value || null;
        const keywords = document.getElementById('blog-keywords')?.value?.trim() || null;
        const autoPublish = document.getElementById('blog-auto-publish')?.checked || false;

        statusEl.textContent = batch ? 'Generating 5 posts... (this may take a minute)' : 'Generating post...';
        statusEl.style.color = 'var(--deep-blue)';

        try {
            let data;
            if (batch) {
                data = await API.post('/blog/admin/generate-batch', { count: 5, auto_publish: autoPublish });
                statusEl.textContent = `Done! Generated ${data.generated} posts. ${data.errors ? data.errors + ' errors.' : ''}`;
            } else {
                data = await API.post('/blog/admin/generate', { topic, city, service, keywords, auto_publish: autoPublish });
                statusEl.textContent = `Created: "${data.title}" (${data.cost_estimate})`;
            }
            statusEl.style.color = '#27ae60';
            document.getElementById('blog-topic').value = '';
            await this._blogLoadPosts();
        } catch(e) {
            statusEl.textContent = 'Error: ' + (e.message || 'Generation failed');
            statusEl.style.color = '#e74c3c';
        }
    },

    async _blogPublish(id) {
        try {
            await API.patch(`/blog/admin/posts/${id}`, { status: 'published' });
            await this._blogLoadPosts();
        } catch(e) { alert('Error publishing: ' + e.message); }
    },

    async _blogArchive(id) {
        try {
            await API.patch(`/blog/admin/posts/${id}`, { status: 'archived' });
            await this._blogLoadPosts();
        } catch(e) { alert('Error archiving: ' + e.message); }
    },

    async _blogDelete(id) {
        if (!confirm('Delete this post permanently?')) return;
        try {
            await API.delete(`/blog/admin/posts/${id}`);
            await this._blogLoadPosts();
        } catch(e) { alert('Error deleting: ' + e.message); }
    },

    async _blogPreview(slug) {
        const modal = document.getElementById('modal-blog-preview');
        const body = document.getElementById('blog-preview-body');
        if (!modal || !body) return;
        body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">Loading preview...</div>';
        modal.style.display = 'flex';
        try {
            const post = await API.get(`/blog/posts/${slug}`);
            body.innerHTML = `
                <div style="margin-bottom:16px;">
                    <span class="status-badge status-${post.status}" style="margin-right:8px;">${post.status}</span>
                    <span style="color:var(--text-muted);font-size:0.85rem;">${post.category || ''} ${post.city ? '• ' + post.city : ''} • ${post.views || 0} views</span>
                </div>
                <h2 style="margin-bottom:8px;font-size:1.4rem;">${this._escapeHtml(post.title)}</h2>
                <p style="color:var(--text-muted);font-size:0.9rem;margin-bottom:16px;font-style:italic;">${this._escapeHtml(post.meta_description || '')}</p>
                <div style="border-top:1px solid var(--border);padding-top:16px;line-height:1.8;font-size:0.95rem;">
                    ${post.content}
                </div>
                ${post.tags?.length ? '<div style="margin-top:16px;display:flex;gap:6px;flex-wrap:wrap;">' + post.tags.map(t => '<span style="background:var(--bg-secondary);padding:2px 10px;border-radius:12px;font-size:0.8rem;">' + this._escapeHtml(t) + '</span>').join('') + '</div>' : ''}
                <div style="margin-top:20px;display:flex;gap:8px;">
                    <a href="/blog/${slug}/" target="_blank" class="btn btn-sm btn-primary">Open Full Page</a>
                </div>`;
        } catch(e) {
            body.innerHTML = '<p style="color:#e74c3c;">Error loading preview: ' + (e.message || 'Unknown error') + '</p>';
        }
    },

    async _blogLoadTopics() {
        const el = document.getElementById('blog-topics-list');
        try {
            const data = await API.get('/blog/admin/topics');
            if (!data.topics?.length) {
                el.innerHTML = '<p>All pre-defined topics have been used! Enter custom topics above.</p>';
                return;
            }
            el.innerHTML = `<p style="margin-bottom:0.5rem;font-weight:600;">${data.available} topics available:</p>` +
                data.topics.map(t => `<div style="padding:6px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
                    <span>${t.topic} ${t.city ? '<em style="color:var(--bright-yellow);">(' + t.city + ')</em>' : ''}</span>
                    <button class="btn btn-sm btn-outline" onclick="document.getElementById('blog-topic').value='${t.topic.replace(/'/g,"\\'")}';document.getElementById('blog-city').value='${t.city||''}';document.getElementById('blog-keywords').value='${(t.keywords||'').replace(/'/g,"\\'")}';this.textContent='Selected';">Use</button>
                </div>`).join('');
        } catch(e) { el.innerHTML = '<p style="color:#e74c3c;">Error loading topics</p>'; }
    }
};

document.addEventListener('DOMContentLoaded', () => Admin.init());
