from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify
from simplified_category_scraper import scrape_category_pages, export_to_csv, scrap_leclerc_product, get_status, get_estimated_time_remaining, timestamp_to_time
import os
import csv
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

app = Flask(__name__)

# Définir les chemins absolus pour les fichiers de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPECIFIC_CSV_PATH = os.path.join(BASE_DIR, "produit_leclerc.csv")
CATEGORY_CSV_PATH = os.path.join(BASE_DIR, "produits_leclerc_soinsvisage.csv")

# Enregistrement des filtres et fonctions pour les templates
@app.template_filter('timestamp_to_time')
def _timestamp_to_time_filter(timestamp):
    """Convertit un timestamp en format lisible pour les templates"""
    return timestamp_to_time(timestamp)

# Rendre les fonctions disponibles dans les templates
@app.context_processor
def utility_processor():
    return dict(
        get_estimated_time_remaining=get_estimated_time_remaining,
    )

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
                    export_to_csv(results, filename=SPECIFIC_CSV_PATH)
                    status = f"Scraping de {len(urls)} produits spécifiques terminé avec succès!"
                finally:
                    driver.quit()
                
            elif scrape_type == "category":
                # Scraper toute la catégorie (exécution en arrière-plan)
                max_pages = request.form.get("max_pages", "")
                max_pages = int(max_pages) if max_pages.isdigit() and int(max_pages) > 0 else None
                
                # Lancer le scraping dans un thread séparé
                category_url = "https://www.e.leclerc/cat/soins-visage"
                
                # Passer le chemin absolu du fichier CSV
                threading.Thread(
                    target=lambda: scrape_category_pages(category_url, max_pages, output_file=CATEGORY_CSV_PATH)
                ).start()
                
                # Rediriger vers la page de statut
                return redirect(url_for('status_page'))
                
        except Exception as e:
            error = f"Erreur pendant le scraping: {str(e)}"
    
    # Vérifier l'existence des fichiers CSV pour afficher les liens de téléchargement
    specific_file_exists = os.path.isfile(SPECIFIC_CSV_PATH)
    category_file_exists = os.path.isfile(CATEGORY_CSV_PATH)
    
    return render_template(
        "index.html", 
        results=results, 
        error=error, 
        status=status,
        specific_file_exists=specific_file_exists,
        category_file_exists=category_file_exists
    )

@app.route("/status")
def status_page():
    """Affiche la page de statut du scraping"""
    current_status = get_status()
    return render_template("status.html", status=current_status)

@app.route("/api/status")
def status_api():
    """Endpoint API pour obtenir le statut actuel du scraping"""
    current_status = get_status()
    current_status["estimated_time_remaining"] = get_estimated_time_remaining()
    return jsonify(current_status)

@app.route("/results")
def results():
    """Affiche les résultats du scraping"""
    results = []
    try:
        # Vérifier si le fichier CSV existe
        if not os.path.isfile(CATEGORY_CSV_PATH):
            return render_template(
                "results.html", 
                error="Fichier de résultats non trouvé. Veuillez lancer le scraping d'abord.", 
                results=[], 
                total_products=0, 
                page=1, 
                per_page=20, 
                total_pages=1
            )
        
        # Lire le fichier CSV
        with open(CATEGORY_CSV_PATH, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            all_results = list(reader)
            
            if not all_results:
                return render_template(
                    "results.html", 
                    error="Aucune donnée trouvée dans le fichier CSV.", 
                    results=[], 
                    total_products=0, 
                    page=1, 
                    per_page=20, 
                    total_pages=1
                )
            
            # Pagination
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            
            # Calculer le nombre total de pages
            total_pages = (len(all_results) + per_page - 1) // per_page
            
            # Ajuster la page si elle est hors limites
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages
            
            # Extraire la page actuelle
            start_idx = (page - 1) * per_page
            end_idx = min(start_idx + per_page, len(all_results))
            
            # S'assurer que les indices sont valides
            if start_idx >= len(all_results):
                start_idx = 0
                end_idx = min(per_page, len(all_results))
            
            results = all_results[start_idx:end_idx]
            
            return render_template(
                "results.html", 
                results=results, 
                page=page, 
                per_page=per_page, 
                total_pages=total_pages,
                total_products=len(all_results)
            )
    except Exception as e:
        error = f"Erreur lors de la lecture des résultats: {str(e)}"
        return render_template(
            "results.html", 
            error=error, 
            results=[], 
            total_products=0, 
            page=1, 
            per_page=20, 
            total_pages=1
        )

@app.route("/download")
def download_csv():
    """Télécharger le fichier CSV des résultats"""
    if os.path.isfile(CATEGORY_CSV_PATH):
        try:
            return send_file(CATEGORY_CSV_PATH, as_attachment=True, download_name="produits_leclerc_soinsvisage.csv")
        except Exception as e:
            return f"Erreur lors du téléchargement: {str(e)}", 500
    else:
        return "Fichier non disponible", 404

@app.route("/download/<file_type>")
def download_specific_csv(file_type):
    """Télécharger un fichier CSV spécifique"""
    try:
        if file_type == "specific":
            if os.path.isfile(SPECIFIC_CSV_PATH):
                return send_file(SPECIFIC_CSV_PATH, as_attachment=True, download_name="produit_leclerc.csv")
            else:
                return "Fichier de produits spécifiques non disponible", 404
        elif file_type == "category":
            if os.path.isfile(CATEGORY_CSV_PATH):
                return send_file(CATEGORY_CSV_PATH, as_attachment=True, download_name="produits_leclerc_soinsvisage.csv")
            else:
                return "Fichier de catégorie non disponible", 404
        else:
            return "Type de fichier non reconnu", 400
    except Exception as e:
        return f"Erreur lors du téléchargement: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)