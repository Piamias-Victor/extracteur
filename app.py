from flask import Flask, render_template, request, send_file, redirect, url_for
from simplified_category_scraper import scrape_category_pages, export_to_csv, scrap_leclerc_product
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    error = None
    status = None
    
    if request.method == "POST":
        scrape_type = request.form.get("scrape_type", "specific")
        
        try:
            if scrape_type == "specific":
                # Scraper les produits spécifiques
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                urls = [
                    "https://www.e.leclerc/fp/avene-cicalfate-creme-reparatrice-protectrice-peaux-sensibles-et-irritees-100-ml-3282770204681",
                    "https://www.e.leclerc/fp/avene-cicalfate-creme-reparatrice-protectrice-peaux-sensibles-et-irritees-40-ml-3282770204667"
                ]
                
                try:
                    results = [scrap_leclerc_product(url, driver) for url in urls]
                    results = [r for r in results if r]  # Filtrer les résultats None
                    export_to_csv(results, filename="produit_leclerc.csv")
                    status = f"Scraping de {len(urls)} produits spécifiques terminé avec succès!"
                finally:
                    driver.quit()
                
            elif scrape_type == "category":
                # Scraper toute la catégorie (nouvelle fonctionnalité)
                max_pages = request.form.get("max_pages", "")
                max_pages = int(max_pages) if max_pages.isdigit() and int(max_pages) > 0 else None
                
                # Rediriger vers la page de scraping de catégorie pour ne pas bloquer la requête HTTP
                return redirect(url_for('category_scraping', max_pages=max_pages))
                
        except Exception as e:
            error = f"Erreur pendant le scraping: {str(e)}"
    
    # Vérifier l'existence des fichiers CSV pour afficher les liens de téléchargement
    specific_file_exists = os.path.isfile("produit_leclerc.csv")
    category_file_exists = os.path.isfile("produits_leclerc_soinsvisage.csv")
    
    return render_template(
        "index.html", 
        results=results, 
        error=error, 
        status=status,
        specific_file_exists=specific_file_exists,
        category_file_exists=category_file_exists
    )

@app.route("/category_scraping")
def category_scraping():
    max_pages = request.args.get("max_pages", None)
    if max_pages:
        max_pages = int(max_pages)
    
    category_url = "https://www.e.leclerc/cat/soins-visage"
    results = []
    
    try:
        # Lancer le scraping de catégorie
        results = scrape_category_pages(category_url, max_pages)
        status = f"Scraping de catégorie terminé avec succès! {len(results)} produits récupérés."
    except Exception as e:
        status = f"Erreur pendant le scraping de catégorie: {str(e)}"
    
    # Vérifier l'existence des fichiers CSV
    specific_file_exists = os.path.isfile("produit_leclerc.csv")
    category_file_exists = os.path.isfile("produits_leclerc_soinsvisage.csv")
    
    return render_template(
        "index.html", 
        results=results, 
        status=status,
        specific_file_exists=specific_file_exists,
        category_file_exists=category_file_exists
    )

@app.route("/download/<file_type>")
def download_csv(file_type):
    if file_type == "specific":
        return send_file("produit_leclerc.csv", as_attachment=True)
    elif file_type == "category":
        return send_file("produits_leclerc_soinsvisage.csv", as_attachment=True)
    else:
        return "Type de fichier non reconnu", 400

if __name__ == "__main__":
    app.run(debug=True)