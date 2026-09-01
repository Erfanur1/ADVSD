import os
import requests
from flask import Flask, render_template_string

app = Flask(__name__)
# Uses internal Docker DNS name when running in compose, otherwise localhost
BACKEND_URL = os.environ.get("BACKEND_URL", "http://student-2-backend:5002")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Portfolio Tracker</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <link rel="stylesheet" href="http://localhost:8080/css/theme.css">
    <style>
        body { padding: 20px; font-family: sans-serif; max-width: 900px; margin: auto; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background-color: #f2f2f2; }
        button { cursor: pointer; padding: 5px 10px; background-color: #ff4d4d; color: white; border: none; border-radius: 3px;}
        .ai-btn { background-color: #3273dc; margin-bottom: 10px; }
    </style>
</head>
<body>
    <a href="http://localhost:8080">← Back to Home</a>
    <h1>Portfolio & Position Tracker</h1>
    
    <div style="background: #eef; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
        <h3>Agentic AI Risk Analyst</h3>
        <button class="ai-btn" hx-post="/proxy/ai/analyze-risk" hx-target="#ai-output" hx-indicator="#loading">
            Analyze My Portfolio Risk
        </button>
        <span id="loading" class="htmx-indicator" style="display:none;"> (Consulting LLM...)</span>
        <div id="ai-output" style="margin-top: 10px;"></div>
    </div>

    <h2>Open Positions</h2>
    <table>
        <thead>
            <tr><th>ID</th><th>Market Ticker</th><th>Side</th><th>Entry Price</th><th>Size</th><th>Action</th></tr>
        </thead>
        <tbody id="positions-body">
            {% for p in positions %}
            <tr id="pos-{{ p.id }}">
                <td>{{ p.id }}</td>
                <td>{{ p.market_ticker }}</td>
                <td>{{ p.side }}</td>
                <td>${{ p.entry_price }}</td>
                <td>{{ p.size }}</td>
                <td>
                    <button hx-delete="/proxy/api/positions/{{ p.id }}" hx-target="#pos-{{ p.id }}" hx-swap="outerHTML">
                        Close Position
                    </button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
"""

@app.get("/")
def home():
    try:
        resp = requests.get(f"{BACKEND_URL}/api/positions")
        positions = resp.json() if resp.status_code == 200 else []
    except:
        positions = []
    return render_template_string(HTML_TEMPLATE, positions=positions)

@app.route("/proxy/api/positions/<int:pos_id>", methods=["DELETE"])
def proxy_delete(pos_id):
    resp = requests.delete(f"{BACKEND_URL}/api/positions/{pos_id}")
    return resp.text, resp.status_code

@app.route("/proxy/ai/analyze-risk", methods=["POST"])
def proxy_ai():
    resp = requests.post(f"{BACKEND_URL}/ai/analyze-risk")
    return resp.text, resp.status_code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5102)
