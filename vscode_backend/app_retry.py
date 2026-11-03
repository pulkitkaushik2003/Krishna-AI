# AI Prompt Studio - backend with automatic retry + fallback model
# Switch to the backup model immediately when Gemini is busy.

import os
import time
from dotenv import load_dotenv
from flask import Flask, request, Response, jsonify, send_from_directory, stream_with_context
from flask_cors import CORS
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
PRIMARY = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
FALLBACK = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
THINKING = os.getenv("GEMINI_THINKING", "low").strip().lower()  # leave empty for Gemini 2.x models
ATTEMPTS_PER_MODEL = 1

MODELS = [PRIMARY] + ([FALLBACK] if FALLBACK and FALLBACK != PRIMARY else [])

if not API_KEY:
    raise SystemExit("GEMINI_API_KEY is missing. Add it to the .env file.")

client = genai.Client(api_key=API_KEY)
config = None
if THINKING:
    config = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level=THINKING))

app = Flask(__name__)
CORS(app)


def is_retryable(e):
    code = getattr(e, "code", None)
    text = str(e)
    return code in (429, 500, 503, 504) or any(k in text for k in ("503", "UNAVAILABLE", "429", "overloaded", "high demand"))


@app.route("/health")
def health():
    return jsonify(ok=True, models=MODELS, thinking=THINKING or "default")


@app.route("/")
def index():
    return send_from_directory(app.root_path, "index-pro.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object"), 400
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="Prompt is required"), 400

    start = time.perf_counter()
    last_error = None

    for model in MODELS:
        try:
            chunks = iter(client.models.generate_content_stream(
                model=model, contents=prompt, config=config
            ))
            first_text = next((chunk.text for chunk in chunks if chunk.text), None)
            if first_text is None:
                last_error = RuntimeError(f"{model} returned an empty response")
                print(f"[{model}] returned an empty response")
                continue

            print(f"[{model}] first words after {time.perf_counter() - start:.1f}s")

            def stream():
                yield first_text
                try:
                    for chunk in chunks:
                        if chunk.text:
                            yield chunk.text
                    print(f"[{model}] finished in {time.perf_counter() - start:.1f}s")
                except Exception as e:
                    print(f"[{model}] stream interrupted: {e}")
                    yield "\n\n[Response interrupted. Please try again.]"

            return Response(
                stream_with_context(stream()),
                mimetype="text/plain",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        except Exception as e:
            last_error = e
            print(f"[{model}] failed before response: {e}")

    if last_error and is_retryable(last_error):
        return jsonify(error="Gemini is temporarily unavailable. Please try again shortly."), 503
    return jsonify(error="Gemini could not generate a response. Check the server log for details."), 502


if __name__ == "__main__":
    print(f"Models (in order): {MODELS} | thinking: {THINKING or 'default'}")
    app.run(host="127.0.0.1", port=2000, debug=False, threaded=True)
