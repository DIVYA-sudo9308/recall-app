from flask import Flask, request, jsonify, render_template_string
from google import genai
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY")
HISTORY_FILE = "chat_history.json"
GAP_THRESHOLD_HOURS = 3

client = genai.Client(api_key=API_KEY)

TIME_SENSITIVE_KEYWORDS = [
    "weather", "rain", "sunny", "cold", "hot", "temperature", "storm",
    "mood", "feeling", "sad", "happy", "anxious", "stressed", "tired",
    "sick", "headache", "fever", "pain", "health",
    "exam", "test", "deadline", "submission", "interview",
    "market", "stock", "price", "crypto", "invest"
]


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def detect_gap_and_stale_context(history):
    if len(history) < 2:
        return False, []

    last_msg_time_str = history[-1].get("timestamp")
    if not last_msg_time_str:
        return False, []

    last_msg_time = datetime.fromisoformat(last_msg_time_str)
    now = datetime.now()
    gap_hours = (now - last_msg_time).total_seconds() / 3600

    if gap_hours < GAP_THRESHOLD_HOURS:
        return False, []

    stale_snippets = []
    for msg in history:
        text = msg.get("content", "").lower()
        for keyword in TIME_SENSITIVE_KEYWORDS:
            if keyword in text:
                snippet = msg.get("content", "")
                if len(snippet) > 80:
                    snippet = snippet[:80] + "..."
                stale_snippets.append(snippet)
                break

    return True, stale_snippets


def build_gemini_messages(history):
    messages = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            messages.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            messages.append({"role": "model", "parts": [{"text": content}]})
    return messages


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Recall</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Segoe UI', sans-serif;
  background: #0f0f13;
  color: #e8e8f0;
  height: 100vh;
  display: flex;
  flex-direction: column;
}
#header {
  padding: 16px 24px;
  border-bottom: 1px solid #2a2a3a;
  display: flex;
  align-items: center;
  gap: 12px;
  background: #13131a;
}
#header h1 {
  font-size: 20px;
  color: #a78bfa;
  letter-spacing: 1px;
}
#header span {
  font-size: 13px;
  color: #666;
}
#gap-alert {
  display: none;
  margin: 12px 16px 0 16px;
  padding: 12px 16px;
  background: #2a1f00;
  border: 1px solid #f59e0b;
  border-radius: 10px;
  color: #fbbf24;
  font-size: 13px;
  line-height: 1.6;
}
#gap-alert strong {
  display: block;
  margin-bottom: 4px;
  font-size: 14px;
}
#messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.bubble.user {
  background: #4c1d95;
  align-self: flex-end;
  border-bottom-right-radius: 4px;
}
.bubble.assistant {
  background: #1e1e2e;
  align-self: flex-start;
  border-bottom-left-radius: 4px;
  border: 1px solid #2a2a3a;
}
.bubble .time {
  font-size: 10px;
  color: #888;
  margin-top: 6px;
}
#input-area {
  padding: 16px;
  border-top: 1px solid #2a2a3a;
  display: flex;
  gap: 10px;
  background: #13131a;
}
#user-input {
  flex: 1;
  background: #1e1e2e;
  border: 1px solid #2a2a3a;
  border-radius: 12px;
  color: #e8e8f0;
  padding: 12px 16px;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  max-height: 140px;
  outline: none;
  transition: border-color 0.2s;
}
#user-input:focus {
  border-color: #7c3aed;
}
#send-btn {
  background: #7c3aed;
  border: none;
  border-radius: 12px;
  color: white;
  padding: 12px 20px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
  align-self: flex-end;
}
#send-btn:hover { background: #6d28d9; }
#send-btn:disabled { background: #3a2060; cursor: not-allowed; }
#typing {
  display: none;
  font-size: 13px;
  color: #888;
  padding: 0 16px 8px;
}
</style>
</head>
<body>

<div id="header">
  <h1>Recall</h1>
  <span>Context-aware AI chat</span>
</div>

<div id="gap-alert"></div>

<div id="messages"></div>
<div id="typing">Recall is thinking...</div>

<div id="input-area">
  <textarea id="user-input" rows="1" placeholder="Type a message..."></textarea>
  <button id="send-btn">Send</button>
</div>

<script>
var messagesDiv = document.getElementById('messages');
var inputEl = document.getElementById('user-input');
var sendBtn = document.getElementById('send-btn');
var typingEl = document.getElementById('typing');
var gapAlert = document.getElementById('gap-alert');

function formatTime(isoString) {
  var d = new Date(isoString);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function addBubble(role, content, timestamp) {
  var div = document.createElement('div');
  div.className = 'bubble ' + role;
  var p = document.createElement('p');
  p.textContent = content;
  div.appendChild(p);
  if (timestamp) {
    var t = document.createElement('div');
    t.className = 'time';
    t.textContent = formatTime(timestamp);
    div.appendChild(t);
  }
  messagesDiv.appendChild(div);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function autoResize() {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + 'px';
}

function send() {
  var text = inputEl.value.trim();
  if (!text) return;

  inputEl.value = '';
  inputEl.style.height = 'auto';
  sendBtn.disabled = true;
  gapAlert.style.display = 'none';

  var now = new Date().toISOString();
  addBubble('user', text, now);
  typingEl.style.display = 'block';

  fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text })
  })
  .then(function(res) { return res.json(); })
  .then(function(data) {
    typingEl.style.display = 'none';
    sendBtn.disabled = false;

    if (data.gap_detected && data.stale_snippets && data.stale_snippets.length > 0) {
      var html = '<strong>Things may have changed since your last visit:</strong>';
      for (var i = 0; i < data.stale_snippets.length; i++) {
        html += '<br>- ' + data.stale_snippets[i];
      }
      gapAlert.innerHTML = html;
      gapAlert.style.display = 'block';
    }

    if (data.reply) {
      addBubble('assistant', data.reply, data.timestamp);
    } else if (data.error) {
      addBubble('assistant', 'Error: ' + data.error, new Date().toISOString());
    }
  })
  .catch(function(err) {
    typingEl.style.display = 'none';
    sendBtn.disabled = false;
    addBubble('assistant', 'Network error. Is the server running?', new Date().toISOString());
  });
}

sendBtn.addEventListener('click', send);

inputEl.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

inputEl.addEventListener('input', autoResize);

// Load history on page open
fetch('/history')
  .then(function(res) { return res.json(); })
  .then(function(data) {
    if (data.history) {
      for (var i = 0; i < data.history.length; i++) {
        var msg = data.history[i];
        addBubble(msg.role, msg.content, msg.timestamp);
      }
    }
  });
</script>

</body>
</html>"""


@app.route("/")
def index():
    return HTML_PAGE


@app.route("/history")
def get_history():
    history = load_history()
    return jsonify({"history": history})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    history = load_history()

    gap_detected, stale_snippets = detect_gap_and_stale_context(history)

    now = datetime.now().isoformat()
    history.append({
        "role": "user",
        "content": user_message,
        "timestamp": now
    })

    try:
        gemini_messages = build_gemini_messages(history)

        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=gemini_messages
        )

        reply_text = response.text

        reply_time = datetime.now().isoformat()
        history.append({
            "role": "assistant",
            "content": reply_text,
            "timestamp": reply_time
        })

        save_history(history)

        return jsonify({
            "reply": reply_text,
            "timestamp": reply_time,
            "gap_detected": gap_detected,
            "stale_snippets": stale_snippets
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)