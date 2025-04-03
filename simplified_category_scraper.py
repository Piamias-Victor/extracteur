"""
Module simplifié pour interfacer l'application Flask avec les fonctions de scraping
"""
import os
import csv
import time
import platform
import subprocess
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import logging
import re
import traceback

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

# Variables globales pour suivre l'état du scraping
scraping_status = {
    "in_progress": False,
    "total_products": 0,
    "processed_products": 0,
    "start_time": None,
    "last_product": None
}

def get_estimated_time_remaining():
    """Calcule le temps estimé restant pour le scraping"""
    if not scraping_status["in_progress"] or scraping_status["processed_products"] == 0:
        return "Estimation en attente"
    
    elapsed_time = time.time() - scraping_status["start_time"]
    products_per_second = scraping_status["processed_products"] / elapsed_time
    
    if products_per_second == 0:
        return "Calcul en cours..."
    
    remaining_products = scraping_status["total_products"] - scraping_status["processed_products"]
    seconds_remaining = remaining_products / products_per_second
    
    if seconds_remaining < 60:
        return f"{int(seconds_remaining)} secondes"
    elif seconds_remaining < 3600:
        return f"{int(seconds_remaining / 60)} minutes"
    else:
        hours = int(seconds_remaining / 3600)
        minutes = int((seconds_remaining % 3600) / 60)
        return f"{hours} heures {minutes} minutes"

def timestamp_to_time(timestamp):
    """Convertit un timestamp en format lisible"""
    return datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')

def reset_status():
    """Réinitialise le statut du scraping"""
    global scraping_status
    scraping_status = {
        "in_progress": False,
        "total_products": 0,
        "processed_products": 0,
        "start_time": None,
        "last_product": None
    }

def extract_product_links(driver):
    """Extrait tous les liens de produits sur une page"""
    # Attendre que la liste de produits se charge
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a.product-card-link"))
    )
    
    # Extraire les URLs des produits (avec le nouveau sélecteur)
    product_links = []
    product_elements = driver.find_elements(By.CSS_SELECTOR, "a.product-card-link")
    
    for element in product_elements:
        # Obtenir l'URL complète
        href = element.get_attribute("href")
        if href:
            product_links.append(href)
    
    logger.info(f"Extraction de {len(product_links)} liens de produits sur la page")
    return product_links

def scrap_leclerc_product(url, driver):
    """Scrape les informations d'un produit spécifique en utilisant des sélecteurs plus robustes"""
    try:
        driver.get(url)
        time.sleep(2)  # Attendre un peu que la page se charge complètement
        
        # Extraction du titre du produit
        nom = ""
        try:
            # Essayer avec différents sélecteurs possibles pour le titre
            for selector in ["h1.product-block-title", "h1.cbBiP", "h1"]:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    nom = elements[0].text.strip()
                    break
            
            # Si toujours pas de titre, essayer une recherche plus large
            if not nom:
                header_elements = driver.find_elements(By.TAG_NAME, "h1")
                for el in header_elements:
                    if el.text and len(el.text.strip()) > 5:  # Un titre significatif
                        nom = el.text.strip()
                        break
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction du titre: {str(e)}")
            # Utiliser l'URL comme fallback pour le nom
            nom_parts = url.split('/')[-1].split('-')
            nom = ' '.join(nom_parts[:-1])  # Exclure le dernier élément qui est probablement l'EAN
        
        # Extraire l'EAN (depuis l'URL si possible)
        ean = ""
        try:
            # Méthode 1: Extraire de l'URL
            url_parts = url.split('-')
            for part in url_parts:
                # Nettoyage et vérification si c'est un EAN (13 chiffres)
                cleaned_part = re.sub(r'\D', '', part)
                if len(cleaned_part) == 13 and cleaned_part.isdigit():
                    ean = cleaned_part
                    break
            
            # Méthode 2: Chercher dans les tableaux de données
            if not ean:
                # Chercher dans tous les éléments de tableau
                table_cells = driver.find_elements(By.TAG_NAME, "td")
                for cell in table_cells:
                    text = cell.text.strip()
                    # Vérifier si c'est un EAN (13 chiffres)
                    cleaned_text = re.sub(r'\D', '', text)
                    if len(cleaned_text) == 13 and cleaned_text.isdigit():
                        ean = cleaned_text
                        break
            
            # Méthode 3: Recherche générique dans le texte de la page
            if not ean:
                page_text = driver.find_element(By.TAG_NAME, "body").text
                ean_matches = re.findall(r'\b\d{13}\b', page_text)
                if ean_matches:
                    ean = ean_matches[0]
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction de l'EAN: {str(e)}")
        
        # Extraire le prix
        prix = "Non disponible"
        try:
            # Faire une tentative avec différents sélecteurs
            # Méthode 1: Chercher des spans spécifiques pour les euros et centimes
            euros_element = None
            cents_element = None
            
            for selector in [".vcEUR", "span.price-unit", "div.price-unit"]:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    euros_element = elements[0]
                    break
            
            for selector in [".bYgjT", "span.price-cents"]:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    cents_element = elements[0]
                    break
            
            if euros_element and cents_element:
                euros = euros_element.text.strip()
                cents = cents_element.text.strip()
                prix = f"{euros},{cents} €"
            else:
                # Méthode 2: Chercher un élément de prix complet
                price_elements = driver.find_elements(By.CSS_SELECTOR, ".price, .product-price, [data-testid*='price']")
                for el in price_elements:
                    price_text = el.text.strip()
                    if price_text and ('€' in price_text or 'EUR' in price_text):
                        prix = price_text
                        break
                
                # Méthode 3: Recherche de motif de prix dans le texte
                if prix == "Non disponible":
                    page_text = driver.find_element(By.TAG_NAME, "body").text
                    price_matches = re.findall(r'\d+[,\.]\d{2}\s*€', page_text)
                    if price_matches:
                        prix = price_matches[0]
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction du prix: {str(e)}")
        
        # Extraire la marque
        marque = ""
        try:
            # Essayer différents sélecteurs pour la marque
            for selector in ["p.product-brand", ".brand-name", "[data-testid*='brand']"]:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    marque = elements[0].text.strip()
                    break
                    
            # Si aucune marque trouvée, essayer de l'extraire du titre
            if not marque and nom:
                first_word = nom.split(' ')[0]
                if len(first_word) > 2:  # Éviter les petits mots comme "Le" ou "La"
                    marque = first_word
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction de la marque: {str(e)}")
        
        # Extraire la catégorie
        categorie = "Soins Visage"
        
        # Mise à jour du statut
        global scraping_status
        scraping_status["processed_products"] += 1
        scraping_status["last_product"] = nom
        
        return {
            "Lien": url,
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Nom du produit": nom,
            "Marque": marque,
            "Catégorie": categorie,
            "EAN": ean,
            "Prix": prix
        }
    except Exception as e:
        logger.error(f"Erreur lors du scraping du produit {url}: {str(e)}")
        return None

def initialize_webdriver():
    """Initialise le webdriver avec une configuration adaptée pour éviter la détection"""
    options = webdriver.ChromeOptions()
    
    # Options pour éviter la détection
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    
    # Définir un user-agent réaliste
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Masquer WebDriver
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    try:
        # Essayer d'initialiser directement avec les options
        driver = webdriver.Chrome(options=options)
        # Masquer la présence de Selenium
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("WebDriver initialisé avec succès (méthode directe)")
        
        return driver
    except Exception as e:
        logger.warning(f"Échec de l'initialisation directe: {e}")
        try:
            # Utiliser ChromeDriverManager comme fallback
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("WebDriver initialisé avec succès (méthode avec ChromeDriverManager)")
            
            return driver
        except Exception as e2:
            logger.error(f"Échec de l'initialisation avec ChromeDriverManager: {e2}")
            raise Exception("Impossible d'initialiser le WebDriver. Vérifiez que Chrome est installé.") from e2

def determine_total_pages(driver):
    """Détermine le nombre total de pages dans la pagination"""
    try:
        logger.info("Détermination du nombre total de pages...")
        
        # Méthode 1: Chercher le span contenant le nombre total de pages
        # Sélecteur spécifique pour le span contenant le dernier numéro de page
        spans = driver.find_elements(By.TAG_NAME, "span")
        
        # Filtrer pour trouver les spans qui contiennent uniquement un nombre
        page_numbers = []
        for span in spans:
            text = span.text.strip()
            if text.isdigit():
                logger.info(f"Span avec nombre trouvé: '{text}'")
                page_numbers.append(int(text))
        
        if page_numbers:
            max_page = max(page_numbers)
            logger.info(f"Nombre maximal de pages trouvé: {max_page}")
            return max_page
        
        # Méthode 2: Chercher directement dans le texte de la page pour les numéros de page
        page_source = driver.page_source
        # Regex pour trouver des modèles comme 'page=X' dans les URLs
        import re
        page_matches = re.findall(r'page=(\d+)', page_source)
        if page_matches:
            page_numbers = [int(num) for num in page_matches]
            max_page = max(page_numbers)
            logger.info(f"Nombre maximal de pages trouvé dans l'HTML: {max_page}")
            return max_page
            
        # Méthode 3: Essayer de déterminer à partir du nombre total de produits
        try:
            # Recherche de textes comme "1-24 sur 1000 produits"
            result_texts = driver.find_elements(By.CSS_SELECTOR, ".description, .results-count, .product-count")
            for element in result_texts:
                text = element.text
                logger.info(f"Texte de comptage trouvé: '{text}'")
                match = re.search(r'sur\s+(\d+)', text)
                if match:
                    total_products = int(match.group(1))
                    # Généralement 24 produits par page
                    max_page = (total_products + 23) // 24
                    logger.info(f"Estimation des pages basée sur {total_products} produits: {max_page}")
                    return max_page
        except Exception as e:
            logger.warning(f"Erreur lors de l'estimation par nombre de produits: {e}")
        
        # Dernière tentative: chercher dans tout le texte de la page
        body_text = driver.find_element(By.TAG_NAME, "body").text
        logger.info("Recherche dans tout le texte de la page...")
        # Recherche de modèles comme "Page X sur Y" ou "X-Y sur Z produits"
        matches = re.findall(r'sur\s+(\d+)', body_text)
        if matches:
            numbers = [int(match) for match in matches]
            # Supposer que le plus grand nombre est soit le nombre de produits, soit le nombre de pages
            largest = max(numbers)
            if largest > 100:  # Probablement nombre de produits
                max_page = (largest + 23) // 24
            else:  # Probablement déjà le nombre de pages
                max_page = largest
            logger.info(f"Dernier essai: nombre de pages estimé à {max_page}")
            return max_page
            
        # Par défaut, recherche des numéros dans le texte et prendre le plus grand inférieur à 100
        all_numbers = re.findall(r'\b(\d+)\b', body_text)
        if all_numbers:
            potential_pages = [int(n) for n in all_numbers if int(n) < 100 and int(n) > 1]
            if potential_pages:
                max_page = max(potential_pages)
                logger.info(f"Analyse générique: nombre de pages probablement {max_page}")
                return max_page
        
        logger.warning("Impossible de déterminer le nombre de pages, utilisation de la valeur par défaut: 47")
        return 47  # Valeur par défaut basée sur votre information
        
    except Exception as e:
        logger.error(f"Erreur lors de la détermination du nombre de pages: {str(e)}")
        logger.warning("Utilisation de la valeur par défaut: 47")
        return 47  # Valeur par défaut en cas d'erreur

def scrape_category_pages(category_url, max_pages=None, output_file="produits_leclerc_soinsvisage.csv"):
    """Scrape toutes les pages d'une catégorie"""
    results = []
    
    # Réinitialiser le statut
    reset_status()
    scraping_status["in_progress"] = True
    scraping_status["start_time"] = time.time()
    
    driver = None
    try:
        # Initialiser le driver avec la fonction spécialisée
        driver = initialize_webdriver()
        
        # Accepter les cookies si nécessaire
        try:
            driver.get(category_url)
            # Attendre et cliquer sur le bouton d'acceptation des cookies s'il existe
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            ).click()
            logger.info("Cookies acceptés")
        except Exception as e:
            logger.info(f"Pas de bannière de cookies ou erreur: {e}")
        
        # Accéder à la page de la catégorie (à nouveau pour s'assurer que la page est chargée après acceptation des cookies)
        driver.get(category_url)
        
        # Attendre que la page se charge complètement
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.product-card-link"))
        )
        
        # Déterminer le nombre total de pages
        total_pages = determine_total_pages(driver)
        
        if max_pages and max_pages < total_pages:
            total_pages = max_pages
            
        logger.info(f"Nombre total de pages à scraper: {total_pages}")
        
        # Compter le nombre total de produits estimé
        product_links_first_page = extract_product_links(driver)
        scraping_status["total_products"] = len(product_links_first_page) * total_pages
        
        # Générer toutes les URLs de page à l'avance
        page_urls = []
        for page_num in range(1, total_pages + 1):
            if page_num == 1:
                page_urls.append(category_url)
            else:
                page_url = f"{category_url}?page={page_num}&code=NAVIGATION_soins-visage"
                page_urls.append(page_url)
        
        logger.info(f"URLs de pages générées: {len(page_urls)}")
        for idx, url in enumerate(page_urls):
            logger.info(f"URL page {idx+1}: {url}")
        
        # Scraper chaque page
        for page_idx, page_url in enumerate(page_urls):
            current_page = page_idx + 1
            logger.info(f"Scraping de la page {current_page}/{total_pages} - URL: {page_url}")
            
            # Accéder à la page
            driver.get(page_url)
            
            # Attendre que la page se charge complètement
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.product-card-link"))
                )
                # Attendre un peu pour être sûr que tous les produits sont chargés
                time.sleep(2)
            except Exception as e:
                logger.error(f"Erreur lors du chargement de la page {current_page}: {e}")
                continue
            
            # Extraire les liens des produits sur cette page
            product_links = extract_product_links(driver)
            logger.info(f"Page {current_page}: {len(product_links)} produits trouvés")
            
            if not product_links:
                logger.warning(f"Aucun produit trouvé sur la page {current_page}! Vérification du HTML...")
                logger.warning(f"URL de la page: {page_url}")
                # Sauvegarder un extrait du HTML pour déboguer
                html_snippet = driver.page_source[:1000] + "..." + driver.page_source[-1000:]
                logger.warning(f"Extrait du HTML: {html_snippet}")
            
            # Scraper chaque produit
            for link_idx, link in enumerate(product_links):
                try:
                    logger.info(f"Scraping du produit {link_idx+1}/{len(product_links)} de la page {current_page}")
                    product_data = scrap_leclerc_product(link, driver)
                    if product_data:
                        results.append(product_data)
                        logger.info(f"Produit scrapé avec succès: {product_data['Nom du produit']}")
                        
                        # Exporter les résultats périodiquement
                        if len(results) % 5 == 0:  # Exporter tous les 5 produits
                            export_to_csv(results, filename=output_file)
                            # Backup avec la méthode simple
                            simple_export_to_csv(results, filename="backup_" + output_file)
                except Exception as e:
                    logger.error(f"Erreur lors du scraping du produit {link}: {str(e)}")
            
            # Exporter les résultats actuels à chaque page (sauvegarde incrémentale)
            if results:
                logger.info(f"Export incrémental après la page {current_page} avec {len(results)} produits")
                export_to_csv(results, filename=output_file)
                # Backup avec la méthode simple
                simple_export_to_csv(results, filename="backup_" + output_file)
            
    except Exception as e:
        logger.error(f"Erreur lors du scraping de la catégorie: {str(e)}")
    
    finally:
        # Exporter une dernière fois pour s'assurer que toutes les données sont sauvegardées
        if results:
            logger.info(f"Export final avec {len(results)} produits")
            export_to_csv(results, filename=output_file)
            # Backup avec la méthode simple
            simple_export_to_csv(results, filename="backup_" + output_file)
        
        # Mettre à jour le statut final
        scraping_status["in_progress"] = False
        if driver:
            driver.quit()
    
    return results

def export_to_csv(data, filename="produits_leclerc_soinsvisage.csv"):
    """Exporte les données dans un fichier CSV avec logs améliorés"""
    if not data:
        logger.warning("Aucune donnée à exporter")
        return
    
    try:
        # Utiliser un chemin absolu pour le fichier
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_path = os.path.join(script_dir, filename)
        
        logger.info(f"Exportation des données vers: {abs_path}")
        logger.info(f"Nombre d'enregistrements: {len(data)}")
        
        # Afficher des infos sur le répertoire
        logger.info(f"Répertoire du script: {script_dir}")
        logger.info(f"Répertoire existe: {os.path.exists(script_dir)}")
        logger.info(f"Permissions d'écriture: {os.access(script_dir, os.W_OK)}")
        
        # Assurez-vous que nous pouvons écrire dans le répertoire
        if not os.access(script_dir, os.W_OK):
            logger.error(f"Pas de permission d'écriture dans {script_dir}")
            # Essayer d'utiliser le chemin relatif plutôt qu'absolu
            abs_path = filename
            logger.info(f"Tentative avec chemin relatif: {abs_path}")
        
        # Exporter les données en mode écriture
        with open(abs_path, mode="w", newline="", encoding="utf-8") as f:
            # Déterminer les en-têtes (toutes les clés possibles)
            all_keys = set()
            for item in data:
                all_keys.update(item.keys())
            
            fieldnames = sorted(list(all_keys))
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
            
            # Force l'écriture sur disque
            f.flush()
            os.fsync(f.fileno())
        
        # Vérifier si le fichier a été créé
        if os.path.isfile(abs_path):
            file_size = os.path.getsize(abs_path)
            logger.info(f"✅ Fichier CSV créé avec succès! Chemin: {abs_path}, Taille: {file_size} octets")
        else:
            logger.error(f"❌ Le fichier CSV n'a pas été créé: {abs_path}")
            
            # Essayer avec le répertoire courant
            current_dir = os.getcwd()
            fallback_path = os.path.join(current_dir, filename)
            logger.info(f"Tentative avec le répertoire courant: {fallback_path}")
            
            with open(fallback_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
                
                # Force l'écriture sur disque
                f.flush()
                os.fsync(f.fileno())
            
            if os.path.isfile(fallback_path):
                file_size = os.path.getsize(fallback_path)
                logger.info(f"✅ Fichier CSV créé avec succès (fallback)! Chemin: {fallback_path}, Taille: {file_size} octets")
            else:
                logger.error(f"❌ Échec de la création du fichier CSV (fallback): {fallback_path}")
        
        return abs_path  # Retourner le chemin pour confirmation
    
    except PermissionError as pe:
        logger.error(f"ERREUR DE PERMISSION: {str(pe)}")
        logger.error(f"Utilisateur actuel: {os.getlogin() if hasattr(os, 'getlogin') else 'Inconnu'}")
        # Essayer la version simplifiée en dernier recours
        simple_export_to_csv(data, filename)
        return None
        
    except Exception as e:
        logger.error(f"Erreur lors de l'export CSV: {str(e)}")
        logger.error(traceback.format_exc())
        # Essayer la version simplifiée en dernier recours
        simple_export_to_csv(data, filename)
        return None

def simple_export_to_csv(data, filename="produits_leclerc_simple.csv"):
    """Version ultra-simplifiée pour garantir la création du fichier CSV"""
    if not data:
        print("Aucune donnée à exporter")
        return
    
    try:
        # Utiliser un chemin relatif pour être à la racine du projet
        print(f"Exportation des données vers: {filename}")
        
        # Créer le fichier en mode texte sans complications
        with open(filename, 'w', encoding='utf-8') as f:
            # Créer l'en-tête
            headers = sorted(list(set().union(*[d.keys() for d in data])))
            header_line = ','.join([f'"{h}"' for h in headers])
            f.write(header_line + '\n')
            
            # Écrire les données
            for item in data:
                values = []
                for header in headers:
                    value = item.get(header, '')
                    # Échapper les guillemets et les virgules
                    if isinstance(value, str):
                        value = value.replace('"', '""')
                        value = f'"{value}"'
                    values.append(str(value))
                f.write(','.join(values) + '\n')
        
        print(f"✅ Fichier créé avec succès: {filename}")
        
        # Vérification
        if os.path.exists(filename):
            print(f"   Taille: {os.path.getsize(filename)} octets")
        else:
            print(f"❌ Le fichier n'a pas été créé!")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'export: {str(e)}")
        traceback.print_exc()

def scrape_category_pages(category_url, max_pages=None, output_file="produits_leclerc_soinsvisage.csv"):
    """Scrape toutes les pages d'une catégorie"""
    results = []
    
    # Réinitialiser le statut
    reset_status()
    scraping_status["in_progress"] = True
    scraping_status["start_time"] = time.time()
    
    driver = None
    try:
        # Initialiser le driver avec la fonction spécialisée
        driver = initialize_webdriver()
        
        # Accepter les cookies si nécessaire
        try:
            driver.get(category_url)
            # Attendre et cliquer sur le bouton d'acceptation des cookies s'il existe
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            ).click()
            logger.info("Cookies acceptés")
        except Exception as e:
            logger.info(f"Pas de bannière de cookies ou erreur: {e}")
        
        # Accéder à la page de la catégorie (à nouveau pour s'assurer que la page est chargée après acceptation des cookies)
        driver.get(category_url)
        
        # Attendre que la page se charge complètement
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.product-card-link"))
        )
        
        # Déterminer le nombre total de pages
        total_pages = determine_total_pages(driver)
        
        if max_pages and max_pages < total_pages:
            total_pages = max_pages
            
        logger.info(f"Nombre total de pages à scraper: {total_pages}")
        
        # Compter le nombre total de produits estimé
        product_links_first_page = extract_product_links(driver)
        scraping_status["total_products"] = len(product_links_first_page) * total_pages
        
        # Scraper chaque page
        current_page = 1
        while current_page <= total_pages:
            logger.info(f"Scraping de la page {current_page}/{total_pages}")
            
            # Extraire les liens des produits sur la page actuelle
            product_links = extract_product_links(driver) if current_page > 1 else product_links_first_page
            
            # Scraper chaque produit
            for link in product_links:
                try:
                    product_data = scrap_leclerc_product(link, driver)
                    if product_data:
                        results.append(product_data)
                        logger.info(f"Produit scrapé avec succès: {product_data['Nom du produit']}")
                        
                        # Exporter les résultats après chaque produit pour garantir la sauvegarde
                        if len(results) % 5 == 0:  # Exporter tous les 5 produits
                            export_to_csv(results, filename=output_file)
                            # Backup avec la méthode simple
                            simple_export_to_csv(results, filename="backup_" + output_file)
                except Exception as e:
                    logger.error(f"Erreur lors du scraping du produit {link}: {str(e)}")
            
            # Passer à la page suivante si ce n'est pas la dernière
            if current_page < total_pages:
                try:
                    # Construire l'URL de la page suivante
                    next_page = current_page + 1
                    next_page_url = f"{category_url}?page={next_page}"
                    # Alternatives si le format ci-dessus ne fonctionne pas
                    if "?" in category_url:
                        next_page_url = f"{category_url}&page={next_page}"
                    
                    driver.get(next_page_url)
                    
                    # Attendre que la nouvelle page se charge
                    WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.product-card-link"))
                    )
                    
                    # Attendre un peu pour être sûr que la page est complètement chargée
                    time.sleep(2)
                    
                    current_page += 1
                except Exception as e:
                    logger.error(f"Erreur lors du passage à la page suivante: {str(e)}")
                    break
            else:
                break
            
            # Exporter les résultats actuels à chaque page (sauvegarde incrémentale)
            export_to_csv(results, filename=output_file)
            # Backup avec la méthode simple
            simple_export_to_csv(results, filename="backup_" + output_file)
            
    except Exception as e:
        logger.error(f"Erreur lors du scraping de la catégorie: {str(e)}")
    
    finally:
        # Exporter une dernière fois pour s'assurer que toutes les données sont sauvegardées
        if results:
            logger.info(f"Export final avec {len(results)} produits")
            export_to_csv(results, filename=output_file)
            # Backup avec la méthode simple
            simple_export_to_csv(results, filename="backup_" + output_file)
        
        # Mettre à jour le statut final
        scraping_status["in_progress"] = False
        if driver:
            driver.quit()
    
    return results

def batch_scrape_products(urls, batch_size=10, output_file="produits_leclerc.csv", start_index=0):
    """
    Scrape les produits par lots avec sauvegarde intermédiaire
    """
    all_results = []
    
    # Chargement des données déjà scrapées si le fichier existe
    if os.path.exists(output_file) and start_index > 0:
        with open(output_file, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            all_results = list(reader)
    
    # Boucle de scraping par lots
    total_urls = len(urls)
    
    for i in range(start_index, total_urls, batch_size):
        print(f"Traitement du lot {i//batch_size + 1}/{(total_urls + batch_size - 1)//batch_size}...")
        
        # Prendre le prochain lot d'URLs
        batch_urls = urls[i:i+batch_size]
        batch_results = []
        
        # Scraper chaque URL du lot
        for url in batch_urls:
            try:
                driver = initialize_webdriver()
                try:
                    product_data = scrap_leclerc_product(url, driver)
                    batch_results.append(product_data)
                    
                    # Pause aléatoire entre chaque requête
                    time.sleep(1 + 2 * random.random())
                finally:
                    driver.quit()
            except Exception as e:
                logger.error(f"Erreur lors du traitement de l'URL {url}: {str(e)}")
        
        # Ajouter les résultats du lot aux résultats globaux
        all_results.extend(batch_results)
        
        # Sauvegarder les résultats intermédiaires
        export_to_csv(all_results, output_file)
        # Backup avec la méthode simple
        simple_export_to_csv(all_results, "backup_" + output_file)
        
        print(f"Progression: {min(i + batch_size, total_urls)}/{total_urls} produits traités")
        
        # Pause entre les lots pour éviter d'être bloqué
        if i + batch_size < total_urls:
            pause_time = 5 + 5 * random.random()
            print(f"Pause de {pause_time:.1f} secondes avant le prochain lot...")
            time.sleep(pause_time)
    
    return all_results

def resume_scraping(urls_file="product_urls.json", output_file="produits_leclerc.csv", batch_size=10):
    """
    Reprend le scraping là où il s'est arrêté
    """
    # Charger les URLs
    urls = load_product_urls(urls_file)
    
    if not urls:
        print("Aucune URL trouvée. Veuillez d'abord exécuter get_all_parapharma_product_urls().")
        return []
    
    # Vérifier s'il y a des résultats précédents
    start_index = 0
    if os.path.exists(output_file):
        with open(output_file, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            previous_results = list(reader)
            start_index = len(previous_results)
            
        print(f"Reprise du scraping à partir de l'index {start_index}/{len(urls)}")
    
    # Continuer le scraping
    return batch_scrape_products(urls, batch_size, output_file, start_index)

# Fonction pour récupérer le statut actuel du scraping
def get_status():
    return scraping_status

# Fonction ajoutée pour charger les URLs depuis un fichier JSON
def load_product_urls(filename="product_urls.json"):
    """
    Charge les URLs des produits depuis un fichier JSON
    """
    if os.path.exists(filename):
        try:
            import json
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement des URLs: {str(e)}")
    return []

# Import ajouté pour random
import random