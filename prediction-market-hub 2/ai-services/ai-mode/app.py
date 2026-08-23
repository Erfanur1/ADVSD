"""AI-Mode service: single entry point every backend calls to reach the LLM.

Implements the shared Plan -> Act -> Observe -> Adapt loop in a minimal,
inspectable form. In Release 0 it forwards a grounded prompt to Ollama and
returns the model's text plus the loop trace (so the workflow is demonstrable).
"""
import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")


def call_ollama(prompt: str) -> str:
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": LLM_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


@app.get("/health")
def health():
    return jsonify(status="ok", model=LLM_MODEL)


@app.post("/ai/complete")
def complete():
    """Body: {task: str, context: str}. Returns model output + P-A-O-A trace."""
    data = request.get_json(force=True) or {}
    task = data.get("task", "")
    context = data.get("context", "")

    # PLAN: decide what to ask, given the task and retrieved context.
    plan = f"Answer the task using only the provided context.\nTask: {task}"
    # ACT: call the LLM.
    prompt = f"{plan}\n\nContext:\n{context}\n\nAnswer:"
    try:
        output = call_ollama(prompt)
        observe = "LLM returned a non-empty response." if output else "Empty response."
        # ADAPT: single retry with a tighter instruction if empty.
        if not output:
            output = call_ollama(prompt + "\n\nBe concise and specific.")
            observe = "Retried with a tighter instruction (adapt step)."
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=str(exc), model=LLM_MODEL), 502

    return jsonify(
        model=LLM_MODEL,
        output=output,
        trace={"plan": plan, "act": "ollama.generate", "observe": observe, "adapt": "as needed"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
