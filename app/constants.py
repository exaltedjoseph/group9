import os
from pathlib import Path

APP_NAME = "Study Library"
APP_ID = "StudyLibrary"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = (Path(os.environ["STUDY_LIBRARY_DATA"]) if os.environ.get("STUDY_LIBRARY_DATA")
            else Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_ID)
SETTINGS_DB = DATA_DIR / "settings.db"
DEFAULT_LIBRARY_DIR = PROJECT_ROOT / "library"
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"
DOTENV_FILES = (PROJECT_ROOT / ".env",)

API_KEY_ENV = "GEMINI_API_KEY"
API_KEY_URL = "https://aistudio.google.com/apikey"

# (model id, display name, short description)
MODELS = [
    ("gemini-3.8-flash", "Gemini 3.8 Flash", "Best balance of quality and speed"),
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "Fastest and lowest cost"),
    ("gemini-3.1-pro-preview", "Gemini 3.1 Pro", "Most capable, paid tier only"),
]
DEFAULT_MODEL = MODELS[0][0]

MODE_FACILITATOR = "facilitator"
MODE_INTERN = "intern"

# (id, display name, SF-style icon)
RESOURCE_KINDS = [
    ("notes", "Notes", "doc"),
    ("slides", "Slides", "rectangle_stack"),
    ("exercise", "Exercise", "checklist"),
    ("reference", "Reference", "book"),
    ("other", "Other", "folder"),
]
KIND_NAMES = {k: name for k, name, _ in RESOURCE_KINDS}

# Apple system colors offered for modules
MODULE_COLORS = ["blue", "purple", "pink", "red", "orange", "yellow", "green", "mint", "teal", "cyan",
                 "indigo", "brown", "gray"]
