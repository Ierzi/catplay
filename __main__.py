import sys
from PySide6.QtWidgets import QApplication, QWidget, QGridLayout, QPushButton, QLabel, QFileDialog, QVBoxLayout
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt
from pathlib import Path
from mutagen.mp3 import MP3
import pygame

class MainWindow(QWidget):
    def __init__(self):
        # Set basic window propreties
        super().__init__()
        self.setWindowTitle("CatPlay")
        self.logo = Path(__file__).parent / "assets" / "logo.png"
        self.setWindowIcon(QIcon(str(self.logo)))
        
        self.loaded_audio = None # This will hold the currently loaded audio file (if any)

        # Set fixed size
        self.setFixedSize(760, 600) # non resizable

        # Create layout
        layout = QVBoxLayout()
        
        # Album cover widget
        # Right now, no album cover is loaded, so it just shows the placeholder image
        placeholder = Path(__file__).parent / "assets" / "placeholder.jpg"
        self.album_cover = QLabel()
        self.album_cover.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) # Align the album cover to the top left corner

        pixmap = QPixmap(str(placeholder))
        pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) # Rescale image
        self.album_cover.setPixmap(pixmap)

        layout.addWidget(self.album_cover)

        # Load album cover button
        # (will remove this later when it actually loads album covers from the metadata of the music file)
        self.load_ac_button = QPushButton("Load Album Cover")
        self.load_ac_button.setFixedWidth(150)
        self.load_ac_button.clicked.connect(self.load_album_cover)
        layout.addWidget(self.load_ac_button)

        # Load metadata button
        self.load_metadata_button = QPushButton("Load Metadata")
        self.load_metadata_button.setFixedWidth(150)
        self.load_metadata_button.clicked.connect(self.load_metadata)
        layout.addWidget(self.load_metadata_button)

        # Play song button
        self.play_button = QPushButton("Play")
        self.play_button.setFixedWidth(150)
        self.play_button.clicked.connect(self.play_song)
        layout.addWidget(self.play_button)

        self.setLayout(layout)
    
    def _set_cover_art(self, cover_art):
        # This function will set the album cover from the cover art data in the metadata
        pixmap = QPixmap()
        pixmap.loadFromData(cover_art.data)
        pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
        self.album_cover.setPixmap(pixmap)

    def load_album_cover(self):
        # Dialog to select an image file
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Album Cover", filter="Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            pixmap = QPixmap(file_path)
            pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
            self.album_cover.setPixmap(pixmap)
        
        print("Image loaded.")
    
    def load_metadata(self):
        # Dialog to select a music file
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Music File", filter="Audio Files (*.mp3 *.flac *.wav *.ogg)")
        if file_path:
            if file_path.endswith(".mp3"):
                audio = MP3(file_path)
                print(audio.pprint())
                title = audio.get("TIT2", "Unknown Title")
                artist = audio.get("TPE1", "Unknown Artist")
                album = audio.get("TALB", "Unknown Album")
                cover_art = audio.get("APIC:", None)
                if cover_art:
                    self._set_cover_art(cover_art)

                print(f"Title: {title}")
                print(f"Artist: {artist}")
                print(f"Album: {album}")
                self.loaded_audio = audio # Store the loaded audio file for later use (e.g. for playback)

    def play_song(self):
        if self.loaded_audio:
            pygame.mixer.init()
            pygame.mixer.music.load(self.loaded_audio.filename)
            pygame.mixer.music.play()
            print("Playing song...")
        else:
            print("No audio file loaded.")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
