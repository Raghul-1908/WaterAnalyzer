from flask import Flask, render_template, jsonify
from water_engine import run_water_bot

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/run")
def run():
    result = run_water_bot()
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True)
