from dataclasses import dataclass
from functools import lru_cache
import sys
from typing import Any, Optional
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QFileDialog, QVBoxLayout, QSlider, QGridLayout, QHBoxLayout, QDialog, QLineEdit, QListWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QUrl
from pathlib import Path
import mimetypes
from mutagen import FileType
from mutagen.mp4 import MP4
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC, # album cover
    TIT2, # title
    TPE1, # artist
    TALB, # album
    TSO2, # album artist
    COMM, # comments
    TCOM, # composer
    TCON, # genre
    TDAT, # date
    TYER, # year
    TDRC, # recording date (v2.4)
    TCOP, # copyright
)
from mutagen.wave import WAVE
import random
from pypresence import Presence
from pypresence.types import ActivityType, StatusDisplayType
from pypresence.exceptions import DiscordNotFound
import time
import requests
import logging
from logging import StreamHandler
from logging.handlers import TimedRotatingFileHandler
import platformdirs
import threading

# Personal TODOs
# TODO: Volume control
# TODO: Last.fm scrobbling, love track
# TODO: Queue management
# TODO: A vinyl view for the album cover, with a disc spinning would be so cool
# TODO: Genius link to get lyrics
# TODO: Add logging

loading_start_time = time.time()

def ressource_path(relative_path: Path) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.absolute()))
    return str(base_path / relative_path)

dirs = platformdirs.PlatformDirs("CatPlay", "Ierzi")

cache_dir = Path(dirs.user_cache_dir)
logs_dir = cache_dir / "logs"
if not logs_dir.exists():
    logs_dir.mkdir(parents=True)

trf_handler = TimedRotatingFileHandler(
    str(logs_dir / "app.log"),
    when="midnight",
    backupCount=7, # 7 days
    encoding="utf-8"
)

console_handler = StreamHandler()

LOGGING_LEVEL = logging.DEBUG

logging.basicConfig(
    level=LOGGING_LEVEL,
    format="[%(levelname)s] [%(asctime)s] - %(message)s",
    handlers=[trf_handler, console_handler]
)

# Putting this in a seperate thread just reduced loading times by 0.3 to TWENTY SECONDS LMAO
def init_discord_rpc():
    global RPC
    try:
        started_rpc_time = time.time()
        logging.debug("discord rpc init...")
        RPC = Presence(1475462488245014568)
        RPC.connect()
        ended_rpc_time = time.time()
        logging.debug(f"discord rpc initialized in {ended_rpc_time - started_rpc_time:.2f} seconds")
    except DiscordNotFound as dnf:
        logging.warning(dnf)
    except Exception as e:
        logging.warning(f"Failed to connect to Discord but another exception idk: {e}")

RPC = None
rpc_thread = threading.Thread(target=init_discord_rpc, daemon=True)
rpc_thread.daemon = True
rpc_thread.start()

loaded_audio = None

@dataclass(slots=True)
class AudioMetadata:
    audio: FileType
    filename: str
    title: str = "Unknown Title"
    artist: str = "Unknown Artist"
    album: str = "Unknown Album"
    album_artist: Optional[str] = None
    cover: Optional[Any] = None # i actually dont know the type lol 
    comment: Optional[str] = None # aka description
    composer: Optional[str] = None
    genre: Optional[str] = None
    date: Optional[str] = None
    year: Optional[int] = None
    discnumber: Optional[int] = None
    tracknumber: Optional[int] = None
    totaltracks: Optional[int] = None
    copyright: Optional[str] = None

@lru_cache(maxsize=128)
def load_metadata(file_path: str) -> AudioMetadata:
    if file_path.endswith(".mp3"):
        audio = MP3(file_path)

        def _text_from_tag(tag, default: str = "") -> str:
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
        
        for key in audio.keys():
            if not key.startswith("APIC"):
                logging.debug(f"{key}: {audio[key]}")

        title = _text_from_tag(audio.get("TIT2"), "Unknown Title")
        artist = _text_from_tag(audio.get("TPE1"), "Unknown Artist")
        album = _text_from_tag(audio.get("TALB"), "Unknown Album")
        cover = audio.get("APIC:") or audio.get("APIC") or None
        album_artist = _text_from_tag(audio.get("TSO2"))
        comment = _text_from_tag(audio.get("COMM")) or _text_from_tag(audio.get("COMM::XXX")) or _text_from_tag(audio.get("COMM::eng")) 
        composer = _text_from_tag(audio.get("TCOM"))
        genre = _text_from_tag(audio.get("TCON"))
        date = _text_from_tag(audio.get("TDAT")) or _text_from_tag(audio.get("TDRC")) # just learned that mutagen auto converts TYEA to TDRC if ID3 v2_4
        year = _text_from_tag(audio.get("TYEA")) 
        copyright = _text_from_tag(audio.get("TCOP"))

        return AudioMetadata(
            audio=audio, 
            filename=audio.filename,
            title=title, 
            artist=artist, 
            album=album,
            album_artist=album_artist, 
            cover=cover,
            comment=comment,
            composer=composer,
            genre=genre,
            date=date,
            year=year,
            copyright=copyright
        )

    elif file_path.endswith(".flac"):
        audio = FLAC(file_path)
        for tag in audio.keys():
            logging.debug(f"{tag}: {audio[tag]}")
        title = audio.get("title", ["Unknown Title"])[0]
        artist = audio.get("artist", ["Unknown Artist"])[0]
        album = audio.get("album", ["Unknown Album"])[0]
        album_artist = audio.get("albumartist")[0] if audio.get("albumartist") else None
        cover = audio.pictures[0] if audio.pictures else None
        composer = audio.get("composer")[0] if audio.get("composer") else None
        date = audio.get("date")[0] if audio.get("date") else None
        discnumber = audio.get("discnumber")[0] if audio.get("discnumber") else None
        year = audio.get("year")[0] if audio.get("year") else None
        description = audio.get("description")[0] if audio.get("description") else None
        tracknumber = audio.get("tracknumber")[0] if audio.get("tracknumber") else None
        genre = audio.get("genre")[0] if audio.get("genre") else None

        return AudioMetadata(
            audio=audio, 
            filename=audio.filename,
            title=title, 
            artist=artist, 
            album=album, 
            album_artist=album_artist,
            cover=cover,
            composer=composer,
            date=date,
            discnumber=discnumber,
            year=year,
            comment=description,
            tracknumber=tracknumber,
            genre=genre
        )

    elif file_path.endswith(".m4a"):
        audio = MP4(file_path)

        title = audio.get("©nam", ["Unknown Title"])[0]
        artist = audio.get("©ART", ["Unknown Artist"])[0]
        album = audio.get("©alb", ["Unknown Album"])[0]
        cover = audio.get("covr", [None])[0] if audio.get("covr") else None
        tracknumber = audio.get("trkn", [None])[0] if audio.get("trkn") else None

        for tag in audio.keys():
            if len(audio[tag][0]) > 300:
                logging.debug(f"{tag}: [album cover data]")
                continue
            logging.debug(f"{tag}: {audio[tag]}")

        return AudioMetadata(
            audio=audio, 
            filename=audio.filename,
            title=title, 
            artist=artist, 
            album=album, 
            cover=cover
        )

    elif file_path.endswith(".wav"):
        audio = WAVE(file_path)

        # Uses ID3 tags
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

        return AudioMetadata(
            audio=audio, 
            filename=audio.filename,
            title=title, 
            artist=artist, 
            album=album, 
            cover=cover
        )

# MP3 metadata popup
class MetadataPopupMP3(QDialog):
    def __init__(self):
        global loaded_audio
        self.data = {
            "title": loaded_audio.title,
            "artist": loaded_audio.artist,
            "album": loaded_audio.album,
            "albumartist": loaded_audio.album_artist,
            "cover": loaded_audio.cover,
            "comment": loaded_audio.comment,
            "composer": loaded_audio.composer,
            "genre": loaded_audio.genre,
            "date": loaded_audio.date,
            "year": loaded_audio.year,
            "copyright": loaded_audio.copyright
        } 
        super().__init__()

        # Get ID3 version
        id3_version = loaded_audio.audio.tags.version if loaded_audio.audio.tags else (2, 4, 0)
        
        # Window propreties
        self.setWindowTitle("Edit Metadata")
        self.setWindowIcon(QIcon(ressource_path(Path("assets") / "logo.png"))) # no randomness here
        self.setFixedSize(650, 400) 

        layout = QHBoxLayout()

        # * Album cover layout
        ac_layout = QVBoxLayout()

        # Album cover widget
        self.ac_label = QLabel()
        self.ac_label.setAlignment( Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter) 
        ac = loaded_audio.cover or (Path(__file__).parent / "assets" / "placeholder.jpg")
        pixmap = QPixmap()

        if isinstance(ac, Path):
            pixmap.load(str(ac))
        else:
            try:
                pixmap.loadFromData(ac.data)
            except Exception as e:
                logging.warning(e)
                logging.warning("Failed to load album cover from data, trying fallback method.")
                pixmap.loadFromData(ac) # fallback
        
        pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.ac_label.setPixmap(pixmap)
        ac_layout.addWidget(self.ac_label)

        # Edit album cover button
        self.edit_ac_button = QPushButton("Edit Album Cover")
        self.edit_ac_button.clicked.connect(self.edit_album_cover)
        self.edit_ac_button.setFixedWidth(200)
        ac_layout.addWidget(self.edit_ac_button)

        # * Metadata edit layout
        editing_layout = QGridLayout()

        # Title edit field
        self.title_label = QLabel("Title:")
        self.title_label.setFixedWidth(65)
        self.title_edit = QLineEdit(loaded_audio.title)
        self.title_edit.setFixedWidth(200)
        self.title_edit.textChanged.connect(self.edit_title)

        editing_layout.addWidget(self.title_label, 0, 0)
        editing_layout.addWidget(self.title_edit, 0, 1)

        # Artist edit field
        self.artist_label = QLabel("Artist:")
        self.artist_label.setFixedWidth(65)
        self.artist_edit = QLineEdit(loaded_audio.artist)
        self.artist_edit.setFixedWidth(200)
        self.artist_edit.textChanged.connect(self.edit_artist)

        editing_layout.addWidget(self.artist_label, 1, 0)
        editing_layout.addWidget(self.artist_edit, 1, 1)

        # Album edit field
        self.album_label = QLabel("Album:")
        self.album_label.setFixedWidth(65)
        self.album_edit = QLineEdit(loaded_audio.album)
        self.album_edit.setFixedWidth(200)
        self.album_edit.textChanged.connect(self.edit_album)

        editing_layout.addWidget(self.album_label, 2, 0)
        editing_layout.addWidget(self.album_edit, 2, 1)

        # Album artist edit field
        self.album_artist_label = QLabel("Album Artist:")
        self.album_artist_label.setFixedWidth(65)
        self.album_artist_edit = QLineEdit(loaded_audio.album_artist or "")
        self.album_artist_edit.setFixedWidth(200)
        self.album_artist_edit.textChanged.connect(self.edit_album_artist)
        editing_layout.addWidget(self.album_artist_label, 3, 0)
        editing_layout.addWidget(self.album_artist_edit, 3, 1)

        # Comment edit field
        self.comment_label = QLabel("Comment:")
        self.comment_label.setFixedWidth(65)
        comment_text = loaded_audio.comment or ""
        self.comment_edit = QLineEdit(comment_text)
        self.comment_edit.setFixedWidth(200)
        self.comment_edit.textChanged.connect(self.edit_comment)
        editing_layout.addWidget(self.comment_label, 4, 0)
        editing_layout.addWidget(self.comment_edit, 4, 1)
        
        # Composer edit field
        self.composer_label = QLabel("Composer:")
        self.composer_label.setFixedWidth(65)
        composer_text = loaded_audio.composer or ""
        self.composer_edit = QLineEdit(composer_text)
        self.composer_edit.setFixedWidth(200)
        self.composer_edit.textChanged.connect(self.edit_composer)
        editing_layout.addWidget(self.composer_label, 5, 0)
        editing_layout.addWidget(self.composer_edit, 5, 1)

        # Genre edit field
        self.genre_label = QLabel("Genre:")
        self.genre_label.setFixedWidth(65)
        genre_text = loaded_audio.genre or ""
        self.genre_edit = QLineEdit(genre_text)
        self.genre_edit.setFixedWidth(200)
        self.genre_edit.textChanged.connect(self.edit_genre)
        editing_layout.addWidget(self.genre_label, 6, 0)
        editing_layout.addWidget(self.genre_edit, 6, 1)

        # Date edit field
        self.date_label = QLabel("Date:")
        self.date_label.setFixedWidth(65)
        date_text = loaded_audio.date or ""
        self.date_edit = QLineEdit(str(date_text))
        self.date_edit.setFixedWidth(200)
        self.date_edit.textChanged.connect(self.edit_date)
        editing_layout.addWidget(self.date_label, 7, 0)
        editing_layout.addWidget(self.date_edit, 7, 1)

        # Year edit field (only for ID3 v2.3)
        if id3_version[1] == 3:
            self.year_label = QLabel("Year:")
            self.year_label.setFixedWidth(65)
            year_text = loaded_audio.year
            self.year_edit = QLineEdit(str(year_text) if year_text is not None else "")
            self.year_edit.setFixedWidth(200)
            self.year_edit.textChanged.connect(self.edit_year)
            editing_layout.addWidget(self.year_label, 8, 0)
            editing_layout.addWidget(self.year_edit, 8, 1)
            copyright_row = 9
        else:
            copyright_row = 8

        # Copyright edit field
        self.copyright_label = QLabel("Copyright:")
        self.copyright_label.setFixedWidth(65)
        copyright_text = loaded_audio.copyright or ""
        self.copyright_edit = QLineEdit(copyright_text)
        self.copyright_edit.setFixedWidth(200)
        self.copyright_edit.textChanged.connect(self.edit_copyright)
        editing_layout.addWidget(self.copyright_label, copyright_row, 0)
        editing_layout.addWidget(self.copyright_edit, copyright_row, 1)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.setFixedWidth(125)
        self.save_button.clicked.connect(self.save) # Close the popup when save is clicked
        editing_layout.addWidget(self.save_button, copyright_row + 1, 1, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        layout.addLayout(ac_layout)
        layout.addLayout(editing_layout)

        self.setLayout(layout)

    def edit_album_cover(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Album Cover", filter="Image Files (*.png *.jpg *.jpeg)")
        if file_path:
            pixmap = QPixmap(file_path)
            pixmap = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
            self.ac_label.setPixmap(pixmap)
            self.data["cover"] = file_path
            logging.info("ac updated in popup")
        
    def edit_title(self, text):
        self.data["title"] = text
    
    def edit_artist(self, text):
        self.data["artist"] = text
    
    def edit_album(self, text):
        self.data["album"] = text
    
    def edit_album_artist(self, text):
        self.data["albumartist"] = text

    def edit_comment(self, text):
        self.data["comment"] = text
    
    def edit_composer(self, text):
        self.data["composer"] = text
    
    def edit_genre(self, text):
        self.data["genre"] = text
    
    def edit_date(self, text):
        self.data["date"] = text
    
    def edit_year(self, text):
        self.data["year"] = text
    
    def edit_copyright(self, text):
        self.data["copyright"] = text
    
    def save(self):
        global loaded_audio
        if not loaded_audio.audio.tags:
            loaded_audio.audio.add_tags()
        version = loaded_audio.audio.tags.version
        encoding = 1 if version[1] == 3 else 3  # UTF-16 for v2.3, UTF-8 for v2.4
        loaded_audio.audio.delete() # Clear all tags
        loaded_audio.audio.tags.version = (2, version[1], 0)  # Ensure version is set

        loaded_audio.audio["TIT2"] = TIT2(encoding=encoding, text=self.data["title"])
        loaded_audio.audio["TPE1"] = TPE1(encoding=encoding, text=self.data["artist"])
        loaded_audio.audio["TALB"] = TALB(encoding=encoding, text=self.data["album"])
        loaded_audio.audio["TSO2"] = TSO2(encoding=encoding, text=self.data["albumartist"])
        loaded_audio.audio["COMM"] = COMM(encoding=encoding, lang='eng', desc='', text=self.data["comment"])
        loaded_audio.audio["TCOM"] = TCOM(encoding=encoding, text=self.data["composer"])
        loaded_audio.audio["TCON"] = TCON(encoding=encoding, text=self.data["genre"])
        if version[1] == 3:  # ID3 v2.3
            loaded_audio.audio["TDAT"] = TDAT(encoding=encoding, text=self.data["date"])
            loaded_audio.audio["TYER"] = TYER(encoding=encoding, text=str(self.data["year"]))
        else:  # ID3 v2.4 - use date field for TDRC
            if self.data["date"]:
                loaded_audio.audio["TDRC"] = TDRC(encoding=encoding, text=self.data["date"])
        loaded_audio.audio["TCOP"] = TCOP(encoding=encoding, text=self.data["copyright"])

        if isinstance(self.data["cover"], str):
            with open(self.data["cover"], "rb") as img_file:
                img_data = img_file.read()
                mime = mimetypes.guess_type(self.data["cover"])[0] or "image/jpeg"
                loaded_audio.audio["APIC"] = APIC(
                    encoding=encoding,
                    mime=mime,
                    type=3, # cover (front)
                    desc="",
                    data=img_data
                )
        
        else:
            # APIC
            loaded_audio.audio["APIC"] = self.data.get("cover")
        
        loaded_audio.audio.save()
        logging.info("Metadata saved.")
        self.close()

# FLAC metadata popup
class MetadataPopupFLAC(QDialog):
    def __init__(self):
        super().__init__()
        
        self.data = {
            "title": loaded_audio.title,
            "artist": loaded_audio.artist,
            "album": loaded_audio.album,
            "albumartist": loaded_audio.album_artist,
            "cover": loaded_audio.cover,
            "date": loaded_audio.date,
            "year": loaded_audio.year,
            "description": loaded_audio.comment,
            "discnumber": loaded_audio.discnumber,
            "tracknumber": loaded_audio.tracknumber,
            "genre": loaded_audio.genre,
            "composer": loaded_audio.composer
        }

        # Window propreties
        self.setWindowTitle("Edit Metadata")
        self.setWindowIcon(QIcon(ressource_path(Path("assets") / "logo.png"))) # no randomness here
        self.setFixedSize(650, 400) 

        layout = QHBoxLayout()

        # * Album cover layout
        ac_layout = QVBoxLayout()

        # Album cover widget
        self.ac_label = QLabel()
        self.ac_label.setAlignment( Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter) 
        ac = loaded_audio.cover or (Path(__file__).parent / "assets" / "placeholder.jpg")
        pixmap = QPixmap()

        if isinstance(ac, Path):
            pixmap.load(str(ac))
        else:
            try:
                pixmap.loadFromData(ac.data)
            except Exception as e:
                logging.warning(e)
                logging.warning("Failed to load album cover from data, trying fallback method.")
                pixmap.loadFromData(ac) # fallback
        
        pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.ac_label.setPixmap(pixmap)
        ac_layout.addWidget(self.ac_label)

        # Edit album cover button
        self.edit_ac_button = QPushButton("Edit Album Cover")
        self.edit_ac_button.clicked.connect(self.edit_album_cover)
        self.edit_ac_button.setFixedWidth(200)
        ac_layout.addWidget(self.edit_ac_button)

        # * Metadata edit layout
        editing_layout = QGridLayout()

        # Title edit field
        self.title_label = QLabel("Title:")
        self.title_label.setFixedWidth(80)
        self.title_edit = QLineEdit(loaded_audio.title)
        self.title_edit.setFixedWidth(200)
        self.title_edit.textChanged.connect(self.edit_title)
        editing_layout.addWidget(self.title_label, 0, 0)
        editing_layout.addWidget(self.title_edit, 0, 1)

        # Artist edit field
        self.artist_label = QLabel("Artist:")
        self.artist_label.setFixedWidth(80)
        self.artist_edit = QLineEdit(loaded_audio.artist)
        self.artist_edit.setFixedWidth(200)
        self.artist_edit.textChanged.connect(self.edit_artist)

        editing_layout.addWidget(self.artist_label, 1, 0)
        editing_layout.addWidget(self.artist_edit, 1, 1)

        # Album edit field
        self.album_label = QLabel("Album:")
        self.album_label.setFixedWidth(80)
        self.album_edit = QLineEdit(loaded_audio.album)
        self.album_edit.setFixedWidth(200)
        self.album_edit.textChanged.connect(self.edit_album)

        editing_layout.addWidget(self.album_label, 2, 0)
        editing_layout.addWidget(self.album_edit, 2, 1)

        # Album artist edit field
        self.album_artist_label = QLabel("Album Artist:")
        self.album_artist_label.setFixedWidth(80)
        self.album_artist_edit = QLineEdit(loaded_audio.album_artist)
        self.album_artist_edit.setFixedWidth(200)
        self.album_artist_edit.textChanged.connect(self.edit_album_artist)

        editing_layout.addWidget(self.album_artist_label, 3, 0)
        editing_layout.addWidget(self.album_artist_edit, 3, 1)

        # Date edit field
        self.date_label = QLabel("Date:")
        self.date_label.setFixedWidth(80)
        self.date_edit = QLineEdit(loaded_audio.date)
        self.date_edit.setFixedWidth(200)
        self.date_edit.textChanged.connect(self.edit_date)
        editing_layout.addWidget(self.date_label, 4, 0)
        editing_layout.addWidget(self.date_edit, 4, 1)
        
        # Year edit field
        self.year_label = QLabel("Year:")
        self.year_label.setFixedWidth(80)
        self.year_edit = QLineEdit(loaded_audio.year)
        self.year_edit.setFixedWidth(200)
        self.year_edit.textChanged.connect(self.edit_year)
        editing_layout.addWidget(self.year_label, 5, 0)
        editing_layout.addWidget(self.year_edit, 5, 1)

        # Description edit field
        self.description_label = QLabel("Description:")
        self.description_label.setFixedWidth(80)
        self.description_edit = QLineEdit(loaded_audio.comment)
        self.description_edit.setFixedWidth(200)
        self.description_edit.textChanged.connect(self.edit_description)
        editing_layout.addWidget(self.description_label, 6, 0)
        editing_layout.addWidget(self.description_edit, 6, 1)

        # Disc number edit field
        self.disc_number_label = QLabel("Disc number:")
        self.disc_number_label.setFixedWidth(80)
        self.disc_number_edit = QLineEdit(loaded_audio.discnumber)
        self.disc_number_edit.setFixedWidth(200)
        self.disc_number_edit.textChanged.connect(self.edit_disc_number)
        editing_layout.addWidget(self.disc_number_label, 7, 0)
        editing_layout.addWidget(self.disc_number_edit, 7, 1)


        # Track number edit field
        self.track_number_label = QLabel("Track number:")
        self.track_number_label.setFixedWidth(80)
        self.track_number_edit = QLineEdit(loaded_audio.tracknumber)
        self.track_number_edit.setFixedWidth(200)
        self.track_number_edit.textChanged.connect(self.edit_track_number)
        editing_layout.addWidget(self.track_number_label, 8, 0)
        editing_layout.addWidget(self.track_number_edit, 8, 1)

        # Genre edit field
        self.genre_label = QLabel("Genre:")
        self.genre_label.setFixedWidth(80)
        self.genre_edit = QLineEdit(loaded_audio.genre)
        self.genre_edit.setFixedWidth(200)
        self.genre_edit.textChanged.connect(self.edit_genre)
        editing_layout.addWidget(self.genre_label, 9, 0)
        editing_layout.addWidget(self.genre_edit, 9, 1)

        # Composer edit field
        self.composer_label = QLabel("Composer:")
        self.composer_label.setFixedWidth(80)
        self.composer_edit = QLineEdit(loaded_audio.composer)
        self.composer_edit.setFixedWidth(200)
        self.composer_edit.textChanged.connect(self.edit_composer)
        editing_layout.addWidget(self.composer_label, 10, 0)
        editing_layout.addWidget(self.composer_edit, 10, 1)


        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.setFixedWidth(125)
        self.save_button.clicked.connect(self.save) # Close the popup when save is clicked
        editing_layout.addWidget(self.save_button, 11, 1, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        layout.addLayout(ac_layout)
        layout.addLayout(editing_layout)

        self.setLayout(layout)

    def edit_album_cover(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Album Cover", filter="Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            pixmap = QPixmap(file_path)
            pixmap = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
            self.ac_label.setPixmap(pixmap)
            self.data["cover"] = file_path
            logging.info("ac updated in popup")
    
    def edit_title(self, text):
        self.data["title"] = text
    
    def edit_artist(self, text):
        self.data["artist"] = text
    
    def edit_album(self, text):
        self.data["album"] = text
    
    def edit_album_artist(self, text):
        self.data["albumartist"] = text
    
    def edit_date(self, text):
        self.data["date"] = text
    
    def edit_year(self, text):
        self.data["year"] = text
    
    def edit_description(self, text):
        self.data["description"] = text
    
    def edit_disc_number(self, text):
        self.data["discnumber"] = text
    
    def edit_track_number(self, text):
        self.data["tracknumber"] = text
    
    def edit_genre(self, text):
        self.data["genre"] = text
    
    def edit_composer(self, text):
        self.data["composer"] = text
    
    def save(self):
        global loaded_audio
        loaded_audio.audio.delete() # Clear all tags

        if self.data["title"]:
            loaded_audio.audio["title"] = [self.data["title"]]
        if self.data["artist"]:
            loaded_audio.audio["artist"] = [self.data["artist"]]
        if self.data["album"]:
            loaded_audio.audio["album"] = [self.data["album"]]
        if self.data["albumartist"]:
            loaded_audio.audio["albumartist"] = [self.data["albumartist"]]
        if self.data["date"]:
            loaded_audio.audio["date"] = [self.data["date"]]
        if self.data["year"]:
            loaded_audio.audio["year"] = [self.data["year"]]
        if self.data["description"]:
            loaded_audio.audio["description"] = [self.data["description"]]
        if self.data["discnumber"]:
            loaded_audio.audio["discnumber"] = [self.data["discnumber"]]
        if self.data["tracknumber"]:
            loaded_audio.audio["tracknumber"] = [self.data["tracknumber"]]
        if self.data["genre"]:
            loaded_audio.audio["genre"] = [self.data["genre"]]
        if self.data["composer"]:
            loaded_audio.audio["composer"] = [self.data["composer"]]
        if self.data["cover"]:
            if isinstance(self.data["cover"], str):
                with open(self.data["cover"], "rb") as img_file:
                    img_data = img_file.read()
                    picture = Picture()
                    picture.data = img_data
                    picture.type = 3 # cover (front)
                    picture.mime = mimetypes.guess_type(self.data["cover"])[0] or "image/jpeg"
                    picture.desc = "Cover"
                    loaded_audio.audio.clear_pictures()
                    loaded_audio.audio.add_picture(picture)
            else:
                loaded_audio.audio.clear_pictures()
                picture = Picture()
                picture.data = self.data["cover"].data
                picture.type = 3 # cover (front)
                picture.mime = self.data["cover"].mime
                picture.desc = "Cover"
                loaded_audio.audio.add_picture(picture)
        
        loaded_audio.audio.save()
        logging.info("Metadata saved.")
        self.close()

# M4A metadata popup
class MetadataPopupM4A(QDialog):
    def __init__(self) -> None:
        super().__init__()
        global loaded_audio

        self.data = {
            "title": loaded_audio.title,
            "artist": loaded_audio.artist,
            "album": loaded_audio.album,
            "cover": loaded_audio.cover,
            "tracknumber": loaded_audio.tracknumber,
            "totaltracks": loaded_audio.totaltracks,
            "discnumber": loaded_audio.discnumber,
            "date": loaded_audio.date,
            "copyright": loaded_audio.copyright,
        }

        # Window propreties
        self.setWindowTitle("Edit Metadata")
        self.setWindowIcon(QIcon(ressource_path(Path("assets") / "logo.png"))) # no randomness here
        self.setFixedSize(650, 400)

        layout = QHBoxLayout()

        # * Album cover layout
        ac_layout = QVBoxLayout()

        # Album cover widget
        self.ac_label = QLabel()
        self.ac_label.setAlignment( Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter) 
        ac = self.data.get("cover") or (Path(__file__).parent / "assets" / "placeholder.jpg")
        pixmap = QPixmap()

        if isinstance(ac, Path):
            pixmap.load(str(ac))
        else:
            try:
                pixmap.loadFromData(ac.data)
            except Exception as e:
                logging.warning(e)
                logging.warning("Failed to load album cover from data, trying fallback method.")
                pixmap.loadFromData(ac) # fallback
        
        pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.ac_label.setPixmap(pixmap)
        ac_layout.addWidget(self.ac_label)

        # Edit album cover button
        self.edit_ac_button = QPushButton("Edit Album Cover")
        self.edit_ac_button.clicked.connect(self.edit_album_cover)
        self.edit_ac_button.setFixedWidth(200)
        ac_layout.addWidget(self.edit_ac_button)

        # * Metadata edit layout
        me_layout = QGridLayout()

        # Edit title field
        self.title_label = QLabel("Title:")
        self.title_label.setFixedWidth(80)
        self.title_edit = QLineEdit(self.data.get("title"))
        self.title_edit.setFixedWidth(200)
        self.title_edit.textChanged.connect(self.edit_title)
        me_layout.addWidget(self.title_label, 0, 0)
        me_layout.addWidget(self.title_edit, 0, 1)

        # Artist edit field
        self.artist_label = QLabel("Artist:")
        self.artist_label.setFixedWidth(80)
        self.artist_edit = QLineEdit(self.data.get("artist"))
        self.artist_edit.setFixedWidth(200)
        self.artist_edit.textChanged.connect(self.edit_artist)

        me_layout.addWidget(self.artist_label, 1, 0)
        me_layout.addWidget(self.artist_edit, 1, 1)

        # Album edit field
        self.album_label = QLabel("Album:")
        self.album_label.setFixedWidth(80)
        self.album_edit = QLineEdit(self.data.get("album"))
        self.album_edit.setFixedWidth(200)
        self.album_edit.textChanged.connect(self.edit_album)

        me_layout.addWidget(self.album_label, 2, 0)
        me_layout.addWidget(self.album_edit, 2, 1)

        # Date edit field
        self.date_label = QLabel("Date:")
        self.date_label.setFixedWidth(80)
        self.date_edit = QLineEdit(self.data.get("date"))
        self.date_edit.setFixedWidth(200)
        self.date_edit.textChanged.connect(self.edit_date)
        me_layout.addWidget(self.date_label, 4, 0)
        me_layout.addWidget(self.date_edit, 4, 1)

        # Track number edit field
        self.track_number_label = QLabel("Track number:")
        self.track_number_label.setFixedWidth(80)
        self.track_number_edit = QLineEdit(str(self.data.get("tracknumber", "")))
        self.track_number_edit.setFixedWidth(200)
        self.track_number_edit.textChanged.connect(self.edit_tracknumber)
        me_layout.addWidget(self.track_number_label, 5, 0)
        me_layout.addWidget(self.track_number_edit, 5, 1)

        # Total tracks edit field
        self.total_tracks_label = QLabel("Total tracks:")
        self.total_tracks_label.setFixedWidth(80)
        self.total_tracks_edit = QLineEdit(str(self.data.get("totaltracks", "")))
        self.total_tracks_edit.setFixedWidth(200)
        self.total_tracks_edit.textChanged.connect(self.edit_totaltracks)
        me_layout.addWidget(self.total_tracks_label, 6, 0)
        me_layout.addWidget(self.total_tracks_edit, 6, 1)

        # Disc number edit field
        self.disc_number_label = QLabel("Disc number:")
        self.disc_number_label.setFixedWidth(80)
        self.disc_number_edit = QLineEdit(str(self.data.get("discnumber", "")))
        self.disc_number_edit.setFixedWidth(200)
        self.disc_number_edit.textChanged.connect(self.edit_discnumber)
        me_layout.addWidget(self.disc_number_label, 7, 0)
        me_layout.addWidget(self.disc_number_edit, 7, 1)

        # Copyright edit field
        self.copyright_label = QLabel("Copyright:")
        self.copyright_label.setFixedWidth(80)
        self.copyright_edit = QLineEdit(self.data.get("copyright", ""))
        self.copyright_edit.setFixedWidth(200)
        self.copyright_edit.textChanged.connect(self.edit_copyright)
        me_layout.addWidget(self.copyright_label, 12, 0)
        me_layout.addWidget(self.copyright_edit, 12, 1)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.setFixedWidth(125)
        self.save_button.clicked.connect(self.save)
        me_layout.addWidget(self.save_button, 13, 1, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        layout.addLayout(ac_layout)
        layout.addLayout(me_layout)

        self.setLayout(layout)

    def edit_album_cover(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Album Cover", filter="Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            pixmap = QPixmap(file_path)
            pixmap = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation) 
            self.ac_label.setPixmap(pixmap)
            self.data["cover"] = file_path
            logging.info("ac updated in popup")
    
    def edit_title(self, text):
        self.data["title"] = text
    
    def edit_artist(self, text):
        self.data["artist"] = text
    
    def edit_album(self, text):
        self.data["album"] = text
    
    def edit_date(self, text):
        self.data["date"] = text
    
    def edit_tracknumber(self, text):
        try:
            self.data["tracknumber"] = int(text) if text else 0
        except ValueError:
            self.data["tracknumber"] = 0
    
    def edit_totaltracks(self, text):
        try:
            self.data["totaltracks"] = int(text) if text else 0
        except ValueError:
            self.data["totaltracks"] = 0
    
    def edit_discnumber(self, text):
        try:
            self.data["discnumber"] = int(text) if text else 0
        except ValueError:
            self.data["discnumber"] = 0

    def edit_copyright(self, text):
        self.data["copyright"] = text
    
    def save(self):
        global loaded_audio
        loaded_audio.audio.delete() # Clear all tags

        if self.data["title"]:
            loaded_audio.audio["©nam"] = [self.data["title"]]
        if self.data["artist"]:
            loaded_audio.audio["©ART"] = [self.data["artist"]]
        if self.data["album"]:
            loaded_audio.audio["©alb"] = [self.data["album"]]
        if self.data["date"]:
            loaded_audio.audio["©day"] = [self.data["date"]]
        if self.data["copyright"]:
            loaded_audio.audio["cprt"] = [self.data["copyright"]]
        
        # Handle track number and total tracks
        if self.data["tracknumber"] or self.data["totaltracks"]:
            track_num = self.data["tracknumber"] or 0
            total_tracks = self.data["totaltracks"] or 0
            loaded_audio.audio["trkn"] = [(track_num, total_tracks)]
        
        # Handle disc number
        if self.data["discnumber"]:
            loaded_audio.audio["disk"] = [(self.data["discnumber"], 0)]
        
        if self.data["cover"]:
            if isinstance(self.data["cover"], str):
                with open(self.data["cover"], "rb") as img_file:
                    img_data = img_file.read()
                    loaded_audio.audio["covr"] = [img_data]
            else:
                loaded_audio.audio["covr"] = [self.data["cover"]]
        
        loaded_audio.audio.save()
        logging.info("Metadata saved.")
        self.close()

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

        logging.debug(f"{self.queue=}")

        self.update_pretty_queue()
    

    def _set_cover_art(self, cover_art):
        # This function will set the album cover from the cover art data in the metadata
        pixmap = QPixmap()
        try:
            pixmap.loadFromData(cover_art.data)
        except Exception as e:
            logging.warning(e)
            logging.warning("Failed to load album cover from data, trying fallback method.")
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
            logging.info("Queue shuffled.")
        else:
            logging.info("No songs in the queue to shuffle.")
    
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
        logging.debug(f"Fetching album cover from Deezer API with url: {url}")
        response = requests.get(url)
        if response.status_code == 200:
            try:
                data = response.json()['data'][0]
                ac_link = data['album']['cover_xl'] if data['album'] else None

                # Double check if the album name matches, since the search is not always accurate
                if data['album'] and album_name.lower() not in data['album']['title'].lower():
                    logging.info("Album name does not match, skipping album cover")
                    ac_link = None
            except Exception as e:
                logging.warning(e)
                ac_link = None
        else:
            logging.warning("Error fetching album cover from Deezer API")

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
            logging.error("Error fetching album cover from CatPlay API")
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
        try:
            RPC.update(
                activity_type=ActivityType.LISTENING,
                status_display_type=StatusDisplayType.DETAILS,
                details=track_title,
                state=f"by {artist}",
                start=start_time,
                end=end_time,
                large_image=link or "logo", # Fallback to default logo if no cover art is found
                small_image="logo" if link else None,
                large_text=album_name if link else "CatPlay",
                small_text="CatPlay" if link else None 
            )
        except AssertionError:
            logging.info("Discord Not Connected")

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
        
        logging.info("Image loaded.")

    def load_metadata_from_path(self, file_path: str):
        global loaded_audio
        logging.info(f"Loading metadata from: {file_path}")
        if file_path:
            loaded_audio = load_metadata(file_path)
            self.info_label.setText(f"Title: {loaded_audio.title}\nArtist: {loaded_audio.artist}\nAlbum: {loaded_audio.album}")
            if loaded_audio.cover:
                self._set_cover_art(loaded_audio.cover)
            else:
                logging.info("No cover art found in metadata.")

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
            logging.info("Playing song...")
        else:
            logging.info("No audio file loaded.")

    def stop_song(self):
        if self.is_playing:
            self.player.stop()
            self.is_playing = False
            self.is_paused = False
            logging.info("Stopping song...")
        else:
            logging.info("No song is currently playing.")

    def toggle_pause(self):
        if self.is_playing:
            if self.is_paused:
                self.player.play()
                self.is_paused = False
                logging.info("Resuming song...")
            else:
                self.player.pause()
                self.is_paused = True
                logging.info("Pausing song...")
        else:
            logging.info("No song is currently playing.")

    def load_folder(self):
        # Dialog to select a folder
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.FileMode.Directory)
        folder_path = folder_dialog.getExistingDirectory(self, "Select Music Folder")
        if folder_path:
            logging.info(f"Selected folder: {folder_path}")
            audio_paths: list[Path] = []
            for ext in ("*.mp3", "*.flac", "*.wav", "*.m4a"):
                audio_paths.extend(Path(folder_path).glob(ext))

            audio_files = [str(path) for path in audio_paths]

            # if audio_files[0][0] == "0":
            #     # Songs are ordered with numbers
            #     audio_files.sort() # Sort files alphabetically

            # If not, just pray it's in order

            logging.info(audio_files)

        self.queue = audio_files 
        
        # Load first track
        if audio_files:
            first_track = audio_files[0]
            logging.info(f"Loading first track: {first_track}")
            self.load_metadata_from_path(first_track)
    
        self.update_pretty_queue()

    def next_song(self):
        global loaded_audio
        if self.queue:
            current_index = self.queue.index(loaded_audio.filename) if loaded_audio else -1
            next_index = (current_index + 1) % len(self.queue)
            next_track = self.queue[next_index]
            logging.info(f"Loading next track: {next_track}")
            self.load_metadata_from_path(next_track)
            self.play_song()
            self.update_pretty_queue()
        else:
            logging.info("No songs in the queue.")
    
    def previous_song(self):
        global loaded_audio
        if self.queue:
            current_index = self.queue.index(loaded_audio.filename) if loaded_audio else -1
            prev_index = (current_index - 1) % len(self.queue)
            prev_track = self.queue[prev_index]
            logging.info(f"Loading previous track: {prev_track}")
            self.load_metadata_from_path(prev_track)
            self.play_song()
            self.update_pretty_queue()
        else:
            logging.info("No songs in the queue.")

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
            logging.info("No audio loaded.")
            return
        
        if isinstance(loaded_audio.audio, MP3) or isinstance(loaded_audio.audio, WAVE):
            logging.info("mp3 popup")
            popup = MetadataPopupMP3()
        elif isinstance(loaded_audio.audio, FLAC):
            logging.info("flac popup")
            popup = MetadataPopupFLAC()
        elif isinstance(loaded_audio.audio, MP4):
            logging.info("m4a popup")
            popup = MetadataPopupM4A()
        elif isinstance(loaded_audio.audio, WAVE):
            logging.info("wav popup")
            pass
        else:
            logging.info("Unsupported audio format for metadata editing.")
            logging.info(f"Loaded audio type: {type(loaded_audio.audio)}")
            return
        popup.exec()

        load_metadata.cache_clear()
        self.load_metadata_from_path(loaded_audio.filename)

def main():
    global loading_start_time
    
    app = QApplication(sys.argv)
    window = MainWindow()
    loading_end_time = time.time()
    logging.info(f"Loaded app {loading_end_time - loading_start_time:.2f} seconds.")
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

