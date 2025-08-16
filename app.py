from flask import Flask, request, jsonify, render_template, url_for
import os, json, re, datetime
import cohere
from dotenv import load_dotenv
import os

# -----------------------------
# Cohere setup (secure: from env)
# -----------------------------

load_dotenv()

API_KEY = os.getenv("COHERE_API_KEY")
if not API_KEY:
    raise RuntimeError("Please set COHERE_API_KEY environment variable.")


co = cohere.Client(API_KEY)

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/preview/<path:job>")
def preview(job):
    """
    SEO/Share page. Loads a client view that fetches live data on the job title.
    OG/Twitter meta is provided to look good in shares.
    """
    job = (job or "").strip()
    return render_template("preview.html", job=job)


@app.route("/check_job", methods=["POST"])
def check_job():
    data = request.get_json(silent=True) or {}
    job_title = (data.get("job_title") or "").strip()
    if not job_title:
        return jsonify({"error": "Missing job_title"}), 400

    # --- System / User prompts with STRICT JSON & link requirements ---
    system_instructions = (
        "You are a concise AI career advisor. "
        "Return STRICT JSON only with these keys: "
        "risk_score (integer 0-100), "
        "summary_global (string), "
        "summary_india (string), "
        "factors (array of 4-6 short bullet strings explaining the score), "
        "tools (array of 5 items, each formatted exactly as 'Name (https://official-or-authoritative-learning-link)' "
        "with reputable sources only; no placeholders or generic homepages), "
        "roadmap (array of 6-8 actionable weekly steps; each step should start with 'Week X:' and be concise). "
        "No markdown, no extra commentary, no code-fences."
    )

    user_prompt = (
        f"Job title: {job_title}\n"
        "Analyze automation/AI risk over the next 3–5 years globally and, where relevant, in India. "
        "Be practical and specific to this role and industry. "
        "Output STRICT JSON only."
    )

    model_candidates = ["command-r-plus", "command-r", "command"]

    def parse_json_from_text(text: str):
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group(0))
            raise ValueError("Model returned non-JSON or malformed JSON")

    last_error = None
    parsed = None
    for model in model_candidates:
        try:
            # Newer SDK pattern
            resp = co.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            text = resp.message.content[0].text
            parsed = parse_json_from_text(text)
            break
        except TypeError:
            try:
                # Older SDK fallback
                combined = f"{system_instructions}\n\n{user_prompt}"
                resp = co.chat(
                    model=model,
                    message=combined,
                    temperature=0.2
                )
                text = resp.text
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

    # --- Coerce / validate fields ---
    def coerce_list(value, max_len):
        if not isinstance(value, list):
            value = [str(value)] if value else []
        return [str(x).strip() for x in value][:max_len]

    # Risk
    try:
        parsed["risk_score"] = int(max(0, min(100, int(parsed.get("risk_score", 0)))))
    except Exception:
        parsed["risk_score"] = 0

    # Summaries
    parsed["summary_global"] = str(parsed.get("summary_global", "")).strip()
    parsed["summary_india"] = str(parsed.get("summary_india", "")).strip()

    # Factors & Roadmap
    parsed["factors"] = coerce_list(parsed.get("factors", []), 8)
    parsed["roadmap"] = coerce_list(parsed.get("roadmap", []), 12)

    # Tools: enforce link format "Name (https://...)"; keep only valid, but if none valid, pass through originals (graceful)
    raw_tools = coerce_list(parsed.get("tools", []), 10)

    valid_tools = []
    for t in raw_tools:
        m = re.match(r"^(.*?)\s*\((https?://[^\s)]+)\)\s*$", t)
        if m:
            name = m.group(1).strip()
            url = m.group(2).strip()
            # tiny sanity checks
            if len(name) >= 2 and url.startswith("http"):
                valid_tools.append(f"{name} ({url})")

    parsed["tools"] = valid_tools if valid_tools else raw_tools

    # (Optional) Lightweight analytics: append to JSONL
    try:
        rec = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "job": job_title,
            "risk": parsed["risk_score"],
            "factors_len": len(parsed["factors"]),
            "tools_len": len(parsed["tools"]),
        }
        with open("analytics.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # best-effort only

    return jsonify(parsed)


if __name__ == "__main__":
    # For local dev
    app.run(debug=True)
