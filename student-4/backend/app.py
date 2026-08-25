import os
from flask import Flask, jsonify
app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(status="ok", feature="ai-market-analyst")

# TODO(Student 4): implement CRUD + AI endpoints for "AI Market Analyst Assistant".
# Mirror the pattern in student-1/backend/app.py (markets/watchlist + /ai/*).

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
