# AnkiTagProcessor_main.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import traceback

# Import constants and utilities using relative paths
try:
    from .constants import DEFAULT_GEMINI_API_KEY, PYMUPDF_INSTALLED
    from .utils.helpers import check_pymupdf_and_warn, show_error_dialog
    # Import core modules used by the main app (e.g., for initial load)
    from .core.anki_connect import load_anki_data, ProcessingError as AnkiProcessingError
    # Import UI Pages
    from .ui.page1_anki_export import AnkiExportPage
    from .ui.page2_process_file import ProcessFilePage
    from .ui.page3_tag_tsv import TagTsvPage
    from .ui.page4_workflow import WorkflowPage
except ImportError as e:
    print(f"Error importing modules in main: {e}. Trying direct imports (might fail if not run as module).")
    # Fallback for direct execution (less ideal)
    from constants import DEFAULT_GEMINI_API_KEY, PYMUPDF_INSTALLED
    from utils.helpers import check_pymupdf_and_warn, show_error_dialog
    from core.anki_connect import load_anki_data, ProcessingError as AnkiProcessingError
    from ui.page1_anki_export import AnkiExportPage
    from ui.page2_process_file import ProcessFilePage
    from ui.page3_tag_tsv import TagTsvPage
    from ui.page4_workflow import WorkflowPage


class AnkiTagProcessorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Anki Tag Processor (Refactored)")
        self.geometry("1200x900")

        # --- Shared State Variables ---
        # Keep StringVars etc. here if multiple pages need to react to them directly
        # Or manage state within pages and use app methods for coordination.
        self.gemini_api_key = tk.StringVar(value=DEFAULT_GEMINI_API_KEY)
        # Anki data (loaded once)
        self.anki_decks = []
        self.anki_tags = []
        self.anki_note_types = {} # {modelName: [field1, field2]}

        # --- PyMuPDF Check ---
        # Check PyMuPDF early, before initializing pages that might depend on it
        check_pymupdf_and_warn(parent_widget=self) # Show initial warning if missing

        # --- Load Initial Anki Data ---
        self._load_initial_anki_data()

        # --- Create Notebook ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Instantiate Pages ---
        # Pass the notebook as master and self (app instance) for shared access
        try:
            self.page1 = AnkiExportPage(self.notebook, self)
            self.page2 = ProcessFilePage(self.notebook, self)
            self.page3 = TagTsvPage(self.notebook, self)
            self.page4 = WorkflowPage(self.notebook, self)
        except Exception as page_init_e:
             show_error_dialog("Page Initialization Error", f"Failed to initialize UI pages:\n{page_init_e}", parent=self)
             # Optionally destroy the window if pages fail to load
             # self.destroy()
             return # Stop initialization

        # --- Add Pages to Notebook ---
        self.notebook.add(self.page1, text="1: Export from Anki")
        self.notebook.add(self.page2, text="2: Process File to TSV")
        self.notebook.add(self.page3, text="3: Tag TSV File")
        self.notebook.add(self.page4, text="4: Workflow (File->TSV->Tag)")

        # Update pages that might need initial Anki data *after* they are created
        if hasattr(self.page1, 'update_anki_data'):
             self.page1.update_anki_data(self.anki_decks, self.anki_tags, self.anki_note_types)
        # Add similar updates for other pages if needed

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
        # Access page widgets safely using getattr with default None
        # Check if page exists before accessing its attributes
        if hasattr(self, 'page2') and hasattr(self.page2, 'p2_api_key_entry'): widgets_to_toggle.append(self.page2.p2_api_key_entry)
        if hasattr(self, 'page3') and hasattr(self.page3, 'p3_api_key_entry'): widgets_to_toggle.append(self.page3.p3_api_key_entry)
        if hasattr(self, 'page4') and hasattr(self.page4, 'p4_wf_api_key_entry'): widgets_to_toggle.append(self.page4.p4_wf_api_key_entry)

        if not widgets_to_toggle: return

        try:
            # Use the first widget found to determine current state
            current_show = widgets_to_toggle[0].cget('show')
            new_show = '' if current_show == '*' else '*'
            for widget in widgets_to_toggle:
                # Check if widget still exists before configuring
                if widget and widget.winfo_exists():
                     widget.config(show=new_show)
        except tk.TclError:
             print("Warning: Could not toggle API key visibility (widget might not exist yet).")
        except Exception as e:
            print(f"Error toggling key visibility: {e}")

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
            # Add elif for other pages if needed
            # elif page_index == 1: # Page 2 (Process File)
            #    if hasattr(self, 'page2'):
            #        target_page = self.page2
            #        # Add logic to pass data if needed

            if target_page:
                self.notebook.select(page_index)
                # Optionally trigger refresh or focus on the target page
                target_page.focus_set() # Or call a specific update method if needed
            else:
                 print(f"Error switching page: Target page for index {page_index} not found or not initialized.")

        except tk.TclError as e:
            print(f"Error switching page: {e}")
        except Exception as e:
            print(f"Unexpected error during page switch: {e}")

# ==========================================================================
# Main Execution Block
# ==========================================================================
if __name__ == "__main__":
    # It's crucial that the script is run from the directory *containing* AnkiTagProcessor
    # OR that AnkiTagProcessor's parent directory is in PYTHONPATH for relative imports to work.
    # If running directly, the fallback direct imports might work if structure is flat.
    try:
        app = AnkiTagProcessorApp()
        app.mainloop()
    except Exception as main_e:
        # Use the utility function for consistency
        # Need to handle potential import error for show_error_dialog itself
        try:
            # Attempt to use the helper function
            show_error_dialog("Fatal Error", f"Application crashed:\n{main_e}")
        except NameError: # If show_error_dialog wasn't imported due to earlier errors
             print("FATAL ERROR (show_error_dialog not available): Application crashed.")
             print(f"{main_e}\n{traceback.format_exc()}")
             # Fallback Tkinter message box
             try:
                 root = tk.Tk(); root.withdraw()
                 messagebox.showerror("Fatal Error", f"Application crashed:\n{main_e}")
                 root.destroy()
             except Exception: pass # Ignore errors in fallback messagebox
        except Exception as dialog_e: # Catch errors within show_error_dialog itself
             print(f"Error showing dialog: {dialog_e}")
             print(f"Original Fatal Error: {main_e}\n{traceback.format_exc()}")
