# ui/page2_process_file.py
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import os
import threading
import traceback # Added for logging
import json # Added to fix undefined variable error
from datetime import datetime

# --- Use relative imports ONLY ---
from ..constants import (DEFAULT_VISUAL_MODEL, VISUAL_CAPABLE_MODELS, DEFAULT_MODEL, # Added DEFAULT_MODEL
                     DEFAULT_VISUAL_EXTRACTION_PROMPT, DEFAULT_BOOK_PROCESSING_PROMPT,
                     PYMUPDF_INSTALLED, GEMINI_UNIFIED_MODELS) # Added GEMINI_UNIFIED_MODELS
from ..utils.helpers import (ProcessingError, WorkflowStepError, sanitize_filename,
                           show_error_dialog, show_info_dialog, ask_yes_no)
from ..core.anki_connect import detect_anki_media_path, guess_anki_media_initial_dir
# Import the correct, existing functions from file_processor
from ..core.file_processor import (generate_page_images, extract_text_from_pdf,
                                   read_text_file, generate_tsv_visual, generate_tsv_text_analysis)
from ..core.gemini_api import (call_gemini_visual_extraction, call_gemini_text_analysis,
                           cleanup_gemini_file)
# --- Removed the try...except ImportError block ---


class ProcessFilePage(ttk.Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance # Reference to the main application

        # --- Page 2 Variables (Use app's shared vars or create local ones) ---
        self.p2_processing_type = tk.StringVar(value="Visual Q&A (PDF)")
        self.p2_input_file_path = tk.StringVar()
        self.p2_output_dir_path = tk.StringVar(value=os.getcwd())
        self.p2_save_directly_to_media = tk.BooleanVar(value=False)
        self.p2_anki_media_path = tk.StringVar() # Could potentially link to app.anki_media_path if shared
        self.p2_gemini_selected_model = tk.StringVar(value=DEFAULT_VISUAL_MODEL)
        self.p2_visual_extraction_prompt_var = tk.StringVar(value=DEFAULT_VISUAL_EXTRACTION_PROMPT)
        self.p2_book_processing_prompt_var = tk.StringVar(value=DEFAULT_BOOK_PROCESSING_PROMPT)

        # NEW: Text Analysis Chunking/Delay Settings
        self.p2_text_chunk_size = tk.IntVar(value=30000) # Chars per chunk
        self.p2_text_api_delay = tk.DoubleVar(value=5.0) # Delay between chunks

        self.p2_is_processing = False
        self.p2_image_output_folder_final = None
        self.p2_page_image_map = {}

        # --- Build UI ---
        self._build_ui()

        # Initial UI state based on default processing type and PyMuPDF check
        self._update_ui_for_processing_type()
        # Check PyMuPDF after UI is built
        if not PYMUPDF_INSTALLED:
            if hasattr(self, 'p2_visual_qa_radio'):
                self.p2_visual_qa_radio.config(state="disabled")
            if self.p2_processing_type.get() == "Visual Q&A (PDF)":
                self.p2_processing_type.set("Text Analysis (PDF/TXT)")
                self.log_status("PyMuPDF not found. Switched to Text Analysis mode.", "warning")
                self._update_ui_for_processing_type() # Update UI again after switch


    def _build_ui(self):
        # --- UI Building Logic (No changes needed here) ---
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(4, weight=1) # Prompt editor area
        main_frame.grid_rowconfigure(6, weight=1) # Status log

        # --- 0. Processing Type Selection ---
        type_frame = ttk.LabelFrame(main_frame, text="0. Select Processing Type")
        type_frame.grid(row=0, column=0, padx=0, pady=(0,10), sticky="ew")
        self.p2_visual_qa_radio = ttk.Radiobutton(
            type_frame, text="Visual Q&A (PDF)", variable=self.p2_processing_type,
            value="Visual Q&A (PDF)", command=self._update_ui_for_processing_type,
            state="disabled" # Will be enabled if PYMUPDF_INSTALLED is True later
        )
        self.p2_visual_qa_radio.pack(side=tk.LEFT, padx=10, pady=5)
        self.p2_text_analysis_radio = ttk.Radiobutton(
            type_frame, text="Text Analysis (PDF/TXT)", variable=self.p2_processing_type,
            value="Text Analysis (PDF/TXT)", command=self._update_ui_for_processing_type
        )
        self.p2_text_analysis_radio.pack(side=tk.LEFT, padx=10, pady=5)

        # --- 1. Input File Selection ---
        input_frame = ttk.LabelFrame(main_frame, text="1. Input File")
        input_frame.grid(row=1, column=0, padx=0, pady=5, sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)
        self.p2_input_file_label = tk.Label(input_frame, text="Input File:") # Dynamic label
        self.p2_input_file_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p2_input_file_entry = tk.Entry(input_frame, textvariable=self.p2_input_file_path, width=60, state="readonly")
        self.p2_input_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.p2_browse_input_button = tk.Button(input_frame, text="Browse...", command=self._select_input_file)
        self.p2_browse_input_button.grid(row=0, column=2, padx=5, pady=5)

        # --- 2. Output & Image Location ---
        self.p2_output_image_frame = ttk.LabelFrame(main_frame, text="2. Output Locations (TSV & Images)")
        self.p2_output_image_frame.grid(row=2, column=0, padx=0, pady=5, sticky="ew")
        self.p2_output_image_frame.grid_columnconfigure(1, weight=1)
        # TSV Output
        tk.Label(self.p2_output_image_frame, text="TSV Output Dir:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p2_outdir_entry = tk.Entry(self.p2_output_image_frame, textvariable=self.p2_output_dir_path, width=60, state="readonly")
        self.p2_outdir_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.p2_browse_outdir_button = tk.Button(self.p2_output_image_frame, text="Browse...", command=self._select_output_dir)
        self.p2_browse_outdir_button.grid(row=0, column=2, padx=5, pady=5)
        # Image specific options (Managed visibility in _update_ui_...)
        self.p2_save_direct_check = tk.Checkbutton(
            self.p2_output_image_frame, text="Save Images Directly to Anki collection.media folder",
            variable=self.p2_save_directly_to_media, command=self._toggle_media_path_entry)
        self.p2_save_direct_check.grid(row=1, column=0, columnspan=3, padx=5, pady=(10,0), sticky="w")
        self.p2_anki_media_label = tk.Label(self.p2_output_image_frame, text="Anki Media Path:")
        self.p2_anki_media_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.p2_anki_media_entry = tk.Entry(self.p2_output_image_frame, textvariable=self.p2_anki_media_path, width=60, state="disabled")
        self.p2_anki_media_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.p2_browse_anki_media_button = tk.Button(self.p2_output_image_frame, text="Browse...", command=self._select_anki_media_dir, state="disabled")
        self.p2_browse_anki_media_button.grid(row=2, column=2, padx=5, pady=5)
        self.p2_detect_anki_media_button = tk.Button(self.p2_output_image_frame, text="Detect via AnkiConnect", command=self._detect_anki_media_path, state="normal")
        self.p2_detect_anki_media_button.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        # --- 3. Gemini Configuration ---
        config_frame = ttk.LabelFrame(main_frame, text="3. Gemini Configuration")
        config_frame.grid(row=3, column=0, padx=0, pady=5, sticky="ew")
        config_frame.grid_columnconfigure(1, weight=1)
        # API Key
        tk.Label(config_frame, text="API Key:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p2_api_key_entry = tk.Entry(config_frame, textvariable=self.app.gemini_api_key, width=50, show="*")
        self.p2_api_key_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.p2_show_key_button = tk.Button(config_frame, text="Show/Hide", command=self.app.toggle_api_key_visibility)
        self.p2_show_key_button.grid(row=0, column=2, padx=(0,5), pady=5)
        # Model
        tk.Label(config_frame, text="Model:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.p2_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p2_gemini_selected_model, values=VISUAL_CAPABLE_MODELS, state="readonly", width=47)
        self.p2_model_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        # Ensure initial model selection is valid
        if VISUAL_CAPABLE_MODELS:
            if self.p2_gemini_selected_model.get() not in VISUAL_CAPABLE_MODELS:
                self.p2_gemini_selected_model.set(VISUAL_CAPABLE_MODELS[0])
        else:
            self.p2_gemini_selected_model.set("") # Handle case where list might be empty

        # Text Analysis Chunking/Delay Widgets (Managed visibility)
        self.p2_text_chunk_label = tk.Label(config_frame, text="Text Chunk Size (chars):")
        self.p2_text_chunk_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.p2_text_chunk_entry = tk.Entry(config_frame, textvariable=self.p2_text_chunk_size, width=10)
        self.p2_text_chunk_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        self.p2_text_delay_label = tk.Label(config_frame, text="Text API Delay (sec):")
        self.p2_text_delay_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.p2_text_delay_entry = tk.Entry(config_frame, textvariable=self.p2_text_api_delay, width=10)
        self.p2_text_delay_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        # --- 4. Prompt Editor Area ---
        self.p2_prompt_area_frame = ttk.Frame(main_frame)
        self.p2_prompt_area_frame.grid(row=4, column=0, padx=0, pady=5, sticky="nsew")
        self.p2_prompt_area_frame.grid_rowconfigure(0, weight=1)
        self.p2_prompt_area_frame.grid_columnconfigure(0, weight=1)
        # Visual Extraction Prompt Frame
        self.p2_visual_prompt_frame = ttk.LabelFrame(self.p2_prompt_area_frame, text="4. Visual Extraction & Formatting Prompt")
        self.p2_visual_prompt_frame.grid_rowconfigure(0, weight=1); self.p2_visual_prompt_frame.grid_columnconfigure(0, weight=1)
        self.p2_visual_prompt_text = scrolledtext.ScrolledText(self.p2_visual_prompt_frame, wrap=tk.WORD, height=10)
        self.p2_visual_prompt_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p2_visual_prompt_text.insert(tk.END, self.p2_visual_extraction_prompt_var.get())
        self.p2_visual_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_visual)
        # Book Processing Prompt Frame
        self.p2_book_prompt_frame = ttk.LabelFrame(self.p2_prompt_area_frame, text="4. Book Processing & Formatting Prompt")
        self.p2_book_prompt_frame.grid_rowconfigure(0, weight=1); self.p2_book_prompt_frame.grid_columnconfigure(0, weight=1)
        self.p2_book_prompt_text = scrolledtext.ScrolledText(self.p2_book_prompt_frame, wrap=tk.WORD, height=10)
        self.p2_book_prompt_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p2_book_prompt_text.insert(tk.END, self.p2_book_processing_prompt_var.get())
        self.p2_book_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_book)

        # --- 5. Action Button ---
        self.p2_run_button = tk.Button(main_frame, text="Process File to TSV", command=self._start_processing_thread, font=('Arial', 12, 'bold'), bg='lightblue')
        self.p2_run_button.grid(row=5, column=0, padx=10, pady=15, sticky="ew")

        # --- 6. Status Log ---
        status_frame = ttk.LabelFrame(main_frame, text="5. Status Log")
        status_frame.grid(row=6, column=0, padx=0, pady=5, sticky="nsew")
        status_frame.grid_rowconfigure(0, weight=1); status_frame.grid_columnconfigure(0, weight=1)
        self.p2_status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=10, state="disabled")
        self.p2_status_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        # --- End of UI Building ---

    # --- Methods specific to Page 2 (Logging, UI Updates, File Selection, Threads) ---
    # --- No changes needed in the logic of these methods, only the imports at the top were fixed ---

    def log_status(self, message, level="info"):
        """Logs messages to the status ScrolledText on this page."""
        try:
            if not hasattr(self, 'p2_status_text') or not self.p2_status_text.winfo_exists(): return
            self.p2_status_text.config(state="normal")
            prefix_map = {"info": "[INFO] ", "step": "[STEP] ", "warning": "[WARN] ", "error": "[ERROR] ", "upload": "[UPLOAD] ", "debug": "[DEBUG] "}
            prefix = prefix_map.get(level, "[INFO] ")
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.p2_status_text.insert(tk.END, f"{timestamp} {prefix}{message}\n")
            self.p2_status_text.see(tk.END) # Scroll to the end
            self.p2_status_text.config(state="disabled")
            self.update_idletasks() # Ensure UI updates immediately
        except tk.TclError as e:
            # Fallback print if TclError occurs (e.g., widget destroyed)
            print(f"P2 STATUS LOG (Backup): {message} (Error: {e})")
        except Exception as e:
            print(f"Unexpected error in P2 log_status: {e}")

    def _update_ui_for_processing_type(self):
        """Shows/hides UI elements based on selected processing type."""
        selected_type = self.p2_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"

        try:
            # Input Label
            if hasattr(self, 'p2_input_file_label'):
                self.p2_input_file_label.config(text="Input PDF:" if is_visual else "Input File (PDF/TXT):")

            # Prompts (use grid/grid_remove for better layout management)
            if hasattr(self, 'p2_visual_prompt_frame') and self.p2_visual_prompt_frame.winfo_exists():
                if is_visual:
                    self.p2_visual_prompt_frame.grid(row=0, column=0, sticky="nsew")
                else:
                    self.p2_visual_prompt_frame.grid_remove()
            if hasattr(self, 'p2_book_prompt_frame') and self.p2_book_prompt_frame.winfo_exists():
                if not is_visual:
                    self.p2_book_prompt_frame.grid(row=0, column=0, sticky="nsew")
                else:
                    self.p2_book_prompt_frame.grid_remove()

            # Image Options Frame Children (Use grid/grid_remove)
            image_options_visible = is_visual
            image_widgets = [
                getattr(self, 'p2_save_direct_check', None),
                getattr(self, 'p2_anki_media_label', None),
                getattr(self, 'p2_anki_media_entry', None),
                getattr(self, 'p2_browse_anki_media_button', None),
                getattr(self, 'p2_detect_anki_media_button', None)
            ]
            for widget in image_widgets:
                if widget and widget.winfo_exists():
                    if image_options_visible:
                        widget.grid() # Re-show using grid
                        # Update state based on checkbox for entry/browse/detect
                        if widget in [self.p2_anki_media_entry, self.p2_browse_anki_media_button]:
                            widget.config(state="normal" if self.p2_save_directly_to_media.get() else "disabled")
                        elif widget == self.p2_detect_anki_media_button:
                             widget.config(state="normal") # Detect button always enabled when visible
                    else:
                        widget.grid_remove()

            # Text Chunking/Delay Widgets (Use grid/grid_remove)
            text_options_visible = not is_visual
            text_widgets = [
                getattr(self, 'p2_text_chunk_label', None),
                getattr(self, 'p2_text_chunk_entry', None),
                getattr(self, 'p2_text_delay_label', None),
                getattr(self, 'p2_text_delay_entry', None)
            ]
            for widget in text_widgets:
                 if widget and widget.winfo_exists():
                     if text_options_visible:
                         widget.grid()
                     else:
                         widget.grid_remove()

            # Run Button Text
            if hasattr(self, 'p2_run_button'):
                self.p2_run_button.config(text="Process Visual PDF to TSV" if is_visual else "Process Text File to TSV")

            # Model Dropdown (Change available models based on type)
            if hasattr(self, 'p2_model_dropdown'):
                current_model = self.p2_gemini_selected_model.get()
                if is_visual:
                    self.p2_model_dropdown.config(values=VISUAL_CAPABLE_MODELS)
                    # Set default visual model if current is invalid or list is non-empty
                    if current_model not in VISUAL_CAPABLE_MODELS and VISUAL_CAPABLE_MODELS:
                        self.p2_gemini_selected_model.set(VISUAL_CAPABLE_MODELS[0])
                    elif not VISUAL_CAPABLE_MODELS:
                         self.p2_gemini_selected_model.set("") # Handle empty list case
                else: # Text Analysis
                    self.p2_model_dropdown.config(values=GEMINI_UNIFIED_MODELS) # Show all models
                    # Try to keep current model if valid, else default
                    if current_model not in GEMINI_UNIFIED_MODELS and GEMINI_UNIFIED_MODELS:
                        self.p2_gemini_selected_model.set(DEFAULT_MODEL if DEFAULT_MODEL in GEMINI_UNIFIED_MODELS else GEMINI_UNIFIED_MODELS[0])
                    elif not GEMINI_UNIFIED_MODELS:
                         self.p2_gemini_selected_model.set("") # Handle empty list case

            # Disable Visual Q&A radio if PyMuPDF is not installed
            if hasattr(self, 'p2_visual_qa_radio'):
                self.p2_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")

        except tk.TclError as e:
            print(f"P2 UI Update Warning: {e}") # Log Tcl errors if widgets are destroyed
        except AttributeError as e:
            print(f"P2 UI Update Warning (AttributeError): {e}") # Log if attributes don't exist yet


    def _sync_prompt_var_from_editor_visual(self, event=None):
         """Syncs the visual prompt editor content to its variable."""
         try:
             if hasattr(self, 'p2_visual_prompt_text') and self.p2_visual_prompt_text.winfo_exists():
                 current_text = self.p2_visual_prompt_text.get("1.0", tk.END).strip()
                 self.p2_visual_extraction_prompt_var.set(current_text)
                 # Reset modified flag to prevent recursive calls if needed
                 self.p2_visual_prompt_text.edit_modified(False)
         except tk.TclError:
             pass # Ignore error if widget is destroyed

    def _sync_prompt_var_from_editor_book(self, event=None):
         """Syncs the book/text prompt editor content to its variable."""
         try:
             if hasattr(self, 'p2_book_prompt_text') and self.p2_book_prompt_text.winfo_exists():
                 current_text = self.p2_book_prompt_text.get("1.0", tk.END).strip()
                 self.p2_book_processing_prompt_var.set(current_text)
                 self.p2_book_prompt_text.edit_modified(False)
         except tk.TclError:
             pass

    def _select_input_file(self):
        """Handles browsing for the input file based on processing type."""
        selected_type = self.p2_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"

        # Define file types based on selection
        if is_visual:
            filetypes = (("PDF files", "*.pdf"), ("All files", "*.*"))
            title = "Select Input PDF for Visual Q&A"
        else:
            filetypes = (("Text files", "*.txt"), ("PDF files", "*.pdf"), ("All files", "*.*"))
            title = "Select Input File for Text Analysis (PDF/TXT)"

        filepath = filedialog.askopenfilename(parent=self, title=title, filetypes=filetypes)
        if filepath:
            # Validate file type against selected processing mode
            is_pdf = filepath.lower().endswith(".pdf")
            is_txt = filepath.lower().endswith(".txt")

            if is_visual and not is_pdf:
                show_error_dialog("Invalid File", "Visual Q&A requires a PDF file.", parent=self)
                return
            if not is_visual and not (is_pdf or is_txt):
                show_error_dialog("Invalid File", "Text Analysis requires a PDF or TXT file.", parent=self)
                return
            # Check for PyMuPDF dependency if PDF selected for Text Analysis
            if not is_visual and is_pdf and not PYMUPDF_INSTALLED:
                show_error_dialog("Dependency Missing", "Processing PDF text requires PyMuPDF (fitz).\nInstall it: pip install PyMuPDF", parent=self)
                return

            self.p2_input_file_path.set(filepath)
            self.log_status(f"Selected input file: {os.path.basename(filepath)}")
            # Suggest output directory based on input file location
            suggested_outdir = os.path.dirname(filepath) or os.getcwd()
            self.p2_output_dir_path.set(suggested_outdir)
            self.log_status(f"TSV Output directory set to: {suggested_outdir}")
        else:
            self.log_status("Input file selection cancelled.")

    def _select_output_dir(self):
        """Handles browsing for the TSV output directory."""
        dirpath = filedialog.askdirectory(parent=self, title="Select TSV Output Directory",
                                          initialdir=self.p2_output_dir_path.get() or os.path.expanduser("~"))
        if dirpath:
            self.p2_output_dir_path.set(dirpath)
            self.log_status(f"Selected TSV output directory: {dirpath}")
        else:
            self.log_status("Output directory selection cancelled.")

    def _toggle_media_path_entry(self):
        """Enables/disables the Anki media path entry based on the checkbox."""
        try:
            if self.p2_save_directly_to_media.get():
                if hasattr(self, 'p2_anki_media_entry'): self.p2_anki_media_entry.config(state="normal")
                if hasattr(self, 'p2_browse_anki_media_button'): self.p2_browse_anki_media_button.config(state="normal")
                # Detect button is always normal when visible, handled in _update_ui...
                self.log_status("Direct save to Anki media enabled.", "info")
                # Attempt to auto-detect path if empty when enabled
                if not self.p2_anki_media_path.get():
                    self._detect_anki_media_path()
            else:
                if hasattr(self, 'p2_anki_media_entry'): self.p2_anki_media_entry.config(state="disabled")
                if hasattr(self, 'p2_browse_anki_media_button'): self.p2_browse_anki_media_button.config(state="disabled")
                self.log_status("Direct save disabled. Images will be saved to a subfolder in the TSV output directory.", "info")
        except tk.TclError:
            pass # Ignore error if widget destroyed

    def _select_anki_media_dir(self):
        """Handles browsing for the Anki media directory."""
        initial_dir = self.p2_anki_media_path.get() or guess_anki_media_initial_dir()
        dirpath = filedialog.askdirectory(parent=self, title="Select Anki 'collection.media' Folder",
                                          initialdir=initial_dir)
        if dirpath:
            # Check if the selected folder name is 'collection.media'
            if os.path.basename(dirpath).lower() != "collection.media":
                 # Ask for confirmation if the name doesn't match
                 if ask_yes_no("Confirm Path",
                               f"Selected folder: '{os.path.basename(dirpath)}'.\nThis usually needs to be the 'collection.media' folder.\n\nIs this the correct path?",
                               parent=self):
                      self.p2_anki_media_path.set(dirpath)
                      self.log_status(f"Selected Anki media path (manual confirm): {dirpath}")
                 else:
                      self.log_status("Anki media path selection cancelled.", "info")
            else:
                 # Set path if name matches
                 self.p2_anki_media_path.set(dirpath)
                 self.log_status(f"Selected Anki media path: {dirpath}")
        else:
            self.log_status("Anki media path selection cancelled.")

    def _detect_anki_media_path(self):
        """Attempts to detect the Anki media path using AnkiConnect."""
        self.log_status("Attempting to detect Anki media path via AnkiConnect...", "info")
        try:
            media_path = detect_anki_media_path(parent_for_dialog=self) # Pass self for dialog parent
            if media_path:
                self.p2_anki_media_path.set(media_path)
                self.log_status(f"Detected Anki media path: {media_path}", "info")
                # Ensure widgets are enabled if direct save is checked
                if self.p2_save_directly_to_media.get():
                    self._toggle_media_path_entry()
            else:
                # Message handled within detect_anki_media_path
                self.log_status("Anki media path detection failed or was cancelled.", "warning")
        except Exception as e:
             # Catch unexpected errors during detection
             self.log_status(f"Error during Anki media path detection: {e}", "error")
             show_error_dialog("Detection Error", f"An unexpected error occurred during path detection:\n{e}", parent=self)

    def _processing_finished(self, success=True):
        """Updates UI elements when processing completes or fails."""
        self.p2_is_processing = False
        selected_type = self.p2_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"
        base_text = "Process Visual PDF to TSV" if is_visual else "Process Text File to TSV"
        final_text = base_text
        final_bg = 'lightblue' # Default button color

        if not success:
            final_text = f"Processing Failed (See Log)"
            final_bg = 'salmon' # Error color

        try:
            if hasattr(self, 'p2_run_button') and self.p2_run_button.winfo_exists():
                self.p2_run_button.config(state="normal", text=final_text, bg=final_bg)
        except tk.TclError:
            print("P2 Warning: Could not re-enable run button.")

    def _start_processing_thread(self):
        """Validates inputs and starts the appropriate processing thread."""
        if self.p2_is_processing:
            show_info_dialog("In Progress", "Processing is already running.", parent=self)
            return

        # --- Input Validation ---
        selected_type = self.p2_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"
        input_file = self.p2_input_file_path.get()
        tsv_output_dir = self.p2_output_dir_path.get()
        api_key = self.app.gemini_api_key.get()
        model_name = self.p2_gemini_selected_model.get()

        if not input_file or not os.path.exists(input_file):
            show_error_dialog("Error", "Please select a valid input file.", parent=self)
            return
        if not tsv_output_dir or not os.path.isdir(tsv_output_dir):
            show_error_dialog("Error", "Please select a valid TSV output directory.", parent=self)
            return
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            show_error_dialog("Error", "Please enter your Gemini API Key.", parent=self)
            return
        if not model_name:
            show_error_dialog("Error", "Please select a Gemini model.", parent=self)
            return

        # --- Prepare Arguments and Target Function ---
        target_func = None
        args = ()
        # Base name for output files/folders
        safe_base_name = sanitize_filename(os.path.basename(input_file))

        if is_visual:
            prompt_text = self.p2_visual_extraction_prompt_var.get()
            save_direct = self.p2_save_directly_to_media.get()
            anki_media_dir = self.p2_anki_media_path.get()

            if not prompt_text:
                show_error_dialog("Error", "Visual Extraction prompt cannot be empty.", parent=self)
                return
            if not PYMUPDF_INSTALLED: # Double check dependency
                show_error_dialog("Error", "PyMuPDF (fitz) is required for Visual Q&A.", parent=self)
                return
            if save_direct and (not anki_media_dir or not os.path.isdir(anki_media_dir)):
                show_error_dialog("Error", "Direct image save is enabled, but the Anki media path is invalid or not set.", parent=self)
                return
            # Optional: Confirm non-standard media path if saving directly
            if save_direct and os.path.basename(anki_media_dir).lower() != "collection.media":
                 if not ask_yes_no("Confirm Path",
                                   f"Direct save path '{os.path.basename(anki_media_dir)}' doesn't end in 'collection.media'.\nProceed anyway?",
                                   parent=self):
                     return # User cancelled

            # Determine final image destination path
            image_destination_path = anki_media_dir if save_direct else tsv_output_dir # If not direct, subfolder created inside tsv_output_dir by generate_page_images
            self.log_status(f"Image destination determined: {image_destination_path}", "debug")

            # Prepare args for the visual processing thread
            args = (input_file, tsv_output_dir, safe_base_name, image_destination_path, api_key, model_name, prompt_text, save_direct)
            target_func = self._run_visual_processing_thread

        else: # Text Analysis
            prompt_text = self.p2_book_processing_prompt_var.get()
            try: # Validate chunk/delay parameters
                chunk_size = self.p2_text_chunk_size.get()
                api_delay = self.p2_text_api_delay.get()
                if chunk_size <= 0:
                    show_error_dialog("Error", "Text Chunk Size must be greater than 0.", parent=self)
                    return
                if api_delay < 0:
                    # Allow 0 delay, but correct negative values
                    self.p2_text_api_delay.set(0.0)
                    show_info_dialog("Warning", "Negative Text API Delay detected. Using 0 seconds.", parent=self)
                    api_delay = 0.0
            except tk.TclError: # Catch non-integer/float inputs
                show_error_dialog("Error", "Invalid input for Text Chunk Size or API Delay. Please enter numbers.", parent=self)
                return

            if not prompt_text:
                show_error_dialog("Error", "Book Processing prompt cannot be empty.", parent=self)
                return
            # Check dependency if PDF is input for text analysis
            if input_file.lower().endswith(".pdf") and not PYMUPDF_INSTALLED:
                show_error_dialog("Error", "PyMuPDF (fitz) is required for PDF text analysis.", parent=self)
                return

            # Prepare args for the text analysis thread
            args = (input_file, tsv_output_dir, api_key, model_name, prompt_text, safe_base_name, chunk_size, api_delay)
            target_func = self._run_text_analysis_thread

        # --- Start Thread ---
        self.p2_is_processing = True
        # Update UI to indicate processing started
        try:
            if hasattr(self, 'p2_run_button') and self.p2_run_button.winfo_exists():
                self.p2_run_button.config(state="disabled", text="Processing...", bg='orange')
            # Clear previous status log
            if hasattr(self, 'p2_status_text') and self.p2_status_text.winfo_exists():
                self.p2_status_text.config(state="normal")
                self.p2_status_text.delete('1.0', tk.END)
                self.p2_status_text.config(state="disabled")
        except tk.TclError:
            pass # Ignore if widgets are gone

        self.log_status(f"Starting {selected_type} processing workflow...")
        # Create and start the background thread
        thread = threading.Thread(target=target_func, args=args, daemon=True)
        thread.start()

    # --- THREAD TARGETS ---

    def _run_visual_processing_thread(self, pdf_path, tsv_output_dir, safe_base_name,
                                       image_destination_path, api_key, model_name,
                                       prompt_text, save_direct_flag):
        """Background thread for VISUAL Q&A workflow."""
        success = False
        uploaded_file_uri = None
        tsv_file_path = None
        parsed_data = None
        try:
            # === Step 1a: Generate Page Images ===
            self.after(0, self.log_status, "Step 1a (Visual): Generating Page Images...", "step")
            # generate_page_images handles subfolder creation if save_direct_flag is False
            img_folder, self.p2_page_image_map = generate_page_images(
                pdf_path, image_destination_path, safe_base_name, save_direct_flag, self.log_status, parent_widget=self
            )
            if img_folder is None:
                raise ProcessingError("Image generation failed.")
            self.p2_image_output_folder_final = img_folder # Store the actual path where images were saved
            self.after(0, self.log_status, f"Step 1a Complete. Images in: {self.p2_image_output_folder_final}", "info")

            # === Step 1b: Invoke Gemini for JSON Extraction ===
            self.after(0, self.log_status, f"Step 1b (Visual): Gemini JSON Extraction ({model_name})...", "step")
            # call_gemini_visual_extraction handles incremental saving internally if needed
            parsed_data, uploaded_file_uri = call_gemini_visual_extraction(
                pdf_path, api_key, model_name, prompt_text, self.log_status, parent_widget=self
            )
            if parsed_data is None: # Check for None specifically, [] is valid (no pairs found)
                raise ProcessingError("Gemini PDF visual extraction failed (check logs/temp files).")
            if not parsed_data: # Log if the list is empty
                self.after(0, self.log_status, "Gemini extraction yielded no Q&A pairs.", "warning")
            self.after(0, self.log_status, "Step 1b Complete.", "info")

            # === Step 1c: Save Intermediate JSON ===
            self.after(0, self.log_status, "Step 1c (Visual): Saving intermediate JSON data...", "step")
            intermediate_json_path = os.path.join(tsv_output_dir, f"{safe_base_name}_intermediate_visual.json")
            try:
                # Add metadata needed for potential TSV generation later (in Page 3 or 4)
                # This might be redundant if Page 3 doesn't use it, but good for consistency
                for item in parsed_data:
                    if isinstance(item, dict):
                        item['_page_image_map'] = self.p2_page_image_map # Map page numbers to image filenames
                        item['_source_pdf_prefix'] = safe_base_name # Store the base name for reference
                # Save the data
                with open(intermediate_json_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, indent=2)
                self.after(0, self.log_status, f"Saved intermediate JSON: {os.path.basename(intermediate_json_path)}", "info")
            except Exception as json_e:
                raise ProcessingError(f"Failed to save intermediate JSON: {json_e}")
            self.after(0, self.log_status, "Step 1c Complete.", "info")

            # === Success ===
            success = True
            self.after(0, self.log_status, "Visual Q&A extraction completed successfully!", "info")

            # Prepare success message
            success_message = f"Visual Q&A Extraction Complete!\n\nIntermediate JSON File:\n{intermediate_json_path}\n\n"
            if save_direct_flag:
                success_message += f"Images Saved Directly To:\n{self.p2_image_output_folder_final}"
            else:
                success_message += f"Images Saved To Subfolder:\n{self.p2_image_output_folder_final}\n\n"
                success_message += f"IMPORTANT: Manually copy images from\n'{os.path.basename(self.p2_image_output_folder_final)}' into Anki's 'collection.media' folder if needed."

            # Show success dialog and ask to switch page
            self.after(0, show_info_dialog, "Extraction Success", success_message, self)
            if intermediate_json_path and os.path.exists(intermediate_json_path):
                 if ask_yes_no("Proceed to Tagging?", f"Created intermediate JSON.\nSwitch to 'Tag TSV File' page and load this JSON file for tagging?", parent=self):
                     self.after(0, self.app.switch_to_page, 2, intermediate_json_path) # Switch to Page 3 (index 2) with JSON path
            elif not parsed_data: # Handle case where no data was extracted
                 self.after(0, self.log_status, "No Q&A data extracted, skipping tagging prompt.", "info")

        except (ProcessingError, WorkflowStepError) as pe:
            # Log and show specific workflow errors
            self.after(0, self.log_status, f"Visual workflow halted: {pe}", "error")
            self.after(0, show_error_dialog, "Workflow Error", f"Workflow failed: {pe}", self)
            success = False
        except Exception as e:
            # Log and show unexpected errors
            error_msg = f"Unexpected error: {type(e).__name__}: {e}"
            self.after(0, self.log_status, f"FATAL ERROR (Visual): {error_msg}\n{traceback.format_exc()}", "error")
            self.after(0, show_error_dialog, "Unexpected Error", f"An unexpected error occurred:\n{error_msg}", self)
            success = False
        finally:
            # Cleanup uploaded file if necessary
            if uploaded_file_uri:
                 try:
                     cleanup_gemini_file(uploaded_file_uri, api_key, self.log_status)
                 except Exception as clean_e:
                     self.after(0, self.log_status, f"Error during Gemini file cleanup: {clean_e}", "warning")
            # Signal processing finished (success or failure)
            self.after(0, self._processing_finished, success)

    def _run_text_analysis_thread(self, input_file_path, tsv_output_dir, api_key, model_name, prompt_text,
                                  safe_base_name, chunk_size, api_delay):
        """Background thread for TEXT ANALYSIS workflow."""
        success = False
        # tsv_file_path = None # No longer generating TSV here
        parsed_data = None
        intermediate_json_path = None # Will be set by call_gemini_text_analysis
        try:
            self.after(0, self.log_status, f"Starting Text Analysis for: {os.path.basename(input_file_path)}", "info")

            # === Step 1a: Extract Text Content ===
            self.after(0, self.log_status, "Step 1a (Text): Extracting text content...", "step")
            extracted_text = ""
            file_type = ""
            if input_file_path.lower().endswith(".pdf"):
                extracted_text = extract_text_from_pdf(input_file_path, self.log_status)
                file_type = "PDF"
            elif input_file_path.lower().endswith(".txt"):
                extracted_text = read_text_file(input_file_path, self.log_status)
                file_type = "TXT"
            else:
                raise ProcessingError("Unsupported file type for text analysis.")

            if extracted_text is None: # Check for None return on error
                raise ProcessingError(f"Text extraction failed for {file_type}.")
            if not extracted_text.strip(): # Check if extracted text is empty/whitespace
                self.after(0, self.log_status, "No text content extracted from the file. Workflow finished.", "warning")
                # Consider this a "success" in terms of workflow completion, though no output generated
                success = True
                self.after(0, self._processing_finished, success)
                return # Stop the thread

            self.after(0, self.log_status, f"Step 1a Complete. Extracted ~{len(extracted_text)} characters.", "info")

            # === Step 1b: Invoke Gemini for Text Analysis (uses chunking API func) ===
            self.after(0, self.log_status, f"Step 1b (Text): Calling Gemini ({model_name}) in chunks...", "step")
            # call_gemini_text_analysis handles chunking and incremental saving internally
            parsed_data = call_gemini_text_analysis(
                extracted_text, api_key, model_name, prompt_text, self.log_status,
                tsv_output_dir, safe_base_name, # Pass output dir and base name for saving temp JSON
                chunk_size, api_delay, # Pass chunking params
                parent_widget=self
            )
            if parsed_data is None: # Check for None on failure
                raise ProcessingError("Failed during Gemini text analysis (check logs/temp files).")
            if not parsed_data: # Log if list is empty
                self.after(0, self.log_status, "Gemini analysis yielded no Q&A pairs.", "warning")
            self.after(0, self.log_status, "Step 1b Complete (Gemini chunk processing).", "info")
            # The intermediate JSON (_text_analysis_final.json) is saved internally by call_gemini_text_analysis

            # === Step 1c: (Removed TSV Generation) ===
            # TSV generation is now deferred to Page 3 after tagging.

            # === Success ===
            success = True
            self.after(0, self.log_status, "Text Analysis extraction completed successfully!", "info")

            # Find the path to the intermediate JSON saved by the API call
            intermediate_json_path = os.path.join(tsv_output_dir, f"{safe_base_name}_text_analysis_final.json")

            # Prepare and show success message
            if os.path.exists(intermediate_json_path):
                success_message = f"Text Analysis Extraction Complete!\n\nIntermediate JSON File Saved To:\n{intermediate_json_path}"
                self.after(0, show_info_dialog, "Extraction Success", success_message, self)
            else:
                # Should not happen if call_gemini_text_analysis succeeded, but handle defensively
                self.after(0, self.log_status, f"Intermediate JSON file not found at expected path: {intermediate_json_path}", "warning")
                self.after(0, show_info_dialog, "Extraction Success", "Text analysis extraction complete, but intermediate JSON file was not found.", self)


            # Ask to switch page
            if intermediate_json_path and os.path.exists(intermediate_json_path):
                if ask_yes_no("Proceed to Tagging?", f"Created intermediate JSON.\nSwitch to 'Tag TSV File' page and load this JSON file for tagging?", parent=self):
                     self.after(0, self.app.switch_to_page, 2, intermediate_json_path) # Switch to Page 3 (index 2) with JSON path
            elif not parsed_data: # Handle case where no data was extracted
                 self.after(0, self.log_status, "No Q&A data extracted, skipping tagging prompt.", "info")


        except (ProcessingError, WorkflowStepError) as pe:
            # Log and show specific workflow errors
            self.after(0, self.log_status, f"Text analysis workflow halted: {pe}", "error")
            self.after(0, show_error_dialog, "Workflow Error", f"Workflow failed: {pe}", self)
            success = False
        except Exception as e:
            # Log and show unexpected errors
            error_msg = f"Unexpected error: {type(e).__name__}: {e}"
            self.after(0, self.log_status, f"FATAL ERROR (Text): {error_msg}\n{traceback.format_exc()}", "error")
            self.after(0, show_error_dialog, "Unexpected Error", f"An unexpected error occurred:\n{error_msg}", self)
            success = False
        finally:
            # Signal processing finished
            self.after(0, self._processing_finished, success)
