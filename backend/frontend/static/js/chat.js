// ENCPServices - Chat Controller
const Chat = {
    currentConversation: null,
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    pendingFiles: [],
    language: 'en',

    // ─── Initialization ───────────────────────────────────────────────

    init() {
        API.init();
        this.language = localStorage.getItem('encp_lang') || 'en';
        if (API.token) {
            this.showChat();
            this.loadConversations();
        } else {
            this.showLogin();
        }
        this.bindEvents();
    },

    // ─── View Switching ───────────────────────────────────────────────

    showLogin() {
        this._hide('chat-container');
        this._hide('register-screen');
        this._show('login-screen');
    },

    showRegister() {
        this._hide('login-screen');
        this._hide('chat-container');
        this._show('register-screen');
    },

    showChat() {
        this._hide('login-screen');
        this._hide('register-screen');
        this._show('chat-container');
    },

    // ─── Event Binding ────────────────────────────────────────────────

    bindEvents() {
        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleLogin();
            });
        }

        // Register form
        const registerForm = document.getElementById('register-form');
        if (registerForm) {
            registerForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleRegister();
            });
        }

        // Switch to register
        const showRegisterLink = document.getElementById('show-register');
        if (showRegisterLink) {
            showRegisterLink.addEventListener('click', (e) => {
                e.preventDefault();
                this.showRegister();
            });
        }

        // Switch to login
        const showLoginLink = document.getElementById('show-login');
        if (showLoginLink) {
            showLoginLink.addEventListener('click', (e) => {
                e.preventDefault();
                this.showLogin();
            });
        }

        // Send message
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        // Message input - Enter to send, Shift+Enter for newline
        const msgInput = document.getElementById('message-input');
        if (msgInput) {
            msgInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
            // Auto-resize textarea
            msgInput.addEventListener('input', () => {
                msgInput.style.height = 'auto';
                msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + 'px';
            });
        }

        // Voice button
        const voiceBtn = document.getElementById('voice-btn');
        if (voiceBtn) {
            voiceBtn.addEventListener('click', () => this.toggleRecording());
        }

        // File upload button
        const fileBtn = document.getElementById('file-btn');
        if (fileBtn) {
            fileBtn.addEventListener('click', () => {
                const fileInput = document.getElementById('file-input');
                if (fileInput) fileInput.click();
            });
        }

        // File input change
        const fileInput = document.getElementById('file-input');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        }

        // New conversation
        const newConvBtn = document.getElementById('new-conversation-btn');
        if (newConvBtn) {
            newConvBtn.addEventListener('click', () => this.newConversation());
        }

        // Language selector
        const langSelect = document.getElementById('language-select');
        if (langSelect) {
            langSelect.value = this.language;
            langSelect.addEventListener('change', (e) => {
                this.language = e.target.value;
                localStorage.setItem('encp_lang', this.language);
            });
        }

        // Logout
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.logout());
        }
    },

    // ─── Authentication ───────────────────────────────────────────────

    async handleLogin() {
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');

        if (!email || !password) {
            this._showError(errorEl, 'Please enter email and password.');
            return;
        }

        this._showError(errorEl, '');
        this._setButtonLoading('login-btn', true);

        try {
            const data = await API.login(email, password);
            API.setToken(data.access_token);
            if (data.refresh_token) {
                localStorage.setItem('encp_refresh', data.refresh_token);
            }
            this.showChat();
            this.loadConversations();
        } catch (err) {
            this._showError(errorEl, err.message || 'Login failed. Please try again.');
        } finally {
            this._setButtonLoading('login-btn', false);
        }
    },

    async handleRegister() {
        const email = document.getElementById('register-email').value.trim();
        const password = document.getElementById('register-password').value;
        const nome = document.getElementById('register-name').value.trim();
        const phone = document.getElementById('register-phone').value.trim();
        const errorEl = document.getElementById('register-error');

        if (!email || !password || !nome) {
            this._showError(errorEl, 'Please fill in all required fields.');
            return;
        }

        this._showError(errorEl, '');
        this._setButtonLoading('register-btn', true);

        try {
            const data = await API.register(email, password, nome, phone);
            API.setToken(data.access_token);
            if (data.refresh_token) {
                localStorage.setItem('encp_refresh', data.refresh_token);
            }
            this.showChat();
            this.loadConversations();
        } catch (err) {
            this._showError(errorEl, err.message || 'Registration failed. Please try again.');
        } finally {
            this._setButtonLoading('register-btn', false);
        }
    },

    logout() {
        API.clearToken();
        this.currentConversation = null;
        this._clearMessages();
        this.showLogin();
    },

    // ─── Conversations ────────────────────────────────────────────────

    async loadConversations() {
        const list = document.getElementById('conversation-list');
        if (!list) return;

        try {
            const data = await API.getConversations();
            const conversations = data.conversations || data || [];
            list.innerHTML = '';

            if (conversations.length === 0) {
                list.innerHTML = '<div class="no-conversations">No conversations yet. Start a new one!</div>';
                return;
            }

            conversations.forEach((conv) => {
                const item = document.createElement('div');
                item.className = 'conversation-item';
                if (this.currentConversation === conv.id) {
                    item.classList.add('active');
                }
                item.dataset.id = conv.id;

                const title = conv.title || conv.last_message || 'New conversation';
                const preview = title.length > 40 ? title.substring(0, 40) + '...' : title;
                const time = conv.updated_at ? this._formatTime(conv.updated_at) : '';

                item.innerHTML = `
                    <div class="conv-preview">${this._escapeHtml(preview)}</div>
                    <div class="conv-time">${time}</div>
                    <button class="conv-delete-btn" title="Delete conversation">&times;</button>
                `;

                item.addEventListener('click', (e) => {
                    if (e.target.classList.contains('conv-delete-btn')) {
                        e.stopPropagation();
                        this.deleteConversation(conv.id);
                        return;
                    }
                    this.selectConversation(conv.id);
                });

                list.appendChild(item);
            });
        } catch (err) {
            console.error('Failed to load conversations:', err);
        }
    },

    async selectConversation(convId) {
        this.currentConversation = convId;

        // Update active state in sidebar
        document.querySelectorAll('.conversation-item').forEach((el) => {
            el.classList.toggle('active', el.dataset.id === convId);
        });

        this._clearMessages();
        this.showTypingIndicator();

        try {
            const data = await API.getMessages(convId);
            this.hideTypingIndicator();
            const messages = data.messages || data || [];
            messages.forEach((msg) => this.appendMessage(msg));
            this.scrollToBottom();
        } catch (err) {
            this.hideTypingIndicator();
            console.error('Failed to load messages:', err);
        }
    },

    async deleteConversation(convId) {
        if (!confirm('Delete this conversation?')) return;

        try {
            await API.deleteConversation(convId);
            if (this.currentConversation === convId) {
                this.currentConversation = null;
                this._clearMessages();
            }
            this.loadConversations();
        } catch (err) {
            console.error('Failed to delete conversation:', err);
        }
    },

    newConversation() {
        this.currentConversation = null;
        this._clearMessages();
        document.querySelectorAll('.conversation-item').forEach((el) => {
            el.classList.remove('active');
        });
        const msgInput = document.getElementById('message-input');
        if (msgInput) msgInput.focus();
    },

    // ─── Messaging ────────────────────────────────────────────────────

    async sendMessage() {
        const input = document.getElementById('message-input');
        if (!input) return;

        const message = input.value.trim();

        // Handle file uploads
        if (this.pendingFiles.length > 0) {
            await this.sendFilesWithMessage(message);
            return;
        }

        if (!message) return;

        // Clear input
        input.value = '';
        input.style.height = 'auto';

        // Display user message
        this.appendMessage({
            role: 'user',
            content: message,
            timestamp: new Date().toISOString()
        });
        this.scrollToBottom();
        this.showTypingIndicator();

        try {
            const data = await API.sendMessage(message, this.currentConversation);
            this.hideTypingIndicator();

            // Set conversation ID if new
            if (data.conversation_id && !this.currentConversation) {
                this.currentConversation = data.conversation_id;
            }

            // Display assistant response
            this.appendMessage({
                role: 'assistant',
                content: data.response || data.message || data.content || '',
                timestamp: new Date().toISOString()
            });
            this.scrollToBottom();
            this.loadConversations();
        } catch (err) {
            this.hideTypingIndicator();
            this.appendMessage({
                role: 'system',
                content: 'Failed to send message. Please try again.',
                timestamp: new Date().toISOString()
            });
            this.scrollToBottom();
            console.error('Send message error:', err);
        }
    },

    async sendFilesWithMessage(message) {
        const files = [...this.pendingFiles];
        this.clearPendingFiles();

        const input = document.getElementById('message-input');
        if (input) {
            input.value = '';
            input.style.height = 'auto';
        }

        // Show user message with file indicators
        const fileNames = files.map((f) => f.name).join(', ');
        const displayMsg = message ? `${message}\n[Files: ${fileNames}]` : `[Files: ${fileNames}]`;
        this.appendMessage({
            role: 'user',
            content: displayMsg,
            timestamp: new Date().toISOString()
        });
        this.scrollToBottom();
        this.showTypingIndicator();

        try {
            const data = await API.sendWithFiles(files, message, this.currentConversation);
            this.hideTypingIndicator();

            if (data.conversation_id && !this.currentConversation) {
                this.currentConversation = data.conversation_id;
            }

            this.appendMessage({
                role: 'assistant',
                content: data.response || data.message || data.content || '',
                timestamp: new Date().toISOString()
            });
            this.scrollToBottom();
            this.loadConversations();
        } catch (err) {
            this.hideTypingIndicator();
            this.appendMessage({
                role: 'system',
                content: 'Failed to upload files. Please try again.',
                timestamp: new Date().toISOString()
            });
            this.scrollToBottom();
        }
    },

    // ─── Message Rendering ────────────────────────────────────────────

    appendMessage(msg) {
        const container = document.getElementById('messages-container');
        if (!container) return;

        const wrapper = document.createElement('div');
        wrapper.className = `message message-${msg.role || 'assistant'}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.innerHTML = this.formatContent(msg.content || '');

        const time = document.createElement('div');
        time.className = 'message-time';
        time.textContent = msg.timestamp ? this._formatTime(msg.timestamp) : '';

        wrapper.appendChild(bubble);
        wrapper.appendChild(time);
        container.appendChild(wrapper);
    },

    formatContent(text) {
        if (!text) return '';

        let html = this._escapeHtml(text);

        // Bold: **text** or __text__
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');

        // Italic: *text* or _text_
        html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
        html = html.replace(/(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/g, '<em>$1</em>');

        // Links: [text](url)
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

        // Bare URLs
        html = html.replace(/(https?:\/\/[^\s<]+)/g, (match) => {
            if (match.includes('</a>') || match.includes('href=')) return match;
            return `<a href="${match}" target="_blank" rel="noopener">${match}</a>`;
        });

        // Unordered lists: lines starting with - or *
        html = html.replace(/^[\-\*]\s+(.+)$/gm, '<li>$1</li>');
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

        // Ordered lists: lines starting with 1. 2. etc.
        html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');

        // Line breaks
        html = html.replace(/\n/g, '<br>');

        return html;
    },

    showTypingIndicator() {
        const container = document.getElementById('messages-container');
        if (!container) return;

        // Remove existing indicator
        this.hideTypingIndicator();

        const indicator = document.createElement('div');
        indicator.id = 'typing-indicator';
        indicator.className = 'message message-assistant typing-indicator';
        indicator.innerHTML = `
            <div class="message-bubble">
                <div class="typing-dots">
                    <span></span><span></span><span></span>
                </div>
                <span class="typing-text">ENCP is typing...</span>
            </div>
        `;
        container.appendChild(indicator);
        this.scrollToBottom();
    },

    hideTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    },

    scrollToBottom() {
        const container = document.getElementById('messages-container');
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    },

    // ─── Voice Recording ──────────────────────────────────────────────

    async toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            await this.startRecording();
        }
    },

    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.audioChunks = [];
            this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.audioChunks.push(e.data);
            };

            this.mediaRecorder.onstop = async () => {
                stream.getTracks().forEach((t) => t.stop());
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                await this.sendVoiceMessage(audioBlob);
            };

            this.mediaRecorder.start();
            this.isRecording = true;
            this._updateVoiceButton(true);
        } catch (err) {
            console.error('Microphone access denied:', err);
            alert('Microphone access is required for voice messages.');
        }
    },

    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        this.isRecording = false;
        this._updateVoiceButton(false);
    },

    async sendVoiceMessage(audioBlob) {
        this.appendMessage({
            role: 'user',
            content: '[Voice message]',
            timestamp: new Date().toISOString()
        });
        this.scrollToBottom();
        this.showTypingIndicator();

        try {
            const data = await API.sendVoice(audioBlob, this.currentConversation);
            this.hideTypingIndicator();

            if (data.conversation_id && !this.currentConversation) {
                this.currentConversation = data.conversation_id;
            }

            // Show transcription if available
            if (data.transcription) {
                this.appendMessage({
                    role: 'system',
                    content: `Transcription: "${data.transcription}"`,
                    timestamp: new Date().toISOString()
                });
            }

            this.appendMessage({
                role: 'assistant',
                content: data.response || data.message || data.content || '',
                timestamp: new Date().toISOString()
            });
            this.scrollToBottom();
            this.loadConversations();
        } catch (err) {
            this.hideTypingIndicator();
            this.appendMessage({
                role: 'system',
                content: 'Voice message failed. Please try again.',
                timestamp: new Date().toISOString()
            });
            this.scrollToBottom();
        }
    },

    // ─── File Upload ──────────────────────────────────────────────────

    handleFileSelect(event) {
        const files = Array.from(event.target.files);
        if (files.length === 0) return;

        this.pendingFiles = [...this.pendingFiles, ...files];
        this._updateFilePreview();

        // Reset file input so same file can be selected again
        event.target.value = '';
    },

    clearPendingFiles() {
        this.pendingFiles = [];
        this._updateFilePreview();
    },

    _updateFilePreview() {
        let preview = document.getElementById('file-preview');

        if (this.pendingFiles.length === 0) {
            if (preview) preview.remove();
            return;
        }

        if (!preview) {
            preview = document.createElement('div');
            preview.id = 'file-preview';
            preview.className = 'file-preview';
            const inputArea = document.getElementById('input-area');
            if (inputArea) inputArea.prepend(preview);
        }

        preview.innerHTML = this.pendingFiles.map((f, i) => `
            <div class="file-preview-item">
                <span class="file-name">${this._escapeHtml(f.name)}</span>
                <button class="file-remove-btn" data-index="${i}">&times;</button>
            </div>
        `).join('');

        preview.querySelectorAll('.file-remove-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.index, 10);
                this.pendingFiles.splice(idx, 1);
                this._updateFilePreview();
            });
        });
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

    _clearMessages() {
        const container = document.getElementById('messages-container');
        if (container) container.innerHTML = '';
    },

    _showError(el, msg) {
        if (el) {
            el.textContent = msg;
            el.style.display = msg ? 'block' : 'none';
        }
    },

    _setButtonLoading(id, loading) {
        const btn = document.getElementById(id);
        if (!btn) return;
        btn.disabled = loading;
        if (loading) {
            btn.dataset.originalText = btn.textContent;
            btn.textContent = 'Loading...';
        } else {
            btn.textContent = btn.dataset.originalText || btn.textContent;
        }
    },

    _updateVoiceButton(recording) {
        const btn = document.getElementById('voice-btn');
        if (!btn) return;
        btn.classList.toggle('recording', recording);
        btn.title = recording ? 'Stop recording' : 'Record voice message';
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    _formatTime(isoString) {
        try {
            const date = new Date(isoString);
            const now = new Date();
            const diffMs = now - date;
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

            if (diffDays === 0) {
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            } else if (diffDays === 1) {
                return 'Yesterday';
            } else if (diffDays < 7) {
                return date.toLocaleDateString([], { weekday: 'short' });
            } else {
                return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
            }
        } catch {
            return '';
        }
    }
};

document.addEventListener('DOMContentLoaded', () => Chat.init());
