from playwright.sync_api import sync_playwright
from datetime import datetime
import csv
import time
import json
import os
import random

def get_all_parapharma_product_urls(base_url="https://www.e.leclerc/cat/parapharmacie", max_pages=None):
    """
    Récupère toutes les URLs des produits de parapharmacie
    """
    product_urls = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        
        # Accéder à la première page de la catégorie
        page.goto(base_url, timeout=60000)
        
        # Accepter les cookies si nécessaire
        try:
            if page.locator("button#onetrust-accept-btn-handler").count() > 0:
                page.click("button#onetrust-accept-btn-handler")
        except:
            pass
            
        # Attendre que les produits se chargent
        page.wait_for_selector("div.product-thumbnail", timeout=30000)
        
        current_page = 1
        has_next_page = True
        
        while has_next_page and (max_pages is None or current_page <= max_pages):
            print(f"Scraping page {current_page}...")
            
            # Attendre que tous les produits soient chargés
            page.wait_for_selector("div.product-thumbnail", timeout=30000)
            
            # Récupérer les URLs des produits sur cette page
            product_cards = page.locator("div.product-thumbnail a.thumbnail-product-content").all()
            
            for card in product_cards:
                href = card.get_attribute("href")
                if href:
                    full_url = f"https://www.e.leclerc{href}"
                    product_urls.append(full_url)
                    print(f"Added product URL: {full_url}")
            
            # Vérifier s'il y a une page suivante
            next_button = page.locator("li.next:not(.disabled) a").first
            
            if next_button.count() > 0:
                next_button.click()
                time.sleep(random.uniform(1, 2))  # Pause aléatoire pour éviter d'être détecté
                current_page += 1
            else:
                has_next_page = False
        
        browser.close()
    
    print(f"Total des produits trouvés: {len(product_urls)}")
    return product_urls

def save_product_urls(urls, filename="product_urls.json"):
    """
    Sauvegarde les URLs des produits dans un fichier JSON
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(urls, f)

def load_product_urls(filename="product_urls.json"):
    """
    Charge les URLs des produits depuis un fichier JSON
    """
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def scrap_leclerc_with_playwright(url, retry_count=3):
    """
    Scrape les données d'un produit Leclerc avec Playwright
    Ajoute un mécanisme de retry en cas d'échec
    """
    for attempt in range(retry_count):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
                page = context.new_page()
                
                # Aller sur la page produit
                page.goto(url, timeout=60000)
                
                # Accepter les cookies si nécessaire
                try:
                    if page.locator("button#onetrust-accept-btn-handler").count() > 0:
                        page.click("button#onetrust-accept-btn-handler")
                except:
                    pass
                
                # Attendre que les éléments nécessaires se chargent
                page.wait_for_selector("h1.product-block-title", timeout=30000)

                # Récupérer les informations du produit
                nom = page.locator("h1.product-block-title").inner_text().strip()
                
                # Récupérer l'EAN (s'il existe)
                ean = ""
                try:
                    ean = page.locator("div.attribute-value.ng-star-inserted").nth(0).inner_text().strip()
                except:
                    # L'EAN n'est peut-être pas disponible pour tous les produits
                    pass
                
                # Récupérer le prix
                prix_complet = ""
                try:
                    euros = page.locator("div.price-unit.ng-star-inserted").inner_text().strip()
                    cents = page.locator("span.price-cents").inner_text().strip().replace(",", "").strip()
                    prix_complet = f"{euros},{cents} €"
                except:
                    # Tenter une autre méthode pour récupérer le prix
                    try:
                        prix_complet = page.locator("div.product-price").inner_text().strip()
                    except:
                        prix_complet = "Prix non disponible"
                
                # Récupérer la catégorie du produit
                categorie = ""
                try:
                    breadcrumbs = page.locator("ol.breadcrumb li").all()
                    if len(breadcrumbs) > 2:  # Premier = Accueil, Dernier = Produit actuel
                        categorie = breadcrumbs[-2].inner_text().strip()
                except:
                    pass
                
                # Récupérer la marque du produit
                marque = ""
                try:
                    marque = page.locator("div.brand-name a").inner_text().strip()
                except:
                    pass
                
                browser.close()
                
                # Créer et retourner l'objet de données
                return {
                    "Lien": url,
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Nom du produit": nom,
                    "EAN": ean,
                    "Prix": prix_complet,
                    "Catégorie": categorie,
                    "Marque": marque
                }
                
        except Exception as e:
            print(f"Erreur lors du scraping de {url}, tentative {attempt+1}/{retry_count}: {str(e)}")
            if attempt < retry_count - 1:
                # Attendre avant de réessayer (temps d'attente exponentiel)
                time.sleep(5 * (attempt + 1))
            else:
                # Toutes les tentatives ont échoué
                return {
                    "Lien": url,
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Nom du produit": "Erreur lors du scraping",
                    "EAN": "",
                    "Prix": "",
                    "Catégorie": "",
                    "Marque": ""
                }

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
                product_data = scrap_leclerc_with_playwright(url)
                batch_results.append(product_data)
                
                # Pause aléatoire entre chaque requête
                time.sleep(random.uniform(1, 3))
            except Exception as e:
                print(f"Erreur lors du traitement de l'URL {url}: {str(e)}")
        
        # Ajouter les résultats du lot aux résultats globaux
        all_results.extend(batch_results)
        
        # Sauvegarder les résultats intermédiaires
        export_to_csv(all_results, output_file)
        
        print(f"Progression: {min(i + batch_size, total_urls)}/{total_urls} produits traités")
        
        # Pause entre les lots pour éviter d'être bloqué
        if i + batch_size < total_urls:
            pause_time = random.uniform(5, 10)
            print(f"Pause de {pause_time:.1f} secondes avant le prochain lot...")
            time.sleep(pause_time)
    
    return all_results

def export_to_csv(data, filename="produits_leclerc.csv"):
    """
    Exporte les données dans un fichier CSV
    """
    if not data:
        print("Aucune donnée à exporter.")
        return
        
    # Assurer que toutes les clés possibles sont incluses dans les en-têtes
    fieldnames = set()
    for item in data:
        fieldnames.update(item.keys())
    
    fieldnames = sorted(list(fieldnames))
    
    # Écrire les données dans le fichier CSV
    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    
    print(f"Données exportées avec succès dans {filename}")

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


if __name__ == "__main__":
    # Exemple d'utilisation
    # 1. Récupérer toutes les URLs (à faire une seule fois)
    # urls = get_all_parapharma_product_urls(max_pages=5)  # Limiter à 5 pages pour test
    # save_product_urls(urls)
    
    # 2. Scraper les produits (peut être exécuté en plusieurs fois)
    # resume_scraping(batch_size=5)
    pass