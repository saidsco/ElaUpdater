import sys
import os
import platform
import subprocess
import stat
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                               QGridLayout, QHBoxLayout, QVBoxLayout, QTextEdit, QProgressBar)
from PySide6.QtGui import QPixmap, QIcon, Qt
from PySide6.QtCore import QThread, Signal

import updater

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class InstallWorker(QThread):
    update_signal = Signal(str)
    progress_signal = Signal(int, int, str)  # current, total, detail_message
    finished_signal = Signal(bool)

    def run(self):
        try:
            config = updater.load_config()
            self.update_signal.emit("🔄 Installation wird gestartet...")
            self.progress_signal.emit(1, 3, "Lade Installationspaket herunter...")
            
            url = config.get("initial_package_url")
            if not url:
                self.update_signal.emit("❌ Installation fehlgeschlagen: Initial package URL not configured")
                self.finished_signal.emit(False)
                return
            
            extract_path = config.get("initial_package_extract_path", ".")
            data_dir = updater.Path(config["data_dir"])
            data_dir.mkdir(parents=True, exist_ok=True)
            
            file_name = url.split("/")[-1]
            download_path = data_dir / file_name
            
            try:
                # Download
                self.progress_signal.emit(1, 3, f"Lade {file_name} herunter...")
                updater.download_file(url, download_path)
                self.update_signal.emit(f"✅ '{file_name}' heruntergeladen")
                
                # Extract
                self.progress_signal.emit(2, 3, f"Entpacke {file_name}...")
                updater.extract_7z(download_path, extract_path)
                self.update_signal.emit(f"📂 '{file_name}' entpackt")
                
                # Verify
                self.progress_signal.emit(3, 3, "Überprüfe Installation...")
                exists, path = updater.check_required_file(config)
                if not exists:
                    self.update_signal.emit(f"❌ Installation fehlgeschlagen: Erforderliche Datei fehlt: {path}")
                    self.finished_signal.emit(False)
                    return
                
                self.update_signal.emit("✅ Installation erfolgreich abgeschlossen!")
                self.finished_signal.emit(True)
                
            except Exception as e:
                self.update_signal.emit(f"❌ Installationsfehler: {e}")
                self.finished_signal.emit(False)
            finally:
                # Clean up
                try:
                    download_path.unlink(missing_ok=True)
                except Exception:
                    pass
                    
        except Exception as e:
            self.update_signal.emit(f"❌ Installationsfehler: {e}")
            self.finished_signal.emit(False)

class UpdateWorker(QThread):
    update_signal = Signal(str)
    progress_signal = Signal(int, int, str)  # current, total, detail_message
    finished_signal = Signal()

    def run(self):
        try:
            config = updater.load_config()
            
            # Check required file before proceeding
            exists, path = updater.check_required_file(config)
            if not exists:
                self.update_signal.emit(f"⚠️ Erforderliche Datei fehlt: {path}")
                return

            data_dir = updater.Path(config["data_dir"])
            unpack_dir = updater.Path(config["unpack_dir"])
            version_map_file = config["version_map_file"]
            patches_url = config["patches_url"]
            
            # Load version map
            version_map = updater.load_version_map(version_map_file)
            
            # Ensure data directory exists
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # Download patches
            self.update_signal.emit(f"Lade Patch-Informationen von {patches_url}...")
            patches = updater.download_patches(patches_url)
            
            # Fall back to local patches if download fails
            if patches is None:
                self.update_signal.emit("Versuche lokal zwischengespeicherte Patches zu verwenden...")
                patches = updater.load_local_patches()
                
                # Exit if no patches are available
                if patches is None:
                    self.update_signal.emit("❌ Fehler: Patches konnten nicht geladen werden. Fortfahren nicht möglich.")
                    return
            
            # Process each patch
            total_patches = len(patches)
            for idx, (file_key, url) in enumerate(patches.items(), 1):
                self.update_signal.emit(f"Überprüfe: {file_key}")
                self.progress_signal.emit(idx, total_patches, f"Überprüfe {file_key}...")
                
                remote_timestamp = updater.get_remote_timestamp(url)
                if remote_timestamp is None:
                    self.update_signal.emit(f"❌ Zeitstempel für {url} konnte nicht abgerufen werden")
                    continue
                
                local_timestamp = version_map.get(file_key, 0)
                
                if remote_timestamp > local_timestamp:
                    self.update_signal.emit(f"⬇️ Neuere Version für '{file_key}' gefunden. Wird heruntergeladen...")
                    file_name = url.split("/")[-1]
                    download_path = data_dir / file_name
                    
                    try:
                        self.progress_signal.emit(idx, total_patches, f"Lade {file_name} herunter...")
                        updater.download_file(url, download_path)
                        self.update_signal.emit(f"✅ '{file_name}' heruntergeladen")
                        
                        self.progress_signal.emit(idx, total_patches, f"Entpacke {file_name}...")
                        updater.extract_7z(download_path, unpack_dir)
                        self.update_signal.emit(f"📂 '{file_name}' entpackt")
                        
                        version_map[file_key] = remote_timestamp
                        updater.save_version_map(version_map, version_map_file)
                        self.update_signal.emit(f"🔄 Version aktualisiert: '{file_key}'")
                    except Exception as e:
                        self.update_signal.emit(f"❌ Fehler bei '{file_key}': {e}")
                else:
                    self.update_signal.emit(f"✔️ '{file_key}' ist aktuell.")
            
            self.update_signal.emit("\n✅ Alle Aufgaben abgeschlossen!")
        except Exception as e:
            self.update_signal.emit(f"\n❌ Fehler während des Update-Prozesses: {e}")
        finally:
            self.finished_signal.emit()


class BorderlessWindow(QWidget):
    def __init__(self):
        print("DEBUG: Starting BorderlessWindow initialization")
        super().__init__()
        self.dragging = False
        
        # Load configuration first
        print("DEBUG: Loading configuration")
        self.config = updater.load_config()
        print(f"DEBUG: Configuration loaded: {self.config}")
        
        # Initialize UI components
        print("DEBUG: Initializing UI components")
        self.initUI()
        print("DEBUG: UI initialization complete")
        
        # Check required file before starting update process
        print("DEBUG: Checking required file")
        self.check_required_file()
        
    def initUI(self):
        # Borderless and transparency setup
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Set window icon
        icon_path = resource_path('ela.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Background image setup
        pixmap = QPixmap(resource_path('background.png'))
        self.background = QLabel(self)
        self.background.setPixmap(pixmap)
        self.background.resize(pixmap.size())

        # Text area for status updates
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setStyleSheet("QTextEdit { "
                               "background-color: rgba(255, 255, 255, 200);"
                               "border-radius: 10px;"
                               "padding: 10px;"
                               "color: rgba(0, 0, 0, 200); }"
                               "QScrollBar:vertical { width: 12px; }")
        self.output.setMinimumWidth(300)
        self.output.setMaximumWidth(400)
        self.output.setMinimumHeight(400)
        self.output.setContentsMargins(0, 75, 0, 0)

        # Progress bar and status in center area
        self.progress_container = QWidget(self)
        self.progress_container.setStyleSheet("background-color: rgba(255, 255, 255, 200);"
                                             "border-radius: 10px;"
                                             "padding: 20px;")
        progress_layout = QVBoxLayout(self.progress_container)
        
        self.progress_label = QLabel('Bereit', self)
        self.progress_label.setStyleSheet("color: rgba(0, 0, 0, 200); font-size: 14px;")
        self.progress_label.setAlignment(Qt.AlignCenter)
        
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            "QProgressBar {"
            "   border: 2px solid grey;"
            "   border-radius: 5px;"
            "   text-align: center;"
            "   color: black;"
            "}"
            "QProgressBar::chunk {"
            "   background-color: #4CAF50;"
            "   width: 10px;"
            "}"
        )
        
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        self.progress_container.hide()  # Hidden by default

        # Create buttons
        self.close_btn = QPushButton('Schließen', self)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("padding: 5px 10px;")
        
        self.start_client_btn = QPushButton('Client Starten', self)
        self.start_client_btn.clicked.connect(self.launch_client)
        self.start_client_btn.setStyleSheet("padding: 5px 10px;")
        
        self.start_client_new_btn = QPushButton('Neuen Client Starten', self)
        self.start_client_new_btn.clicked.connect(self.launch_client_new)
        self.start_client_new_btn.setStyleSheet("padding: 5px 10px;")
        
        self.install_btn = QPushButton('Installieren', self)
        self.install_btn.clicked.connect(self.start_installation)
        self.install_btn.setStyleSheet("padding: 5px 10px;")
        self.install_btn.hide()  # Hidden by default

        # Button layout
        self.button_layout = QHBoxLayout()
        self.button_layout.addWidget(self.start_client_btn)
        self.button_layout.addWidget(self.start_client_new_btn)
        self.button_layout.addWidget(self.install_btn)
        self.button_layout.addWidget(self.close_btn)

        # Grid layout
        grid = QGridLayout(self)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.addWidget(self.progress_container, 0, 0, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.output, 0, 1, 1, 1, Qt.AlignRight | Qt.AlignTop)
        grid.addLayout(self.button_layout, 1, 0, 1, 2, Qt.AlignBottom | Qt.AlignRight)
        
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)

        self.setLayout(grid)
        self.resize(pixmap.size())

    def check_required_file(self):
        """Check if required file exists and update UI accordingly."""
        print("DEBUG: In check_required_file method")
        exists, path = updater.check_required_file(self.config)
        print(f"DEBUG: Required file check result - exists: {exists}, path: {path}")
        if not exists:
            print("DEBUG: Required file missing, showing install button")
            self.update_status(f"⚠️ Erforderliche Datei fehlt: {path}")
            self.start_client_btn.hide()
            self.start_client_new_btn.hide()
            self.install_btn.show()
        else:
            print("DEBUG: Required file exists, showing client button")
            self.start_client_btn.show()
            self.start_client_new_btn.show()
            self.install_btn.hide()
            # Disable buttons during update
            self.start_client_btn.setEnabled(False)
            self.start_client_new_btn.setEnabled(False)
            # Show progress container
            self.progress_container.show()
            # Start update worker only if file exists
            print("DEBUG: Creating and starting UpdateWorker")
            self.worker = UpdateWorker()
            self.worker.update_signal.connect(self.update_status)
            self.worker.progress_signal.connect(self.update_progress)
            self.worker.finished_signal.connect(self.update_finished)
            self.worker.start()

    def start_installation(self):
        """Start the installation process."""
        self.install_btn.setEnabled(False)
        self.update_status("🔄 Installationsprozess wird gestartet...")
        
        self.progress_container.show()
        self.install_worker = InstallWorker()
        self.install_worker.update_signal.connect(self.update_status)
        self.install_worker.progress_signal.connect(self.update_progress)
        self.install_worker.finished_signal.connect(self.installation_finished)
        self.install_worker.start()

    def installation_finished(self, success):
        """Handle installation completion."""
        self.install_btn.setEnabled(True)
        if success:
            self.check_required_file()  # This will update button visibility and start update worker
        else:
            self.update_status("⚠️ Installation fehlgeschlagen. Bitte erneut versuchen.")
    
    def update_finished(self):
        """Handle update completion."""
        self.start_client_btn.setEnabled(True)
        self.start_client_new_btn.setEnabled(True)
        self.progress_container.hide()
        self.progress_label.setText('Bereit')
        self.progress_bar.setValue(0)
    
    def update_progress(self, current, total, detail_message):
        """Update the progress bar and detail message."""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
            self.progress_bar.setFormat(f"{current}/{total} - {percentage}%")
        self.progress_label.setText(detail_message)

    def update_status(self, message):
        """Update the status text area."""
        self.output.append(message)

    def launch_client(self):
        """Launch the client application based on the operating system."""
        # Check if required file exists before launching
        exists, path = updater.check_required_file(self.config)
        if not exists:
            self.update_status(f"❌ Client kann nicht gestartet werden. Erforderliche Datei fehlt: {path}")
            return

        client_exe = "client.exe"
        try:
            self.update_status("Client wird gestartet...")
            
            if platform.system() == "Windows":
                self.update_status("Windows erkannt: Client wird direkt gestartet.")
                subprocess.Popen([client_exe], shell=True)
            else:
                self.update_status("Linux/Unix erkannt: Client wird mit Wine gestartet.")
                wine_path = "wine"
                
                try:
                    subprocess.run([wine_path, "--version"], capture_output=True, check=True)
                except (subprocess.SubprocessError, FileNotFoundError):
                    self.update_status("❌ Fehler: Wine ist nicht installiert oder nicht im PATH.")
                    return
                
                subprocess.Popen([wine_path, client_exe])
                
            self.update_status("✅ Client erfolgreich gestartet.")
        except Exception as e:
            self.update_status(f"❌ Fehler beim Starten des Clients: {e}")

    def launch_client_new(self):
        """Launch the client application based on the operating system."""
        # Check if required file exists before launching
        exists, path = updater.check_required_file(self.config)
        if not exists:
            self.update_status(f"❌ Client kann nicht gestartet werden. Erforderliche Datei fehlt: {path}")
            return

        client_exe = "ElaUO.exe"
        try:
            self.update_status("Client wird gestartet...")
            
            if platform.system() == "Windows":
                settings_path = ".\\settings.json"
                self.update_status("Windows erkannt: Client wird direkt gestartet.")
                subprocess.Popen([client_exe, "-settings", settings_path], shell=True)
            else:
                settings_path = "./settings.json"
                self.update_status("Linux/Unix erkannt: Client wird mit nativ gestartet.")
                client_linux = "./ClassicUO.bin.x86_64"
                #wine_path = "wine"
                
                #try:
                #    subprocess.run([wine_path, "--version"], capture_output=True, check=True)
                #except (subprocess.SubprocessError, FileNotFoundError):
                #    self.update_status("❌ Fehler: Wine ist nicht installiert oder nicht im PATH.")
                #    return
                os.chmod(client_linux, os.stat(client_linux).st_mode | stat.S_IEXEC)
                subprocess.Popen([client_linux, "-settings", settings_path])
                
            self.update_status("✅ Client erfolgreich gestartet.")
        except Exception as e:
            self.update_status(f"❌ Fehler beim Starten des Clients: {e}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            child_widget = self.childAt(event.position().toPoint())
            if not child_widget or isinstance(child_widget, QLabel):
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
            else:
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.dragging:
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

if __name__ == '__main__':
    print("DEBUG: Application starting")
    app = QApplication(sys.argv)
    print("DEBUG: QApplication created")
    window = BorderlessWindow()
    print("DEBUG: BorderlessWindow created")
    window.show()
    print("DEBUG: Window shown")
    sys.exit(app.exec())
