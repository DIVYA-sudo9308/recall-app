from flask import Flask, request, jsonify, render_template_string
from google import genai
import json
import os
from datetime import datetime

app = Flask(__name__)

API_KEY = "AIzaSyAQMNdQVfunh2Gq5GxvY9AyFmWoNs4a9ck"
client = genai.Client(api_key=API_KEY)

HISTORY_FILE = "chat_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
            
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def get_gap_minutes(history):
    if not history:
        return 0
    last_time = datetime.fromisoformat(history[-1]["timestamp"])
    now = datetime.now()
    return (now - last_time).total_seconds() / 60

def find_perishable_context(history):
    keywords = ["rain", "sick", "fever", "sad", "happy", "stressed", "tired",
                "exam", "crash", "market", "anxious", "cold", "hot", "mood",
                "hungry", "pain", "headache", "angry", "excited", "nervous"]
    found = []
    for msg in history[-10:]:
        if msg["role"] == "user":
            for word in keywords:
                if word in msg["content"].lower():
                    found.append(f'"{msg["content"][:60]}"')
                    break
    return found

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recall - AI that remembers wisely</title>
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg: #0a0a0f;
            --surface: #111118;
            --border: #1e1e2e;
            --accent: #7c6aff;
            --accent-soft: rgba(124, 106, 255, 0.12);
            --text: #e8e8f0;
            --text-muted: #5a5a7a;
            --user-bg: #7c6aff;
            --ai-bg: #16161f;
            --warn: #ff9f43;
            --warn-bg: rgba(255, 159, 67, 0.08);
            --warn-border: rgba(255, 159, 67, 0.25);
        }

        body {
            background: var(--bg);
            color: var(--text);
            font-family: 'DM Sans', sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }

        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background: 
                radial-gradient(ellipse 80% 50% at 20% 0%, rgba(124,106,255,0.06) 0%, transparent 60%),
                radial-gradient(ellipse 60% 40% at 80% 100%, rgba(124,106,255,0.04) 0%, transparent 60%);
            pointer-events: none;
        }

        .container {
            width: 100%;
            max-width: 720px;
            height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 0 16px;
            position: relative;
        }

        header {
            padding: 24px 0 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            border-bottom: 1px solid var(--border);
        }

        .logo-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent);
            box-shadow: 0 0 12px var(--accent);
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.6; transform: scale(0.85); }
        }

        .logo-text {
            font-family: 'Syne', sans-serif;
            font-weight: 700;
            font-size: 1.1rem;
            letter-spacing: -0.02em;
            color: var(--text);
        }

        .logo-tag {
            margin-left: auto;
            font-size: 0.72rem;
            color: var(--text-muted);
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }

        #chat {
            flex: 1;
            overflow-y: auto;
            padding: 24px 0;
            display: flex;
            flex-direction: column;
            gap: 16px;
            scrollbar-width: thin;
            scrollbar-color: var(--border) transparent;
        }

        #chat::-webkit-scrollbar { width: 4px; }
        #chat::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

        .empty-state {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 12px;
            color: var(--text-muted);
            text-align: center;
            padding: 40px;
        }

        .empty-state .big { font-size: 2rem; }
        .empty-state p { font-size: 0.9rem; line-height: 1.6; max-width: 300px; }

        .msg-row {
            display: flex;
            animation: fadeUp 0.3s ease;
        }

        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .msg-row.user { justify-content: flex-end; }
        .msg-row.ai { justify-content: flex-start; }

        .bubble {
            max-width: 72%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 0.92rem;
            line-height: 1.6;
            word-break: break-word;
        }

        .msg-row.user .bubble {
            background: var(--user-bg);
            color: #fff;
            border-bottom-right-radius: 4px;
        }

        .msg-row.ai .bubble {
            background: var(--ai-bg);
            color: var(--text);
            border: 1px solid var(--border);
            border-bottom-left-radius: 4px;
        }

        .typing .bubble {
            background: var(--ai-bg);
            border: 1px solid var(--border);
            padding: 14px 18px;
        }

        .dots { display: flex; gap: 4px; align-items: center; }
        .dots span {
            width: 5px; height: 5px;
            background: var(--text-muted);
            border-radius: 50%;
            animation: dot 1.2s ease-in-out infinite;
        }
        .dots span:nth-child(2) { animation-delay: 0.2s; }
        .dots span:nth-child(3) { animation-delay: 0.4s; }

        @keyframes dot {
            0%, 80%, 100% { transform: scale(0.8); opacity: 0.4; }
            40% { transform: scale(1.1); opacity: 1; }
        }

        .context-alert {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            background: var(--warn-bg);
            border: 1px solid var(--warn-border);
            border-radius: 12px;
            padding: 12px 16px;
            font-size: 0.84rem;
            color: #ffb87a;
            line-height: 1.5;
            animation: fadeUp 0.4s ease;
        }

        .context-alert .icon { font-size: 1rem; flex-shrink: 0; margin-top: 1px; }

        .input-area {
            padding: 16px 0 24px;
            border-top: 1px solid var(--border);
        }

        .input-row {
            display: flex;
            gap: 10px;
            align-items: flex-end;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 10px 10px 10px 16px;
            transition: border-color 0.2s;
        }

        .input-row:focus-within {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-soft);
        }

        textarea {
            flex: 1;
            background: transparent;
            border: none;
            outline: none;
            color: var(--text);
            font-family: 'DM Sans', sans-serif;
            font-size: 0.93rem;
            resize: none;
            max-height: 120px;
            line-height: 1.5;
            padding: 2px 0;
        }

        textarea::placeholder { color: var(--text-muted); }

        .send-btn {
            width: 38px;
            height: 38px;
            border-radius: 10px;
            background: var(--accent);
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            transition: transform 0.15s, opacity 0.15s;
        }

        .send-btn:hover { transform: scale(1.05); }
        .send-btn:active { transform: scale(0.95); }
        .send-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
        .send-btn svg { width: 16px; height: 16px; fill: white; }

        .hint {
            text-align: center;
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-top: 10px;
        }
    </style>
</head>
<body>
<div class="container">
    <header>
        <div class="logo-dot"></div>
        <span class="logo-text">Recall</span>
        <span class="logo-tag">Context-aware AI</span>
    </header>

    <div id="chat">
        <div class="empty-state" id="empty">
            <div class="big">💬</div>
            <p>Start a conversation. Recall remembers what matters - and knows when to let go.</p>
        </div>
    </div>

    <div class="input-area">
        <div class="input-row">
            <textarea id="inp" placeholder="Say something..." rows="1"
                onkeydown="if(event.key==='Enter' && !event.shiftKey){ event.preventDefault(); send(); }"
                oninput="autoResize(this)"></textarea>
            <button class="send-btn" id="sendBtn" onclick="send()">
                <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
            </button>
        </div>
        <p class="hint">Enter to send &nbsp;·&nbsp; Shift+Enter for new line</p>
    </div>
</div>

<script>
function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function removeEmpty() {
    const e = document.getElementById('empty');
    if (e) e.remove();
}

function addMsg(text, role) {
    removeEmpty();
    const chat = document.getElementById('chat');
    const row = document.createElement('div');
    row.className = `msg-row ${role}`;
    row.innerHTML = `<div class="bubble">${text.split('\n').join('<br>')}</div>`;
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
}

function addContextAlert(text) {
    removeEmpty();
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = 'context-alert';
    div.innerHTML = `<span class="icon">🕐</span><span>${text}</span>`;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function addTyping() {
    removeEmpty();
    const chat = document.getElementById('chat');
    const row = document.createElement('div');
    row.className = 'msg-row ai typing';
    row.id = 'typing';
    row.innerHTML = `<div class="bubble"><div class="dots"><span></span><span></span><span></span></div></div>`;
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
}

function removeTyping() {
    const t = document.getElementById('typing');
    if (t) t.remove();
}

async function send() {
    const inp = document.getElementById('inp');
    const btn = document.getElementById('sendBtn');
    const msg = inp.value.trim();
    if (!msg) return;

    inp.value = '';
    inp.style.height = 'auto';
    btn.disabled = true;

    addMsg(msg, 'user');
    addTyping();

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg })
        });
        const data = await res.json();
        removeTyping();
        if (data.checkin) addContextAlert(data.checkin);
        addMsg(data.reply, 'ai');
    } catch(e) {
        removeTyping();
        addMsg('Something went wrong. Please try again.', 'ai');
    }

    btn.disabled = false;
    inp.focus();
}

window.onload = async () => {
    const res = await fetch('/history');
    const data = await res.json();
    if (data.length > 0) {
        data.forEach(m => addMsg(m.content, m.role === 'user' ? 'user' : 'ai'));
    }
    document.getElementById('inp').focus();
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/history")
def history():
    return jsonify(load_history())

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.json.get("message")
    history = load_history()

    gap = get_gap_minutes(history)
    checkin_msg = None

    if gap >= 180:
        stale = find_perishable_context(history)
        hours = round(gap / 60, 1)
        checkin_msg = f"Welcome back - it's been {hours} hours. "
        if stale:
            checkin_msg += f"You mentioned {', '.join(stale[:2])} earlier. Still the case?"
        else:
            checkin_msg += "A lot may have changed. Feel free to update me."

    history.append({
        "role": "user",
        "content": user_msg,
        "timestamp": datetime.now().isoformat()
    })

    conversation = "\n".join([
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in history[-10:]
    ])

    prompt = f"You are a helpful assistant. Here is the conversation so far:\n{conversation}\nAssistant:"

    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt
    )
    reply = response.text

    history.append({
        "role": "assistant",
        "content": reply,
        "timestamp": datetime.now().isoformat()
    })

    save_history(history)
    return jsonify({"reply": reply, "checkin": checkin_msg})

if __name__ == "__main__":
    app.run(debug=True)
