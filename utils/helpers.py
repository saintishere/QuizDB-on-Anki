# utils/helpers.py
import re
import os
import subprocess
import traceback
import tkinter as tk
from tkinter import messagebox

# --- Custom Exceptions ---
class ProcessingError(Exception): pass
class WorkflowStepError(Exception): pass

def sanitize_filename(filename):
    """Removes invalid characters for filenames."""
    base_name = os.path.basename(filename); name_part, _ = os.path.splitext(base_name)
    sanitized = re.sub(r'[\\/*?:"<>|\s]+', '_', name_part); return sanitized if sanitized else "processed_file"

def get_subprocess_startupinfo():
    """Creates startupinfo object to hide console window on Windows."""
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def check_pymupdf_and_warn(parent_widget=None):
     """Checks for PyMuPDF and shows a warning if needed."""
     # Import PYMUPDF_INSTALLED here or pass it as an argument
     # This assumes constants.py is importable from where this function is called
     try:
         from ..constants import PYMUPDF_INSTALLED # Relative import
     except ImportError:
         # Fallback if relative import fails (e.g., running script directly)
         try:
             from constants import PYMUPDF_INSTALLED
         except ImportError:
              print("ERROR in check_pymupdf_and_warn: Could not import PYMUPDF_INSTALLED.")
              return False # Assume not installed if import fails

     if not PYMUPDF_INSTALLED:
         warning_message = (
             "-----------------------------------------------------------\n"
             "WARNING: PyMuPDF (fitz) library not found.\n"
             "         PDF image generation (Visual Q&A mode)\n"
             "         and PDF text extraction (Text Analysis mode)\n"
             "         will be disabled.\n"
             "         To enable fitz features, run: pip install PyMuPDF\n"
             "-----------------------------------------------------------"
         )
         print(warning_message)
         if parent_widget: # Show messagebox if a parent is provided
             messagebox.showwarning("Dependency Missing", warning_message.replace("-\n","\n").replace("-",""), parent=parent_widget)
     return PYMUPDF_INSTALLED

def show_error_dialog(title, message, parent=None):
    """Consistent way to show error dialogs."""
    full_message = f"{message}\n\n{traceback.format_exc()}"
    print(f"ERROR [{title}]: {full_message}") # Log full traceback
    messagebox.showerror(title, message, parent=parent)

def show_info_dialog(title, message, parent=None):
    messagebox.showinfo(title, message, parent=parent)

def ask_yes_no(title, question, parent=None):
    return messagebox.askyesno(title, question, parent=parent)

# Add more helper GUI functions if needed (e.g., safe_widget_config)
