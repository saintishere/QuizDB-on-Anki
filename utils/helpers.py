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
             # This fallback might still fail if run directly, but it's better than nothing
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
    try:
        messagebox.showerror(title, message, parent=parent)
    except Exception as e:
        print(f"Error displaying error dialog: {e}")


def show_info_dialog(title, message, parent=None):
    """Consistent way to show info dialogs."""
    try:
        messagebox.showinfo(title, message, parent=parent)
    except Exception as e:
        print(f"Error displaying info dialog: {e}")

def ask_yes_no(title, question, parent=None):
    """Consistent way to ask yes/no questions."""
    try:
        return messagebox.askyesno(title, question, parent=parent)
    except Exception as e:
        print(f"Error displaying yes/no dialog: {e}")
        return False # Default to No on error

# --- NEW FUNCTION ---
def save_tsv_incrementally(data_rows, output_dir, base_filename, step_name, log_func):
    """
    Saves the current list of data rows (including header) to a temporary TSV file.

    Args:
        data_rows (list of lists): The data including the header row.
        output_dir (str): Directory to save the temp file.
        base_filename (str): Base name for the temp file (e.g., sanitized original name).
        step_name (str): Identifier for the step (e.g., 'tagging_pass1').
        log_func (callable): Function for logging messages.

    Returns:
        str or None: The path to the saved temporary file, or None on error.
    """
    if not data_rows:
        return None  # Don't save if empty

    temp_filename = f"{base_filename}_{step_name}_temp_results.tsv"
    temp_filepath = os.path.join(output_dir, temp_filename)
    try:
        with open(temp_filepath, 'w', encoding='utf-8', newline='') as f:
            for row in data_rows:
                f.write("\t".join(map(str, row)) + "\n")
        log_func(f"Saved intermediate {step_name} results ({len(data_rows)-1} data rows) to {temp_filename}", "debug")
        return temp_filepath
    except Exception as e:
        log_func(f"Error saving intermediate {step_name} results to {temp_filepath}: {e}", "error")
        return None

# Add more helper GUI functions if needed (e.g., safe_widget_config)

