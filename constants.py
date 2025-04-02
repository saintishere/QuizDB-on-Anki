# constants.py
import os
import prompts # Keep prompts accessible here too

# --- Gemini API ---
DEFAULT_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
GEMINI_UNIFIED_MODELS = [
    "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash",
    "gemini-2.0-flash-lite", "gemini-2.0-flash-thinking-exp-01-21",
    "gemini-2.5-pro-exp-03-25", "gemma-3-27b-it",
]
DEFAULT_MODEL = "gemini-2.0-flash"
if DEFAULT_MODEL not in GEMINI_UNIFIED_MODELS and GEMINI_UNIFIED_MODELS:
    DEFAULT_MODEL = GEMINI_UNIFIED_MODELS[0]

VISUAL_CAPABLE_MODELS = [
    "gemini-2.0-flash", "gemini-1.5-pro", "gemini-2.5-pro-exp-03-25",
    "gemini-1.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash-thinking-exp-01-21"
]
DEFAULT_VISUAL_MODEL = "gemini-2.0-flash"
if DEFAULT_VISUAL_MODEL not in VISUAL_CAPABLE_MODELS and VISUAL_CAPABLE_MODELS:
    DEFAULT_VISUAL_MODEL = VISUAL_CAPABLE_MODELS[0]

GEMINI_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# --- Default Prompts ---
def get_default_prompt(prompt_name, fallback_message):
    try:
        # Ensure prompts is treated as a module relative to where constants is used
        # This might need adjustment depending on how prompts.py is loaded/structured
        import prompts
        return getattr(prompts, prompt_name)
    except (AttributeError, ImportError) as e:
        print(f"Warning: {prompt_name} not found or prompts module error ({e}). Using placeholder.")
        return fallback_message

DEFAULT_VISUAL_EXTRACTION_PROMPT = get_default_prompt(
    "VISUAL_EXTRACTION", "ERROR: Visual extraction prompt missing."
)
DEFAULT_BOOK_PROCESSING_PROMPT = get_default_prompt(
    "BOOK_PROCESSING", "ERROR: Book processing prompt missing."
)
DEFAULT_BATCH_TAGGING_PROMPT = get_default_prompt(
    "BATCH_TAGGING", "ERROR: Batch tagging prompt missing."
)

# --- PyMuPDF Check ---
try:
    import fitz
    PYMUPDF_INSTALLED = True
except ImportError:
    PYMUPDF_INSTALLED = False
    fitz = None # Ensure fitz is None if import fails
