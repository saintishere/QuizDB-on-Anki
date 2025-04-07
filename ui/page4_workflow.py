# ui/page4_workflow.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, BooleanVar, StringVar, IntVar
import os
import threading
import traceback
import time
import json # Added for JSON handling
from datetime import datetime
import shutil

# Use relative imports ONLY
# Assuming these imports are correct based on your project structure
try:
    from ..constants import (DEFAULT_VISUAL_MODEL, VISUAL_CAPABLE_MODELS, DEFAULT_MODEL, GEMINI_UNIFIED_MODELS,
                             DEFAULT_VISUAL_EXTRACTION_PROMPT, DEFAULT_BOOK_PROCESSING_PROMPT,
                             DEFAULT_BATCH_TAGGING_PROMPT, PYMUPDF_INSTALLED, DEFAULT_SECOND_PASS_MODEL)
    from ..prompts import (VISUAL_EXTRACTION, BOOK_PROCESSING, BATCH_TAGGING, SECOND_PASS_TAGGING)
    from ..utils.helpers import (ProcessingError, WorkflowStepError, sanitize_filename,
                             show_error_dialog, show_info_dialog, ask_yes_no, save_tsv_incrementally) # Added save_tsv_incrementally
    from ..core.anki_connect import detect_anki_media_path, guess_anki_media_initial_dir
    # Import the correct functions from file_processor
    from ..core.file_processor import (generate_page_images, extract_text_from_pdf,
                                       read_text_file, generate_tsv_visual, generate_tsv_text_analysis,
                                       generate_tsv_from_json_data) # Make sure this is imported
    # Import the correct functions from gemini_api
    from ..core.gemini_api import (call_gemini_visual_extraction, call_gemini_text_analysis,
                                   cleanup_gemini_file, tag_tsv_rows_gemini, # Corrected name
                                   configure_gemini, save_json_incrementally)
except ImportError as e:
    # Fallback for running the script directly or if relative imports fail
    print(f"Warning: Relative import failed ({e}). This might happen if running the script directly. Ensure it's run as part of the package.")
    # Add alternative import paths or handle the error as needed for standalone execution/testing
    # For now, we'll let it proceed, but functionality might be limited.
    PYMUPDF_INSTALLED = False # Assume false if imports fail
    # Define dummy constants/functions if needed for basic UI loading without full functionality
    DEFAULT_VISUAL_MODEL, VISUAL_CAPABLE_MODELS, DEFAULT_MODEL, GEMINI_UNIFIED_MODELS = "gemini-pro-vision", ["gemini-pro-vision"], "gemini-pro", ["gemini-pro"]
    DEFAULT_VISUAL_EXTRACTION_PROMPT, DEFAULT_BOOK_PROCESSING_PROMPT, DEFAULT_BATCH_TAGGING_PROMPT, DEFAULT_SECOND_PASS_MODEL = "Extract Q&A", "Analyze Text", "Tag Data", "gemini-pro"
    VISUAL_EXTRACTION, BOOK_PROCESSING, BATCH_TAGGING, SECOND_PASS_TAGGING = "Extract Q&A", "Analyze Text", "Tag Data", "Second Pass Tag"
    def show_error_dialog(title, msg, parent=None): print(f"ERROR: {title} - {msg}")
    def show_info_dialog(title, msg, parent=None): print(f"INFO: {title} - {msg}")
    def ask_yes_no(title, msg, parent=None): print(f"ASK: {title} - {msg}"); return False
    def sanitize_filename(name): return name.replace(" ", "_")
    def detect_anki_media_path(parent_for_dialog=None): return None
    def guess_anki_media_initial_dir(): return os.path.expanduser("~")
    def generate_page_images(*args, **kwargs): print("WARN: generate_page_images unavailable"); return None, {}
    def extract_text_from_pdf(*args, **kwargs): print("WARN: extract_text_from_pdf unavailable"); return None
    def read_text_file(*args, **kwargs): print("WARN: read_text_file unavailable"); return None
    def generate_tsv_from_json_data(*args, **kwargs): print("WARN: generate_tsv_from_json_data unavailable"); return False
    def call_gemini_visual_extraction(*args, **kwargs): print("WARN: call_gemini_visual_extraction unavailable"); return None, None
    def call_gemini_text_analysis(*args, **kwargs): print("WARN: call_gemini_text_analysis unavailable"); return None
    def cleanup_gemini_file(*args, **kwargs): print("WARN: cleanup_gemini_file unavailable")
    def tag_tsv_rows_gemini(*args, **kwargs): print("WARN: tag_tsv_rows_gemini unavailable"); yield ["Error", "Function Unavailable"]; return # Yield header and exit
    class WorkflowStepError(Exception): pass


class WorkflowPage(ttk.Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance

        # --- Page 4 Variables ---
        self.p4_wf_processing_type = StringVar(value="Visual Q&A (PDF)")
        self.p4_wf_input_file_path = StringVar()
        self.p4_wf_is_bulk_mode = BooleanVar(value=False)
        self.p4_wf_input_file_paths = []
        self.p4_wf_save_directly_to_media = BooleanVar(value=False)
        self.p4_wf_anki_media_path = StringVar()
        self.p4_wf_extraction_model = StringVar(value=DEFAULT_VISUAL_MODEL)
        self.p4_wf_tagging_model = StringVar(value=DEFAULT_MODEL) # Pass 1
        self.p4_wf_tagging_batch_size = IntVar(value=10)
        self.p4_wf_tagging_api_delay = tk.DoubleVar(value=10.0)
        self.p4_wf_text_chunk_size = IntVar(value=30000)
        self.p4_wf_text_api_delay = tk.DoubleVar(value=5.0)
        self.p4_wf_visual_extraction_prompt_var = StringVar(value=VISUAL_EXTRACTION)
        self.p4_wf_book_processing_prompt_var = StringVar(value=BOOK_PROCESSING)
        self.p4_wf_tagging_prompt_var = StringVar(value=BATCH_TAGGING) # Pass 1
        self.p4_wf_enable_second_pass = BooleanVar(value=False)
        self.p4_wf_second_pass_model = StringVar(value=DEFAULT_SECOND_PASS_MODEL)
        self.p4_wf_second_pass_prompt_var = StringVar(value=SECOND_PASS_TAGGING)
        self.p4_wf_progress_var = tk.DoubleVar(value=0)
        self.p4_wf_is_processing = False

        # --- Instance variables for UI elements needed across methods ---
        self.left_frame = None # Will be assigned in _build_ui

        # --- Build UI ---
        self._build_ui()

        # --- Initial UI state ---
        self._toggle_bulk_mode()
        self._update_ui_for_processing_type()
        self._toggle_media_path_entry()
        self._toggle_second_pass_widgets() # Ensure initial state is correct

        # Handle PyMuPDF dependency check after initial UI setup
        if not PYMUPDF_INSTALLED:
            if hasattr(self, 'p4_wf_visual_qa_radio'):
                self.p4_wf_visual_qa_radio.config(state="disabled")
            if self.p4_wf_processing_type.get() == "Visual Q&A (PDF)":
                self.p4_wf_processing_type.set("Text Analysis (PDF/TXT)")
                self.log_status("PyMuPDF not found. Switched to Text Analysis workflow.", "warning")
                self._update_ui_for_processing_type()

        print("Initialized WorkflowPage")

    # --- UI Build and Control Logic ---
    def _build_ui(self):
        """Initialize the Full Workflow page with a two-column layout."""
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1); main_frame.grid_columnconfigure(1, weight=2)
        main_frame.grid_rowconfigure(0, weight=1); main_frame.grid_rowconfigure(1, weight=0)

        # Assign left_frame to instance variable
        self.left_frame = ttk.Frame(main_frame); self.left_frame.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")
        right_frame = ttk.Frame(main_frame); right_frame.grid(row=0, column=1, padx=(10, 0), pady=5, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1); right_frame.grid_rowconfigure(1, weight=1); right_frame.grid_rowconfigure(2, weight=1); right_frame.grid_rowconfigure(3, weight=1); right_frame.grid_columnconfigure(0, weight=1)
        bottom_frame = ttk.Frame(main_frame); bottom_frame.grid(row=1, column=0, columnspan=2, padx=0, pady=(10, 0), sticky="ew"); bottom_frame.grid_columnconfigure(0, weight=1)

        # --- Left Column Widgets ---
        bulk_toggle_frame = ttk.Frame(self.left_frame); bulk_toggle_frame.pack(fill=tk.X, pady=(0, 10))
        self.p4_wf_bulk_mode_check = ttk.Checkbutton(bulk_toggle_frame, text="Enable Bulk PDF Processing Mode", variable=self.p4_wf_is_bulk_mode, command=self._toggle_bulk_mode); self.p4_wf_bulk_mode_check.pack(side=tk.LEFT, padx=5, pady=5)
        self.p4_type_frame = ttk.LabelFrame(self.left_frame, text="0. Select Workflow Type"); self.p4_type_frame.pack(fill=tk.X, pady=5)
        self.p4_wf_visual_qa_radio = ttk.Radiobutton(self.p4_type_frame, text="Visual Q&A (PDF)", variable=self.p4_wf_processing_type, value="Visual Q&A (PDF)", command=self._update_ui_for_processing_type, state="disabled"); self.p4_wf_visual_qa_radio.pack(side=tk.LEFT, padx=10, pady=5)
        self.p4_wf_text_analysis_radio = ttk.Radiobutton(self.p4_type_frame, text="Text Analysis (PDF/TXT)", variable=self.p4_wf_processing_type, value="Text Analysis (PDF/TXT)", command=self._update_ui_for_processing_type); self.p4_wf_text_analysis_radio.pack(side=tk.LEFT, padx=10, pady=5)
        self.p4_input_frame = ttk.LabelFrame(self.left_frame, text="1. Select Input File(s)"); self.p4_input_frame.pack(fill=tk.X, pady=5); self.p4_input_frame.grid_columnconfigure(1, weight=1)
        self.p4_wf_input_label_single = tk.Label(self.p4_input_frame, text="Input File:"); self.p4_wf_input_label_single.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_input_file_entry = tk.Entry(self.p4_input_frame, textvariable=self.p4_wf_input_file_path, width=40, state="readonly"); self.p4_wf_input_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.p4_wf_browse_button_single = tk.Button(self.p4_input_frame, text="Browse...", command=self._select_input_file_single); self.p4_wf_browse_button_single.grid(row=0, column=2, padx=5, pady=5)

        # Bulk Input List Frame setup
        self.p4_wf_bulk_input_list_frame = ttk.Frame(self.p4_input_frame)
        self.p4_wf_bulk_input_list_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        self.p4_wf_bulk_input_list_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_bulk_input_list_frame.grid_rowconfigure(0, weight=1)
        self.p4_wf_bulk_files_listbox = tk.Listbox(self.p4_wf_bulk_input_list_frame, selectmode=tk.EXTENDED, height=4) # Parent is list_frame now
        self.p4_wf_bulk_files_listbox.grid(row=0, column=0, sticky="nsew") # Grid within list_frame
        bulk_scrollbar = ttk.Scrollbar(self.p4_wf_bulk_input_list_frame, orient=tk.VERTICAL, command=self.p4_wf_bulk_files_listbox.yview); bulk_scrollbar.grid(row=0, column=1, sticky="ns"); self.p4_wf_bulk_files_listbox.config(yscrollcommand=bulk_scrollbar.set)
        bulk_button_frame = ttk.Frame(self.p4_wf_bulk_input_list_frame); bulk_button_frame.grid(row=0, column=2, sticky="ns", padx=(5,0))
        self.p4_wf_browse_button_bulk = tk.Button(bulk_button_frame, text="Select PDFs...", command=self._select_input_files_bulk); self.p4_wf_browse_button_bulk.pack(pady=2, fill=tk.X)
        self.p4_wf_clear_button_bulk = tk.Button(bulk_button_frame, text="Clear List", command=self._clear_bulk_files_list); self.p4_wf_clear_button_bulk.pack(pady=2, fill=tk.X)
        self.p4_wf_bulk_input_list_frame.grid_remove() # Hide initially

        self.p4_wf_image_output_frame = ttk.LabelFrame(self.left_frame, text="2. Image Output Location (Visual Q&A)"); # Packed conditionally later
        self.p4_wf_image_output_frame.grid_columnconfigure(1, weight=1)
        self.p4_wf_save_direct_check = tk.Checkbutton(self.p4_wf_image_output_frame, text="Save Images Directly to Anki collection.media", variable=self.p4_wf_save_directly_to_media, command=self._toggle_media_path_entry); self.p4_wf_save_direct_check.grid(row=0, column=0, columnspan=3, padx=5, pady=(5,0), sticky="w")
        self.p4_wf_anki_media_label = tk.Label(self.p4_wf_image_output_frame, text="Anki Media Path:"); self.p4_wf_anki_media_label.grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.p4_wf_anki_media_entry = tk.Entry(self.p4_wf_image_output_frame, textvariable=self.p4_wf_anki_media_path, width=40, state="disabled"); self.p4_wf_anki_media_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        self.p4_wf_browse_anki_media_button = tk.Button(self.p4_wf_image_output_frame, text="Browse...", command=self._select_anki_media_dir, state="disabled"); self.p4_wf_browse_anki_media_button.grid(row=1, column=2, padx=5, pady=2)
        self.p4_wf_detect_anki_media_button = tk.Button(self.p4_wf_image_output_frame, text="Detect via AnkiConnect", command=self._detect_anki_media_path, state="normal"); self.p4_wf_detect_anki_media_button.grid(row=2, column=1, padx=5, pady=(0,5), sticky="w")

        # Configuration Frame - assign to instance variable for reference
        self.p4_wf_config_frame = ttk.LabelFrame(self.left_frame, text="3. Workflow Configuration");
        self.p4_wf_config_frame.pack(fill=tk.BOTH, pady=5, expand=True);
        self.p4_wf_config_frame.grid_columnconfigure(1, weight=1); self.p4_wf_config_frame.grid_columnconfigure(3, weight=1)

        # Pack image output frame *before* config frame if needed initially
        # This will be managed by _update_ui_for_processing_type
        # self.p4_wf_image_output_frame.pack(fill=tk.X, pady=5, before=self.p4_wf_config_frame) # Initial pack if visual is default

        tk.Label(self.p4_wf_config_frame, text="API Key:").grid(row=0, column=0, padx=5, pady=2, sticky="w"); self.p4_wf_api_key_entry = tk.Entry(self.p4_wf_config_frame, textvariable=self.app.gemini_api_key, width=30, show="*"); self.p4_wf_api_key_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=2, sticky="ew"); self.p4_wf_show_key_button = tk.Button(self.p4_wf_config_frame, text="S/H", command=self.app.toggle_api_key_visibility, width=4); self.p4_wf_show_key_button.grid(row=0, column=4, padx=5, pady=2)
        self.p4_wf_step1_model_label = tk.Label(self.p4_wf_config_frame, text="Extraction/Analysis Model:"); self.p4_wf_step1_model_label.grid(row=1, column=0, columnspan=2, padx=5, pady=2, sticky="w"); self.p4_wf_extraction_model_dropdown = ttk.Combobox(self.p4_wf_config_frame, textvariable=self.p4_wf_extraction_model, values=VISUAL_CAPABLE_MODELS, state="readonly", width=25); current_extract_model = self.p4_wf_extraction_model.get();
        if current_extract_model in VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model_dropdown.set(current_extract_model)
        elif VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model_dropdown.set(VISUAL_CAPABLE_MODELS[0])
        self.p4_wf_extraction_model_dropdown.grid(row=1, column=2, columnspan=3, padx=5, pady=2, sticky="ew")
        tk.Label(self.p4_wf_config_frame, text="Tagging Model (Pass 1):").grid(row=2, column=0, columnspan=2, padx=5, pady=2, sticky="w"); self.p4_wf_tagging_model_dropdown = ttk.Combobox(self.p4_wf_config_frame, textvariable=self.p4_wf_tagging_model, values=GEMINI_UNIFIED_MODELS, state="readonly", width=25);
        if GEMINI_UNIFIED_MODELS and self.p4_wf_tagging_model.get() in GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(self.p4_wf_tagging_model.get())
        elif GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(GEMINI_UNIFIED_MODELS[0])
        self.p4_wf_tagging_model_dropdown.grid(row=2, column=2, columnspan=3, padx=5, pady=2, sticky="ew")
        self.p4_wf_second_pass_check = ttk.Checkbutton(self.p4_wf_config_frame, text="Enable Second Tagging Pass", variable=self.p4_wf_enable_second_pass, command=self._toggle_second_pass_widgets); self.p4_wf_second_pass_check.grid(row=3, column=0, columnspan=5, padx=5, pady=(5,0), sticky="w"); self.p4_wf_second_pass_model_label = tk.Label(self.p4_wf_config_frame, text="Tagging Model (Pass 2):"); self.p4_wf_second_pass_model_label.grid(row=4, column=0, columnspan=2, padx=5, pady=2, sticky="w"); self.p4_wf_second_pass_model_dropdown = ttk.Combobox(self.p4_wf_config_frame, textvariable=self.p4_wf_second_pass_model, values=GEMINI_UNIFIED_MODELS, state="disabled", width=25);
        if GEMINI_UNIFIED_MODELS and self.p4_wf_second_pass_model.get() in GEMINI_UNIFIED_MODELS: self.p4_wf_second_pass_model_dropdown.set(self.p4_wf_second_pass_model.get())
        elif GEMINI_UNIFIED_MODELS: self.p4_wf_second_pass_model_dropdown.set(GEMINI_UNIFIED_MODELS[0])
        self.p4_wf_second_pass_model_dropdown.grid(row=4, column=2, columnspan=3, padx=5, pady=2, sticky="ew")
        self.p4_wf_text_config_frame = ttk.Frame(self.p4_wf_config_frame); self.p4_wf_text_config_frame.grid(row=5, column=0, columnspan=5, sticky="ew"); tk.Label(self.p4_wf_text_config_frame, text="Text Chunk Size:").grid(row=0, column=0, padx=5, pady=2, sticky="w"); p4_wf_text_chunk_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_chunk_size, width=8); p4_wf_text_chunk_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w"); tk.Label(self.p4_wf_text_config_frame, text="Text API Delay(s):").grid(row=0, column=2, padx=5, pady=2, sticky="w"); p4_wf_text_delay_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_api_delay, width=6); p4_wf_text_delay_entry.grid(row=0, column=3, padx=5, pady=2, sticky="w")
        tk.Label(self.p4_wf_config_frame, text="Tag Batch Size:").grid(row=6, column=0, padx=5, pady=2, sticky="w"); p4_wf_tag_batch_entry = ttk.Entry(self.p4_wf_config_frame, textvariable=self.p4_wf_tagging_batch_size, width=8); p4_wf_tag_batch_entry.grid(row=6, column=1, padx=5, pady=2, sticky="w"); tk.Label(self.p4_wf_config_frame, text="Tag API Delay(s):").grid(row=6, column=2, padx=5, pady=2, sticky="w"); p4_wf_tag_delay_entry = ttk.Entry(self.p4_wf_config_frame, textvariable=self.p4_wf_tagging_api_delay, width=6); p4_wf_tag_delay_entry.grid(row=6, column=3, padx=5, pady=2, sticky="w")

        # --- Right Column Widgets (Prompts) ---
        self.p4_wf_visual_extract_prompt_frame = ttk.LabelFrame(right_frame, text="Visual Extraction Prompt (Step 1)"); self.p4_wf_visual_extract_prompt_frame.grid(row=0, column=0, padx=0, pady=(0,5), sticky="nsew"); self.p4_wf_visual_extract_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_visual_extract_prompt_frame.grid_columnconfigure(0, weight=1); self.p4_wf_visual_extraction_prompt_text = scrolledtext.ScrolledText(self.p4_wf_visual_extract_prompt_frame, wrap=tk.WORD, height=6); self.p4_wf_visual_extraction_prompt_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew"); self.p4_wf_visual_extraction_prompt_text.insert(tk.END, self.p4_wf_visual_extraction_prompt_var.get()); self.p4_wf_visual_extraction_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_visual_extract)
        self.p4_wf_text_analysis_prompt_frame = ttk.LabelFrame(right_frame, text="Text Analysis Prompt (Step 1)"); self.p4_wf_text_analysis_prompt_frame.grid(row=1, column=0, padx=0, pady=(0,5), sticky="nsew"); self.p4_wf_text_analysis_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_text_analysis_prompt_frame.grid_columnconfigure(0, weight=1); self.p4_wf_book_processing_prompt_text = scrolledtext.ScrolledText(self.p4_wf_text_analysis_prompt_frame, wrap=tk.WORD, height=6); self.p4_wf_book_processing_prompt_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew"); self.p4_wf_book_processing_prompt_text.insert(tk.END, self.p4_wf_book_processing_prompt_var.get()); self.p4_wf_book_processing_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_book_process)
        self.p4_wf_tagging_pass1_prompt_frame = ttk.LabelFrame(right_frame, text="Tagging Prompt (Pass 1)"); self.p4_wf_tagging_pass1_prompt_frame.grid(row=2, column=0, padx=0, pady=5, sticky="nsew"); self.p4_wf_tagging_pass1_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_tagging_pass1_prompt_frame.grid_columnconfigure(0, weight=1); self.p4_wf_tagging_prompt_text_editor = scrolledtext.ScrolledText(self.p4_wf_tagging_pass1_prompt_frame, wrap=tk.WORD, height=8); self.p4_wf_tagging_prompt_text_editor.grid(row=0, column=0, padx=5, pady=5, sticky="nsew"); self.p4_wf_tagging_prompt_text_editor.insert(tk.END, self.p4_wf_tagging_prompt_var.get()); self.p4_wf_tagging_prompt_text_editor.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag)
        self.p4_wf_tagging_pass2_prompt_frame = ttk.LabelFrame(right_frame, text="Tagging Prompt (Pass 2)"); self.p4_wf_tagging_pass2_prompt_frame.grid(row=3, column=0, padx=0, pady=(5,0), sticky="nsew"); self.p4_wf_tagging_pass2_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_tagging_pass2_prompt_frame.grid_columnconfigure(0, weight=1); self.p4_wf_second_pass_prompt_text_editor = scrolledtext.ScrolledText(self.p4_wf_tagging_pass2_prompt_frame, wrap=tk.WORD, height=8, state="disabled"); self.p4_wf_second_pass_prompt_text_editor.grid(row=0, column=0, padx=5, pady=5, sticky="nsew"); self.p4_wf_second_pass_prompt_text_editor.insert(tk.END, self.p4_wf_second_pass_prompt_var.get()); self.p4_wf_second_pass_prompt_text_editor.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag_pass2)

        # --- Bottom Frame Widgets ---
        self.p4_wf_run_button = tk.Button(bottom_frame, text="Run Workflow", command=self._start_workflow_thread, font=('Arial', 11, 'bold'), bg='lightyellow'); self.p4_wf_run_button.grid(row=0, column=0, columnspan=2, padx=10, pady=(5, 5), sticky="ew")
        status_frame = ttk.LabelFrame(bottom_frame, text="Workflow Status"); status_frame.grid(row=1, column=0, columnspan=2, padx=0, pady=(5,0), sticky="nsew"); status_frame.grid_rowconfigure(1, weight=1); status_frame.grid_columnconfigure(0, weight=1); self.p4_wf_progress_bar = ttk.Progressbar(status_frame, variable=self.p4_wf_progress_var, maximum=100); self.p4_wf_progress_bar.grid(row=0, column=0, padx=5, pady=(5,2), sticky="ew"); self.p4_wf_status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=6, state="disabled"); self.p4_wf_status_text.grid(row=1, column=0, padx=5, pady=(2,5), sticky="nsew")

    def _toggle_bulk_mode(self):
        """Updates UI elements based on whether Bulk Mode is enabled."""
        is_bulk = self.p4_wf_is_bulk_mode.get()
        try:
            if is_bulk:
                # Hide single file input widgets
                if hasattr(self, 'p4_wf_input_label_single'): self.p4_wf_input_label_single.grid_remove()
                if hasattr(self, 'p4_wf_input_file_entry'): self.p4_wf_input_file_entry.grid_remove()
                if hasattr(self, 'p4_wf_browse_button_single'): self.p4_wf_browse_button_single.grid_remove()
                # Show bulk file input widgets
                if hasattr(self, 'p4_wf_bulk_input_list_frame'): self.p4_wf_bulk_input_list_frame.grid() # Use grid() to show
                # Force settings for bulk mode
                self.p4_wf_processing_type.set("Visual Q&A (PDF)")
                if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="disabled")
                if hasattr(self, 'p4_wf_text_analysis_radio'): self.p4_wf_text_analysis_radio.config(state="disabled")
                # self.p4_wf_save_directly_to_media.set(True) # <-- REMOVED
                # if hasattr(self, 'p4_wf_save_direct_check'): self.p4_wf_save_direct_check.config(state="disabled") # <-- REMOVED
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(text="Run Bulk Visual Workflow")
            else:
                # Show single file input widgets
                if hasattr(self, 'p4_wf_input_label_single'): self.p4_wf_input_label_single.grid()
                if hasattr(self, 'p4_wf_input_file_entry'): self.p4_wf_input_file_entry.grid()
                if hasattr(self, 'p4_wf_browse_button_single'): self.p4_wf_browse_button_single.grid()
                # Hide bulk file input widgets
                if hasattr(self, 'p4_wf_bulk_input_list_frame'): self.p4_wf_bulk_input_list_frame.grid_remove()
                # Restore normal state for non-bulk mode
                if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")
                if hasattr(self, 'p4_wf_text_analysis_radio'): self.p4_wf_text_analysis_radio.config(state="normal")
                if hasattr(self, 'p4_wf_save_direct_check'): self.p4_wf_save_direct_check.config(state="normal")
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(text="Run Workflow") # Text updated later by _update_ui_for_processing_type

            # Update UI based on the (potentially changed) processing type and media save setting
            self._update_ui_for_processing_type()
            self._toggle_media_path_entry()

        except tk.TclError as e: print(f"P4 WF Bulk Toggle Warning: {e}")
        except AttributeError as e: print(f"P4 WF Bulk Toggle Warning (AttributeError): {e}")

    def _update_ui_for_processing_type(self):
        """Shows/hides UI elements based on selected processing type (Visual vs Text)."""
        selected_type = self.p4_wf_processing_type.get(); is_visual = selected_type == "Visual Q&A (PDF)"; is_bulk = self.p4_wf_is_bulk_mode.get()
        try:
            # Update input label text (only in single mode)
            if not is_bulk and hasattr(self, 'p4_wf_input_label_single'):
                self.p4_wf_input_label_single.config(text="Input PDF:" if is_visual else "Input File (PDF/TXT):")

            # Show/Hide Image Output Frame (using pack/pack_forget)
            # Ensure self.left_frame and self.p4_wf_config_frame are available
            if hasattr(self, 'p4_wf_image_output_frame') and self.left_frame and hasattr(self, 'p4_wf_config_frame'):
                if is_visual:
                    if not self.p4_wf_image_output_frame.winfo_ismapped():
                        # Pack the image frame *before* the config frame within the left_frame
                        self.p4_wf_image_output_frame.pack(in_=self.left_frame, fill=tk.X, pady=5, before=self.p4_wf_config_frame)
                else:
                    if self.p4_wf_image_output_frame.winfo_ismapped():
                        self.p4_wf_image_output_frame.pack_forget()
            elif not self.left_frame:
                 print("P4 WF UI Update Warning: self.left_frame not initialized yet.")
            elif not hasattr(self, 'p4_wf_config_frame'):
                 print("P4 WF UI Update Warning: self.p4_wf_config_frame not initialized yet.")


            # Show/Hide Prompt Frames (using grid/grid_remove)
            if hasattr(self, 'p4_wf_visual_extract_prompt_frame'):
                 if is_visual: self.p4_wf_visual_extract_prompt_frame.grid()
                 else: self.p4_wf_visual_extract_prompt_frame.grid_remove()
            if hasattr(self, 'p4_wf_text_analysis_prompt_frame'):
                 if not is_visual: self.p4_wf_text_analysis_prompt_frame.grid()
                 else: self.p4_wf_text_analysis_prompt_frame.grid_remove()

            # Update Step 1 Model Label and Dropdown options
            if hasattr(self, 'p4_wf_step1_model_label'): self.p4_wf_step1_model_label.config(text="Extraction/Analysis Model:")
            if hasattr(self, 'p4_wf_extraction_model_dropdown'):
                current_model = self.p4_wf_extraction_model.get()
                if is_visual:
                    self.p4_wf_extraction_model_dropdown.config(values=VISUAL_CAPABLE_MODELS)
                    # Update selection if current model is invalid for visual
                    if current_model not in VISUAL_CAPABLE_MODELS and VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model.set(VISUAL_CAPABLE_MODELS[0])
                    elif not VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model.set("")
                else:
                    self.p4_wf_extraction_model_dropdown.config(values=GEMINI_UNIFIED_MODELS)
                    # Update selection if current model is invalid for text
                    if current_model not in GEMINI_UNIFIED_MODELS and GEMINI_UNIFIED_MODELS: self.p4_wf_extraction_model.set(DEFAULT_MODEL if DEFAULT_MODEL in GEMINI_UNIFIED_MODELS else GEMINI_UNIFIED_MODELS[0])
                    elif not GEMINI_UNIFIED_MODELS: self.p4_wf_extraction_model.set("")

            # Show/Hide Text Config Frame (using grid/grid_remove)
            if hasattr(self, 'p4_wf_text_config_frame'): # Check existence
                if not is_visual:
                    if not self.p4_wf_text_config_frame.winfo_ismapped(): self.p4_wf_text_config_frame.grid() # Show if hidden
                elif self.p4_wf_text_config_frame.winfo_ismapped(): self.p4_wf_text_config_frame.grid_remove() # Hide if visible

            # Update Run Button Text (only in single mode)
            if not is_bulk and hasattr(self, 'p4_wf_run_button'):
                self.p4_wf_run_button.config(text="Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow")

            # Ensure Visual Q&A radio state is correct (only in single mode)
            if not is_bulk and hasattr(self, 'p4_wf_visual_qa_radio'):
                self.p4_wf_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")

        except tk.TclError as e: print(f"P4 WF UI Update Warning: {e}")
        except AttributeError as e: print(f"P4 WF UI Update Warning (AttributeError): {e}") # Catch potential errors if widgets aren't ready

    def _toggle_second_pass_widgets(self):
        """Enables/disables the second pass model and prompt widgets."""
        try:
            is_enabled = self.p4_wf_enable_second_pass.get()
            new_state_widget = tk.NORMAL if is_enabled else tk.DISABLED
            new_state_combo = 'readonly' if is_enabled else tk.DISABLED # Use readonly for combobox

            if hasattr(self, 'p4_wf_second_pass_model_label'): self.p4_wf_second_pass_model_label.config(state=new_state_widget)
            if hasattr(self, 'p4_wf_second_pass_model_dropdown'): self.p4_wf_second_pass_model_dropdown.config(state=new_state_combo)

            editor = getattr(self, 'p4_wf_second_pass_prompt_text_editor', None)
            frame = getattr(self, 'p4_wf_tagging_pass2_prompt_frame', None)

            if frame and frame.winfo_exists():
                 if is_enabled:
                     if not frame.winfo_ismapped():
                         frame.grid() # Ensure it's visible
                     if editor and editor.winfo_exists():
                         editor.config(state=tk.NORMAL)
                         # Force text update if needed (sometimes state change doesn't refresh content)
                         editor.delete('1.0', tk.END)
                         editor.insert('1.0', self.p4_wf_second_pass_prompt_var.get())
                         editor.edit_modified(False)
                 else:
                     if frame.winfo_ismapped():
                         frame.grid_remove() # Hide frame
                     if editor and editor.winfo_exists():
                         editor.config(state=tk.DISABLED)

        except tk.TclError as e: print(f"P4 WF Toggle Second Pass Warning: {e}")
        except AttributeError as e: print(f"P4 WF Toggle Second Pass Warning (AttributeError): {e}")


    # --- Prompt Sync Methods ---
    def _sync_prompt_var_from_editor_p4_visual_extract(self, event=None):
        try:
            if hasattr(self, 'p4_wf_visual_extraction_prompt_text') and self.p4_wf_visual_extraction_prompt_text.winfo_exists():
                 current_text = self.p4_wf_visual_extraction_prompt_text.get("1.0", tk.END).strip()
                 self.p4_wf_visual_extraction_prompt_var.set(current_text)
                 self.p4_wf_visual_extraction_prompt_text.edit_modified(False) # Reset modified flag
        except tk.TclError: pass # Ignore errors if widget is destroyed during sync
    def _sync_prompt_var_from_editor_p4_book_process(self, event=None):
        try:
            if hasattr(self, 'p4_wf_book_processing_prompt_text') and self.p4_wf_book_processing_prompt_text.winfo_exists():
                 current_text = self.p4_wf_book_processing_prompt_text.get("1.0", tk.END).strip()
                 self.p4_wf_book_processing_prompt_var.set(current_text)
                 self.p4_wf_book_processing_prompt_text.edit_modified(False) # Reset modified flag
        except tk.TclError: pass
    def _sync_prompt_var_from_editor_p4_tag(self, event=None):
        try:
            widget = self.p4_wf_tagging_prompt_text_editor
            if widget and widget.winfo_exists():
                 current_text = widget.get("1.0", tk.END).strip()
                 self.p4_wf_tagging_prompt_var.set(current_text)
                 widget.edit_modified(False) # Reset modified flag
        except tk.TclError: pass
    def _sync_prompt_var_from_editor_p4_tag_pass2(self, event=None):
        try:
            widget = self.p4_wf_second_pass_prompt_text_editor
            if widget and widget.winfo_exists():
                 current_text = widget.get("1.0", tk.END).strip()
                 self.p4_wf_second_pass_prompt_var.set(current_text)
                 widget.edit_modified(False) # Reset modified flag
        except tk.TclError: pass

    # --- Logging ---
    def log_status(self, message, level="info"):
        """Logs messages to the status ScrolledText on this page."""
        try:
            if not hasattr(self, 'p4_wf_status_text') or not self.p4_wf_status_text.winfo_exists():
                print(f"P4 WF Status Log (No Widget): {message}")
                return

            self.p4_wf_status_text.config(state="normal")
            prefix_map = {"info": "[INFO] ", "step": "[STEP] ", "warning": "[WARN] ", "error": "[ERROR] ", "upload": "[UPLOAD] ", "debug": "[DEBUG] ", "skip": "[SKIP] "}
            prefix = prefix_map.get(level, "[INFO] ")
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.p4_wf_status_text.insert(tk.END, f"{timestamp} {prefix}{message}\n")
            self.p4_wf_status_text.see(tk.END) # Scroll to the end
            self.p4_wf_status_text.config(state="disabled")
            self.update_idletasks() # Ensure UI updates immediately

        except tk.TclError as e:
            # Fallback if widget becomes unavailable during logging
            print(f"P4 WF Status Log (backup): {message} (Error: {e})")
        except Exception as e:
            print(f"Unexpected error in P4 WF log_status: {e}")

    # --- File/Directory Selection ---
    def _select_input_file_single(self):
        """Handles browsing for a single input file."""
        selected_type = self.p4_wf_processing_type.get()
        if selected_type == "Visual Q&A (PDF)":
            filetypes = (("PDF files", "*.pdf"), ("All files", "*.*"))
            title = "Select Input PDF for Visual Q&A Workflow"
        else: # Text Analysis
            filetypes = (("Text files", "*.txt"), ("PDF files", "*.pdf"), ("All files", "*.*"))
            title = "Select Input File for Text Analysis Workflow (PDF/TXT)"

        filepath = filedialog.askopenfilename(parent=self, title=title, filetypes=filetypes)
        if filepath:
            is_pdf = filepath.lower().endswith(".pdf")
            is_txt = filepath.lower().endswith(".txt")

            # Validate file type based on workflow
            if selected_type == "Visual Q&A (PDF)" and not is_pdf:
                show_error_dialog("Invalid File", "Visual Q&A workflow requires a PDF file.", parent=self)
                return
            if selected_type == "Text Analysis (PDF/TXT)" and not (is_pdf or is_txt):
                show_error_dialog("Invalid File", "Text Analysis workflow requires a PDF or TXT file.", parent=self)
                return
            # Validate dependency for PDF text extraction
            if selected_type == "Text Analysis (PDF/TXT)" and is_pdf and not PYMUPDF_INSTALLED:
                show_error_dialog("Dependency Missing", "Processing PDF text requires PyMuPDF (fitz).\nPlease install it: pip install PyMuPDF", parent=self)
                return

            self.p4_wf_input_file_path.set(filepath)
            self.log_status(f"Selected input file: {os.path.basename(filepath)}")
        else:
            self.log_status("Input file selection cancelled.")

    def _select_input_files_bulk(self):
        """Handles browsing for multiple PDF files for bulk mode."""
        filepaths = filedialog.askopenfilenames(parent=self, title="Select PDF Files for Bulk Processing", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if filepaths:
            self.p4_wf_input_file_paths = list(filepaths) # Store full paths
            if hasattr(self, 'p4_wf_bulk_files_listbox'):
                self.p4_wf_bulk_files_listbox.delete(0, tk.END) # Clear existing list
                skipped_count = 0
                valid_paths = []
                for fp in self.p4_wf_input_file_paths:
                    if fp.lower().endswith(".pdf"):
                        self.p4_wf_bulk_files_listbox.insert(tk.END, os.path.basename(fp)) # Display only basename
                        valid_paths.append(fp)
                    else:
                        skipped_count += 1
                        self.log_status(f"Skipped non-PDF file: {os.path.basename(fp)}", level="skip")
                self.p4_wf_input_file_paths = valid_paths # Update internal list to only valid PDFs
                log_msg = f"Selected {len(self.p4_wf_input_file_paths)} PDF files for bulk processing."
                if skipped_count > 0:
                    log_msg += f" Skipped {skipped_count} non-PDF files."
                self.log_status(log_msg)
            else:
                # Fallback log if listbox somehow doesn't exist
                 self.log_status(f"Selected {len(self.p4_wf_input_file_paths)} PDF files (listbox not found).")
        else:
            self.log_status("Bulk file selection cancelled.")

    def _clear_bulk_files_list(self):
        """Clears the list of files selected for bulk processing."""
        self.p4_wf_input_file_paths = [] # Clear internal list
        if hasattr(self, 'p4_wf_bulk_files_listbox'):
            self.p4_wf_bulk_files_listbox.delete(0, tk.END) # Clear UI listbox
        self.log_status("Cleared bulk file list.")

    def _toggle_media_path_entry(self):
        """Enables/disables the Anki media path entry and browse button."""
        try:
            is_direct_save = self.p4_wf_save_directly_to_media.get()
            is_bulk = self.p4_wf_is_bulk_mode.get()

            # Determine state based on whether direct save is checked OR bulk mode is on
            media_state = "normal" if (is_direct_save or is_bulk) else "disabled"
            detect_state = "normal" # Detect button is always enabled when the section is visible

            if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state=media_state)
            if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state=media_state)
            # Ensure detect button state is managed correctly (should usually be normal if visible)
            if hasattr(self, 'p4_wf_detect_anki_media_button') and self.p4_wf_detect_anki_media_button.winfo_exists():
                 self.p4_wf_detect_anki_media_button.config(state=detect_state) # Keep it enabled if visible

            # Log and potentially auto-detect path if enabled and empty
            if (is_direct_save or is_bulk):
                if not is_bulk: # Don't log this message repeatedly in bulk mode toggle
                    self.log_status("Workflow: Direct image save to Anki media enabled.", "info")
                # Attempt auto-detection if path is currently empty
                if not self.p4_wf_anki_media_path.get():
                    self._detect_anki_media_path() # Try to auto-populate
            elif not is_bulk: # Only log disable message if not in bulk mode
                 self.log_status("Workflow: Direct image save disabled. Images will be saved to a subfolder.", "info")

        except tk.TclError: pass # Ignore errors if widgets don't exist

    def _select_anki_media_dir(self):
        """Handles browsing for the Anki media directory."""
        initial_dir = self.p4_wf_anki_media_path.get() or guess_anki_media_initial_dir()
        dirpath = filedialog.askdirectory(parent=self, title="Select Anki 'collection.media' Folder (for Workflow)", initialdir=initial_dir)
        if dirpath:
            # Check if the selected folder name is exactly 'collection.media'
            if os.path.basename(dirpath).lower() != "collection.media":
                 # Ask for confirmation if it's not the expected name
                 if ask_yes_no("Confirm Path", f"Selected folder: '{os.path.basename(dirpath)}'.\nThis usually needs to be the 'collection.media' folder.\n\nIs this the correct path?", parent=self):
                     self.p4_wf_anki_media_path.set(dirpath)
                     self.log_status(f"Workflow: Set Anki media path (manual confirm): {dirpath}", "info")
                 else:
                     self.log_status("Workflow: Anki media path selection cancelled.", "info")
            else:
                 # Set the path if it is 'collection.media'
                 self.p4_wf_anki_media_path.set(dirpath)
                 self.log_status(f"Workflow: Selected Anki media path: {dirpath}", "info")
        else:
            self.log_status("Workflow: Anki media path selection cancelled.")

    def _detect_anki_media_path(self):
        """Attempts to detect the Anki media path using AnkiConnect."""
        self.log_status("Workflow: Detecting Anki media path via AnkiConnect...", "info")
        try:
            media_path = detect_anki_media_path(parent_for_dialog=self) # Pass self for potential dialogs
            if media_path:
                self.p4_wf_anki_media_path.set(media_path)
                self.log_status(f"Workflow: Detected Anki media path: {media_path}", "info")
                # Ensure widgets are enabled if detection was successful and needed
                if self.p4_wf_save_directly_to_media.get() or self.p4_wf_is_bulk_mode.get():
                    if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state="normal")
                    if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state="normal")
            else:
                 self.log_status("Workflow: AnkiConnect did not return a valid path.", "warning")
        except Exception as e:
            self.log_status(f"Workflow: Failed AnkiConnect path detection: {e}", "error")
            # Optionally show error dialog to user
            # show_error_dialog("AnkiConnect Error", f"Failed to detect media path via AnkiConnect:\n{e}", parent=self)


    # --- Workflow Execution ---
    def _start_workflow_thread(self):
        """Validates inputs and starts the appropriate workflow thread."""
        if self.p4_wf_is_processing:
            show_info_dialog("In Progress", "Workflow is already running.", parent=self)
            return

        # --- Gather Common Inputs ---
        is_bulk = self.p4_wf_is_bulk_mode.get()
        selected_type = self.p4_wf_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"
        api_key = self.app.gemini_api_key.get()
        step1_model = self.p4_wf_extraction_model.get()
        tag_model_pass1 = self.p4_wf_tagging_model.get()
        tag_prompt_pass1 = self.p4_wf_tagging_prompt_var.get()
        enable_second_pass = self.p4_wf_enable_second_pass.get()
        tag_model_pass2 = self.p4_wf_second_pass_model.get()
        tag_prompt_pass2 = self.p4_wf_second_pass_prompt_var.get()

        # --- Common Validations ---
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            show_error_dialog("Error", "Please enter your Gemini API Key.", parent=self); return
        if not step1_model:
            show_error_dialog("Error", f"Please select {'Visual Extraction' if is_visual else 'Text Analysis'} Model.", parent=self); return
        if not tag_model_pass1:
            show_error_dialog("Error", "Please select Tagging Model (Pass 1).", parent=self); return
        if not tag_prompt_pass1:
            show_error_dialog("Error", "Tagging prompt (Pass 1) cannot be empty.", parent=self); return
        if enable_second_pass:
            if not tag_model_pass2:
                show_error_dialog("Error", "Second Pass is enabled, but Pass 2 model is not selected.", parent=self); return
            if not tag_prompt_pass2:
                show_error_dialog("Error", "Second Pass is enabled, but Pass 2 prompt is empty.", parent=self); return
        try:
            tag_batch_size = self.p4_wf_tagging_batch_size.get()
            tag_api_delay = self.p4_wf_tagging_api_delay.get()
            if tag_batch_size <= 0:
                show_error_dialog("Error", "Tagging Batch size must be greater than 0.", parent=self); return
            if tag_api_delay < 0:
                self.p4_wf_tagging_api_delay.set(0.0) # Correct the value
                show_info_dialog("Warning", "Tagging API Delay cannot be negative. Setting to 0.", parent=self)
                tag_api_delay=0.0 # Use the corrected value
        except tk.TclError:
            show_error_dialog("Error", "Invalid input for Tagging Batch Size or Delay.", parent=self); return

        # --- Workflow Specific Logic and Validation ---
        target_func = None
        args = ()
        if is_bulk:
            # --- Bulk Mode Validation ---
            input_files = self.p4_wf_input_file_paths
            if not input_files:
                show_error_dialog("Error", "Bulk Mode: No PDF files selected in the list.", parent=self); return
            extract_prompt = self.p4_wf_visual_extraction_prompt_var.get()
            anki_media_dir = self.p4_wf_anki_media_path.get()
            if not extract_prompt:
                show_error_dialog("Error", "Visual Extraction prompt cannot be empty.", parent=self); return
            if not PYMUPDF_INSTALLED:
                show_error_dialog("Error", "PyMuPDF (fitz) is required for Bulk Visual Q&A workflow.", parent=self); return
            if not anki_media_dir or not os.path.isdir(anki_media_dir):
                show_error_dialog("Error", "Bulk Mode requires a valid Anki media path for direct image saving. Please set it.", parent=self); return
            # Warn if path doesn't look like collection.media, but allow proceeding
            if os.path.basename(anki_media_dir).lower() != "collection.media":
                 if not ask_yes_no("Confirm Path", f"Anki media path '{os.path.basename(anki_media_dir)}' doesn't end in 'collection.media'.\nProceed anyway?", parent=self): return

            output_dir = os.path.dirname(input_files[0]) if input_files else os.getcwd() # Use dir of first file
            args = (input_files, output_dir, api_key, step1_model, tag_model_pass1, extract_prompt, tag_prompt_pass1, anki_media_dir, tag_batch_size, tag_api_delay,
                    enable_second_pass, tag_model_pass2, tag_prompt_pass2)
            target_func = self._run_bulk_visual_workflow_thread

        else: # Single File Mode
            # --- Single File Validation ---
            input_file = self.p4_wf_input_file_path.get()
            if not input_file or not os.path.exists(input_file):
                show_error_dialog("Error", "Please select a valid input file.", parent=self); return
            output_dir = os.path.dirname(input_file) if input_file else os.getcwd()
            safe_base_name = sanitize_filename(os.path.splitext(os.path.basename(input_file))[0]) if input_file else "workflow_output"

            if is_visual:
                # --- Visual Q&A (Single) Validation ---
                extract_prompt = self.p4_wf_visual_extraction_prompt_var.get()
                save_direct = self.p4_wf_save_directly_to_media.get()
                anki_media_path_from_ui = self.p4_wf_anki_media_path.get()
                if not extract_prompt:
                    show_error_dialog("Error", "Visual Extraction prompt cannot be empty.", parent=self); return
                if not PYMUPDF_INSTALLED:
                    show_error_dialog("Error", "PyMuPDF (fitz) is required for Visual Q&A workflow.", parent=self); return
                if save_direct and (not anki_media_path_from_ui or not os.path.isdir(anki_media_path_from_ui)):
                    show_error_dialog("Error", "Direct image save is enabled, but the Anki media path is invalid or not set.", parent=self); return
                # Warn if path doesn't look like collection.media, but allow proceeding
                if save_direct and os.path.basename(anki_media_path_from_ui).lower() != "collection.media":
                      if not ask_yes_no("Confirm Path", f"Direct save path '{os.path.basename(anki_media_path_from_ui)}' doesn't end in 'collection.media'.\nProceed anyway?", parent=self): return

                args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model_pass1, extract_prompt, tag_prompt_pass1, save_direct, anki_media_path_from_ui, tag_batch_size, tag_api_delay,
                        enable_second_pass, tag_model_pass2, tag_prompt_pass2)
                target_func = self._run_single_visual_workflow_thread

            else: # Text Analysis (Single)
                # --- Text Analysis (Single) Validation ---
                analysis_prompt = self.p4_wf_book_processing_prompt_var.get()
                try:
                    text_chunk_size = self.p4_wf_text_chunk_size.get()
                    text_api_delay = self.p4_wf_text_api_delay.get()
                    if text_chunk_size <= 0:
                        show_error_dialog("Error", "Text Chunk Size must be greater than 0.", parent=self); return
                    if text_api_delay < 0:
                        self.p4_wf_text_api_delay.set(0.0) # Correct value
                        show_info_dialog("Warning", "Text API Delay cannot be negative. Setting to 0.", parent=self)
                        text_api_delay=0.0 # Use corrected value
                except tk.TclError:
                    show_error_dialog("Error", "Invalid input for Text Chunk Size or Delay.", parent=self); return
                if not analysis_prompt:
                    show_error_dialog("Error", "Text Analysis prompt cannot be empty.", parent=self); return
                # Check PyMuPDF only if input is PDF
                if input_file.lower().endswith(".pdf") and not PYMUPDF_INSTALLED:
                    show_error_dialog("Error", "PyMuPDF (fitz) is required for PDF text analysis.", parent=self); return

                args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model_pass1, analysis_prompt, tag_prompt_pass1, text_chunk_size, text_api_delay, tag_batch_size, tag_api_delay,
                        enable_second_pass, tag_model_pass2, tag_prompt_pass2)
                target_func = self._run_single_text_analysis_workflow_thread

        # --- Start Thread ---
        if target_func:
            self.p4_wf_is_processing = True
            try:
                # Update UI to indicate processing start
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(state="disabled", text="Workflow Running...", bg='lightgrey') # Change bg
                if hasattr(self, 'p4_wf_status_text'):
                    self.p4_wf_status_text.config(state="normal")
                    self.p4_wf_status_text.delete('1.0', tk.END) # Clear previous logs
                    self.p4_wf_status_text.config(state="disabled")
                if hasattr(self, 'p4_wf_progress_bar'): self.p4_wf_progress_var.set(0)
            except tk.TclError: pass # Ignore if widgets destroyed

            self.log_status(f"Starting {'Bulk' if is_bulk else 'Single File'} {selected_type} workflow...")
            # Configure Gemini API before starting thread (optional, could be done in thread too)
            # configure_gemini(api_key) # Assuming configure_gemini is thread-safe or called appropriately

            thread = threading.Thread(target=target_func, args=args, daemon=True)
            thread.start()
        else:
            # This case should ideally not be reached due to prior checks
            show_error_dialog("Error", "Could not determine workflow function to run.", parent=self)

    def _update_progress_bar(self, value):
        """Safely updates the progress bar value from any thread."""
        try:
            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists():
                self.p4_wf_progress_var.set(value)
                self.update_idletasks() # Ensure UI updates
        except tk.TclError:
            print(f"P4 WF Warning: Could not update progress bar (value: {value})")

    def _workflow_finished(self, success=True, final_tsv_path=None, summary_message=None):
        """Called from the main thread after workflow finishes to update UI."""
        self.p4_wf_is_processing = False
        is_bulk = self.p4_wf_is_bulk_mode.get()
        selected_type = self.p4_wf_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"

        # Determine button text and background based on mode and success
        if is_bulk:
            base_text = "Run Bulk Visual Workflow"
        else:
            base_text = "Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow"

        final_button_text = base_text
        final_bg = 'lightyellow' # Default success color
        if not success:
            final_button_text = "Workflow Failed (See Log)"
            final_bg = 'salmon' # Error color

        try:
            # Update Run Button
            if hasattr(self, 'p4_wf_run_button') and self.p4_wf_run_button.winfo_exists():
                self.p4_wf_run_button.config(state="normal", text=final_button_text, bg=final_bg)

            # Log final status message
            if summary_message:
                self.log_status(summary_message, level="info" if success else "error")
            elif success and final_tsv_path:
                self.log_status(f"Workflow successful. Final Output: {os.path.basename(final_tsv_path)}", level="info")
            elif not success:
                self.log_status(f"Workflow failed. See previous logs for details.", level="error")
            else: # Success but no specific path/message
                 self.log_status(f"Workflow finished.", level="info")


            # Update Progress Bar
            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists():
                self.p4_wf_progress_var.set(100 if success else 0) # Full or zero based on success

        except tk.TclError:
            print("P4 WF Warning: Could not update workflow button/status state on finish.")


    # --- Internal Helper for Tagging ---
    def _wf_gemini_tag_json(self, intermediate_json_path, tag_prompt_template_pass1, api_key,
                            tag_model_name_pass1, tag_batch_size, tag_api_delay,
                            enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2):
        """
        Handles the Gemini tagging process (Pass 1 and optional Pass 2).
        Loads data from intermediate_json_path, performs tagging,
        saves the final tagged JSON data, and returns it.
        """
        final_tagged_data = None
        # Define path for the final tagged JSON *before* TSV conversion
        output_dir = os.path.dirname(intermediate_json_path)
        base_name = os.path.splitext(os.path.basename(intermediate_json_path))[0]
        # Ensure base_name doesn't contain suffixes like '_intermediate_visual' for cleaner final name
        suffixes_to_remove = ["_intermediate_visual", "_intermediate_analysis", "_intermediate"]
        for suffix in suffixes_to_remove:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break
        final_tagged_json_output_path = os.path.join(output_dir, f"{base_name}_final_tagged_data.json")


        try:
            # --- Load Input JSON ---
            self.after(0, self.log_status, f"Loading intermediate data from: {os.path.basename(intermediate_json_path)}", "debug")
            try:
                with open(intermediate_json_path, 'r', encoding='utf-8') as f_p1:
                    json_data_pass1 = json.load(f_p1)
                if not json_data_pass1:
                    self.after(0, self.log_status, "Intermediate JSON is empty. Skipping tagging.", "warning")
                    return [] # Return empty list if input is empty
            except Exception as load_e:
                raise WorkflowStepError(f"Failed to load intermediate JSON for Pass 1: {load_e}")

            # --- Pass 1 Tagging ---
            self.after(0, self.log_status, f"  Starting Tagging Pass 1 ({tag_model_name_pass1}, Batch: {tag_batch_size}, Delay: {tag_api_delay}s)...", "debug")
            progress_start_pass1 = 35 # Progress after extraction/analysis
            progress_end_pass1 = 75 if enable_second_pass else 90 # End progress for pass 1

            def update_tag_progress_pass1(processed, total):
                progress = progress_start_pass1 + ((processed / total) * (progress_end_pass1 - progress_start_pass1)) if total > 0 else progress_end_pass1
                self.after(0, self._update_progress_bar, progress)

            # Use generator to process tags
            tagged_data_pass1_generator = tag_tsv_rows_gemini(
                input_data=json_data_pass1,                 # Pass loaded data
                api_key=api_key,
                model_name_pass1=tag_model_name_pass1,      # Correct parameter name
                system_prompt_pass1=tag_prompt_template_pass1, # Correct parameter name
                batch_size=tag_batch_size,
                api_delay=tag_api_delay,
                log_func=self.log_status,
                progress_callback=update_tag_progress_pass1,
                output_dir=output_dir, # Pass output dir for potential internal temp files
                base_filename=f"{base_name}_tagging_p1", # Base name for internal temp files
                parent_widget=self
            )
            # Collect results (yields header first, then tagged dicts)
            tagged_data_pass1_results = list(tagged_data_pass1_generator)
            if not tagged_data_pass1_results or len(tagged_data_pass1_results) <= 1 and json_data_pass1: # Check if only header or nothing yielded
                raise WorkflowStepError("Gemini tagging (Pass 1) failed (no data yielded).")
            tagged_data_pass1 = tagged_data_pass1_results[1:] # Skip header

            self.after(0, self.log_status, "  Tagging Pass 1 Complete.", "info")
            self.after(0, self._update_progress_bar, progress_end_pass1)
            final_tagged_data = tagged_data_pass1 # Start with pass 1 results

            # --- Pass 2 Tagging (Optional) ---
            if enable_second_pass:
                self.after(0, self.log_status, f"  Starting Tagging Pass 2 ({tag_model_name_pass2}, Batch: {tag_batch_size}, Delay: {tag_api_delay}s)...", "debug")
                progress_start_pass2 = 75
                progress_end_pass2 = 90

                def update_tag_progress_pass2(processed, total):
                    progress = progress_start_pass2 + ((processed / total) * (progress_end_pass2 - progress_start_pass2)) if total > 0 else progress_end_pass2
                    self.after(0, self._update_progress_bar, progress)

                # Input for Pass 2 is the result of Pass 1 (already in memory)
                tagged_data_pass2_generator = tag_tsv_rows_gemini(
                    input_data=tagged_data_pass1,                # Pass Pass 1 results
                    api_key=api_key,
                    # Pass 2 specific parameters
                    model_name_pass1=tag_model_name_pass2,       # Use Pass 2 model here
                    system_prompt_pass1=tag_prompt_template_pass2, # Use Pass 2 prompt here
                    # Common parameters
                    batch_size=tag_batch_size,
                    api_delay=tag_api_delay,
                    log_func=self.log_status,
                    progress_callback=update_tag_progress_pass2,
                    output_dir=output_dir, # Pass output dir for potential internal temp files
                    base_filename=f"{base_name}_tagging_p2", # Base name for internal temp files
                    # Add enable_second_pass and second pass model/prompt if function uses them
                    enable_second_pass=True,
                    second_pass_model_name=tag_model_name_pass2, # Pass explicitly if needed by function
                    second_pass_prompt=tag_prompt_template_pass2, # Pass explicitly if needed by function
                    parent_widget=self
                )
                # Collect results (yields header first, then tagged dicts)
                tagged_data_pass2_results = list(tagged_data_pass2_generator)
                if not tagged_data_pass2_results or len(tagged_data_pass2_results) <= 1 and tagged_data_pass1: # Check if only header or nothing yielded
                    raise WorkflowStepError("Gemini tagging (Pass 2) failed (no data yielded).")
                tagged_data_pass2 = tagged_data_pass2_results[1:] # Skip header

                self.after(0, self.log_status, "  Tagging Pass 2 Complete.", "info")
                self.after(0, self._update_progress_bar, progress_end_pass2)
                final_tagged_data = tagged_data_pass2 # Update final data with pass 2 results

            # --- ADDED: Save the final tagged data (after Pass 1 or Pass 2) ---
            if final_tagged_data is not None:
                try:
                    self.after(0, self.log_status, f"Saving final tagged intermediate JSON: {os.path.basename(final_tagged_json_output_path)}", "debug")
                    with open(final_tagged_json_output_path, 'w', encoding='utf-8') as f_tagged:
                        json.dump(final_tagged_data, f_tagged, indent=2)
                    self.after(0, self.log_status, f"Saved final tagged data to {os.path.basename(final_tagged_json_output_path)}", "info")
                except Exception as save_err:
                    # Log warning but don't necessarily stop the whole workflow
                    self.after(0, self.log_status, f"Warning: Error saving final tagged intermediate JSON: {save_err}", "warning")
            # --- END OF ADDED SECTION ---

            # Return the final tagged data for TSV generation
            return final_tagged_data

        except WorkflowStepError as wse: # Catch errors specific to this helper
             self.after(0, self.log_status, f"Error during tagging process: {wse}", "error")
             return None # Indicate failure
        except Exception as e: # Catch unexpected errors
            self.after(0, self.log_status, f"Unexpected error during tagging process: {e}", "error")
            # traceback.print_exc() # Optional: print full traceback to console for debugging
            return None # Indicate failure


    def _run_single_visual_workflow_thread(self, input_pdf_path, output_dir, safe_base_name, api_key,
                                            extract_model_name, tag_model_name_pass1, extract_prompt, tag_prompt_template_pass1,
                                            save_direct_flag, anki_media_dir_from_ui,
                                            tag_batch_size, tag_api_delay,
                                            enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2):
        """Core logic for SINGLE FILE VISUAL Q&A workflow."""
        final_tsv_path = None; success = False; uploaded_file_uri = None; final_image_folder = None; parsed_data = None; tagging_success = False
        intermediate_json_path = os.path.join(output_dir, f"{safe_base_name}_intermediate_visual.json")
        final_tsv_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_visual.txt")

        try:
            start_time = time.time()
            # STEP 1a: Generate Images
            self.after(0, self.log_status, f"Starting Step 1a (Visual): Generating Page Images...", "step"); self.after(0, self._update_progress_bar, 5)
            image_destination_path = anki_media_dir_from_ui if save_direct_flag else output_dir
            final_image_folder, page_image_map = generate_page_images(input_pdf_path, image_destination_path, safe_base_name, save_direct_flag, self.log_status, parent_widget=self, filename_prefix=safe_base_name)
            if final_image_folder is None: raise WorkflowStepError("Failed during page image generation.")
            self.after(0, self.log_status, f"Step 1a Complete. Images in: {final_image_folder}", "info"); self.after(0, self._update_progress_bar, 10)

            # STEP 1b: Gemini Extraction -> JSON
            self.after(0, self.log_status, f"Starting Step 1b (Visual): Gemini JSON Extraction ({extract_model_name})...", "step")
            parsed_data, uploaded_file_uri = call_gemini_visual_extraction(input_pdf_path, api_key, extract_model_name, extract_prompt, self.log_status, parent_widget=self)
            if parsed_data is None: raise WorkflowStepError("Gemini PDF visual extraction failed (check logs/temp files).")
            if not parsed_data: self.after(0, self.log_status, "No Q&A pairs extracted from the document.", "warning")

            # Add metadata needed for TSV generation later
            for item in parsed_data:
                if isinstance(item, dict):
                    item['_page_image_map'] = page_image_map # Map page numbers to image filenames
                    item['_source_pdf_prefix'] = safe_base_name # Store the base name for reference

            # Save intermediate JSON (useful for debugging)
            try:
                with open(intermediate_json_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, indent=2)
                self.after(0, self.log_status, f"Saved intermediate JSON: {os.path.basename(intermediate_json_path)}", "info")
            except Exception as json_e:
                raise WorkflowStepError(f"Failed to save intermediate JSON: {json_e}")
            self.after(0, self.log_status, "Step 1b Complete.", "info"); self.after(0, self._update_progress_bar, 35)

            # STEP 2: Tag Intermediate JSON
            if not parsed_data:
                 self.after(0, self.log_status, f"Skipping Tagging Step: No data extracted.", "warning")
                 # Still generate an empty TSV file for consistency
                 tsv_gen_success = generate_tsv_from_json_data([], final_tsv_path, self.log_status)
                 if not tsv_gen_success: raise WorkflowStepError("Failed to generate empty final TSV.")
                 tagging_success = True # Consider it a success (no data to tag)
            else:
                self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging extracted JSON...", "step")
                final_tagged_data = self._wf_gemini_tag_json(
                    intermediate_json_path, tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                    tag_batch_size, tag_api_delay, enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2
                )
                if final_tagged_data is None:
                    raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")
                tagging_success = True

                # STEP 3: Generate Final TSV from tagged JSON data
                self.after(0, self.log_status, f"Starting Step 3: Generating Final TSV from tagged data...", "step")
                tsv_gen_success = generate_tsv_from_json_data(final_tagged_data, final_tsv_path, self.log_status)
                if not tsv_gen_success: raise WorkflowStepError("Failed to generate final TSV file from tagged data.")
                self.after(0, self.log_status, f"Step 3 Complete: Final tagged file saved: {os.path.basename(final_tsv_path)}", "info"); self.after(0, self._update_progress_bar, 95)

            # Workflow Complete
            end_time = time.time(); total_time = end_time - start_time
            self.after(0, self.log_status, f"Visual Q&A Workflow finished successfully in {total_time:.2f} seconds!", "info")
            self.after(0, self._update_progress_bar, 100)
            success_message = f"Processed '{os.path.basename(input_pdf_path)}'.\nFinal TSV:\n{final_tsv_path}\n\n"
            if save_direct_flag:
                success_message += f"Images Saved Directly To:\n{final_image_folder}"
            else:
                success_message += f"Images Saved To Subfolder:\n{final_image_folder}\n\nIMPORTANT: Manually copy images from\n'{os.path.basename(final_image_folder)}' to Anki's 'collection.media' folder before importing the TSV."
            self.after(0, show_info_dialog, "Workflow Complete", success_message, self)
            success = True

        except WorkflowStepError as wse:
            self.after(0, self.log_status, f"Visual Workflow stopped: {wse}", "error")
            self.after(0, show_error_dialog, "Workflow Failed", f"Failed: {wse}\nCheck log and intermediate files.", self)
            success = False
        except Exception as e:
            error_message = f"Unexpected visual workflow error: {type(e).__name__}: {e}"
            self.after(0, self.log_status, f"FATAL WORKFLOW ERROR (Visual): {error_message}\n{traceback.format_exc()}", "error")
            self.after(0, show_error_dialog, "Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self)
            success = False
        finally:
            # Cleanup Gemini uploaded file
            if uploaded_file_uri:
                try:
                    cleanup_gemini_file(uploaded_file_uri, api_key, self.log_status)
                except Exception as clean_e:
                    self.after(0, self.log_status, f"Error during cleanup: {clean_e}", "warning")

            # Cleanup intermediate JSON file (only on success, keep on failure for debugging) ---Changing this, hopefully briefly
            if success and os.path.exists(intermediate_json_path):
                try:
                   #  os.remove(intermediate_json_path)
                    # self.after(0, self.log_status, f"Cleaned up intermediate JSON: {os.path.basename(intermediate_json_path)}", "debug")
                    pass
                except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")
            elif not success and os.path.exists(intermediate_json_path):
                 self.after(0, self.log_status, f"Keeping intermediate JSON on failure: {os.path.basename(intermediate_json_path)}", "warning")


            # Update UI state via main thread
            self.after(0, self._workflow_finished, success, final_tsv_path if success else None)


    def _run_single_text_analysis_workflow_thread(self, input_file_path, output_dir, safe_base_name, api_key,
                                                  analysis_model_name, tag_model_name_pass1, analysis_prompt, tag_prompt_template_pass1,
                                                  text_chunk_size, text_api_delay,
                                                  tag_batch_size, tag_api_delay,
                                                  enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2):
        """Core logic for SINGLE FILE TEXT ANALYSIS workflow."""
        final_tsv_path = None; success = False; parsed_data = None; tagging_success = False
        intermediate_json_path = os.path.join(output_dir, f"{safe_base_name}_intermediate_analysis.json")
        final_tsv_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_analysis.txt")

        try:
            start_time = time.time()
            # STEP 1a: Extract Text
            self.after(0, self.log_status, f"Starting Step 1a (Text): Extracting Text...", "step"); self.after(0, self._update_progress_bar, 5)
            extracted_text = ""; file_type = ""
            if input_file_path.lower().endswith(".pdf"):
                extracted_text = extract_text_from_pdf(input_file_path, self.log_status)
                file_type = "PDF"
            elif input_file_path.lower().endswith(".txt"):
                extracted_text = read_text_file(input_file_path, self.log_status)
                file_type = "TXT"
            else:
                raise WorkflowStepError("Unsupported file type.")

            if extracted_text is None: raise WorkflowStepError(f"Text extraction failed for {file_type}.")
            if not extracted_text.strip():
                self.after(0, self.log_status, f"No text content extracted from the {file_type} file. Workflow finished.", "warning")
                # Generate empty TSV
                tsv_gen_success = generate_tsv_from_json_data([], final_tsv_path, self.log_status)
                if not tsv_gen_success: raise WorkflowStepError("Failed to generate empty final TSV.")
                self.after(0, self._workflow_finished, True, final_tsv_path) # Finish successfully
                return # Exit thread

            self.after(0, self.log_status, f"Step 1a Complete. Extracted ~{len(extracted_text)} characters.", "info"); self.after(0, self._update_progress_bar, 10)

            # STEP 1b: Gemini Analysis -> JSON
            self.after(0, self.log_status, f"Starting Step 1b (Text): Gemini Analysis ({analysis_model_name}) in chunks...", "step")
            parsed_data = call_gemini_text_analysis(extracted_text, api_key, analysis_model_name, analysis_prompt, self.log_status, output_dir, safe_base_name, text_chunk_size, text_api_delay, parent_widget=self)
            if parsed_data is None: raise WorkflowStepError("Gemini text analysis failed (check logs/temp files).")
            if not parsed_data: self.after(0, self.log_status, "No Q&A pairs extracted from text.", "warning")

            # Save intermediate JSON
            try:
                with open(intermediate_json_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, indent=2)
                self.after(0, self.log_status, f"Saved intermediate JSON: {os.path.basename(intermediate_json_path)}", "info")
            except Exception as json_e:
                raise WorkflowStepError(f"Failed to save intermediate JSON: {json_e}")
            self.after(0, self.log_status, "Step 1b Complete (Gemini chunk processing).", "info"); self.after(0, self._update_progress_bar, 35)

            # STEP 2: Tag Intermediate JSON
            if not parsed_data:
                 self.after(0, self.log_status, f"Skipping Tagging Step: No data extracted.", "warning")
                 # Generate empty TSV
                 tsv_gen_success = generate_tsv_from_json_data([], final_tsv_path, self.log_status)
                 if not tsv_gen_success: raise WorkflowStepError("Failed to generate empty final TSV.")
                 tagging_success = True # Consider success
            else:
                self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging extracted JSON...", "step")
                final_tagged_data = self._wf_gemini_tag_json(
                    intermediate_json_path, tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                    tag_batch_size, tag_api_delay, enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2
                )
                if final_tagged_data is None:
                    raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")
                tagging_success = True

                # STEP 3: Generate Final TSV from tagged JSON data
                self.after(0, self.log_status, f"Starting Step 3: Generating Final TSV from tagged data...", "step")
                tsv_gen_success = generate_tsv_from_json_data(final_tagged_data, final_tsv_path, self.log_status)
                if not tsv_gen_success: raise WorkflowStepError("Failed to generate final TSV file from tagged data.")
                self.after(0, self.log_status, f"Step 3 Complete: Final tagged file saved: {os.path.basename(final_tsv_path)}", "info"); self.after(0, self._update_progress_bar, 95)

            # Workflow Complete
            end_time = time.time(); total_time = end_time - start_time
            self.after(0, self.log_status, f"Text Analysis Workflow finished successfully in {total_time:.2f} seconds!", "info")
            self.after(0, self._update_progress_bar, 100)
            success_message = f"Processed '{os.path.basename(input_file_path)}'.\nFinal TSV:\n{final_tsv_path}\n"
            self.after(0, show_info_dialog, "Workflow Complete", success_message, self)
            success = True

        except WorkflowStepError as wse:
            self.after(0, self.log_status, f"Text Analysis Workflow stopped: {wse}", "error")
            self.after(0, show_error_dialog, "Workflow Failed", f"Failed: {wse}\nCheck log and intermediate files.", self)
            success = False
        except Exception as e:
            error_message = f"Unexpected text analysis workflow error: {type(e).__name__}: {e}"
            self.after(0, self.log_status, f"FATAL WORKFLOW ERROR (Text): {error_message}\n{traceback.format_exc()}", "error")
            self.after(0, show_error_dialog, "Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self)
            success = False
        finally:
            # Cleanup intermediate JSON file (only on success)
            if success and os.path.exists(intermediate_json_path):
                try:
                    # os.remove(intermediate_json_path)
                    #self.after(0, self.log_status, f"Cleaned up intermediate JSON: {os.path.basename(intermediate_json_path)}", "debug")
                    pass
                except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")
            elif not success and os.path.exists(intermediate_json_path):
                 self.after(0, self.log_status, f"Keeping intermediate JSON on failure: {os.path.basename(intermediate_json_path)}", "warning")


            # Update UI state via main thread
            self.after(0, self._workflow_finished, success, final_tsv_path if success else None)


    def _run_bulk_visual_workflow_thread(self, input_pdf_paths, output_dir, api_key,
                                          extract_model_name, tag_model_name_pass1, extract_prompt, tag_prompt_template_pass1,
                                          anki_media_dir,
                                          tag_batch_size, tag_api_delay,
                                          enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2):
        """Core logic for BULK VISUAL Q&A workflow."""
        final_tsv_path = None; success = False; uploaded_file_uris = {}; tagging_success = False
        aggregated_json_data = []; total_files = len(input_pdf_paths); processed_files = 0; success_files = 0; failed_files = 0; skipped_files = 0
        start_time = time.time(); timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        intermediate_json_path = os.path.join(output_dir, f"bulk_visual_{timestamp_str}_intermediate.json")
        final_tsv_path = os.path.join(output_dir, f"bulk_visual_{timestamp_str}_final_tagged.txt")

        try:
            # STEP 1: Process Each PDF -> JSON
            self.after(0, self.log_status, f"Starting Step 1: Processing {total_files} PDF files...", "step")
            for pdf_path in input_pdf_paths:
                current_file_success = False; uploaded_file_uri = None; parsed_data = None
                processed_files += 1
                file_basename = os.path.basename(pdf_path)
                sanitized_pdf_name = sanitize_filename(os.path.splitext(file_basename)[0])
                self.after(0, self.log_status, f"Processing file {processed_files}/{total_files}: {file_basename}", "info")
                # Update progress based on file count (up to 50% for this step)
                self.after(0, self._update_progress_bar, (processed_files / total_files) * 50 if total_files > 0 else 0)

                # Skip if not a PDF (already filtered, but double-check)
                if not pdf_path.lower().endswith(".pdf"):
                    self.after(0, self.log_status, f"Skipping non-PDF file: {file_basename}", "skip")
                    skipped_files += 1
                    continue

                try:
                    # STEP 1a: Generate Images (Directly to Anki Media)
                    self.after(0, self.log_status, f"  Step 1a: Generating images for {file_basename}...", "debug")
                    final_image_folder, page_image_map = generate_page_images(
                        pdf_path, anki_media_dir, sanitized_pdf_name, save_direct_flag=True,
                        log_func=self.log_status, parent_widget=self, filename_prefix=sanitized_pdf_name
                    )
                    if final_image_folder is None: raise WorkflowStepError("Image generation failed.")

                    # STEP 1b: Gemini Extraction -> JSON
                    self.after(0, self.log_status, f"  Step 1b: Extracting JSON for {file_basename}...", "debug")
                    parsed_data, uploaded_file_uri = call_gemini_visual_extraction(
                        pdf_path, api_key, extract_model_name, extract_prompt,
                        self.log_status, parent_widget=self
                    )
                    if uploaded_file_uri: uploaded_file_uris[pdf_path] = uploaded_file_uri # Store URI for cleanup
                    if parsed_data is None: raise WorkflowStepError("Gemini PDF visual extraction failed.")
                    if not parsed_data: self.after(0, self.log_status, f"Warning: No Q&A pairs extracted from {file_basename}.", "warning")

                    # STEP 1c: Add metadata to extracted items
                    for item in parsed_data:
                        if isinstance(item, dict):
                            item['_page_image_map'] = page_image_map
                            item['_source_pdf_prefix'] = sanitized_pdf_name

                    # Add successfully parsed data to the aggregate list
                    if parsed_data:
                        aggregated_json_data.extend(parsed_data)
                        self.after(0, self.log_status, f"  Success: Added {len(parsed_data)} items from {file_basename}.", "debug")
                    success_files += 1
                    current_file_success = True

                except (WorkflowStepError, Exception) as file_e:
                    failed_files += 1
                    current_file_success = False
                    self.after(0, self.log_status, f"Failed processing {file_basename}: {file_e}. Attempting to rename...", "error")
                    # Attempt to rename the failed PDF file
                    try:
                        pdf_dir = os.path.dirname(pdf_path)
                        new_basename = f"UP_{file_basename}" # Prepend UP_
                        new_name = os.path.join(pdf_dir, new_basename)
                        counter = 1
                        # Handle potential name collisions for renamed files
                        while os.path.exists(new_name):
                            name, ext = os.path.splitext(new_basename)
                            new_name = os.path.join(pdf_dir, f"{name}_{counter}{ext}")
                            counter += 1
                        os.rename(pdf_path, new_name)
                        self.after(0, self.log_status, f"Renamed failed file to: {os.path.basename(new_name)}", "warning")
                    except Exception as rename_e:
                        self.after(0, self.log_status, f"Could not rename failed file {file_basename}: {rename_e}", "error")
                finally:
                    # Clean up Gemini file immediately if this specific file failed
                    if not current_file_success and uploaded_file_uri:
                        try:
                            cleanup_gemini_file(uploaded_file_uri, api_key, self.log_status)
                            if pdf_path in uploaded_file_uris:
                                del uploaded_file_uris[pdf_path] # Remove from final cleanup list
                        except Exception as clean_e:
                            self.after(0, self.log_status, f"Error during immediate cleanup for {file_basename}: {clean_e}", "warning")

            self.after(0, self.log_status, f"Finished processing all {total_files} files. Extracted {len(aggregated_json_data)} total items.", "info")
            self.after(0, self._update_progress_bar, 50) # Mark end of file processing phase

            # STEP 2: Aggregate and Tag
            if not aggregated_json_data:
                raise WorkflowStepError("No data successfully extracted from any PDF. Cannot proceed.")

            self.after(0, self.log_status, f"Writing aggregated intermediate JSON ({len(aggregated_json_data)} items)...", "step")
            try:
                with open(intermediate_json_path, 'w', encoding='utf-8') as f:
                    json.dump(aggregated_json_data, f, indent=2)
                self.after(0, self.log_status, f"Aggregated JSON saved: {os.path.basename(intermediate_json_path)}", "info")
            except IOError as e:
                raise WorkflowStepError(f"Failed to write aggregated intermediate JSON file: {e}")
            self.after(0, self._update_progress_bar, 55) # Progress after saving JSON

            self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging aggregated JSON...", "step")
            # Reuse the tagging helper function
            final_tagged_data = self._wf_gemini_tag_json(
                intermediate_json_path, tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                tag_batch_size, tag_api_delay, enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2
            )
            if final_tagged_data is None:
                raise WorkflowStepError("Gemini tagging step failed for aggregated JSON (check logs/temp files).")
            tagging_success = True

            # STEP 3: Generate Final TSV
            self.after(0, self.log_status, f"Starting Step 3: Generating Final TSV from tagged data...", "step")
            tsv_gen_success = generate_tsv_from_json_data(final_tagged_data, final_tsv_path, self.log_status)
            if not tsv_gen_success: raise WorkflowStepError("Failed to generate final TSV file from tagged data.")
            self.after(0, self.log_status, f"Step 3 Complete: Final tagged file saved: {os.path.basename(final_tsv_path)}", "info")
            self.after(0, self._update_progress_bar, 95) # Progress before final completion

            # Workflow Complete
            end_time = time.time(); total_time = end_time - start_time
            self.after(0, self.log_status, f"Bulk Visual Q&A Workflow finished successfully in {total_time:.2f} seconds!", "info")
            self.after(0, self._update_progress_bar, 100)
            summary = (
                f"Bulk Processing Complete!\n\n"
                f"Files Processed: {processed_files}/{total_files}\n"
                f"Successful: {success_files}\n"
                f"Failed (Renamed 'UP_'): {failed_files}\n"
                f"Skipped (Non-PDF): {skipped_files}\n\n"
                f"Final Tagged File:\n{final_tsv_path}\n\n"
                f"Images Saved Directly To:\n{anki_media_dir}"
            )
            self.after(0, show_info_dialog, "Bulk Workflow Complete", summary, self)
            success = True

        except WorkflowStepError as wse:
            self.after(0, self.log_status, f"Bulk Workflow stopped: {wse}", "error")
            self.after(0, show_error_dialog, "Bulk Workflow Failed", f"Failed: {wse}\nCheck log and intermediate files.", self)
            success = False
        except Exception as e:
            error_message = f"Unexpected bulk workflow error: {type(e).__name__}: {e}"
            self.after(0, self.log_status, f"FATAL BULK WORKFLOW ERROR: {error_message}\n{traceback.format_exc()}", "error")
            self.after(0, show_error_dialog, "Bulk Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self)
            success = False
        finally:
            # Final cleanup of all successfully uploaded Gemini files
            for pdf_p, uri in uploaded_file_uris.items():
                try:
                    cleanup_gemini_file(uri, api_key, self.log_status)
                except Exception as clean_e:
                    self.after(0, self.log_status, f"Error during final cleanup for {os.path.basename(pdf_p)}: {clean_e}", "warning")

            # Cleanup intermediate JSON (only on success)
            if success and os.path.exists(intermediate_json_path):
                try:
                    # os.remove(intermediate_json_path)
                    # self.after(0, self.log_status, f"Cleaned up intermediate JSON: {os.path.basename(intermediate_json_path)}", "debug")
                    pass
                except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")
            elif not success and os.path.exists(intermediate_json_path):
                 self.after(0, self.log_status, f"Keeping intermediate JSON on failure: {os.path.basename(intermediate_json_path)}", "warning")


            # Prepare final summary message for the log/button update
            final_summary = f"Bulk processing finished. {success_files}/{total_files} successful, {failed_files} failed (renamed 'UP_'), {skipped_files} skipped."
            # Update UI state via main thread
            self.after(0, self._workflow_finished, success, final_tsv_path if success else None, final_summary)

# Example usage (for testing purposes, if run directly)
if __name__ == '__main__':
    root = tk.Tk()
    root.title("Workflow Page Test")
    root.geometry("800x700")

    # Mock App instance with necessary attributes
    class MockApp:
        def __init__(self):
            self.gemini_api_key = StringVar(value="YOUR_API_KEY_HERE") # Replace with a real key for actual testing
            self.api_key_visible = False

        def toggle_api_key_visibility(self):
             print("Toggling API Key visibility (Mock)")
             # In a real app, you'd update the show character of the entry
             pass

    mock_app = MockApp()
    page = WorkflowPage(root, mock_app)
    page.pack(expand=True, fill='both')

    root.mainloop()
