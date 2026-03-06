/**
 * ENCP Services Group - Chat Widget (Embeddable)
 * Adds a floating chat button that opens the AI assistant in an iframe.
 *
 * Usage: Add to any page:
 *   <script src="http://localhost:8004/static/js/widget.js"></script>
 *
 * In production:
 *   <script src="https://api.encpservices.com/static/js/widget.js"></script>
 */
(function() {
    'use strict';

    // Config
    var API_BASE = (document.currentScript && document.currentScript.src)
        ? new URL(document.currentScript.src).origin
        : 'http://localhost:8004';

    var CHAT_URL = API_BASE + '/chat';

    // Colors matching ENCP brand
    var PRIMARY_COLOR = '#1B365D';  // Navy Blue
    var ACCENT_COLOR = '#D4A84B';   // Gold

    // Create styles
    var style = document.createElement('style');
    style.textContent = `
        #encp-chat-widget-btn {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: ${PRIMARY_COLOR};
            color: white;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 16px rgba(0,0,0,0.3);
            z-index: 99998;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s, box-shadow 0.2s;
            font-size: 28px;
        }
        #encp-chat-widget-btn:hover {
            transform: scale(1.08);
            box-shadow: 0 6px 20px rgba(0,0,0,0.4);
        }
        #encp-chat-widget-btn.open {
            background: #666;
        }
        #encp-chat-widget-frame {
            position: fixed;
            bottom: 96px;
            right: 24px;
            width: 380px;
            height: 560px;
            max-height: calc(100vh - 120px);
            max-width: calc(100vw - 48px);
            border: none;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            z-index: 99999;
            display: none;
            background: white;
        }
        #encp-chat-widget-frame.visible {
            display: block;
        }
        @media (max-width: 480px) {
            #encp-chat-widget-frame {
                width: calc(100vw - 16px);
                height: calc(100vh - 80px);
                bottom: 8px;
                right: 8px;
                border-radius: 12px;
            }
            #encp-chat-widget-btn {
                bottom: 16px;
                right: 16px;
            }
        }
    `;
    document.head.appendChild(style);

    // Create button
    var btn = document.createElement('button');
    btn.id = 'encp-chat-widget-btn';
    btn.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
    btn.title = 'Chat with ENCP Services';
    document.body.appendChild(btn);

    // Create iframe
    var iframe = document.createElement('iframe');
    iframe.id = 'encp-chat-widget-frame';
    iframe.src = CHAT_URL;
    iframe.title = 'ENCP Services Chat';
    iframe.allow = 'microphone';
    document.body.appendChild(iframe);

    // Toggle
    var isOpen = false;
    btn.addEventListener('click', function() {
        isOpen = !isOpen;
        iframe.classList.toggle('visible', isOpen);
        btn.classList.toggle('open', isOpen);
        btn.innerHTML = isOpen
            ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
            : '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
    });
})();
