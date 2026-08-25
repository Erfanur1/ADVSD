import os
from flask import Flask, jsonify
app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(status="ok", feature="portfolio-position-tracker")

# TODO(Student 2): implement CRUD + AI endpoints for "Portfolio & Position Tracker".
# Mirror the pattern in student-1/backend/app.py (markets/watchlist + /ai/*).

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
