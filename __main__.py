from functools import lru_cache
import sys
from typing import Any, Optional
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QFileDialog, QVBoxLayout, QSlider, QGridLayout, QHBoxLayout, QDialog, QLineEdit, QListWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QUrl
from pathlib import Path
from mutagen.mp4 import MP4
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
from mutagen.wave import WAVE
import random
from pypresence import Presence
from pypresence.types import ActivityType
from dotenv import load_dotenv
import time
import requests

# TODO: Volume control
# TODO: Last.fm scrobbling, love track
# TODO: Queue management
# TODO: A vinyl view for the album cover, with a disc spinning would be so cool
# TODO: Genius link to get lyrics

def ressource_path(relative_path: Path) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.absolute()))
    return str(base_path / relative_path)

load_dotenv(ressource_path(".env"))

RPC = Presence(1475462488245014568)
RPC.connect()

loaded_audio = None

class AudioMetadata:
    def __init__(self, title: str, artist: str, album: str, cover: Any, audio: Any):
        self.title = title
        self.artist = artist
        self.album = album
        self.cover = cover
        self.audio = audio
        self.filename = audio.filename
        self._make_unique_hash = str(cover) + str(audio)
    
    def __hash__(self):
        return hash((self.title, self.artist, self.album, self.filename, self._make_unique_hash))

@lru_cache(maxsize=128)
def load_metadata(file_path: str) -> AudioMetadata:
    if file_path.endswith(".mp3"):
        audio = MP3(file_path)

        def _text_from_tag(tag, default: str = "Unknown") -> str:
            if tag is None:
                return default
            # mutagen ID3 frames usually expose a .text list
            if hasattr(tag, "text"):
                try:
                    return tag.text[0] if tag.text else default
                except Exception:
                    return str(tag)
            # fallback to string conversion
            return str(tag)

        title = _text_from_tag(audio.get("TIT2"), "Unknown Title")
        artist = _text_from_tag(audio.get("TPE1"), "Unknown Artist")
        album = _text_from_tag(audio.get("TALB"), "Unknown Album")
        cover = audio.get("APIC:") or audio.get("APIC") or None
        return AudioMetadata(title, artist, album, cover, audio)

    elif file_path.endswith(".flac"):
        audio = FLAC(file_path)
        title = audio.get("title", ["Unknown Title"])[0]
        artist = audio.get("artist", ["Unknown Artist"])[0]
        album = audio.get("album", ["Unknown Album"])[0]
        cover = audio.pictures[0] if audio.pictures else None

        return AudioMetadata(title, artist, album, cover, audio)

    elif file_path.endswith(".m4a"):
        audio = MP4(file_path)
        title = audio.get("©nam", ["Unknown Title"])[0]
        artist = audio.get("©ART", ["Unknown Artist"])[0]
        album = audio.get("©alb", ["Unknown Album"])[0]
        cover = audio.get("covr", [None])[0] if audio.get("covr") else None
        return AudioMetadata(title, artist, album, cover, audio)

    elif file_path.endswith(".wav"):
        audio = WAVE(file_path)

        return AudioMetadata("Unknown Title", "Unknown Artist", "Unknown Album", None, audio) #what

class MetadataPopup(QDialog):
    def __init__(self):
        global loaded_audio
        super().__init__()
        self.setWindowTitle("Edit Metadata")
        layout = QHBoxLayout()
        album_cover_layout = QVBoxLayout()
        editing_layout = QGridLayout()

        self.title = loaded_audio.title
        self.artist = loaded_audio.artist
        self.album = loaded_audio.album
        self.album_cover_data = loaded_audio.cover
        self.filename = loaded_audio.filename
        self.audio = loaded_audio.audio

        # * Album cover layout
        # Album cover image
        placeholder = Path(__file__).parent / "assets" / "placeholder.jpg"
        self.album_cover = QLabel()
        self.album_cover.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop) # Align the album cover to the top left corner

        pixmap = QPixmap()
        if loaded_audio.cover:
            try:
                pixmap.loadFromData(loaded_audio.cover.data)
            except AttributeError:
                pixmap.loadFromData(loaded_audio.cover)
        else:
            pixmap.load(str(placeholder))

        pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) # Rescale image
        self.album_cover.setPixmap(pixmap)

        album_cover_layout.addWidget(self.album_cover)

        # Edit album cover button
        self.edit_ac_button = QPushButton("Edit Album Cover")
        self.edit_ac_button.setFixedWidth(250)
        self.edit_ac_button.clicked.connect(self.update_ac)
        album_cover_layout.addWidget(self.edit_ac_button)

        # * Editing layout

        # Title edit field
        self.title_label = QLabel("Title:")
        self.title_label.setFixedWidth(35)
        self.title_edit = QLineEdit(loaded_audio.title)
        self.title_edit.setFixedWidth(200)
        self.title_edit.textChanged.connect(self.update_title)

        editing_layout.addWidget(self.title_label, 0, 0)
        editing_layout.addWidget(self.title_edit, 0, 1)

        # Artist edit field
        self.artist_label = QLabel("Artist:")
        self.artist_label.setFixedWidth(35)
        self.artist_edit = QLineEdit(loaded_audio.artist)
        self.artist_edit.setFixedWidth(200)
        self.artist_edit.textChanged.connect(self.update_artist)

        editing_layout.addWidget(self.artist_label, 1, 0)
        editing_layout.addWidget(self.artist_edit, 1, 1)

        # Album edit field
        self.album_label = QLabel("Album:")
        self.artist_label.setFixedWidth(35)
        self.album_edit = QLineEdit(loaded_audio.album)
        self.artist_edit.setFixedWidth(200)
        self.album_edit.textChanged.connect(self.update_album)

        editing_layout.addWidget(self.album_label, 2, 0)
        editing_layout.addWidget(self.album_edit, 2, 1)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.setFixedWidth(125)
        self.save_button.clicked.connect(self.save) # Close the popup when save is clicked
        editing_layout.addWidget(self.save_button, 5, 1, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        layout.addLayout(album_cover_layout)
        layout.addLayout(editing_layout)

        self.setLayout(layout)

    def update_ac(self):
        new_ac_dialog = QFileDialog()
        file_path, _ = new_ac_dialog.getOpenFileName(self, "Select New Album Cover", filter="Image Files (*.png *.jpg *.jpeg)")
        
        if not file_path:
            print("No file selected.")
            return

        # Update album cover image
        pixmap = QPixmap(file_path)
        pixmap = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.album_cover.setPixmap(pixmap)
        self.album_cover_path = file_path
        print("Album cover updated.")

    def update_title(self, text):
        self.title = text

    def update_artist(self, text):
        self.artist = text

    def update_album(self, text):
        self.album = text

    def save(self):
        global loaded_audio
        # * Update metadata for MP3
        if self.filename.endswith(".mp3"):
            self.audio = MP3(self.filename, ID3=ID3)

            if self.audio.tags is None:
                self.audio.add_tags()
            
            self.audio.tags.add(TIT2(encoding=3, text=self.title))
            self.audio.tags.add(TPE1(encoding=3, text=self.artist))
            self.audio.tags.add(TALB(encoding=3, text=self.album))

            if self.album_cover_path:
                image_type = "image/jpeg" if self.album_cover_path.endswith((".jpg", ".jpeg")) else "image/png"
                with open(self.album_cover_path, "rb") as img:
                    self.audio.tags.add(
                        APIC(
                        encoding=3,
                        mime=image_type,
                        type=3,
                        desc="Cover",
                        data=img.read()
                        )
                    )
            
            self.audio.save()
            print("MP3 metadata updated.")
        
        # * Update metadata for FLAC
        elif self.filename.endswith(".flac"):
            self.audio = FLAC(self.filename)
            
            self.audio["title"] = self.title
            self.audio["artist"] = self.artist
            self.audio["album"] = self.album
            
            if self.album_cover_path:
                pic = Picture()
                pic.type = 3
                pic.mime = "image/jpeg" if self.album_cover_path.endswith((".jpg", ".jpeg")) else "image/png"
                pic.desc = "Cover"
                
                with open(self.album_cover_path, "rb") as img:
                    pic.data = img.read()
            
                self.audio.clear_pictures()
                self.audio.add_picture(pic)

            self.audio.save()
            print("FLAC metadata updated.")
        
        elif self.filename.endswith(".m4a"):
            self.audio = MP4(self.filename)

            self.audio["©nam"] = self.title
            self.audio["©ART"] = self.artist
            self.audio["©alb"] = self.album

            if self.album_cover_path:
                with open(self.album_cover_path, "rb") as img:
                    cover_data = img.read()
                self.audio["covr"] = [cover_data]

            self.audio.save()
            print("M4A metadata updated.")
    
        loaded_audio = AudioMetadata(self.title, self.artist, self.album, self.album_cover_path, self.audio)

class MainWindow(QWidget):
    def __init__(self):
        # Set basic window propreties and important variables
        super().__init__()
        self.setWindowTitle("CatPlay")
        self.logo = Path(__file__).parent / "assets" / "logo.png"
        self.rare_logo = Path(__file__).parent / "assets" / "rare_logo.png"
        self.evil_logo = Path(__file__).parent / "assets" / "evil_logo.png"

        chance = random.random()
        if chance < 0.01:
            logo = self.evil_logo
        elif chance < 0.1:
            logo = self.rare_logo
        else:
            logo = self.logo

        self.setWindowIcon(QIcon(str(logo)))
        
        self.is_playing = False # updates if play or stop is pressed, not pause/resume
        self.is_paused = False 
        self.queue = []
        self.pretty_queue = [] # Song name - Artist
        self.start_song = 0
        self.last_position = 0

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()

        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self.handle_media_status)
        self.player.playbackStateChanged.connect(self.handle_state_change)


        # Set fixed size
        self.setFixedSize(800, 600) # non resizable

        # Create layout
        layout = QHBoxLayout()
        main_layout = QVBoxLayout()
        external_layout = QVBoxLayout()
        
        # * Main layout

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

        # Volume control slider 
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        # Default volume is 50%
        self.volume_slider.setValue(50) 
        self.audio_output.setVolume(0.5) # Set initial volume to 50%

        self.volume_slider.setFixedWidth(250)

        # Connect volume slider to audio output
        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))

        self.volume_text = QLabel("50%")
        self.audio_output.volumeChanged.connect(lambda: self.volume_text.setText(f"{int(self.audio_output.volume() * 100)}%"))

        button_layout.addWidget(self.volume_slider, 1, 0)
        button_layout.addWidget(self.volume_text, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)

        # Play song button
        self.play_button = QPushButton("Play")
        self.play_button.setFixedWidth(387)
        self.play_button.clicked.connect(self.play_song)
        button_layout.addWidget(self.play_button, 2, 0)

        # Pause song button
        self.pause_button = QPushButton("Pause / Resume")
        self.pause_button.setFixedWidth(387)
        self.pause_button.clicked.connect(self.toggle_pause)
        button_layout.addWidget(self.pause_button, 3, 0)

        # Previous song button
        self.prev_button = QPushButton("Previous")
        self.prev_button.setFixedWidth(190)
        self.prev_button.clicked.connect(self.previous_song) 
        button_layout.addWidget(self.prev_button, 4, 0)

        # Next song button
        self.next_button = QPushButton("Next")
        self.next_button.setFixedWidth(190)
        self.next_button.clicked.connect(self.next_song)
        button_layout.addWidget(self.next_button, 4, 1)

        # Shuffle button 
        self.shuffle_button = QPushButton("Shuffle")
        self.shuffle_button.setFixedWidth(387)
        self.shuffle_button.clicked.connect(self.shuffle_queue)
        button_layout.addWidget(self.shuffle_button, 5, 0)

        # Stop song button
        self.stop_button = QPushButton("Stop")
        self.stop_button.setFixedWidth(387)
        self.stop_button.clicked.connect(self.stop_song)
        button_layout.addWidget(self.stop_button, 6, 0)

        main_layout.addLayout(album_info_layout)
        main_layout.addLayout(button_layout)

        # * External layout
        # Manual metadata edit button
        load_layout = QHBoxLayout()

        # Load Song button
        self.load_metadata_button = QPushButton("Load Song")
        self.load_metadata_button.setFixedWidth(190)
        self.load_metadata_button.clicked.connect(self.load_metadata)
        load_layout.addWidget(self.load_metadata_button)

        # Load folder button
        self.load_folder_button = QPushButton("Load Folder")
        self.load_folder_button.setFixedWidth(190)
        self.load_folder_button.clicked.connect(self.load_folder)
        load_layout.addWidget(self.load_folder_button)

        external_layout.addLayout(load_layout)

        self.manual_metadata = QPushButton("Edit Metadata")
        self.manual_metadata.setFixedWidth(387)
        self.manual_metadata.clicked.connect(self.edit_metadata_popup)

        external_layout.addWidget(self.manual_metadata, alignment=Qt.AlignmentFlag.AlignTop)

        # Queue editor list
        self.queue_editor = QListWidget()
        self.queue_editor.setFixedWidth(387)
        self.queue_editor.setFixedHeight(300)

        # Proprieties
        self.queue_editor.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.queue_editor.model().rowsMoved.connect(self.reorder_queue)


        external_layout.addWidget(self.queue_editor)

        layout.addLayout(main_layout)
        layout.addLayout(external_layout)

        self.setLayout(layout)

    def reorder_queue(self, source_parent, source_start, source_end, dest_parent, dest_row):
        # This function will reorder the queue based on the new order of the items in the queue editor list
        if source_start == dest_row or source_start == dest_row - 1:
            return  # No change in order

        moved_item = self.queue.pop(source_start)
        if source_start < dest_row:
            self.queue.insert(dest_row - 1, moved_item)
        else:
            self.queue.insert(dest_row, moved_item)

        print(f"{self.queue=}")

        self.update_pretty_queue()
    

    def _set_cover_art(self, cover_art):
        # This function will set the album cover from the cover art data in the metadata
        pixmap = QPixmap()
        try:
            pixmap.loadFromData(cover_art.data)
        except Exception as e:
            print(e)
            pixmap.loadFromData(cover_art) # fallback
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

        self.update_rpc(loaded_audio.title, loaded_audio.artist, loaded_audio.album, duration)

    def update_position(self, position):
        if not self.song_pb.isSliderDown():
            self.song_pb.setValue(position)

        formatted_time = self.format_time(position)
        self.current_time_label.setText(formatted_time)

        delta = abs(position - self.last_position)

        # If jump is larger than 2 seconds, assume user skipped.
        # Only update RPC if we have loaded audio metadata.
        if delta > 2000 and loaded_audio:
            self.update_rpc(loaded_audio.title, loaded_audio.artist, loaded_audio.album, self.player.duration())
        
        self.last_position = position

    def shuffle_queue(self):
        if self.queue:
            self.queue.pop(self.queue.index(loaded_audio.filename)) 
            random.shuffle(self.queue)
            self.queue.insert(0, loaded_audio.filename)
            self.update_pretty_queue()
            print("Queue shuffled.")
        else:
            print("No songs in the queue to shuffle.")
    
    def update_pretty_queue(self):
        global loaded_audio
        self.pretty_queue = []
        for track in self.queue:
            if track == loaded_audio.filename:
                self.pretty_queue.append(f"> {loaded_audio.title} - {loaded_audio.artist} <")
            else:
                audio = load_metadata(track)
                self.pretty_queue.append(f"{audio.title} - {audio.artist}")
        
        self.queue_editor.clear()
        self.queue_editor.addItems(self.pretty_queue)

    @lru_cache(maxsize=50)
    def get_ac_link(self, artist, track_title, album_name) -> Optional[str]:
        # * Deezer API yay
        query = f"{artist} {track_title}"
        url = f"https://api.deezer.com/search?q={query}"
        response = requests.get(url)
        if response.status_code == 200:
        
            data = response.json()['data'][0]
            print(data)
            ac_link = data['album']['cover_xl'] if data['album'] else None

            # Double check if the album name matches, since the search is not always accurate
            if data['album'] and album_name.lower() not in data['album']['title'].lower():
                print("Album name does not match, skipping album cover")
                ac_link = None
        else:
            print("Error fetching album cover from Deezer API")

        if ac_link:
            return ac_link

        # * Ask my API
        catplay_url = "https://catplay-server-production.up.railway.app/get-album-cover"
        params = {
            "artist": artist,
            "album": album_name,
        }
        response = requests.get(catplay_url, params=params)
        if response.status_code != 200:
            print("Error fetching album cover from CatPlay API")
            return None
        
        data = response.json()
        ac_link = data.get("cover")
        return ac_link


    def update_rpc(self, track_title, artist, album_name, duration_ms):
        global RPC

        start_time = int(time.time()) 
        end_time = start_time + (duration_ms // 1000)

        # Get image for the current track's album cover
        link = self.get_ac_link(artist, track_title, album_name)

        RPC.update(
            activity_type=ActivityType.LISTENING,
            details=track_title,
            state=f"by {artist}",
            start=start_time,
            end=end_time,
            large_image=link or "logo", # Fallback to default logo if no cover art is found
            small_image="logo" if link else None,
            large_text=album_name
        )

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
        global loaded_audio
        print(f"Loading metadata from: {file_path}")
        if file_path:
            loaded_audio = load_metadata(file_path)
            self.info_label.setText(f"Title: {loaded_audio.title}\nArtist: {loaded_audio.artist}\nAlbum: {loaded_audio.album}")
            if loaded_audio.cover:
                self._set_cover_art(loaded_audio.cover)
            else:
                print("No cover art found in metadata.")

    def load_metadata(self):
        # Dialog to select a music file
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Music File", filter="Audio Files (*.mp3 *.flac *.wav *.m4a)")
        self.load_metadata_from_path(file_path)

    def play_song(self):
        global loaded_audio
        if loaded_audio:
            self.player.setSource(QUrl.fromLocalFile(loaded_audio.filename))
            self.player.play()
            self.is_playing = True
            self.is_paused = False
            self.start_song = int(time.time())
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
            for ext in ("*.mp3", "*.flac", "*.wav", "*.m4a"):
                audio_paths.extend(Path(folder_path).glob(ext))

            audio_files = [str(path) for path in audio_paths]

            # if audio_files[0][0] == "0":
            #     # Songs are ordered with numbers
            #     audio_files.sort() # Sort files alphabetically

            # If not, just pray it's in order

            print(audio_files)

        self.queue = audio_files 
        
        # Load first track
        if audio_files:
            first_track = audio_files[0]
            print(f"Loading first track: {first_track}")
            self.load_metadata_from_path(first_track)
    
        self.update_pretty_queue()

    def next_song(self):
        global loaded_audio
        if self.queue:
            current_index = self.queue.index(loaded_audio.filename) if loaded_audio else -1
            next_index = (current_index + 1) % len(self.queue)
            next_track = self.queue[next_index]
            print(f"Loading next track: {next_track}")
            self.load_metadata_from_path(next_track)
            self.play_song()
            self.update_pretty_queue()
        else:
            print("No songs in the queue.")
    
    def previous_song(self):
        global loaded_audio
        if self.queue:
            current_index = self.queue.index(loaded_audio.filename) if loaded_audio else -1
            prev_index = (current_index - 1) % len(self.queue)
            prev_track = self.queue[prev_index]
            print(f"Loading previous track: {prev_track}")
            self.load_metadata_from_path(prev_track)
            self.play_song()
            self.update_pretty_queue()
        else:
            print("No songs in the queue.")

    def handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.queue:
            self.next_song()
    
    def handle_state_change(self, state):
        global loaded_audio
        if state == QMediaPlayer.PlaybackState.PlayingState and loaded_audio:
            self.update_rpc(loaded_audio.title, loaded_audio.artist, loaded_audio.album, self.player.duration())
        elif state in (QMediaPlayer.PlaybackState.PausedState, QMediaPlayer.PlaybackState.StoppedState):
            RPC.clear()
    
    def edit_metadata_popup(self):
        global loaded_audio
        if not loaded_audio:
            print("No audio loaded.")
            return
        
        popup = MetadataPopup()
        popup.exec()

        # Refresh metadata after editing
        self.load_metadata_from_path(loaded_audio.filename)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
