import os
import json
from collections import deque
from flask import Flask, render_template, request, jsonify
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# In-memory stores (reset on server restart)
ratings_log = []
recent_riddles = deque(maxlen=20)
recent_jokes = deque(maxlen=20)


def generate_riddle_or_joke(mode="riddle"):
    """Generate a riddle or joke via OpenRouter, avoiding recent repeats."""
    recent = recent_riddles if mode == "riddle" else recent_jokes

    if mode == "riddle":
        system_prompt = (
            "You are a riddle master. Generate a clever, fun riddle. "
            "Respond in JSON format: {\"type\": \"riddle\", \"content\": \"the riddle text\", \"answer\": \"the answer\"}. "
            "Make the riddle challenging but solvable. Vary the style — some short, some longer, "
            "some wordplay, some logic."
        )
    else:
        system_prompt = (
            "You are a comedian. Generate a short, funny joke. "
            "Respond in JSON format: {\"type\": \"joke\", \"content\": \"the joke text\"}. "
            "Keep it clean and clever. Vary the style — puns, one-liners, short stories."
        )

    avoid_msg = ""
    if recent:
        items = "\n".join(f"- {r}" for r in recent)
        avoid_msg = (
            f"\n\nDO NOT repeat any of these recently shown {mode}s:\n{items}\n\n"
            f"Generate something completely new and different."
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "google/gemini-2.5-flash-lite",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate one now.{avoid_msg}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.95,
    }

    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    result = json.loads(content)

    # Track it so we don't repeat
    recent.append(result["content"])

    return result


@app.route("/")
def index():
    """Serve the main page."""
    return render_template("index.html")


@app.route("/generate")
def generate():
    """Generate a new riddle or joke."""
    mode = request.args.get("mode", "riddle")
    try:
        result = generate_riddle_or_joke(mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/rate", methods=["POST"])
def rate():
    """Record a rating and return stats."""
    data = request.json
    rating = data.get("rating")
    item_type = data.get("type")
    content = data.get("content", "")
    answer = data.get("answer", "")

    ratings_log.append({
        "rating": rating,
        "type": item_type,
        "content": content,
        "answer": answer,
    })

    total = len(ratings_log)
    avg = sum(r["rating"] for r in ratings_log) / total if total else 0

    return jsonify({"total_rated": total, "average_rating": round(avg, 1)})


@app.route("/stats")
def stats():
    """Get rating statistics."""
    total = len(ratings_log)
    if total == 0:
        return jsonify({"total": 0, "average": 0, "by_type": {}})

    avg = sum(r["rating"] for r in ratings_log) / total

    by_type = {}
    for r in ratings_log:
        t = r["type"]
        if t not in by_type:
            by_type[t] = {"count": 0, "total_rating": 0}
        by_type[t]["count"] += 1
        by_type[t]["total_rating"] += r["rating"]

    for t in by_type:
        by_type[t]["average"] = round(by_type[t]["total_rating"] / by_type[t]["count"], 1)
        del by_type[t]["total_rating"]

    return jsonify({
        "total": total,
        "average": round(avg, 1),
        "by_type": by_type,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
