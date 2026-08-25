import os
from flask import Flask, jsonify
app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(status="ok", feature="research-notes-news-feed")

# TODO(Student 3): implement CRUD + AI endpoints for "Market Research Notes & News Feed".
# Mirror the pattern in student-1/backend/app.py (markets/watchlist + /ai/*).

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
