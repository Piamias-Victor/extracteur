from flask import Flask, render_template, request, send_file
from scraper import scrap_leclerc_with_playwright, export_to_csv

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    if request.method == "POST":
        urls = [
            "https://www.e.leclerc/fp/avene-cicalfate-creme-reparatrice-protectrice-peaux-sensibles-et-irritees-100-ml-3282770204681",
            "https://www.e.leclerc/fp/avene-cicalfate-creme-reparatrice-protectrice-peaux-sensibles-et-irritees-40-ml-3282770204667"
        ]
        results = [scrap_leclerc_with_playwright(url) for url in urls]
        export_to_csv(results)
    return render_template("index.html", results=results)

@app.route("/download")
def download_csv():
    return send_file("produit_leclerc.csv", as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)