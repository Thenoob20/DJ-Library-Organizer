#!/usr/bin/env python3
"""
DJ Library Organizer - Safe Migration Engine
Author: Jdiaz Design workflow

Purpose:
- Scan your old Apple Music/iTunes media folder
- Copy music into a clean DJ_MUSIC folder structure
- Auto-detect genre/category using tags, paths, filenames, and keywords
- Detect duplicates by file hash
- Clean filenames safely
- Detect versions: Clean, Dirty, Intro, Outro, Acapella, Instrumental, Extended
- Generate CSV reports
- Create M3U playlists that Serato and VirtualDJ can import

IMPORTANT:
- Default mode is COPY ONLY.
- It does NOT delete originals.
- It does NOT overwrite files.
- It does NOT modify metadata by default.

Recommended workflow:
1. Run this script in dry-run mode first.
2. Review CSV reports.
3. Run copy mode.
4. Use One Tagger after migration for deeper metadata tagging.

Install:
    pip3 install mutagen

Run dry scan:
    python3 dj_library_organizer_full.py --dry-run

Run real copy:
    python3 dj_library_organizer_full.py --copy

Optional: only process one genre/category:
    python3 dj_library_organizer_full.py --copy --only Hip-Hop
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("Missing dependency: mutagen")
    print("Install it with: pip3 install mutagen")
    sys.exit(1)

# ==========================================================
# USER CONFIG
# ==========================================================

SOURCE_ROOT = Path("/Users/UserName/DJ_MUSIC")
DEST_ROOT = Path("/Users/Usernaem/DJ_MUSIC_2")

REPORT_DIR = DEST_ROOT / "_Reports"
PLAYLIST_DIR = DEST_ROOT / "_Playlists"
STATE_DIR = DEST_ROOT / "_State"
DUPLICATE_DIR = DEST_ROOT / "Duplicate"
UNSORTED_DIR = DEST_ROOT / "Uncategorized"
VIDEO_DIR = DEST_ROOT / "Videos"
LOW_QUALITY_DIR = DEST_ROOT / "_Review_Low_Quality"
CORRUPTED_DIR = DEST_ROOT / "_Review_Corrupted"
MISSING_TAGS_DIR = DEST_ROOT / "_Review_Missing_Tags"
SIDECAR_DIR = DEST_ROOT / "_OneTagger_Import"

AUDIO_EXTS = {
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".aiff", ".aif", ".ogg"
}

VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".m4v"
}

# Best hybrid DJ folder system:
# Physical folders stay minimal. Performance/vibe organization should happen with comments, tags, Serato Smart Crates, and VDJ filters.
STANDARD_SUBFOLDERS = [
    "Clean",
    "Dirty",
    "Intro Edits",
    "Acapellas",
    "Instrumentals",
]

# Keep this simple. One Tagger can do deeper genre intelligence later.
GENRE_KEYWORDS: Dict[str, List[str]] = {
    "Acid": [
        "acid", "acid house", "acid techno", "acid tech", "303", "tb-303", "acid line", "acid bass"
    ],
    "Afro House": [
        "afro house", "afro-house", "afrohouse", "afro tech", "afrobeat", "afrobeats",
        "amapiano", "black coffee", "major league djz", "uncle waffles", "burna boy", "tems", "wizkid"
    ],
    "Alternative Music": [
        "alternative", "alternative music", "alt rock", "indie", "indie rock", "indie pop",
        "alanteative", "alanteative music"
    ],
    "Bachata": ["bachata", "romeo santos", "aventura", "prince royce", "xreme"],
    "Baladas": ["balada", "baladas", "latin ballad", "baladas romanticas"],
    "Big Room": ["big room", "bigroom", "mainstage", "festival edm", "hardwell", "w&w"],
    "Blends": ["blend", "blends", "blend edit", "transition blend"],
    "Bootleg": ["bootleg", "bootlegs", "unofficial remix"],
    "Classic Rock": [
        "classic rock", "led zeppelin", "queen", "acdc", "ac/dc", "aerosmith", "rolling stones",
        "journey", "eagles", "guns n roses"
    ],
    "Classical": ["classical", "orchestra", "symphony", "mozart", "beethoven", "bach"],
    "Club": ["club", "club mix", "club edit", "club banger", "club anthem"],
    "Corridos": ["corrido", "corridos", "corridos tumbados", "peso pluma", "natanael cano", "junior h"],
    "Country": ["country", "country music", "luke combs", "morgan wallen", "zach bryan"],
    "Cumbia": ["cumbia", "cumbias", "cumbia sonidera", "cumbia villera"],
    "Dance": ["dance", "dance music", "dance pop", "dance-pop"],
    "Dancehall": [
        "dancehall", "dance hall", "vybz", "popcaan", "sean paul", "beenie man", "shenseea",
        "spice", "alkaline", "mavado", "konshens", "ding dong"
    ],
    "Deep House": ["deep house", "deephouse", "deep-house", "kerri chandler", "maya jane coles"],
    "Dembow": ["dembow", "dembow dominicano", "el alfa", "rochy rd", "bulin 47"],
    "Dirty Dutch": ["dirty dutch", "dirt dutch", "dutch house", "chuckie", "afrojack"],
    "Disco": ["disco", "70s disco", "bee gees", "chic", "donna summer"],
    "Drum and Bass": ["drum and bass", "drum & bass", "dnb", "d&b", "jungle"],
    "Dubstep": ["dubstep", "brostep", "skrillex", "excision", "zeds dead"],
    "Duranguense": ["duranguense", "durangence", "duranguense mix"],
    "Dutch": ["dutch", "dutch house", "dirty dutch"],
    "EDM": [
        "edm", "electronic dance music", "festival", "mainstage", "martin garrix", "tiesto",
        "zedd", "calvin harris", "david guetta", "avicii", "illenium"
    ],
    "Electronic": ["electronic", "electronica", "electro", "electro house", "synth", "synthwave"],
    "Eurodance": ["eurodance", "euro dance", "euro", "cascada", "alice deejay", "aqua"],
    "Funk": ["funk", "funky", "funk music", "james brown", "parliament", "zapp"],
    "Future Bass": ["future bass", "futurebass", "marshmello", "flume", "illenium"],
    "House": [
        "house", "house music", "vocal house", "classic house", "defected", "mk", "duke dumont",
        "disclosure", "purple disco machine"
    ],
    "Hip-Hop": [
        "hip-hop", "hip hop", "hiphop", "rap", "boom bap", "drake", "future", "kendrick",
        "j cole", "cole", "jay-z", "jay z", "kanye", "ye ", "travis scott", "21 savage",
        "migos", "lil ", "nicki", "cardi", "meek mill", "nas", "biggie", "notorious",
        "2pac", "tupac", "eminem", "asap", "a$ap", "metro boomin"
    ],
    "Instrumentals": ["instrumental", "instrumentall", "inst", "beat only", "beats"],
    "International": ["international", "world music", "global", "worldbeat"],
    "Jersey Club": ["jersey club", "jerseyclub", "baltimore club", "bmore club"],
    "Latin House": ["latin house", "latin-house", "tribal latin house"],
    "Mambo": ["mambo", "mambo urbano", "mambo mix"],
    "Marroneo": ["marroneo", "marroeno", "perreo intenso", "perreo sucio"],
    "Mash-Up": ["mashup", "mash-up", "mash up", "mashups"],
    "Merengue": ["merengue", "mérengue", "mambo merengue"],
    "Mixes": ["mix", "mixes", "mix’s", "megamix", "mini mix", "dj mix"],
    "Moombahton": ["moombahton", "moombah", "moomba", "dillon francis"],
    "Norteño": ["norteno", "norteño", "norton", "banda nortena", "grupo frontera"],
    "Nu Disco": ["nu disco", "nudisco", "nu-disco", "disco house"],
    "Perreo": ["perreo", "perreo intenso", "perreo sucio", "reggaeton perreo"],
    "Pop": [
        "pop", "pop music", "taylor swift", "dua lipa", "ariana grande", "justin bieber",
        "miley cyrus", "olivia rodrigo", "billie eilish", "sabrina carpenter"
    ],
    "Progressive": ["progressive", "progressive house", "prog house", "progressive trance"],
    "Punta": ["punta", "punta catracha", "punta hondurena", "punta hondureña"],
    "R&B": [
        "r&b", "rnb", "r b", "soul", "neo soul", "usher", "sza", "bryson tiller",
        "partynextdoor", "chris brown", "summer walker", "jhene", "mary j", "trey songz",
        "miguel", "the weeknd", "kehlani"
    ],
    "Ranchera": ["ranchera", "rancheras", "vicente fernandez", "alejandro fernandez"],
    "Reggae": ["reggae", "roots reggae", "bob marley", "damian marley", "chronixx"],
    "Reggaeton": [
        "reggaeton", "reggaetón", "bad bunny", "daddy yankee", "don omar", "wisin", "yandel",
        "nicky jam", "j balvin", "maluma", "ozuna", "anuel", "feid", "rauw alejandro",
        "myke towers", "arcangel", "de la ghetto"
    ],
    "Regional Mexicano": [
        "regional mexicano", "regional mexican", "banda", "corridos", "norteno", "norteño",
        "ranchera", "grupo frontera", "peso pluma", "fuerza regida"
    ],
    "Remix": ["remix", "remixes", "refix", "edit", "rework"],
    "Rock": [
        "rock", "punk", "alternative", "metal", "nirvana", "blink", "green day", "foo fighters",
        "linkin park", "fall out boy", "my chemical romance"
    ],
    "Rock en Español": [
        "rock en español", "rock en espanol", "mana", "caifanes", "soda stereo", "heroes del silencio",
        "enrique bunbury", "hombres g"
    ],
    "Romantico": ["romantico", "romántico", "romantica", "romántica", "romantic", "love songs"],
    "Salsa": ["salsa", "salsa romantica", "salsa dura", "marc anthony", "hector lavoe", "willie colon"],
    "Sandunga": ["sandunga", "sandunguero", "reggaeton sandunga"],
    "Soca": ["soca", "soca music", "machel montano", "kes", "destra"],
    "Soul": ["soul", "soul music", "motown", "marvin gaye", "al green", "stevie wonder"],
    "Tech House": [
        "tech house", "tech-house", "techhouse", "fisher", "chris lake", "john summit", "mau p",
        "green velvet", "dom dolla", "solardo"
    ],
    "Techno": ["techno", "detroit techno", "minimal techno", "hard techno", "charlotte de witte"],
    "Tech": ["tech", "tech music", "tech edit", "tech mix"],
    "Tex-Mex": ["tex mex", "tex-mex", "tejano", "texmex", "selena"],
    "Tipico": ["tipico", "típico", "perico ripiao", "merengue tipico"],
    "Top 40": ["top 40", "top40", "charts", "billboard", "radio hits", "mainstream"],
    "Trance": ["trance", "uplifting trance", "psytrance", "armin", "above & beyond"],
    "Transition": ["transition", "transition edit", "transition mix", "dj transition"],
    "Trap": ["trap", "trap music", "808", "metro boomin", "lex luger"],
    "Trap Latino": ["trap latino", "latin trap", "bad bunny", "anuel", "bryant myers", "almighty"],
    "Tribal": ["tribal", "tribal house", "tribal guarachero", "tribal latin"],
    "Twerk": ["twerk", "twerk music", "bounce", "new orleans bounce"],
    "Urban": ["urban", "urbano", "latin urban", "musica urbana", "música urbana"],
    "Videos": ["video", "mp4", "music video", "video edit", "vdj video", "video mp4"],
}


# Genre priority fixes crossover confusion.
# More specific DJ genres should win over broad genres like House, EDM, Dance, Pop, Urban, or Club.
GENRE_PRIORITY = [
    "Videos",

    # Specific electronic / DJ styles
    "Acid",
    "Afro House",
    "Latin House",
    "Deep House",
    "Tech House",
    "Techno",
    "Tech",
    "Trance",
    "Progressive",
    "Nu Disco",
    "Future Bass",
    "Drum and Bass",
    "Dubstep",
    "Big Room",
    "Dirty Dutch",
    "Moombahton",
    "Jersey Club",
    "Tribal",
    "Twerk",

    # Latin / Caribbean / Regional
    "Trap Latino",
    "Reggaeton",
    "Dembow",
    "Perreo",
    "Sandunga",
    "Soca",
    "Dancehall",
    "Reggae",
    "Bachata",
    "Salsa",
    "Merengue",
    "Mambo",
    "Punta",
    "Tipico",
    "Cumbia",
    "Regional Mexicano",
    "Corridos",
    "Ranchera",
    "Tex-Mex",
    "Duranguense",
    "Norteño",

    # Electronic broad styles
    "House",
    "EDM",
    "Electronic",
    "Dance",
    "Eurodance",
    "Club",

    # Urban / open format
    "Hip-Hop",
    "Trap",
    "R&B",
    "Soul",
    "Funk",
    "Urban",

    # Rock / Pop
    "Rock en Español",
    "Classic Rock",
    "Rock",
    "Alternative Music",
    "Pop",
    "Top 40",

    # DJ utility categories
    "Mash-Up",
    "Blends",
    "Transition",
    "Bootleg",
    "Remix",
    "Mixes",
    "Instrumentals",

    # Cultural / general
    "International",
    "Romantico",
    "Baladas",
    "Country",
    "Classical",

    "Uncategorized",
]

# Some folder/tag names should normalize into one clean canonical genre.
GENRE_ALIASES = {
    "Dance Hall": "Dancehall",
    "Alanteative Music": "Alternative Music",
    "Dirt Dutch": "Dirty Dutch",
    "Durangence": "Duranguense",
    "Instrumentall": "Instrumentals",
    "Marroeno": "Marroneo",
    "Mix’s": "Mixes",
    "Norton": "Norteño",
    "Tex mex": "Tex-Mex",
    "Video MP4 etc": "Videos",
    "Edm": "EDM",
}

GENRE_SCORE_THRESHOLD = 1

VERSION_KEYWORDS: Dict[str, List[str]] = {
    "Clean": ["clean", "radio edit", "radio", "censored"],
    "Dirty": ["dirty", "explicit", "uncensored"],
    "Intro": ["intro", "dj intro", "quick hit intro"],
    "Outro": ["outro", "dj outro"],
    "Extended": ["extended", "extended mix", "club mix", "long mix"],
    "Acapella": ["acapella", "a cappella", "pella"],
    "Instrumental": ["instrumental", "inst", "beat only"],
    "Remix": ["remix", "refix", "edit", "bootleg", "mashup"],
}

BAD_FILENAME_PATTERNS = [
    r"\bfree download\b",
    r"\bofficial audio\b",
    r"\bofficial video\b",
    r"\blyric video\b",
    r"\bwww\.[^\s]+",
    r"\bhttps?[^\s]+",
    r"\bconverted by[^\s]+",
    r"\byoutube\b",
    r"\bsoundcloud\b",
]

INVALID_FILENAME_CHARS = r'<>:"/\|?*'
MAX_FILENAME_LENGTH = 165
LOW_BITRATE_LIMIT = 192_000
REVIEW_BITRATE_LIMIT = 256_000

# ==========================================================
# DATA MODEL
# ==========================================================

@dataclass
class TrackInfo:
    source_path: Path
    ext: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre_tag: str = ""
    comment: str = ""
    duration: Optional[float] = None
    bitrate: Optional[int] = None
    detected_genre: str = "Uncategorized"
    detected_versions: List[str] = field(default_factory=list)
    hash_md5: str = ""
    destination_path: Optional[Path] = None
    status: str = "PENDING"
    notes: str = ""
    quality_flag: str = ""
    review_flags: List[str] = field(default_factory=list)
    suggested_comment: str = ""

# ==========================================================
# UTILITIES
# ==========================================================

def ensure_dirs() -> None:
    folders = [
        REPORT_DIR,
        PLAYLIST_DIR,
        DUPLICATE_DIR,
        UNSORTED_DIR,
        VIDEO_DIR,
        LOW_QUALITY_DIR,
        CORRUPTED_DIR,
        MISSING_TAGS_DIR,
        SIDECAR_DIR,
        STATE_DIR,
    ]

    for genre in GENRE_KEYWORDS.keys():
        genre_root = DEST_ROOT / genre
        folders.append(genre_root)
        for subfolder in STANDARD_SUBFOLDERS:
            folders.append(genre_root / subfolder)

    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    cleaned = (name or "").strip()

    for pattern in BAD_FILENAME_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Remove leading track numbers like 01 -, 001_, 12.
    cleaned = re.sub(r"^\s*\d{1,3}\s*[-_.]\s*", "", cleaned)

    # Normalize separators
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+-\s+", " - ", cleaned)

    for ch in INVALID_FILENAME_CHARS:
        cleaned = cleaned.replace(ch, "")

    cleaned = cleaned.strip(" .-_")

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .-_")

    return cleaned or "Unknown Track"


def title_case_safely(text: str) -> str:
    if not text:
        return text
    # Avoid ruining all-caps known abbreviations too aggressively.
    words = text.split()
    fixed = []
    for word in words:
        if word.upper() in {"DJ", "R&B", "EDM", "DMV", "NYC", "LA"}:
            fixed.append(word.upper())
        elif word.isupper() and len(word) <= 4:
            fixed.append(word)
        else:
            fixed.append(word[:1].upper() + word[1:].lower())
    return " ".join(fixed)


def file_md5(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def safe_unique_path(path: Path) -> Path:
    max_stem_length = MAX_FILENAME_LENGTH - len(path.suffix)

    if len(path.name) > MAX_FILENAME_LENGTH:
        path = path.with_name(f"{path.stem[:max_stem_length].rstrip(' .-_')}{path.suffix}")

    try:
        if not path.exists():
            return path
    except OSError:
        path = path.with_name(f"{path.stem[:max_stem_length].rstrip(' .-_')}{path.suffix}")
        if not path.exists():
            return path

    counter = 1
    while True:
        suffix_text = f" ({counter})"
        shortened_stem = path.stem[: max_stem_length - len(suffix_text)].rstrip(" .-_")
        candidate = path.with_name(f"{shortened_stem}{suffix_text}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def get_tag_value(tags, possible_keys: List[str]) -> str:
    if not tags:
        return ""
    for key in possible_keys:
        try:
            value = tags.get(key)
        except Exception:
            value = None
        if value:
            if isinstance(value, list):
                return "; ".join(str(v) for v in value)
            return str(value)
    return ""


def read_track_info(path: Path) -> TrackInfo:
    info = TrackInfo(source_path=path, ext=path.suffix.lower())

    try:
        audio = MutagenFile(path, easy=True)
        if audio:
            info.title = get_tag_value(audio.tags, ["title"])
            info.artist = get_tag_value(audio.tags, ["artist", "albumartist"])
            info.album = get_tag_value(audio.tags, ["album"])
            info.genre_tag = get_tag_value(audio.tags, ["genre"])
            info.comment = get_tag_value(audio.tags, ["comment", "description"])

            if getattr(audio, "info", None):
                info.duration = getattr(audio.info, "length", None)
                info.bitrate = getattr(audio.info, "bitrate", None)
    except Exception as e:
        info.notes += f"Tag read error: {e}; "

    return info


def combined_search_text(info: TrackInfo) -> str:
    parts = [
        str(info.source_path),
        info.source_path.stem,
        info.title,
        info.artist,
        info.album,
        info.genre_tag,
        info.comment,
    ]
    return " ".join(p for p in parts if p).lower()


def normalize_genre_name(genre: str) -> str:
    if not genre:
        return "Uncategorized"
    cleaned = genre.strip()
    return GENRE_ALIASES.get(cleaned, cleaned)


def score_keyword_match(keyword: str, text: str, genre_tag: str, title: str, artist: str, album: str, path_text: str) -> int:
    """Weighted scoring so true genre tags beat artist names and broad path noise."""
    keyword = keyword.lower().strip()
    if not keyword:
        return 0

    score = 0
    if keyword in genre_tag:
        score += 10
    if keyword in title:
        score += 4
    if keyword in album:
        score += 3
    if keyword in path_text:
        score += 2
    if keyword in artist:
        score += 1
    if keyword in text:
        score += 1
    return score


def detect_genre(info: TrackInfo) -> str:
    # Videos route first by extension.
    if info.ext in VIDEO_EXTS:
        return "Videos"

    genre_tag = (info.genre_tag or "").lower()
    title = (info.title or "").lower()
    artist = (info.artist or "").lower()
    album = (info.album or "").lower()
    path_text = str(info.source_path).lower()
    text = combined_search_text(info)

    scores: Dict[str, int] = {}

    for genre, keywords in GENRE_KEYWORDS.items():
        canonical_genre = normalize_genre_name(genre)
        total = 0
        for kw in keywords:
            total += score_keyword_match(kw, text, genre_tag, title, artist, album, path_text)
        if total >= GENRE_SCORE_THRESHOLD:
            scores[canonical_genre] = max(scores.get(canonical_genre, 0), total)

    if not scores:
        return "Uncategorized"

    # Priority bonus: specific genres beat broad genres when scores are close.
    priority_rank = {genre: index for index, genre in enumerate(GENRE_PRIORITY)}

    def sort_key(item):
        genre, score = item
        rank = priority_rank.get(genre, len(GENRE_PRIORITY))
        return (-score, rank)

    winner = sorted(scores.items(), key=sort_key)[0][0]

    # If a broad genre and a specific genre are tied/close, priority decides.
    top_score = scores[winner]
    close_matches = [g for g, s in scores.items() if top_score - s <= 2]
    if len(close_matches) > 1:
        winner = sorted(close_matches, key=lambda g: priority_rank.get(g, len(GENRE_PRIORITY)))[0]

    return winner


def detect_versions(info: TrackInfo) -> List[str]:
    text = combined_search_text(info)
    versions = []
    for label, keywords in VERSION_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            versions.append(label)
    return versions


def detect_quality(info: TrackInfo) -> str:
    if info.ext in {".wav", ".aiff", ".aif", ".flac"}:
        return "LOSSLESS_OR_HIGH"
    if not info.bitrate:
        return "UNKNOWN_BITRATE"
    if info.bitrate < LOW_BITRATE_LIMIT:
        return "LOW_BITRATE_REVIEW"
    if info.bitrate < REVIEW_BITRATE_LIMIT:
        return "OK_BUT_REVIEW"
    return "GOOD"


def detect_review_flags(info: TrackInfo) -> List[str]:
    flags = []

    try:
        if info.source_path.stat().st_size == 0:
            flags.append("ZERO_BYTE_FILE")
    except Exception:
        flags.append("FILE_STAT_ERROR")

    if not info.artist or info.artist.strip() == "":
        flags.append("MISSING_ARTIST")
    if not info.title or info.title.strip() == "":
        flags.append("MISSING_TITLE")
    if not info.genre_tag or info.genre_tag.strip() == "":
        flags.append("MISSING_GENRE_TAG")
    if info.duration is not None and info.duration < 30:
        flags.append("VERY_SHORT_TRACK_REVIEW")
    if info.duration is None:
        flags.append("UNKNOWN_DURATION")
    if info.quality_flag in {"LOW_BITRATE_REVIEW", "UNKNOWN_BITRATE"}:
        flags.append(info.quality_flag)
    if "Tag read error" in info.notes:
        flags.append("TAG_READ_ERROR")

    return flags


def build_suggested_comment(info: TrackInfo) -> str:
    parts = []

    for version in info.detected_versions:
        parts.append(version)

    if info.detected_genre and info.detected_genre not in {"Uncategorized", "Videos"}:
        parts.append(info.detected_genre)

    if info.quality_flag in {"LOW_BITRATE_REVIEW", "OK_BUT_REVIEW", "UNKNOWN_BITRATE"}:
        parts.append(info.quality_flag)

    # Placeholder for future BPM/key/energy analyzer.
    # Example future format: BPM:124 | KEY:8A | ENERGY:Peak
    return " | ".join(dict.fromkeys(parts))


def build_clean_filename(info: TrackInfo) -> str:
    artist = sanitize_filename(info.artist, max_length=55)
    title = sanitize_filename(info.title, max_length=75)

    # Fallback to current filename if tags are bad.
    if not artist or artist == "Unknown Track" or not title or title == "Unknown Track":
        base = sanitize_filename(info.source_path.stem, max_length=130)
    else:
        artist = title_case_safely(artist)
        title = title_case_safely(title)
        base = f"{artist} - {title}"

    # Add version tags if they are not already obvious.
    version_text = " ".join(info.detected_versions)
    if version_text:
        existing_lower = base.lower()
        missing = [v for v in info.detected_versions if v.lower() not in existing_lower]
        if missing:
            base += " (" + " ".join(missing) + ")"

    base = sanitize_filename(base, max_length=MAX_FILENAME_LENGTH - len(info.ext))
    return f"{base}{info.ext}"


def choose_subfolder(info: TrackInfo) -> Path:
    genre = info.detected_genre

    if genre == "Videos":
        return VIDEO_DIR

    if genre == "Uncategorized":
        return UNSORTED_DIR

    if "ZERO_BYTE_FILE" in info.review_flags or "TAG_READ_ERROR" in info.review_flags:
        return CORRUPTED_DIR / genre

    if "MISSING_ARTIST" in info.review_flags or "MISSING_TITLE" in info.review_flags or "MISSING_GENRE_TAG" in info.review_flags:
        return MISSING_TAGS_DIR / genre

    if info.quality_flag == "LOW_BITRATE_REVIEW":
        return LOW_QUALITY_DIR / genre

    base = DEST_ROOT / genre
    versions = set(info.detected_versions)

    if "Acapella" in versions:
        return base / "Acapellas"
    if "Instrumental" in versions:
        return base / "Instrumentals"
    if "Intro" in versions:
        return base / "Intro Edits"
    if "Clean" in versions:
        return base / "Clean"
    if "Dirty" in versions:
        return base / "Dirty"

    return base


def scan_source() -> List[Path]:
    files = []
    for path in SOURCE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in AUDIO_EXTS or ext in VIDEO_EXTS:
            files.append(path)
    return files


def write_report(rows: List[TrackInfo], filename: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / filename

    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Status",
            "Detected Genre",
            "Versions",
            "Quality Flag",
            "Review Flags",
            "Suggested Comment",
            "Artist",
            "Title",
            "Genre Tag",
            "Bitrate",
            "Duration",
            "Source Path",
            "Destination Path",
            "Hash",
            "Notes",
        ])
        for info in rows:
            writer.writerow([
                info.status,
                info.detected_genre,
                " | ".join(info.detected_versions),
                info.quality_flag,
                " | ".join(info.review_flags),
                info.suggested_comment,
                info.artist,
                info.title,
                info.genre_tag,
                info.bitrate or "",
                round(info.duration, 2) if info.duration else "",
                str(info.source_path),
                str(info.destination_path or ""),
                info.hash_md5,
                info.notes,
            ])

    return report_path


def make_job_name(mode: str, only_genre: Optional[str]) -> str:
    genre_part = (only_genre or "ALL").replace("/", "-").replace(" ", "_")
    return f"{mode}_{genre_part}"


def load_processed_state(job_name: str) -> Set[str]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"{job_name}_processed.txt"
    if not state_file.exists():
        return set()
    with state_file.open("r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_processed_state(job_name: str, source_path: Path) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"{job_name}_processed.txt"
    with state_file.open("a", encoding="utf-8") as f:
        f.write(str(source_path) + "\n")


def write_onetagger_sidecar(rows: List[TrackInfo], filename: str) -> Path:
    SIDECAR_DIR.mkdir(parents=True, exist_ok=True)
    sidecar_path = SIDECAR_DIR / filename
    with sidecar_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "File Path",
            "Detected Genre",
            "Suggested Comment",
            "Versions",
            "Quality Flag",
            "Review Flags",
        ])
        for info in rows:
            target = info.destination_path if info.destination_path else info.source_path
            writer.writerow([
                str(target),
                info.detected_genre,
                info.suggested_comment,
                " | ".join(info.detected_versions),
                info.quality_flag,
                " | ".join(info.review_flags),
            ])
    return sidecar_path


def write_m3u_playlists(rows: List[TrackInfo]) -> List[Path]:
    PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)
    by_genre: Dict[str, List[Path]] = {}

    for info in rows:
        if info.status not in {"COPIED", "MOVED"} or not info.destination_path:
            continue
        by_genre.setdefault(info.detected_genre, []).append(info.destination_path)

    created = []
    for genre, paths in by_genre.items():
        playlist_path = PLAYLIST_DIR / f"{genre}.m3u"
        with playlist_path.open("w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for p in sorted(paths):
                f.write(str(p) + "\n")
        created.append(playlist_path)

    return created


def audit_library(limit: Optional[int] = None) -> None:
    ensure_dirs()

    print("DJ Library Genre Audit")
    print(f"Source: {SOURCE_ROOT}")
    print(f"Reports: {REPORT_DIR}")

    source_files = scan_source()
    if limit:
        source_files = source_files[:limit]

    print(f"Found {len(source_files)} audio/video files.")

    summary: Dict[str, Dict[str, int]] = {}
    processed_rows: List[TrackInfo] = []
    seen_hashes: Set[str] = set()
    started = time.time()

    for index, path in enumerate(source_files, start=1):
        info = read_track_info(path)
        info.detected_genre = detect_genre(info)
        info.detected_versions = detect_versions(info)
        info.quality_flag = detect_quality(info)
        info.review_flags = detect_review_flags(info)
        info.suggested_comment = build_suggested_comment(info)

        try:
            info.hash_md5 = file_md5(path)
        except Exception as e:
            info.status = "ERROR_HASH"
            info.notes += str(e)

        genre = info.detected_genre or "Uncategorized"
        if genre not in summary:
            summary[genre] = {
                "Total": 0,
                "Low Bitrate": 0,
                "Unknown Bitrate": 0,
                "Missing Tags": 0,
                "Corrupted/Tag Errors": 0,
                "Duplicates": 0,
                "Videos": 0,
            }

        summary[genre]["Total"] += 1

        if info.quality_flag == "LOW_BITRATE_REVIEW":
            summary[genre]["Low Bitrate"] += 1
        if info.quality_flag == "UNKNOWN_BITRATE":
            summary[genre]["Unknown Bitrate"] += 1
        if any(flag.startswith("MISSING_") for flag in info.review_flags):
            summary[genre]["Missing Tags"] += 1
        if "ZERO_BYTE_FILE" in info.review_flags or "TAG_READ_ERROR" in info.review_flags:
            summary[genre]["Corrupted/Tag Errors"] += 1
        if info.ext in VIDEO_EXTS:
            summary[genre]["Videos"] += 1

        if info.hash_md5:
            if info.hash_md5 in seen_hashes:
                summary[genre]["Duplicates"] += 1
                info.status = "DUPLICATE_FOUND"
            else:
                seen_hashes.add(info.hash_md5)
                info.status = "AUDITED"
        else:
            info.status = info.status or "AUDITED"

        processed_rows.append(info)

        if index % 500 == 0:
            elapsed = max(time.time() - started, 1)
            rate = index / elapsed
            remaining_files = max(len(source_files) - index, 0)
            eta_seconds = int(remaining_files / rate) if rate else 0
            print(f"Audited {index}/{len(source_files)} files | {rate:.1f} files/sec | ETA {eta_seconds // 60}m {eta_seconds % 60}s")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = REPORT_DIR / f"library_genre_audit_summary_{timestamp}.csv"
    detail_path = REPORT_DIR / f"library_genre_audit_details_{timestamp}.csv"

    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Detected Genre",
            "Total Tracks",
            "Low Bitrate",
            "Unknown Bitrate",
            "Missing Tags",
            "Corrupted/Tag Errors",
            "Duplicates",
            "Videos",
        ])
        for genre, counts in sorted(summary.items(), key=lambda item: item[1]["Total"], reverse=True):
            writer.writerow([
                genre,
                counts["Total"],
                counts["Low Bitrate"],
                counts["Unknown Bitrate"],
                counts["Missing Tags"],
                counts["Corrupted/Tag Errors"],
                counts["Duplicates"],
                counts["Videos"],
            ])

    write_report(processed_rows, detail_path.name)

    print("Audit complete.")
    print(f"Summary CSV: {summary_path}")
    print(f"Detail CSV: {detail_path}")


def get_current_top_folder(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
        return rel.parts[0] if rel.parts else ""
    except Exception:
        return ""


def clean_audit_library(limit: Optional[int] = None) -> None:
    """Audit the already-organized DJ_MUSIC library and suggest cleanup moves.

    This does NOT move files. It only creates CSV reports showing:
    - current folder
    - detected genre
    - current path
    - suggested path
    - review reason
    """
    ensure_dirs()

    print("DJ Library Clean Audit")
    print(f"Library scanned: {DEST_ROOT}")
    print(f"Reports: {REPORT_DIR}")

    # Clean mode scans the organized destination library, not the old Apple Music source.
    source_files = []
    for path in DEST_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith("_Reports") or part.startswith("_State") or part.startswith("_Playlists") or part.startswith("_OneTagger_Import") for part in path.parts):
            continue
        if path.suffix.lower() in AUDIO_EXTS or path.suffix.lower() in VIDEO_EXTS:
            source_files.append(path)

    if limit:
        source_files = source_files[:limit]

    print(f"Found {len(source_files)} audio/video files in DJ_MUSIC.")

    rows = []
    started = time.time()

    for index, path in enumerate(source_files, start=1):
        info = read_track_info(path)
        info.detected_genre = detect_genre(info)
        info.detected_versions = detect_versions(info)
        info.quality_flag = detect_quality(info)
        info.review_flags = detect_review_flags(info)
        info.suggested_comment = build_suggested_comment(info)

        current_top = get_current_top_folder(path, DEST_ROOT)
        suggested_folder = choose_subfolder(info)
        suggested_name = build_clean_filename(info)
        suggested_path = safe_unique_path(suggested_folder / suggested_name)

        reasons = []
        if current_top != info.detected_genre and info.detected_genre not in {"Uncategorized", "Videos"}:
            reasons.append("POSSIBLE_WRONG_GENRE_FOLDER")
        if info.detected_genre == "Uncategorized":
            reasons.append("UNCATEGORIZED_REVIEW")
        if info.quality_flag == "LOW_BITRATE_REVIEW":
            reasons.append("LOW_BITRATE_REVIEW")
        if any(flag.startswith("MISSING_") for flag in info.review_flags):
            reasons.append("MISSING_TAGS_REVIEW")
        if "TAG_READ_ERROR" in info.review_flags or "ZERO_BYTE_FILE" in info.review_flags:
            reasons.append("CORRUPTED_OR_TAG_ERROR_REVIEW")
        if path.parent != suggested_folder:
            reasons.append("SUBFOLDER_MISMATCH")
        if path.name != suggested_name:
            reasons.append("FILENAME_FORMAT_REVIEW")

        status = "OK" if not reasons else "REVIEW"

        rows.append([
            status,
            " | ".join(dict.fromkeys(reasons)),
            current_top,
            info.detected_genre,
            " | ".join(info.detected_versions),
            info.quality_flag,
            " | ".join(info.review_flags),
            info.suggested_comment,
            str(path),
            str(suggested_path),
            info.artist,
            info.title,
            info.genre_tag,
            info.bitrate or "",
            round(info.duration, 2) if info.duration else "",
        ])

        if index % 500 == 0:
            elapsed = max(time.time() - started, 1)
            rate = index / elapsed
            remaining_files = max(len(source_files) - index, 0)
            eta_seconds = int(remaining_files / rate) if rate else 0
            print(f"Clean-audited {index}/{len(source_files)} files | {rate:.1f} files/sec | ETA {eta_seconds // 60}m {eta_seconds % 60}s")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_report = REPORT_DIR / f"clean_audit_{timestamp}.csv"

    with clean_report.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Status",
            "Reasons",
            "Current Top Folder",
            "Detected Genre",
            "Versions",
            "Quality Flag",
            "Review Flags",
            "Suggested Comment",
            "Current Path",
            "Suggested Path",
            "Artist",
            "Title",
            "Genre Tag",
            "Bitrate",
            "Duration",
        ])
        writer.writerows(rows)

    total_review = sum(1 for row in rows if row[0] == "REVIEW")
    total_ok = sum(1 for row in rows if row[0] == "OK")

    print("Clean audit complete.")
    print(f"Clean audit CSV: {clean_report}")
    print(f"OK: {total_ok}")
    print(f"Review needed: {total_review}")
    print("No files were moved. Review the CSV before making cleanup changes.")


def process_library(dry_run: bool, copy_mode: bool, move_mode: bool, resume_mode: bool, reset_resume: bool, only_genre: Optional[str] = None, limit: Optional[int] = None) -> None:
    ensure_dirs()

    print("DJ Library Organizer")
    print(f"Source: {SOURCE_ROOT}")
    print(f"Destination: {DEST_ROOT}")
    mode_name = 'DRY_RUN' if dry_run else 'MOVE' if move_mode else 'COPY' if copy_mode else 'SCAN_ONLY'
    print(f"Mode: {mode_name}")

    job_name = make_job_name(mode_name, only_genre)
    state_file = STATE_DIR / f"{job_name}_processed.txt"
    if reset_resume and state_file.exists():
        state_file.unlink()
        print(f"Reset resume state: {state_file}")

    processed_state = load_processed_state(job_name) if resume_mode else set()
    if resume_mode:
        print(f"Resume mode ON. Already processed in this job: {len(processed_state)}")
    if only_genre:
        print(f"Only genre/category: {only_genre}")

    source_files = scan_source()
    if limit:
        source_files = source_files[:limit]

    print(f"Found {len(source_files)} audio/video files.")

    seen_hashes: Set[str] = set()
    processed: List[TrackInfo] = []
    started = time.time()

    for index, path in enumerate(source_files, start=1):
        if resume_mode and str(path) in processed_state:
            continue

        info = read_track_info(path)
        info.detected_genre = detect_genre(info)
        info.detected_versions = detect_versions(info)
        info.quality_flag = detect_quality(info)
        info.review_flags = detect_review_flags(info)
        info.suggested_comment = build_suggested_comment(info)

        if only_genre and info.detected_genre.lower() != only_genre.lower():
            continue

        try:
            info.hash_md5 = file_md5(path)
        except Exception as e:
            info.status = "ERROR_HASH"
            info.notes += str(e)
            processed.append(info)
            continue

        if info.hash_md5 in seen_hashes:
            info.status = "DUPLICATE_SKIPPED"
            info.destination_path = DUPLICATE_DIR / path.name
            processed.append(info)
            continue

        seen_hashes.add(info.hash_md5)

        clean_name = build_clean_filename(info)
        dest_folder = choose_subfolder(info)
        destination = safe_unique_path(dest_folder / clean_name)
        info.destination_path = destination

        if dry_run or not (copy_mode or move_mode):
            info.status = "WOULD_MOVE" if move_mode else "WOULD_COPY"
        else:
            try:
                dest_folder.mkdir(parents=True, exist_ok=True)
                if move_mode:
                    shutil.move(str(path), str(destination))
                    info.status = "MOVED"
                else:
                    shutil.copy2(path, destination)
                    info.status = "COPIED"
            except Exception as e:
                info.status = "ERROR_TRANSFER"
                info.notes += str(e)

        processed.append(info)
        if resume_mode:
            append_processed_state(job_name, path)

        if index % 500 == 0:
            elapsed = max(time.time() - started, 1)
            rate = index / elapsed
            remaining_files = max(len(source_files) - index, 0)
            eta_seconds = int(remaining_files / rate) if rate else 0
            print(f"Processed {index}/{len(source_files)} files | {rate:.1f} files/sec | ETA {eta_seconds // 60}m {eta_seconds % 60}s")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = write_report(processed, f"dj_library_report_{timestamp}.csv")
    playlists = write_m3u_playlists(processed)
    sidecar = write_onetagger_sidecar(processed, f"onetagger_suggestions_{timestamp}.csv")

    copied = sum(1 for r in processed if r.status == "COPIED")
    moved = sum(1 for r in processed if r.status == "MOVED")
    would_copy = sum(1 for r in processed if r.status == "WOULD_COPY")
    would_move = sum(1 for r in processed if r.status == "WOULD_MOVE")
    duplicates = sum(1 for r in processed if r.status == "DUPLICATE_SKIPPED")
    errors = sum(1 for r in processed if r.status.startswith("ERROR"))

    print("\nDone.")
    print(f"Report: {report}")
    print(f"Playlists folder: {PLAYLIST_DIR}")
    print(f"One Tagger sidecar suggestions: {sidecar}")
    print(f"Copied: {copied}")
    print(f"Moved: {moved}")
    print(f"Would copy: {would_copy}")
    print(f"Would move: {would_move}")
    print(f"Low bitrate review: {sum(1 for r in processed if r.quality_flag == 'LOW_BITRATE_REVIEW')}")
    print(f"Unknown bitrate: {sum(1 for r in processed if r.quality_flag == 'UNKNOWN_BITRATE')}")
    print(f"Missing tags review: {sum(1 for r in processed if any(flag.startswith('MISSING_') for flag in r.review_flags))}")
    print(f"Corrupted/tag error review: {sum(1 for r in processed if 'ZERO_BYTE_FILE' in r.review_flags or 'TAG_READ_ERROR' in r.review_flags)}")
    print(f"Duplicates skipped: {duplicates}")
    print(f"Errors: {errors}")

    if playlists:
        print("\nCreated playlists:")
        for p in playlists:
            print(f"- {p}")

    print("\nNext step:")
    print("Open the CSV report before importing the full result into Serato or VirtualDJ.")
    print("Then run One Tagger on the copied folders for deeper genre/BPM/key cleanup.")


def print_bash_helper() -> None:
    script_path = Path(__file__).resolve()
    bash_text = f'''#!/bin/bash
# DJ Organizer Helper
# Save this as run_dj_organizer.sh if you want quick commands.

cd "{script_path.parent}"

# Install dependency
python3 -m pip install mutagen

# 1) Test scan Hip-Hop
python3 "{script_path}" --dry-run --only "Hip-Hop" --limit 1000 --resume

# 2) Safe copy test Hip-Hop
# python3 "{script_path}" --copy --only "Hip-Hop" --limit 1000

# 3) Move test Hip-Hop after backup and review
# python3 "{script_path}" --move --only "Hip-Hop" --limit 1000

# 4) Full Hip-Hop move after everything looks correct
# python3 "{script_path}" --move --only "Hip-Hop" --resume

# 5) CHAOS MODE - full audit of entire source library
# python3 "{script_path}" --audit

# 6) CHAOS MODE - move EVERYTHING detected by the script
# WARNING: only use this if your music is fully backed up.
# python3 "{script_path}" --move --resume
'''
    print(bash_text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe DJ library migration and organizer.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Scan and report only. No files copied or moved.")
    mode.add_argument("--copy", action="store_true", help="Copy files into DJ_MUSIC structure.")
    mode.add_argument("--move", action="store_true", help="Move files into DJ_MUSIC structure. Use only after dry-run, copy test, and backup.")
    mode.add_argument("--bash", action="store_true", help="Print a Bash helper script you can save and run.")
    mode.add_argument("--audit", action="store_true", help="Scan the full source library and export genre count/audit CSV reports. No files copied or moved.")
    mode.add_argument("--clean", action="store_true", help="Scan the organized DJ_MUSIC library and create a cleanup suggestion CSV. No files moved.")
    parser.add_argument("--only", type=str, default=None, help="Only process detected genre/category, e.g. Hip-Hop")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of scanned files for testing.")
    parser.add_argument("--resume", action="store_true", help="Skip files already processed for this same mode/genre job.")
    parser.add_argument("--reset-resume", action="store_true", help="Clear saved resume state for this same mode/genre job before running.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not SOURCE_ROOT.exists():
        print(f"Source folder not found: {SOURCE_ROOT}")
        sys.exit(1)

    if args.bash:
        print_bash_helper()
        return

    if args.audit:
        audit_library(limit=args.limit)
        return

    if args.clean:
        clean_audit_library(limit=args.limit)
        return

    if not args.dry_run and not args.copy and not args.move and not args.audit and not args.clean:
        print("No mode selected. Use --dry-run first, then --copy or --move when ready.")
        print("Example: python3 dj_library_organizer_full.py --dry-run --only Hip-Hop")
        print("Bash helper: python3 dj_library_organizer_full.py --bash")
        print("Clean audit: python3 dj_library_organizer_full.py --clean")
        sys.exit(1)

    process_library(
        dry_run=args.dry_run,
        copy_mode=args.copy,
        move_mode=args.move,
        resume_mode=args.resume,
        reset_resume=args.reset_resume,
        only_genre=args.only,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
