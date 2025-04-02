from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import csv
import time
import os
import re
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper_log.txt"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extract_product_links(driver):
    """Extrait tous les liens de produits sur une page"""
    # Attendre que la liste de produits se charge
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "app-product-card-result-list a"))
    )
    
    # Extraire les URLs des produits
    product_links = []
    product_elements = driver.find_elements(By.CSS_SELECTOR, "app-product-card-result-list a.product-visual")
    
    for element in product_elements:
        # Obtenir l'URL complète
        href = element.get_attribute("href")
        if href:
            product_links.append(href)
    
    logger.info(f"Extraction de {len(product_links)} liens de produits sur la page")
    return product_links

def scrap_leclerc_product(url, driver):
    """Scrape les informations d'un produit spécifique"""
    try:
        driver.get(url)
        
        # Attendre que les éléments principaux soient chargés
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.product-block-title"))
        )
        
        # Extraction des informations produit
        nom = driver.find_element(By.CSS_SELECTOR, "h1.product-block-title").text.strip()
        
        # Extraire l'EAN (parfois dans différents éléments)
        ean = ""
        try:
            ean_elements = driver.find_elements(By.CSS_SELECTOR, "div.attribute-value.ng-star-inserted")
            for element in ean_elements:
                text = element.text.strip()
                # Vérifier si le texte correspond à un format EAN (13 chiffres)
                if re.match(r'^\d{13}$', text):
                    ean = text
                    break
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction de l'EAN: {str(e)}")
        
        # Extraire le prix
        try:
            euros = driver.find_element(By.CSS_SELECTOR, "div.price-unit.ng-star-inserted").text.strip()
            cents = driver.find_element(By.CSS_SELECTOR, "span.price-cents").text.strip().replace(",", "").strip()
            prix = f"{euros},{cents} €"
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction du prix: {str(e)}")
            prix = "Non disponible"
        
        # Extraire la marque
        marque = ""
        try:
            marque_element = driver.find_element(By.CSS_SELECTOR, "p.product-brand")
            if marque_element:
                marque = marque_element.text.strip()
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction de la marque: {str(e)}")
        
        # Extraire la catégorie
        categorie = "Soins Visage"
        
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

def scrape_category_pages(category_url, max_pages=None):
    """Scrape toutes les pages d'une catégorie"""
    results = []
    
    # Configuration du navigateur
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Exécution sans interface graphique
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Accéder à la page de la catégorie
        driver.get(category_url)
        
        # Attendre que la page se charge
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "app-product-card-result-list"))
        )
        
        # Déterminer le nombre total de pages
        pagination_text = driver.find_element(By.CSS_SELECTOR, "li.small-screen").text.strip()
        total_pages = int(pagination_text.split("/")[1].strip())
        
        if max_pages and max_pages < total_pages:
            total_pages = max_pages
            
        logger.info(f"Nombre total de pages à scraper: {total_pages}")
        
        # Scraper chaque page
        current_page = 1
        while current_page <= total_pages:
            logger.info(f"Scraping de la page {current_page}/{total_pages}")
            
            # Extraire les liens des produits sur la page actuelle
            product_links = extract_product_links(driver)
            
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
                    # Cliquer sur le bouton "page suivante"
                    next_button = driver.find_element(By.CSS_SELECTOR, "li.pagination-next a")
                    next_button.click()
                    
                    # Attendre que la nouvelle page se charge
                    WebDriverWait(driver, 30).until(
                        EC.staleness_of(next_button)
                    )
                    WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "app-product-card-result-list"))
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
            export_to_csv(results, filename="produits_leclerc_soinsvisage.csv")
            
    except Exception as e:
        logger.error(f"Erreur lors du scraping de la catégorie: {str(e)}")
    
    finally:
        driver.quit()
    
    return results

def export_to_csv(data, filename="produits_leclerc_soinsvisage.csv"):
    """Exporte les données dans un fichier CSV"""
    if not data:
        logger.warning("Aucune donnée à exporter")
        return
    
    # Vérifier si le fichier existe déjà pour déterminer s'il faut écrire les en-têtes
    file_exists = os.path.isfile(filename)
    
    with open(filename, mode="a" if file_exists else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        
        if not file_exists:
            writer.writeheader()
        
        writer.writerows(data)
    
    logger.info(f"Données exportées dans {filename}")

if __name__ == "__main__":
    category_url = "https://www.e.leclerc/cat/soins-visage"
    
    # Limiter à un certain nombre de pages pour les tests (None pour toutes les pages)
    max_pages = None
    
    # Lancer le scraping
    logger.info(f"Démarrage du scraping de la catégorie: {category_url}")
    results = scrape_category_pages(category_url, max_pages)
    
    # Export final des résultats
    export_to_csv(results)
    logger.info(f"Scraping terminé. {len(results)} produits récupérés au total.")