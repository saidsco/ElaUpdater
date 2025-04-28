import os
import sys
import json
import requests
import py7zr
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime

CONFIG_FILE = Path("./config.json")
PATCHES_FILE = Path("./patches_local.json")

# Default configuration (used if config.json is missing or invalid)
DEFAULT_CONFIG = {
    "patches_url": "http://uo-elantharil.de:8080/patcher/patches.json",
    "data_dir": "./data",
    "version_map_file": "./versions.json"
}

def load_config():
    """Load configuration from config.json or use defaults if not available."""
    try:
        if not CONFIG_FILE.exists():
            print(f"Warnung: Konfigurationsdatei {CONFIG_FILE} nicht gefunden. Verwende Standardkonfiguration.")
            return DEFAULT_CONFIG
            
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            
        # Ensure all required keys exist
        for key in DEFAULT_CONFIG:
            if key not in config:
                print(f"Warnung: '{key}' fehlt in der Konfiguration. Verwende Standardwert.")
                config[key] = DEFAULT_CONFIG[key]
        return config
    except json.JSONDecodeError:
        print(f"Fehler: Konfigurationsdatei {CONFIG_FILE} ist kein gültiges JSON. Verwende Standardkonfiguration.")
        return DEFAULT_CONFIG
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}. Verwende Standardkonfiguration.")
        return DEFAULT_CONFIG

def download_patches(patches_url):
    """Download patches.json from the specified URL."""
    try:
        print(f"Lade Patches von {patches_url}...")
        response = requests.get(patches_url, timeout=10)
        response.raise_for_status()
        
        # Parse and validate the JSON
        patches = response.json()
        if not isinstance(patches, dict) or not patches:
            raise ValueError("Heruntergeladene Patches-Datei enthält kein gültiges Wörterbuch")
            
        # Save the patches locally for reference
        with open(PATCHES_FILE, "w") as f:
            json.dump(patches, f, indent=4)
            
        return patches
    except requests.exceptions.RequestException as e:
        print(f"Netzwerkfehler beim Herunterladen der Patches: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Fehler: Heruntergeladene Patches-Datei ist kein gültiges JSON")
        return None
    except Exception as e:
        print(f"Fehler beim Herunterladen der Patches: {e}")
        return None

def load_local_patches():
    """Load locally cached patches if available."""
    try:
        if PATCHES_FILE.exists():
            with open(PATCHES_FILE, "r") as f:
                patches = json.load(f)
                print("Patches erfolgreich aus lokalem Cache geladen.")
                return patches
        else:
            print(f"Lokale Patches-Datei {PATCHES_FILE} nicht gefunden.")
            return None
    except json.JSONDecodeError:
        print(f"Fehler: Lokale Patches-Datei {PATCHES_FILE} ist kein gültiges JSON")
        return None
    except Exception as e:
        print(f"Fehler beim Laden der lokalen Patches: {e}")
        return None

def load_version_map(version_map_file):
    """Load version map from the specified file."""
    if not Path(version_map_file).exists():
        return {}
    try:
        with open(version_map_file, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Fehler beim Laden der Versionsübersicht: {e}")
        return {}

def save_version_map(version_map, version_map_file):
    """Save version map to the specified file."""
    try:
        with open(version_map_file, "w") as f:
            json.dump(version_map, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Speichern der Versionsübersicht: {e}")

def get_remote_timestamp(url):
    """Get the last-modified timestamp of a remote file."""
    try:
        response = requests.head(url, timeout=10)
        if response.status_code == 200:
            last_modified = response.headers.get('Last-Modified')
            if last_modified:
                dt = parsedate_to_datetime(last_modified)
                return dt.timestamp()
        return None
    except requests.exceptions.RequestException as e:
        print(f"Netzwerkfehler beim Abrufen des Zeitstempels: {e}")
        return None
    except Exception as e:
        print(f"Fehler beim Abrufen des Zeitstempels: {e}")
        return None

def download_file(url, dest_path):
    """Download a file from URL to the specified destination path."""
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def extract_7z(file_path, extract_to):
    """Extract a 7z archive to the specified directory."""
    with py7zr.SevenZipFile(file_path, mode='r') as archive:
        archive.extractall(path=extract_to)

def check_and_update_files():
    """Main function to check for updates and download/extract files as needed."""
    # Load configuration
    config = load_config()
    data_dir = Path(config["data_dir"])
    version_map_file = config["version_map_file"]
    patches_url = config["patches_url"]
    
    # Load version map
    version_map = load_version_map(version_map_file)
    
    # Ensure data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Download patches from URL
    patches = download_patches(patches_url)
    
    # If download fails, try to use the local copy
    if patches is None:
        print("Versuche lokal zwischengespeicherte Patches zu verwenden...")
        patches = load_local_patches()
        
        # If no local copy exists, exit with error
        if patches is None:
            print("Fehler: Patches konnten nicht geladen werden. Fortfahren nicht möglich.")
            sys.exit(1)
    
    # Now process each file in the patches dictionary
    for file_key, url in patches.items():
        print(f"Überprüfe: {file_key}")
        
        try:
            remote_timestamp = get_remote_timestamp(url)
            if remote_timestamp is None:
                print(f"Zeitstempel für {url} konnte nicht abgerufen werden")
                continue
                
            local_timestamp = version_map.get(file_key, 0)
            
            if remote_timestamp > local_timestamp:
                print(f"Neuere Version für '{file_key}' gefunden. Wird heruntergeladen...")
                file_name = url.split("/")[-1]
                download_path = data_dir / file_name
                
                try:
                    download_file(url, download_path)
                    print(f"'{file_name}' erfolgreich heruntergeladen.")
                    
                    # Extract the file
                    extract_7z(download_path, data_dir)
                    print(f"'{file_name}' erfolgreich entpackt.")
                    
                    # Update the local version map
                    version_map[file_key] = remote_timestamp
                    save_version_map(version_map, version_map_file)
                    print(f"Versionsübersicht für '{file_key}' aktualisiert.")
                    
                except Exception as e:
                    print(f"Fehler bei der Verarbeitung von '{file_key}': {e}")
            else:
                print(f"Keine Aktualisierung für '{file_key}' nötig.")
                
        except Exception as e:
            print(f"Fehler bei der Verarbeitung der Datei '{file_key}': {e}")
            continue

if __name__ == "__main__":
    try:
        check_and_update_files()
        print("Aktualisierungsprüfung erfolgreich abgeschlossen.")
    except KeyboardInterrupt:
        print("\nAktualisierungsprozess vom Benutzer unterbrochen.")
    except Exception as e:
        print(f"Fehler während des Aktualisierungsprozesses: {e}")
        sys.exit(1)
