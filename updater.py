import os
import sys
import json
import requests
import py7zr
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime

CONFIG_FILE_PATH = "./config.json"
PATCHES_FILE = Path("./patches_local.json")

# Default configuration (used if config.json is missing or invalid)
DEFAULT_CONFIG = {
    "patches_url": "http://uo-elantharil.de:8080/patcher/patches.json",
    "data_dir": "./data",
    "unpack_dir": ".",
    "version_map_file": "./versions.json",
    "required_file": None,  # Path to required file
    "initial_package_url": None,  # URL for initial package download
    "initial_package_extract_path": "."  # Where to extract initial package
}

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
    
def check_required_file(config):
    """Check if the required file exists.
    Returns:
        tuple: (bool, str) - (exists, error_message)
    """
    if not config.get("required_file"):
        return True, ""  # No required file specified, consider it exists
        
    required_file = Path(config["required_file"])
    return required_file.exists(), str(required_file)

def download_and_extract_initial_package(config):
    """Download and extract the initial package if configured.
    Returns:
        tuple: (bool, str) - (success, error_message)
    """
    url = config.get("initial_package_url")
    if not url:
        return False, "Initial package URL not configured"
        
    extract_path = config.get("initial_package_extract_path", ".")
    
    try:
        # Create temporary download location
        data_dir = Path(config["data_dir"])
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Download the package
        file_name = url.split("/")[-1]
        download_path = data_dir / file_name
        
        download_file(url, download_path)
        
        # Extract the package
        extract_7z(download_path, extract_path)
        
        # Verify the required file now exists
        exists, path = check_required_file(config)
        if not exists:
            return False, f"Required file still missing after installation: {path}"
            
        return True, "Installation successful"
        
    except requests.exceptions.RequestException as e:
        return False, f"Failed to download initial package: {e}"
    except py7zr.Bad7zFile as e:
        return False, f"Failed to extract initial package: {e}"
    except Exception as e:
        return False, f"Installation failed: {e}"
    finally:
        # Clean up downloaded package
        if 'download_path' in locals():
            try:
                download_path.unlink(missing_ok=True)
            except Exception:
                pass

def load_config():
    """Load configuration from config.json or use defaults if not available."""
    configfile = Path(resource_path(CONFIG_FILE_PATH))
    try:
        if not configfile.exists():
            print(f"Warning: Configuration file {configfile} not found. Using default configuration.")
            return DEFAULT_CONFIG
            
        with open(configfile, "r") as f:
            config = json.load(f)
            
        # Ensure all required keys exist
        for key, default_value in DEFAULT_CONFIG.items():
            if key not in config:
                print(f"Warning: '{key}' missing from configuration. Using default value.")
                config[key] = default_value
                
        return config
    except json.JSONDecodeError:
        print(f"Error: Configuration file {configfile} is not valid JSON. Using default configuration.")
        return DEFAULT_CONFIG
    except Exception as e:
        print(f"Error loading configuration: {e}. Using default configuration.")
        return DEFAULT_CONFIG

def update_version_map_from_patches(patches, version_map_file):
    """
    Update versions.json based on the timestamps of files in patches.json.
    Creates the file if it doesn't exist, and updates only when remote timestamps differ.
    
    Args:
        patches: Dictionary of patches from patches.json
        version_map_file: Path to the versions.json file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load existing version map if it exists
        version_map = load_version_map(version_map_file)
        updated = False
        
        print(f"Aktualisiere Versionsübersicht für {len(patches)} Patches...")
        
        # Check each patch file for timestamp
        for file_key, url in patches.items():
            try:
                remote_timestamp = get_remote_timestamp(url)
                if remote_timestamp is None:
                    print(f"Zeitstempel für {url} konnte nicht abgerufen werden")
                    continue
                    
                local_timestamp = version_map.get(file_key, 0)
                
                # Update only if timestamp differs
                if remote_timestamp != local_timestamp:
                    print(f"Aktualisiere Zeitstempel für '{file_key}'")
                    version_map[file_key] = remote_timestamp
                    updated = True
            except Exception as e:
                print(f"Fehler beim Abrufen des Zeitstempels für '{file_key}': {e}")
                continue
        
        # Save the version map if any updates were made
        if updated:
            save_version_map(version_map, version_map_file)
            print(f"Versionsübersicht gespeichert in {version_map_file}")
        else:
            print("Keine Änderungen in der Versionsübersicht")
            
        return True
    except Exception as e:
        print(f"Fehler beim Aktualisieren der Versionsübersicht: {e}")
        return False

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
    
    # Automatically update versions.json based on patches
    update_version_map_from_patches(patches, version_map_file)
    
    # Load version map after potential update
    version_map = load_version_map(version_map_file)
    
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
