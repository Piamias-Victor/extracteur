from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify
from simplified_category_scraper import scrape_category_pages, export_to_csv, scrap_leclerc_product, get_status, get_estimated_time_remaining, timestamp_to_time
import os
import csv
import threading
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import logging

app = Flask(__name__)

# Configuration de base du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper_log.txt"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Définir les chemins absolus pour les fichiers de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPECIFIC_CSV_PATH = os.path.join(BASE_DIR, "produit_leclerc.csv")
CATEGORY_CSV_PATH = os.path.join(BASE_DIR, "produits_leclerc_soinsvisage.csv")

# Fonction de diagnostic pour les permissions
def check_file_permissions():
    """Vérifie et corrige les permissions de fichiers"""
    try:
        logger.info(f"Vérification des permissions dans {BASE_DIR}")
        
        # Tester l'écriture dans le répertoire
        test_file_path = os.path.join(BASE_DIR, "test_permission.txt")
        with open(test_file_path, 'w') as f:
            f.write("Test de permission")
        
        # Si on arrive ici, l'écriture a fonctionné
        logger.info(f"✅ Test d'écriture réussi dans {BASE_DIR}")
        
        # Nettoyage du fichier de test
        if os.path.exists(test_file_path):
            os.remove(test_file_path)
            
        return True
    except Exception as e:
        logger.error(f"❌ Erreur de permission: {str(e)}")
        return False

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
    # Vérifier les permissions au début
    check_file_permissions()
    
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
                category_url = "https://www.e.leclerc/cat/marques-parapharmacie"
                
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
    try:
        # Vérifier l'existence du fichier
        if os.path.isfile(CATEGORY_CSV_PATH):
            file_size = os.path.getsize(CATEGORY_CSV_PATH)
            logger.info(f"Fichier trouvé: {CATEGORY_CSV_PATH}, taille: {file_size} octets")
            
            # Si le fichier existe mais est vide, renvoyer une erreur
            if file_size == 0:
                logger.warning(f"Fichier vide: {CATEGORY_CSV_PATH}")
                return "Fichier vide, aucune donnée à télécharger", 404
                
            # Essayer de renvoyer le fichier
            try:
                return send_file(
                    CATEGORY_CSV_PATH,
                    as_attachment=True,
                    download_name="produits_leclerc_soinsvisage.csv",
                    mimetype='text/csv'
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi du fichier: {str(e)}")
                # Essayer une approche alternative
                with open(CATEGORY_CSV_PATH, 'r', encoding='utf-8') as f:
                    csv_content = f.read()
                response = app.response_class(
                    response=csv_content,
                    status=200,
                    mimetype='text/csv'
                )
                response.headers["Content-Disposition"] = "attachment; filename=produits_leclerc_soinsvisage.csv"
                return response
        else:
            logger.warning(f"Fichier non disponible: {CATEGORY_CSV_PATH}")
            return "Fichier non disponible. Veuillez d'abord exécuter le scraping.", 404
    except Exception as e:
        logger.error(f"Erreur lors du téléchargement: {str(e)}")
        return f"Erreur lors du téléchargement: {str(e)}", 500

@app.route("/download/<file_type>")
def download_specific_csv(file_type):
    """Télécharger un fichier CSV spécifique"""
    try:
        if file_type == "specific":
            target_file = SPECIFIC_CSV_PATH
            filename = "produit_leclerc.csv"
        elif file_type == "category":
            target_file = CATEGORY_CSV_PATH
            filename = "produits_leclerc_soinsvisage.csv"
        else:
            return "Type de fichier non reconnu", 400
            
        if os.path.isfile(target_file):
            file_size = os.path.getsize(target_file)
            logger.info(f"Fichier trouvé: {target_file}, taille: {file_size} octets")
            
            if file_size == 0:
                return "Fichier vide, aucune donnée à télécharger", 404
            
            try:
                return send_file(
                    target_file,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='text/csv'
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi du fichier: {str(e)}")
                # Approche alternative
                with open(target_file, 'r', encoding='utf-8') as f:
                    csv_content = f.read()
                response = app.response_class(
                    response=csv_content,
                    status=200,
                    mimetype='text/csv'
                )
                response.headers["Content-Disposition"] = f"attachment; filename={filename}"
                return response
        else:
            return f"Fichier {filename} non disponible", 404
    except Exception as e:
        logger.error(f"Erreur lors du téléchargement: {str(e)}")
        return f"Erreur lors du téléchargement: {str(e)}", 500

# Code de diagnostic qui s'exécute au démarrage
@app.before_first_request
def check_environment():
    """Vérifier l'environnement au démarrage de l'application"""
    logger.info("----- DIAGNOSTIC D'ENVIRONNEMENT -----")
    # Vérifier les chemins
    logger.info(f"Répertoire de base: {BASE_DIR}")
    logger.info(f"Chemin du CSV spécifique: {SPECIFIC_CSV_PATH}")
    logger.info(f"Chemin du CSV de catégorie: {CATEGORY_CSV_PATH}")
    
    # Vérifier les permissions
    try:
        # Vérifier si on peut écrire dans le répertoire de base
        test_file = os.path.join(BASE_DIR, "test_write.tmp")
        with open(test_file, 'w') as f:
            f.write("Test d'écriture")
        if os.path.exists(test_file):
            os.remove(test_file)
            logger.info(f"✅ Test d'écriture réussi dans {BASE_DIR}")
        else:
            logger.error(f"❌ Échec du test d'écriture dans {BASE_DIR}")
    except Exception as e:
        logger.error(f"❌ Erreur lors du test d'écriture: {str(e)}")
    
    # Vérifier si les fichiers CSV existent déjà
    logger.info(f"Le fichier spécifique existe: {os.path.exists(SPECIFIC_CSV_PATH)}")
    logger.info(f"Le fichier de catégorie existe: {os.path.exists(CATEGORY_CSV_PATH)}")
    
    # Vérifier l'environnement Python
    logger.info(f"Version Python: {sys.version}")
    logger.info(f"Encodage par défaut: {sys.getdefaultencoding()}")
    logger.info(f"Répertoire de travail actuel: {os.getcwd()}")
    logger.info("----- FIN DU DIAGNOSTIC -----")

if __name__ == "__main__":
    app.run(debug=True)