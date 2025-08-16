from flask import Flask, request, jsonify, render_template
import os, json, re
import cohere

# Read your API key from environment variable for safety
# Windows (PowerShell):  $env:COHERE_API_KEY="your_key"
# macOS/Linux:           export COHERE_API_KEY="your_key"
API_KEY = "EwR8ZztIGV78GCKkoYolCPo6xIipRSprbQks25Ur"
if not API_KEY:
    raise RuntimeError("Please set COHERE_API_KEY environment variable.")

# Init client
co = cohere.Client(API_KEY)

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/check_job", methods=["POST"])
def check_job():
    data = request.get_json(silent=True) or {}
    job_title = (data.get("job_title") or "").strip()
    if not job_title:
        return jsonify({"error": "Missing job_title"}), 400

    # We ask Cohere to return STRICT JSON only.
    # Works across new/old SDKs because we’ll pass this as either 'messages' or single 'message'.
    system_instructions = (
        "You are a concise AI career advisor. "
        "Return STRICT JSON only with these keys: "
        "risk_score (integer 0-100), summary (string), "
        "factors (array of 4-6 short bullet strings explaining the score), "
        "tools (array of 5 concrete AI tools relevant to the role), "
        "roadmap (array of 6-8 actionable weekly steps for 6-8 weeks). "
        "No markdown, no extra commentary."
    )

    user_prompt = (
        f"Job title: {job_title}\n"
        "Analyze automation risk over the next 3-5 years globally (and note India where relevant). "
        "Be practical and specific for this role and industry.\n"
        "Output STRICT JSON only."
    )

    # New SDK supports messages=[{role, content}, ...]
    # Old SDK supports message="...". We'll try new style first, then fallback.
    # Also handle model name differences across accounts/regions.
    model_candidates = ["command-r-plus", "command-r", "command"]  # try in order

    def parse_json_from_text(text: str):
        # Return dict or raise
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group(0))
            raise ValueError("Model returned non-JSON or malformed JSON")

    last_error = None
    for model in model_candidates:
        # Try role-based messages (newer SDKs)
        try:
            resp = co.chat(
                model=model,
                # NEW SDK signature:
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            text = resp.message.content[0].text  # new SDK shape
            parsed = parse_json_from_text(text)
            break
        except TypeError as te:
            # Older SDK doesn't accept 'messages' -> fallback to message=
            try:
                combined = f"{system_instructions}\n\n{user_prompt}"
                resp = co.chat(
                    model=model,
                    message=combined,     # OLD SDK signature
                    temperature=0.2
                )
                text = resp.text       # old SDK shape
                parsed = parse_json_from_text(text)
                break
            except Exception as e2:
                last_error = e2
                parsed = None
        except Exception as e1:
            last_error = e1
            parsed = None

    if not parsed:
        return jsonify({"error": f"Cohere call failed: {last_error}"}), 500

    # Coerce/validate fields
    try:
        parsed["risk_score"] = int(max(0, min(100, int(parsed.get("risk_score", 0)))))
    except Exception:
        parsed["risk_score"] = 0

    parsed["summary"] = str(parsed.get("summary", ""))

    def coerce_list(key, max_len):
        value = parsed.get(key, [])
        if not isinstance(value, list):
            value = [str(value)] if value else []
        return [str(x) for x in value][:max_len]

    parsed["factors"] = coerce_list("factors", 8)
    parsed["tools"] = coerce_list("tools", 8)
    parsed["roadmap"] = coerce_list("roadmap", 12)

    return jsonify(parsed)


if __name__ == "__main__":
    app.run(debug=True)
