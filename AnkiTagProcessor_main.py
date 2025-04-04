# AnkiTagProcessor_main.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import traceback
# Corrected import: Use relative import for constants within the package
from . import constants

# Use only relative imports for package components
from .constants import DEFAULT_GEMINI_API_KEY, PYMUPDF_INSTALLED
from .utils.helpers import check_pymupdf_and_warn, show_error_dialog
from .core.anki_connect import load_anki_data, ProcessingError as AnkiProcessingError
from .ui.page1_anki_export import AnkiExportPage
from .ui.page2_process_file import ProcessFilePage
from .ui.page3_tag_tsv import TagTsvPage
from .ui.page4_workflow import WorkflowPage


class AnkiTagProcessorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Anki Tag Processor (Refactored)")
        self.geometry("1200x900")

        # --- Shared State Variables ---
        # Access constants via the imported module object
        self.gemini_api_key = tk.StringVar(value=constants.DEFAULT_GEMINI_API_KEY)
        # Anki data (loaded once)
        self.anki_decks = []
        self.anki_tags = []
        self.anki_note_types = {} # {modelName: [field1, field2]}

        # --- PyMuPDF Check ---
        check_pymupdf_and_warn(parent_widget=self) # Show initial warning if missing

        # --- Load Initial Anki Data ---
        self._load_initial_anki_data()

        # --- Create Notebook ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Instantiate Pages ---
        try:
            self.page1 = AnkiExportPage(self.notebook, self)
            self.page2 = ProcessFilePage(self.notebook, self)
            self.page3 = TagTsvPage(self.notebook, self)
            self.page4 = WorkflowPage(self.notebook, self)
        except Exception as page_init_e:
             show_error_dialog("Page Initialization Error", f"Failed to initialize UI pages:\n{page_init_e}", parent=self)
             # self.destroy() # Optionally destroy
             return # Stop initialization

        # --- Add Pages to Notebook ---
        self.notebook.add(self.page1, text="1: Export from Anki")
        self.notebook.add(self.page2, text="2: Process File to TSV")
        self.notebook.add(self.page3, text="3: Tag TSV File")
        self.notebook.add(self.page4, text="4: Workflow (File->TSV->Tag)")

        # Update pages that might need initial Anki data
        if hasattr(self.page1, 'update_anki_data'):
             self.page1.update_anki_data(self.anki_decks, self.anki_tags, self.anki_note_types)

    def _load_initial_anki_data(self):
        """Loads data from AnkiConnect and stores it in app variables."""
        print("Loading initial Anki data...")
        try:
            data = load_anki_data() # Function from core.anki_connect
            self.anki_decks = data.get("decks", [])
            self.anki_tags = data.get("tags", [])
            self.anki_note_types = data.get("note_types", {})
            print(f"Loaded {len(self.anki_decks)} decks, {len(self.anki_tags)} tags, {len(self.anki_note_types)} note types.")
        except AnkiProcessingError as e:
             messagebox.showwarning("Anki Connect", f"Could not load initial Anki data: {e}\n\nAnki features limited.", parent=self)
        except Exception as e:
             messagebox.showerror("Error", f"Unexpected error loading Anki data: {e}", parent=self)

    # --- Shared Methods ---
    def toggle_api_key_visibility(self):
        """Toggles visibility of API key entries across all relevant pages."""
        widgets_to_toggle = []
        if hasattr(self, 'page2') and hasattr(self.page2, 'p2_api_key_entry'): widgets_to_toggle.append(self.page2.p2_api_key_entry)
        if hasattr(self, 'page3') and hasattr(self.page3, 'p3_api_key_entry'): widgets_to_toggle.append(self.page3.p3_api_key_entry)
        if hasattr(self, 'page4') and hasattr(self.page4, 'p4_wf_api_key_entry'): widgets_to_toggle.append(self.page4.p4_wf_api_key_entry)

        if not widgets_to_toggle: return

        try:
            current_show = widgets_to_toggle[0].cget('show')
            new_show = '' if current_show == '*' else '*'
            for widget in widgets_to_toggle:
                if widget and widget.winfo_exists():
                     widget.config(show=new_show)
        except tk.TclError: print("Warning: Could not toggle API key visibility.")
        except Exception as e: print(f"Error toggling key visibility: {e}")

    def switch_to_page(self, page_index, file_path=None):
        """Switches notebook to the specified page and optionally sets a file path."""
        print(f"Switching to page index {page_index}, file: {file_path}")
        try:
            target_page = None
            if page_index == 2: # Page 3 (Tag TSV)
                if hasattr(self, 'page3'):
                    target_page = self.page3
                    if file_path and hasattr(target_page, 'p3_input_file_var'):
                        target_page.p3_input_file_var.set(file_path)
                        if hasattr(target_page, 'log_status'):
                            target_page.log_status(f"Loaded input file: {os.path.basename(file_path)}")

            if target_page:
                self.notebook.select(page_index)
                target_page.focus_set()
            else: print(f"Error switching page: Target page for index {page_index} not found.")

        except tk.TclError as e: print(f"Error switching page: {e}")
        except Exception as e: print(f"Unexpected error during page switch: {e}")

# ==========================================================================
# Main Execution Block
# ==========================================================================
if __name__ == "__main__":
    # IMPORTANT: Run this script as a module from the PARENT directory
    # Example: python -m AnkiTagProcessor.AnkiTagProcessor_main
    try:
        app = AnkiTagProcessorApp()
        app.mainloop()
    except Exception as main_e:
        try:
            # Attempt to use the helper function if imported successfully
            # Need to make sure show_error_dialog is accessible here if needed
            # It might be better to handle this import within the except block
            # or ensure helpers is imported earlier if needed globally.
            # For now, assuming show_error_dialog might not be loaded if init fails early.
            print(f"FATAL ERROR in main execution: {main_e}\n{traceback.format_exc()}")
            try: # Fallback Tkinter message box
                root = tk.Tk(); root.withdraw()
                messagebox.showerror("Fatal Error", f"Application crashed:\n{main_e}")
                root.destroy()
            except Exception: pass # Ignore errors in fallback
        except Exception as dialog_e: # Catch errors within the error handling itself
             print(f"Error showing dialog: {dialog_e}")
             print(f"Original Fatal Error: {main_e}\n{traceback.format_exc()}")

