# diagnostic.py - Exécutez ce script pour diagnostiquer et corriger les problèmes de permissions

import os
import sys
import logging
import stat
import traceback

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("diagnostic")

def print_separator():
    print("\n" + "=" * 60 + "\n")

def check_python_environment():
    """Vérifie l'environnement Python"""
    print_separator()
    logger.info("VÉRIFICATION DE L'ENVIRONNEMENT PYTHON")
    logger.info(f"Version Python: {sys.version}")
    logger.info(f"Encodage par défaut: {sys.getdefaultencoding()}")
    logger.info(f"Répertoire de travail actuel: {os.getcwd()}")
    logger.info(f"Chemin du script: {os.path.abspath(__file__)}")
    
    # Vérifier l'utilisateur
    try:
        import getpass
        username = getpass.getuser()
        logger.info(f"Utilisateur exécutant le script: {username}")
    except Exception as e:
        logger.warning(f"Impossible de déterminer l'utilisateur: {str(e)}")

def check_directory_permissions():
    """Vérifie les permissions du répertoire du projet"""
    print_separator()
    logger.info("VÉRIFICATION DES PERMISSIONS DE RÉPERTOIRE")
    
    # Chemin du répertoire du projet
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logger.info(f"Répertoire du projet: {script_dir}")
    
    # Vérifier l'existence et les permissions
    if os.path.exists(script_dir):
        logger.info("✅ Le répertoire existe")
        
        # Vérifier les permissions
        readable = os.access(script_dir, os.R_OK)
        writable = os.access(script_dir, os.W_OK)
        executable = os.access(script_dir, os.X_OK)
        
        logger.info(f"Lecture: {'✅' if readable else '❌'}")
        logger.info(f"Écriture: {'✅' if writable else '❌'}")
        logger.info(f"Exécution: {'✅' if executable else '❌'}")
        
        # Afficher les permissions en format Unix
        try:
            stat_info = os.stat(script_dir)
            permissions = stat.S_IMODE(stat_info.st_mode)
            logger.info(f"Permissions (octal): {oct(permissions)}")
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des permissions: {str(e)}")
    else:
        logger.error("❌ Le répertoire n'existe pas!")

def test_file_creation():
    """Teste la création de fichiers"""
    print_separator()
    logger.info("TEST DE CRÉATION DE FICHIERS")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = [
        os.path.join(script_dir, "test_file.txt"),
        os.path.join(script_dir, "produits_leclerc_soinsvisage.csv"),
        os.path.join(script_dir, "produit_leclerc.csv")
    ]
    
    for test_file in test_files:
        try:
            logger.info(f"Essai de création: {test_file}")
            with open(test_file, 'w') as f:
                f.write("Test de création de fichier")
            
            if os.path.exists(test_file):
                logger.info(f"✅ Fichier créé avec succès: {test_file}")
                
                # Vérifier la taille
                size = os.path.getsize(test_file)
                logger.info(f"   Taille: {size} octets")
                
                # Nettoyage
                os.remove(test_file)
                logger.info(f"   Fichier supprimé")
            else:
                logger.error(f"❌ Le fichier n'a pas été créé: {test_file}")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la création du fichier {test_file}: {str(e)}")
            logger.error(traceback.format_exc())

def fix_permissions():
    """Tente de corriger les permissions"""
    print_separator()
    logger.info("TENTATIVE DE CORRECTION DES PERMISSIONS")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        # Sur Unix/Linux/macOS, on peut utiliser chmod
        if sys.platform != "win32":
            import subprocess
            logger.info(f"Exécution de chmod 755 sur {script_dir}")
            subprocess.run(["chmod", "-R", "755", script_dir], check=True)
            logger.info("✅ Permissions modifiées avec chmod")
            
            # Vérifier également si le répertoire appartient à l'utilisateur actuel
            subprocess.run(["whoami"], check=True)
            logger.info("✅ Vérification de l'utilisateur terminée")
        else:
            # Sur Windows
            logger.info("Sur Windows, on va essayer de modifier les attributs du dossier")
            try:
                # Utiliser icacls pour donner les droits complets
                import subprocess
                command = f'icacls "{script_dir}" /grant:r *S-1-1-0:(OI)(CI)F /T'
                logger.info(f"Exécution de: {command}")
                subprocess.run(command, shell=True, check=True)
                logger.info("✅ Permissions modifiées avec icacls")
            except:
                logger.warning("Impossible de modifier les permissions avec icacls")
                logger.info("Sur Windows, assurez-vous d'exécuter ce script en tant qu'administrateur")
    except Exception as e:
        logger.error(f"❌ Erreur lors de la modification des permissions: {str(e)}")
        logger.error(traceback.format_exc())

def check_csv_libraries():
    """Vérifie les bibliothèques pour manipuler les CSV"""
    print_separator()
    logger.info("VÉRIFICATION DES BIBLIOTHÈQUES CSV")
    
    try:
        import csv
        logger.info("✅ Module csv importé avec succès")
        
        # Vérifier si nous pouvons créer un CSV de test
        test_file = os.path.join(os.getcwd(), "test_csv.csv")
        data = [
            {"nom": "Produit 1", "prix": "10,99 €", "marque": "Test"},
            {"nom": "Produit 2", "prix": "20,50 €", "marque": "Test2"}
        ]
        
        with open(test_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["nom", "prix", "marque"])
            writer.writeheader()
            writer.writerows(data)
        
        # Vérifier si le fichier a été créé
        if os.path.exists(test_file):
            size = os.path.getsize(test_file)
            logger.info(f"✅ Fichier CSV de test créé avec succès ({size} octets)")
            
            # Lire le fichier pour vérifier
            with open(test_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                logger.info(f"✅ Fichier CSV lu avec succès ({len(rows)} lignes)")
            
            # Nettoyer
            os.remove(test_file)
            logger.info("✅ Fichier CSV de test supprimé")
        else:
            logger.error("❌ Échec de la création du fichier CSV de test")
    except Exception as e:
        logger.error(f"❌ Erreur lors des opérations CSV: {str(e)}")
        logger.error(traceback.format_exc())

def test_alternate_paths():
    """Teste l'écriture dans différents chemins (fallbacks)"""
    print_separator()
    logger.info("TEST D'ÉCRITURE DANS DIFFÉRENTS CHEMINS")
    
    paths_to_test = [
        os.getcwd(),  # Répertoire de travail actuel
        os.path.dirname(os.path.abspath(__file__)),  # Répertoire du script
        os.path.expanduser("~"),  # Répertoire personnel
        os.path.join(os.path.expanduser("~"), "Documents"),  # Documents
        os.path.join(os.path.expanduser("~"), "Desktop"),  # Bureau
        "."  # Chemin relatif
    ]
    
    for path in paths_to_test:
        if os.path.exists(path):
            test_file = os.path.join(path, "test_path.txt")
            try:
                logger.info(f"Test d'écriture dans: {path}")
                with open(test_file, 'w') as f:
                    f.write("Test de chemin alternatif")
                
                if os.path.exists(test_file):
                    logger.info(f"✅ Écriture réussie dans: {path}")
                    os.remove(test_file)
                else:
                    logger.error(f"❌ Échec d'écriture dans: {path}")
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'écriture dans {path}: {str(e)}")
        else:
            logger.warning(f"⚠️ Le chemin n'existe pas: {path}")

def main():
    """Fonction principale"""
    logger.info("DÉBUT DU DIAGNOSTIC")
    logger.info(f"Date et heure: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    check_python_environment()
    check_directory_permissions()
    test_file_creation()
    check_csv_libraries()
    test_alternate_paths()
    
    # Demander à l'utilisateur s'il veut tenter de corriger les permissions
    print_separator()
    try:
        response = input("Voulez-vous tenter de corriger les permissions? (o/N): ").strip().lower()
        if response in ['o', 'oui', 'y', 'yes']:
            fix_permissions()
            # Vérifier à nouveau après correction
            check_directory_permissions()
            test_file_creation()
    except Exception as e:
        logger.error(f"Erreur lors de la demande utilisateur: {str(e)}")
    
    print_separator()
    logger.info("FIN DU DIAGNOSTIC")
    logger.info("Si vous rencontrez toujours des problèmes d'écriture de fichiers:")
    logger.info("1. Essayez d'exécuter l'application en tant qu'administrateur/sudo")
    logger.info("2. Vérifiez les paramètres anti-virus qui pourraient bloquer l'écriture")
    logger.info("3. Essayez d'exécuter l'application depuis un autre dossier avec plus de permissions")

# Ajouter l'import de datetime
from datetime import datetime

if __name__ == "__main__":
    main()