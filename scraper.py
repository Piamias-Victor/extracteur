from playwright.sync_api import sync_playwright
from datetime import datetime
import csv

def scrap_leclerc_with_playwright(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_selector("h1.product-block-title")

        nom = page.locator("h1.product-block-title").inner_text().strip()
        ean = page.locator("div.attribute-value.ng-star-inserted").nth(0).inner_text().strip()
        euros = page.locator("div.price-unit.ng-star-inserted").inner_text().strip()
        cents = page.locator("span.price-cents").inner_text().strip().replace(",", "").strip()
        prix = f"{euros},{cents} €"

        browser.close()

        return {
            "Lien": url,
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Nom du produit": nom,
            "EAN": ean,
            "Prix": prix
        }

def export_to_csv(data, filename="produit_leclerc.csv"):
    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)