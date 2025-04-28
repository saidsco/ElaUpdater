import sys
import os
import platform
import subprocess
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                               QGridLayout, QHBoxLayout, QTextEdit)
from PySide6.QtGui import QPixmap, Qt
from PySide6.QtCore import QThread, Signal

import updater


class UpdateWorker(QThread):
    update_signal = Signal(str)

    def run(self):
        try:
            # Load configuration
            self.update_signal.emit("Konfiguration wird geladen...")
            config = updater.load_config()
            data_dir = updater.Path(config["data_dir"])
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
            for file_key, url in patches.items():
                self.update_signal.emit(f"Überprüfe: {file_key}")
                
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
                        updater.download_file(url, download_path)
                        self.update_signal.emit(f"✅ '{file_name}' heruntergeladen")
                        
                        updater.extract_7z(download_path, data_dir)
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


class BorderlessWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Variables for window dragging
        self.dragging = False
        self.drag_position = None
        self.initUI()

    def initUI(self):
        # Borderless and transparency setup
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Background image setup
        pixmap = QPixmap('background.png')
        self.background = QLabel(self)
        self.background.setPixmap(pixmap)
        self.background.resize(pixmap.size())

        # Text area for status updates
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setStyleSheet("background-color: rgba(255, 255, 255, 200);"
                                 "border-radius: 10px; margin-top: 75px;"
                                 "padding: 10px;"
                                 "color: rgba(0, 0, 0, 200);")
        # Make output widget smaller to fit in top right
        self.output.setMinimumWidth(300)
        self.output.setMaximumWidth(400)
        self.output.setMinimumHeight(400)

        # Create buttons
        close_btn = QPushButton('Schließen', self)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("padding: 5px 10px;")
        
        start_client_btn = QPushButton('Client Starten', self)
        start_client_btn.clicked.connect(self.launch_client)
        start_client_btn.setStyleSheet("padding: 5px 10px;")
        
        # Create a horizontal layout for buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(start_client_btn)
        button_layout.addWidget(close_btn)
        
        # Create grid layout
        grid = QGridLayout(self)
        grid.setContentsMargins(20, 20, 20, 20)
        
        # Add output widget to top right (row 0, column 1)
        grid.addWidget(self.output, 0, 1, 1, 1, Qt.AlignRight | Qt.AlignTop)
        
        # Add button layout to bottom row spanning both columns (row 1, column 0-1)
        grid.addLayout(button_layout, 1, 0, 1, 2, Qt.AlignBottom | Qt.AlignRight)
        
        # Set row and column stretching
        grid.setRowStretch(0, 3)  # Top row gets more space
        grid.setRowStretch(1, 1)  # Bottom row gets less space
        grid.setColumnStretch(0, 2)  # Left column gets more space
        grid.setColumnStretch(1, 1)  # Right column gets less space

        self.setLayout(grid)
        self.resize(pixmap.size())

        # Start updating process
        self.worker = UpdateWorker()
        self.worker.update_signal.connect(self.update_status)
        self.worker.start()

    def update_status(self, message):
        self.output.append(message)

    def launch_client(self):
        """Launch the client application based on the operating system"""
        client_exe = "client.exe"
        try:
            self.update_status("Client wird gestartet...")
            
            # Check operating system
            if platform.system() == "Windows":
                # On Windows, run the client directly
                self.update_status("Windows erkannt: Client wird direkt gestartet.")
                subprocess.Popen([client_exe], shell=True)
            else:
                # On Linux/macOS, use wine
                self.update_status("Linux/Unix erkannt: Client wird mit Wine gestartet.")
                wine_path = "wine"  # Assumes wine is in PATH
                
                # Check if wine exists
                try:
                    subprocess.run([wine_path, "--version"], capture_output=True, check=True)
                except (subprocess.SubprocessError, FileNotFoundError):
                    self.update_status("❌ Fehler: Wine ist nicht installiert oder nicht im PATH.")
                    return
                
                # Launch with wine
                subprocess.Popen([wine_path, client_exe])
                
            self.update_status("✅ Client erfolgreich gestartet.")
        except Exception as e:
            self.update_status(f"❌ Fehler beim Starten des Clients: {e}")

    def mousePressEvent(self, event):
        """Handle mouse press event to enable window dragging"""
        if event.button() == Qt.LeftButton:
            # Check if the click is on a child widget
            child_widget = self.childAt(event.position().toPoint())
            
            # Allow dragging only if clicking on the background or a label
            if not child_widget or isinstance(child_widget, QLabel):
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
            else:
                # For other widgets, continue normal processing
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move event to drag the window"""
        if event.buttons() & Qt.LeftButton and self.dragging:
            # Calculate new position
            new_pos = event.globalPosition().toPoint() - self.drag_position
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release event to end dragging"""
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = BorderlessWindow()
    window.show()

    sys.exit(app.exec())
