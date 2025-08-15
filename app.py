from flask import Flask, render_template, request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("COHERE_API_KEY")

@app.route("/", methods=["GET", "HEAD"])
def home():
    if request.method == "HEAD":
        return "", 200
    return render_template("index.html")  # Load UI from templates folder

@app.route("/check_job", methods=["POST"])
def check_job():
    data = request.json
    job_title = data.get("job_title", "")

    # Placeholder logic for AI job risk
    return jsonify({
        "risk_score": 72,
        "summary": f"AI could automate parts of the job '{job_title}'.",
        "tools": ["Python", "TensorFlow", "Cohere API"],
        "factors": ["Repetitive tasks", "Data-driven decision making"],
        "roadmap": ["Learn Python", "Get AI fundamentals", "Practice with real data"]
    })

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Error occurred: {str(e)}")
    return "Internal Server Error", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
