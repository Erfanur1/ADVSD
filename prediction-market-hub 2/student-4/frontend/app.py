import os
from flask import Flask, render_template_string
app = Flask(__name__)

@app.get("/")
def home():
    return render_template_string(
        '<link rel="stylesheet" href="http://localhost:8080/css/theme.css">'
        '<h1>AI Market Analyst Assistant</h1><p>Student 4 feature — scaffold. '
        '<a href="http://localhost:8080/">Home</a></p>')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5104)
