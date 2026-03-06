// ENCPServices - API Client
const API = {
    baseUrl: '',
    token: null,

    init() {
        this.token = localStorage.getItem('encp_token');
    },

    setToken(token) {
        this.token = token;
        localStorage.setItem('encp_token', token);
    },

    clearToken() {
        this.token = null;
        localStorage.removeItem('encp_token');
        localStorage.removeItem('encp_refresh');
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },
    patch(path, body) { return this.request('PATCH', path, body); },
    delete(path) { return this.request('DELETE', path); },

    async request(method, path, body = null, options = {}) {
        const headers = { 'Content-Type': 'application/json' };
        if (this.token) headers['Authorization'] = `Bearer ${this.token}`;

        const config = { method, headers };
        if (body && method !== 'GET') config.body = JSON.stringify(body);

        const resp = await fetch(`${this.baseUrl}${path}`, config);

        if (resp.status === 401) {
            const refreshed = await this.refreshToken();
            if (refreshed) return this.request(method, path, body, options);
            this.clearToken();
            window.location.reload();
            throw new Error('Session expired');
        }

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        return resp.json();
    },

    async refreshToken() {
        const refresh = localStorage.getItem('encp_refresh');
        if (!refresh) return false;
        try {
            const resp = await fetch(`${this.baseUrl}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refresh })
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            this.setToken(data.access_token);
            if (data.refresh_token) localStorage.setItem('encp_refresh', data.refresh_token);
            return true;
        } catch { return false; }
    },

    // Auth
    login: (email, password) => API.request('POST', '/auth/login', { email, password }),
    register: (email, password, nome, phone) => API.request('POST', '/auth/register', { email, password, nome, phone }),

    // Chat
    sendMessage: (message, conversation_id) => API.request('POST', '/chat/', { message, conversation_id }),
    getHistory: (conversation_id) => API.request('GET', `/chat/history?conversation_id=${conversation_id || ''}`),
    getConversations: () => API.request('GET', '/chat/conversations'),
    getMessages: (convId, limit = 50) => API.request('GET', `/chat/conversations/${convId}/messages?limit=${limit}`),
    deleteConversation: (convId) => API.request('DELETE', `/chat/conversations/${convId}`),

    // Voice
    async sendVoice(audioBlob, conversationId) {
        const form = new FormData();
        form.append('audio', audioBlob, 'audio.webm');
        if (conversationId) form.append('conversation_id', conversationId);
        const headers = {};
        if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
        const resp = await fetch(`${this.baseUrl}/chat/voice`, { method: 'POST', headers, body: form });
        if (!resp.ok) throw new Error('Voice request failed');
        return resp.json();
    },

    // File upload
    async sendWithFiles(files, message, conversationId) {
        const form = new FormData();
        files.forEach(f => form.append('files', f));
        form.append('message', message || '');
        if (conversationId) form.append('conversation_id', conversationId);
        const headers = {};
        if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
        const resp = await fetch(`${this.baseUrl}/chat/with-file`, { method: 'POST', headers, body: form });
        if (!resp.ok) throw new Error('File upload failed');
        return resp.json();
    },

    // Profile
    getProfile: () => API.request('GET', '/profile/'),
    updateProfile: (data) => API.request('PATCH', '/profile/', data),

    // Memories
    getMemories: (categoria) => API.request('GET', `/memories/${categoria ? `?categoria=${categoria}` : ''}`),

    // TTS
    async getTTS(text, voice, provider) {
        const resp = await API.request('POST', '/voice/tts', { text, voice, provider });
        return resp;
    },

    // Admin endpoints
    admin: {
        dashboard: () => API.request('GET', '/admin/dashboard'),
        conversations: (limit, offset) => API.request('GET', `/admin/conversations?limit=${limit || 50}&offset=${offset || 0}`),
        search: (q) => API.request('GET', `/admin/search?q=${encodeURIComponent(q)}`),

        // Leads
        getLeads: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return API.request('GET', `/leads/${qs ? '?' + qs : ''}`);
        },
        getLead: (id) => API.request('GET', `/leads/${id}`),
        createLead: (data) => API.request('POST', '/leads/', data),
        updateLead: (id, data) => API.request('PATCH', `/leads/${id}`, data),
        updateLeadStatus: (id, status, loss_reason) => API.request('PATCH', `/leads/${id}/status`, { status, loss_reason }),
        getPipeline: () => API.request('GET', '/leads/pipeline'),
        getLeadStats: () => API.request('GET', '/leads/stats'),

        // Estimates
        getEstimates: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return API.request('GET', `/estimates/${qs ? '?' + qs : ''}`);
        },
        createEstimate: (data) => API.request('POST', '/estimates/', data),
        updateEstimate: (id, data) => API.request('PATCH', `/estimates/${id}`, data),
        updateEstimateStatus: (id, status) => API.request('PATCH', `/estimates/${id}/status`, { status }),

        // Projects
        getProjects: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return API.request('GET', `/projects/${qs ? '?' + qs : ''}`);
        },
        getActiveProjects: () => API.request('GET', '/projects/active'),
        createProject: (data) => API.request('POST', '/projects/', data),
        updateProject: (id, data) => API.request('PATCH', `/projects/${id}`, data),
        updateProjectStage: (id, stage) => API.request('PATCH', `/projects/${id}/stage`, { stage }),

        // Marketing
        marketing: {
            seoTerms: () => API.request('GET', '/marketing/seo/terms'),
            addSeoTerm: (data) => API.request('POST', '/marketing/seo/terms', data),
            deleteSeoTerm: (id) => API.request('DELETE', `/marketing/seo/terms/${id}`),
            runSeoCheck: () => API.request('POST', '/marketing/seo/check'),
            syncGsc: () => API.request('POST', '/marketing/seo/sync-gsc'),
            seoDashboard: () => API.request('GET', '/marketing/seo/dashboard'),
            generateReview: (data) => API.request('POST', '/marketing/reviews/generate', data),
            getReviews: (status) => API.request('GET', `/marketing/reviews${status ? '?status=' + status : ''}`),
            updateReview: (id, status) => API.request('PATCH', `/marketing/reviews/${id}`, { status }),
            generateContent: (data) => API.request('POST', '/marketing/content/generate', data),
            getContent: (status) => API.request('GET', `/marketing/content${status ? '?status=' + status : ''}`),
            updateContent: (id, status) => API.request('PATCH', `/marketing/content/${id}`, { status }),
        }
    }
};

API.init();
