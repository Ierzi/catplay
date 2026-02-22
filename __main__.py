import sys
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QFileDialog, QVBoxLayout, QSlider, QGridLayout, QHBoxLayout
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QUrl
from pathlib import Path
from mutagen.mp4 import MP4
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.wave import WAVE
import random

class MainWindow(QWidget):
    def __init__(self):
        # Set basic window propreties and important variables
        super().__init__()
        self.setWindowTitle("CatPlay")
        self.logo = Path(__file__).parent / "assets" / "logo.png"
        self.setWindowIcon(QIcon(str(self.logo)))
        
        self.is_playing = False # updates if play or stop is pressed, not pause/resume
        self.is_paused = False 
        self.loaded_audio = None 
        self.queue = []

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()

        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self.handle_media_status)

        # Set fixed size
        self.setFixedSize(400, 600) # non resizable

        # Create layout
        main_layout = QVBoxLayout()
        
        album_info_layout = QVBoxLayout()

        # Album cover widget
        # Right now, no album cover is loaded, so it just shows the placeholder image
        placeholder = Path(__file__).parent / "assets" / "placeholder.jpg"
        self.album_cover = QLabel()
        self.album_cover.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop) # Align the album cover to the top left corner

        pixmap = QPixmap(str(placeholder))
        pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) # Rescale image
        self.album_cover.setPixmap(pixmap)

        album_info_layout.addWidget(self.album_cover)

        # Song info labels (title, artist, album)
        self.info_label = QLabel("No song loaded")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop) # Align the info label to the top left corner
        album_info_layout.addWidget(self.info_label)

        button_layout = QGridLayout()

        # Load album cover button
        # (will remove this later when it actually loads album covers from the metadata of the music file)
        # self.load_ac_button = QPushButton("Load Album Cover")
        # self.load_ac_button.setFixedWidth(150)
        # self.load_ac_button.clicked.connect(self.load_album_cover)
        # button_layout.addWidget(self.load_ac_button, 0, 0)

        # Song progress bar / slider
        self.song_pb = QSlider(Qt.Orientation.Horizontal)
        self.song_pb.setRange(0, 0) # to change later
        self.song_pb.setFixedWidth(250)

        # Connect it to the media player
        self.player.durationChanged.connect(self.update_duration)
        self.player.positionChanged.connect(self.update_position)
        self.song_pb.sliderMoved.connect(self.set_position)

        button_layout.addWidget(self.song_pb, 0, 0)

        # Song time label
        self.current_time_label = QLabel("0:00")
        self.slash_bar = QLabel(" / ")
        self.total_time_label = QLabel("0:00")

        time_layout = QHBoxLayout()
        time_layout.addWidget(self.current_time_label)
        time_layout.addWidget(self.slash_bar)
        time_layout.addWidget(self.total_time_label)

        button_layout.addLayout(time_layout, 0, 1, alignment=Qt.AlignmentFlag.AlignRight)

        # Load Song button
        self.load_metadata_button = QPushButton("Load Song")
        self.load_metadata_button.setFixedWidth(150)
        self.load_metadata_button.clicked.connect(self.load_metadata)
        button_layout.addWidget(self.load_metadata_button, 1, 0)

        # Load folder button
        # (loads an entire folder, sorts and plays in order)
        self.load_folder_button = QPushButton("Load Folder")
        self.load_folder_button.setFixedWidth(150)
        self.load_folder_button.clicked.connect(self.load_folder)
        button_layout.addWidget(self.load_folder_button, 1, 1)

        # Play song button
        self.play_button = QPushButton("Play")
        self.play_button.setFixedWidth(380)
        self.play_button.clicked.connect(self.play_song)
        button_layout.addWidget(self.play_button, 2, 0)

        # Pause song button
        self.pause_button = QPushButton("Pause / Resume")
        self.pause_button.setFixedWidth(380)
        self.pause_button.clicked.connect(self.toggle_pause)
        button_layout.addWidget(self.pause_button, 3, 0)

        # Next song button
        self.next_button = QPushButton("Next")
        self.next_button.setFixedWidth(150)
        self.next_button.clicked.connect(self.next_song)
        button_layout.addWidget(self.next_button, 4, 0)

        # Previous song button
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFixedWidth(150)
        self.prev_button.clicked.connect(self.previous_song) 
        button_layout.addWidget(self.prev_button, 4, 1)

        # Shuffle button 
        self.shuffle_button = QPushButton("Shuffle")
        self.shuffle_button.setFixedWidth(380)
        self.shuffle_button.clicked.connect(lambda: random.shuffle(self.queue))
        button_layout.addWidget(self.shuffle_button, 5, 0)

        # Stop song button
        self.stop_button = QPushButton("Stop")
        self.stop_button.setFixedWidth(380)
        self.stop_button.clicked.connect(self.stop_song)
        button_layout.addWidget(self.stop_button, 6, 0)

        main_layout.addLayout(album_info_layout)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)


    def _set_cover_art(self, cover_art):
        # This function will set the album cover from the cover art data in the metadata
        pixmap = QPixmap()
        try:
            pixmap.loadFromData(cover_art.data)
        except Exception as e:
            print(e)
            pixmap.loadFromData(cover_art)
        pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
        self.album_cover.setPixmap(pixmap)
    
    def format_time(self, ms):
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def update_duration(self, duration):
        self.song_pb.setRange(0, duration)
        self.total_time_label.setText(self.format_time(duration))

    def update_position(self, position):
        if not self.song_pb.isSliderDown():
            self.song_pb.setValue(position)

        self.current_time_label.setText(self.format_time(position))

    def set_position(self, position):
        self.player.setPosition(position)

    def load_album_cover(self):
        # Dialog to select an image file
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Album Cover", filter="Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            pixmap = QPixmap(file_path)
            pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
            self.album_cover.setPixmap(pixmap)
        
        print("Image loaded.")

    def load_metadata_from_path(self, file_path: str):
        print(f"Loading metadata from: {file_path}")
        if file_path:
            if file_path.endswith(".mp3"):
                audio = MP3(file_path)
                print(audio.pprint())
                title = audio.get("TIT2", "Unknown Title")
                artist = audio.get("TPE1", "Unknown Artist")
                album = audio.get("TALB", "Unknown Album")
                cover_art = audio.get("APIC:") or audio.get("APIC") or None
                if cover_art:
                    self._set_cover_art(cover_art)

                print(f"Title: {title}")
                print(f"Artist: {artist}")
                print(f"Album: {album}")
                self.loaded_audio = audio # Store the loaded audio file for later use (e.g. for playback)

                self.info_label.setText(f"Title: {title}\nArtist: {artist}\nAlbum: {album}")

            elif file_path.endswith(".flac"):
                audio = FLAC(file_path)
                print(audio.pprint())
                title = audio.get("title", ["Unknown Title"])[0]
                artist = audio.get("artist", ["Unknown Artist"])[0]
                album = audio.get("album", ["Unknown Album"])[0]
                cover_art = audio.pictures[0] if audio.pictures else None
                if cover_art:
                    self._set_cover_art(cover_art)

                print(f"Title: {title}")
                print(f"Artist: {artist}")
                print(f"Album: {album}")
                self.loaded_audio = audio # Store the loaded audio file for later use (e.g. for playback)

                self.info_label.setText(f"Title: {title}\nArtist: {artist}\nAlbum: {album}")
            
            elif file_path.endswith(".m4a"):
                audio = MP4(file_path)
                print(audio.pprint())
                title = audio.get("©nam", ["Unknown Title"])[0]
                artist = audio.get("©ART", ["Unknown Artist"])[0]
                album = audio.get("©alb", ["Unknown Album"])[0]
                cover_art = audio.get("covr", [None])[0] if audio.get("covr") else None
                if cover_art:
                    self._set_cover_art(cover_art)

                print(f"Title: {title}")
                print(f"Artist: {artist}")
                print(f"Album: {album}")
                self.loaded_audio = audio

                self.info_label.setText(f"Title: {title}\nArtist: {artist}\nAlbum: {album}")

    def load_metadata(self):
        # Dialog to select a music file
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Music File", filter="Audio Files (*.mp3 *.flac *.wav *.m4a)")
        self.load_metadata_from_path(file_path)

    def play_song(self):
        if self.loaded_audio:
            self.player.setSource(QUrl.fromLocalFile(self.loaded_audio.filename))
            self.player.play()
            self.is_playing = True
            self.is_paused = False
            print("Playing song...")
        else:
            print("No audio file loaded.")

    def stop_song(self):
        if self.is_playing:
            self.player.stop()
            self.is_playing = False
            self.is_paused = False
            print("Stopping song...")
        else:
            print("No song is currently playing.")

    def toggle_pause(self):
        if self.is_playing:
            if self.is_paused:
                self.player.play()
                self.is_paused = False
                print("Resuming song...")
            else:
                self.player.pause()
                self.is_paused = True
                print("Pausing song...")
        else:
            print("No song is currently playing.")

    def load_folder(self):
        # Dialog to select a folder
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.FileMode.Directory)
        folder_path = folder_dialog.getExistingDirectory(self, "Select Music Folder")
        if folder_path:
            print(f"Selected folder: {folder_path}")
            audio_paths: list[Path] = []
            for ext in ("*.mp3", "*.flac", "*.wav", "*.ogg"):
                audio_paths.extend(Path(folder_path).glob(ext))

            audio_files = [str(path) for path in audio_paths]

            if audio_files[0][0] == "0":
                # Songs are ordered with numbers
                audio_files.sort() # Sort files alphabetically

            # If not, just pray it's in order

            print(audio_files)

        self.queue = audio_files 
        
        # Load first track
        if audio_files:
            first_track = audio_files[0]
            print(f"Loading first track: {first_track}")
            self.load_metadata_from_path(first_track)
    
    def next_song(self):
        if self.queue:
            current_index = self.queue.index(self.loaded_audio.filename) if self.loaded_audio else -1
            next_index = (current_index + 1) % len(self.queue)
            next_track = self.queue[next_index]
            print(f"Loading next track: {next_track}")
            self.load_metadata_from_path(next_track)
            self.play_song()
        else:
            print("No songs in the queue.")
    
    def previous_song(self):
        if self.queue:
            current_index = self.queue.index(self.loaded_audio.filename) if self.loaded_audio else -1
            prev_index = (current_index - 1) % len(self.queue)
            prev_track = self.queue[prev_index]
            print(f"Loading previous track: {prev_track}")
            self.load_metadata_from_path(prev_track)
            self.play_song()
        else:
            print("No songs in the queue.")

    def handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.queue:
            self.next_song()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
