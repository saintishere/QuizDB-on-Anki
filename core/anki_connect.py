# core/anki_connect.py
import json
import urllib.request
import os
from tkinter import messagebox # Keep messagebox for specific warnings here
# Use relative import for helpers within the same package structure
try:
    from ..utils.helpers import ProcessingError # Use custom exception
except ImportError:
    # Fallback for direct execution or different structure
    from utils.helpers import ProcessingError

ANKICONNECT_URL = 'http://127.0.0.1:8765'
ANKICONNECT_TIMEOUT = 5

def invoke_anki_connect(action, params=None):
    """Sends a request to the AnkiConnect addon."""
    if params is None: params = {}
    request_json = json.dumps({'action': action, 'params': params, 'version': 6}).encode('utf-8')
    try:
        req = urllib.request.Request(ANKICONNECT_URL, request_json)
        response = urllib.request.urlopen(req, timeout=ANKICONNECT_TIMEOUT)
        response_data = json.load(response)
        if response_data.get('error') is not None:
            raise ProcessingError(f"AnkiConnect Error: {response_data['error']}")
        return response_data['result']
    except urllib.error.URLError as e:
        raise ProcessingError(f"Failed to connect to AnkiConnect (is Anki/profile running?): {e}")
    except json.JSONDecodeError as e:
        raise ProcessingError(f"Failed to decode AnkiConnect response: {e}")
    except ProcessingError as e:
        raise e # Re-raise specific processing errors
    except Exception as e:
        raise ProcessingError(f"AnkiConnect call error: {type(e).__name__}: {e}")

def load_anki_data():
    """Loads decks, tags, and note types from AnkiConnect. Returns a dict."""
    data = {"decks": [], "tags": [], "note_types": {}}
    try:
        data["decks"] = invoke_anki_connect("deckNames") or []
        data["tags"] = invoke_anki_connect("getTags") or []
        model_names = invoke_anki_connect("modelNames") or []
        for model in model_names:
            try:
                fields = invoke_anki_connect("modelFieldNames", {"modelName": model})
                if fields: data["note_types"][model] = fields
            except Exception as e:
                print(f"Warning: Could not get fields for model '{model}': {e}")
        return data
    except ProcessingError as e:
         print(f"Could not load initial Anki data: {e}")
         # Optionally re-raise or return partially loaded data
         return data # Return empty/partial data
    except Exception as e:
         print(f"Unexpected error loading Anki data: {e}")
         return data

def detect_anki_media_path(parent_for_dialog=None):
    """Detects Anki media path using AnkiConnect."""
    try:
        media_path = invoke_anki_connect("getMediaDirPath")
        if media_path and os.path.isdir(media_path):
            return media_path
        else:
            messagebox.showwarning("Detection Failed",
                                   "AnkiConnect did not return a valid media directory path.",
                                   parent=parent_for_dialog)
            return None
    except ProcessingError as e:
        messagebox.showerror("AnkiConnect Error",
                             f"Could not get media path from AnkiConnect.\nError: {e}",
                             parent=parent_for_dialog)
        return None
    except Exception as e:
         messagebox.showerror("Error", f"Unexpected error detecting media path: {e}", parent=parent_for_dialog)
         return None

def guess_anki_media_initial_dir():
    """Provides a likely starting directory for the media path browse dialog."""
    # (Logic from p2_select_anki_media_dir)
    initial_dir_guess = os.path.expanduser("~")
    appdata = os.getenv('APPDATA')
    if appdata and os.path.isdir(os.path.join(appdata, "Anki2")):
        initial_dir_guess = os.path.join(appdata, "Anki2")
    elif os.path.isdir(os.path.expanduser("~/Library/Application Support/Anki2")):
        initial_dir_guess = os.path.expanduser("~/Library/Application Support/Anki2")
    elif os.path.isdir(os.path.expanduser("~/.local/share/Anki2")):
        initial_dir_guess = os.path.expanduser("~/.local/share/Anki2")
    return initial_dir_guess
