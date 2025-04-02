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
        # Attendre que la pagination se charge
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "nav.pagination"))
        )
        
        # Méthode 1: Chercher le dernier lien de pagination
        pagination_links = driver.find_elements(By.CSS_SELECTOR, "nav.pagination a")
        if pagination_links:
            # Filtrer pour ne garder que les liens avec des chiffres
            page_numbers = []
            for link in pagination_links:
                text = link.text.strip()
                if text.isdigit():
                    page_numbers.append(int(text))
            
            if page_numbers:
                return max(page_numbers)
        
        # Méthode 2: Chercher d'autres éléments indiquant le nombre de pages
        pagination_text = driver.find_element(By.CSS_SELECTOR, "nav.pagination").text
        matches = re.findall(r'\d+', pagination_text)
        if matches:
            return int(matches[-1])
            
        # Méthode 3: Essayer de déterminer à partir du nombre total de produits et de la taille de page
        try:
            # Souvent affiché comme "1-24 sur 123 produits"
            result_count_element = driver.find_element(By.CSS_SELECTOR, ".product-count, .result-count")
            if result_count_element:
                result_text = result_count_element.text
                total_matches = re.search(r'sur\s+(\d+)', result_text)
                if total_matches:
                    total_products = int(total_matches.group(1))
                    # Généralement 24 produits par page
                    return (total_products + 23) // 24
        except:
            pass
        
        # Par défaut, supposer au moins une page
        return 1
    except Exception as e:
        logger.warning(f"Impossible de déterminer le nombre total de pages: {e}")
        return 1  # Par défaut, supposer au moins une page

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
            
    except Exception as e:
        logger.error(f"Erreur lors du scraping de la catégorie: {str(e)}")
    
    finally:
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
        # Obtenir le chemin absolu pour être sûr
        abs_path = os.path.abspath(filename)
        logger.info(f"Tentative d'écriture du fichier CSV à : {abs_path}")
        
        # Vérifier si le répertoire existe et est accessible en écriture
        dir_path = os.path.dirname(abs_path)
        if not os.path.exists(dir_path):
            logger.warning(f"Le répertoire {dir_path} n'existe pas. Création...")
            os.makedirs(dir_path, exist_ok=True)
            
        # Vérifier si on peut écrire dans le répertoire
        if not os.access(dir_path, os.W_OK):
            logger.error(f"Pas de permission d'écriture dans {dir_path}")
            return
            
        # Vérifier si le fichier existe déjà pour déterminer s'il faut écrire les en-têtes
        file_exists = os.path.isfile(abs_path)
        logger.info(f"Le fichier existe déjà ? {file_exists}")
        
        with open(abs_path, mode="a" if file_exists else "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerows(data)
            logger.info(f"Données exportées dans {abs_path} - {len(data)} enregistrements")
            
        # Vérifier si le fichier a été créé avec succès
        if os.path.isfile(abs_path):
            file_size = os.path.getsize(abs_path)
            logger.info(f"Fichier créé avec succès. Taille : {file_size} octets")
        else:
            logger.error(f"Échec de la création du fichier {abs_path}")
            
    except Exception as e:
        logger.error(f"Erreur lors de l'export CSV : {str(e)}")

# Fonction pour récupérer le statut actuel du scraping
def get_status():
    return scraping_status