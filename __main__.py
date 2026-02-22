import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt
from pathlib import Path

class MainWindow(QWidget):
    def __init__(self):
        # Set basic window propreties
        super().__init__()
        self.setWindowTitle("CatPlay")
        self.logo = Path(__file__).parent / "assets" / "logo.png"
        self.setWindowIcon(QIcon(str(self.logo)))
        
        # Set fixed size
        self.setFixedSize(960, 720) # non resizable

        # Create layout
        layout = QVBoxLayout()
        
        # Album cover widget
        # Right now, no album cover is loaded, so it just shows the placeholder image
        placeholder = Path(__file__).parent / "assets" / "placeholder.jpg"
        self.album_cover = QLabel()
        self.album_cover.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) # Align the album cover to the top left corner

        pixmap = QPixmap(str(placeholder))
        pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
        self.album_cover.setPixmap(pixmap)

        layout.addWidget(self.album_cover)

        self.load_ac_button = QPushButton("Load Album Cover")
        self.load_ac_button.setFixedWidth(150)
        self.load_ac_button.clicked.connect(self.load_album_cover)
        layout.addWidget(self.load_ac_button)

        self.setLayout(layout)
    
    def load_album_cover(self):
        # Dialog to select an image file
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Album Cover", filter="Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            pixmap = QPixmap(file_path)
            pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
            self.album_cover.setPixmap(pixmap)
        
        print("Image loaded.")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
