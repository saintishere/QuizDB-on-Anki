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
                               generate_tsv_from_json_data) # <<< Added generate_tsv_from_json_data here
# Import the correct functions from gemini_api
from ..core.gemini_api import (call_gemini_visual_extraction, call_gemini_text_analysis,
                       cleanup_gemini_file, tag_tsv_rows_gemini, # Corrected name
                       configure_gemini, save_json_incrementally)


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

        # --- Build UI ---
        self._build_ui()

        # --- Initial UI state ---
        # IMPORTANT: Call _toggle_media_path_entry *after* _toggle_bulk_mode
        # because _toggle_bulk_mode might change settings used by _toggle_media_path_entry
        self._toggle_bulk_mode()
        self._update_ui_for_processing_type()
        self._toggle_media_path_entry() # Ensure media path state is correct initially
        self._toggle_second_pass_widgets() # Ensure second pass state is correct

        # Handle PyMuPDF dependency check after initial UI setup
        if not PYMUPDF_INSTALLED:
            if hasattr(self, 'p4_wf_visual_qa_radio'):
                self.p4_wf_visual_qa_radio.config(state="disabled")
            # If default is visual and it's disabled, switch to text
            if self.p4_wf_processing_type.get() == "Visual Q&A (PDF)":
                self.p4_wf_processing_type.set("Text Analysis (PDF/TXT)")
                self.log_status("PyMuPDF not found. Switched to Text Analysis workflow.", "warning")
                self._update_ui_for_processing_type() # Update UI based on new type

        print("Initialized WorkflowPage")

    # --- UI Build and Control Logic ---
    def _build_ui(self):
        """Initialize the Full Workflow page with a two-column layout."""
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1) # Left column less weight
        main_frame.grid_columnconfigure(1, weight=2) # Right column more weight for prompts
        main_frame.grid_rowconfigure(0, weight=1) # Allow rows to expand
        main_frame.grid_rowconfigure(1, weight=0) # Bottom frame fixed height

        # --- Left Column Frame ---
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")
        # Configure left frame to allow config section to expand if needed
        left_frame.grid_rowconfigure(4, weight=1) # Allow config frame row to take space

        # --- Right Column Frame (Prompts) ---
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, padx=(10, 0), pady=5, sticky="nsew")
        # Configure right frame rows for prompt sections to expand equally
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_rowconfigure(3, weight=1)
        right_frame.grid_columnconfigure(0, weight=1) # Allow prompts to fill width

        # --- Bottom Frame (Run Button, Status) ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=1, column=0, columnspan=2, padx=0, pady=(10, 0), sticky="ew")
        bottom_frame.grid_columnconfigure(0, weight=1) # Allow status section to fill width

        # --- Left Column Widgets ---
        # Bulk Mode Toggle
        bulk_toggle_frame = ttk.Frame(left_frame)
        bulk_toggle_frame.pack(fill=tk.X, pady=(0, 10)) # Use pack for simple top elements
        self.p4_wf_bulk_mode_check = ttk.Checkbutton(bulk_toggle_frame, text="Enable Bulk PDF Processing Mode", variable=self.p4_wf_is_bulk_mode, command=self._toggle_bulk_mode)
        self.p4_wf_bulk_mode_check.pack(side=tk.LEFT, padx=5, pady=5)

        # Processing Type
        self.p4_type_frame = ttk.LabelFrame(left_frame, text="0. Select Workflow Type")
        self.p4_type_frame.pack(fill=tk.X, pady=5) # Use pack
        self.p4_wf_visual_qa_radio = ttk.Radiobutton(self.p4_type_frame, text="Visual Q&A (PDF)", variable=self.p4_wf_processing_type, value="Visual Q&A (PDF)", command=self._update_ui_for_processing_type, state="disabled") # Initial state disabled
        self.p4_wf_visual_qa_radio.pack(side=tk.LEFT, padx=10, pady=5)
        self.p4_wf_text_analysis_radio = ttk.Radiobutton(self.p4_type_frame, text="Text Analysis (PDF/TXT)", variable=self.p4_wf_processing_type, value="Text Analysis (PDF/TXT)", command=self._update_ui_for_processing_type)
        self.p4_wf_text_analysis_radio.pack(side=tk.LEFT, padx=10, pady=5)

        # Input Selection
        self.p4_input_frame = ttk.LabelFrame(left_frame, text="1. Select Input File(s)")
        self.p4_input_frame.pack(fill=tk.X, pady=5) # Use pack
        self.p4_input_frame.grid_columnconfigure(1, weight=1) # Allow entry to expand

        # Single File Input (managed visibility)
        self.p4_wf_input_label_single = tk.Label(self.p4_input_frame, text="Input File:")
        self.p4_wf_input_label_single.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_input_file_entry = tk.Entry(self.p4_input_frame, textvariable=self.p4_wf_input_file_path, width=40, state="readonly")
        self.p4_wf_input_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.p4_wf_browse_button_single = tk.Button(self.p4_input_frame, text="Browse...", command=self._select_input_file_single)
        self.p4_wf_browse_button_single.grid(row=0, column=2, padx=5, pady=5)

        # Bulk File Input (managed visibility)
        self.p4_wf_bulk_input_list_frame = ttk.Frame(self.p4_input_frame)
        self.p4_wf_bulk_input_list_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        self.p4_wf_bulk_input_list_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_bulk_input_list_frame.grid_rowconfigure(0, weight=1)
        # Listbox and Scrollbar
        self.p4_wf_bulk_files_listbox = tk.Listbox(self.p4_wf_bulk_input_list_frame, selectmode=tk.EXTENDED, height=4)
        self.p4_wf_bulk_files_listbox.grid(row=0, column=0, sticky="nsew")
        bulk_scrollbar = ttk.Scrollbar(self.p4_wf_bulk_input_list_frame, orient=tk.VERTICAL, command=self.p4_wf_bulk_files_listbox.yview)
        bulk_scrollbar.grid(row=0, column=1, sticky="ns")
        self.p4_wf_bulk_files_listbox.config(yscrollcommand=bulk_scrollbar.set)
        # Buttons for Bulk List
        bulk_button_frame = ttk.Frame(self.p4_wf_bulk_input_list_frame)
        bulk_button_frame.grid(row=0, column=2, sticky="ns", padx=(5,0))
        self.p4_wf_browse_button_bulk = tk.Button(bulk_button_frame, text="Select PDFs...", command=self._select_input_files_bulk)
        self.p4_wf_browse_button_bulk.pack(pady=2, fill=tk.X)
        self.p4_wf_clear_button_bulk = tk.Button(bulk_button_frame, text="Clear List", command=self._clear_bulk_files_list)
        self.p4_wf_clear_button_bulk.pack(pady=2, fill=tk.X)

        # Image Output Location (managed visibility)
        self.p4_wf_image_output_frame = ttk.LabelFrame(left_frame, text="2. Image Output Location (Visual Q&A)")
        self.p4_wf_image_output_frame.pack(fill=tk.X, pady=5) # Use pack
        self.p4_wf_image_output_frame.grid_columnconfigure(1, weight=1) # Allow entry to expand
        # Checkbox
        self.p4_wf_save_direct_check = tk.Checkbutton(self.p4_wf_image_output_frame, text="Save Images Directly to Anki collection.media", variable=self.p4_wf_save_directly_to_media, command=self._toggle_media_path_entry)
        self.p4_wf_save_direct_check.grid(row=0, column=0, columnspan=3, padx=5, pady=(5,0), sticky="w")
        # Path Entry and Buttons
        self.p4_wf_anki_media_label = tk.Label(self.p4_wf_image_output_frame, text="Anki Media Path:")
        self.p4_wf_anki_media_label.grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.p4_wf_anki_media_entry = tk.Entry(self.p4_wf_image_output_frame, textvariable=self.p4_wf_anki_media_path, width=40, state="disabled")
        self.p4_wf_anki_media_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        self.p4_wf_browse_anki_media_button = tk.Button(self.p4_wf_image_output_frame, text="Browse...", command=self._select_anki_media_dir, state="disabled")
        self.p4_wf_browse_anki_media_button.grid(row=1, column=2, padx=5, pady=2)
        self.p4_wf_detect_anki_media_button = tk.Button(self.p4_wf_image_output_frame, text="Detect via AnkiConnect", command=self._detect_anki_media_path, state="normal") # Initially normal, state managed by visibility logic
        self.p4_wf_detect_anki_media_button.grid(row=2, column=1, padx=5, pady=(0,5), sticky="w")

        # Workflow Configuration
        config_frame = ttk.LabelFrame(left_frame, text="3. Workflow Configuration")
        config_frame.pack(fill=tk.BOTH, pady=5, expand=True) # Use pack and expand
        config_frame.grid_columnconfigure(1, weight=1) # Allow dropdowns to expand slightly more
        config_frame.grid_columnconfigure(3, weight=1)

        # API Key Row
        tk.Label(config_frame, text="API Key:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.p4_wf_api_key_entry = tk.Entry(config_frame, textvariable=self.app.gemini_api_key, width=30, show="*")
        self.p4_wf_api_key_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=2, sticky="ew")
        self.p4_wf_show_key_button = tk.Button(config_frame, text="S/H", command=self.app.toggle_api_key_visibility, width=4)
        self.p4_wf_show_key_button.grid(row=0, column=4, padx=5, pady=2)

        # Extraction/Analysis Model Row
        self.p4_wf_step1_model_label = tk.Label(config_frame, text="Extraction/Analysis Model:")
        self.p4_wf_step1_model_label.grid(row=1, column=0, columnspan=2, padx=5, pady=2, sticky="w")
        self.p4_wf_extraction_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p4_wf_extraction_model, values=VISUAL_CAPABLE_MODELS, state="readonly", width=25)
        # Set initial value safely
        current_extract_model = self.p4_wf_extraction_model.get()
        if current_extract_model in VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model_dropdown.set(current_extract_model)
        elif VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model_dropdown.set(VISUAL_CAPABLE_MODELS[0])
        self.p4_wf_extraction_model_dropdown.grid(row=1, column=2, columnspan=3, padx=5, pady=2, sticky="ew")

        # Tagging Model (Pass 1) Row
        tk.Label(config_frame, text="Tagging Model (Pass 1):").grid(row=2, column=0, columnspan=2, padx=5, pady=2, sticky="w")
        self.p4_wf_tagging_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p4_wf_tagging_model, values=GEMINI_UNIFIED_MODELS, state="readonly", width=25)
        # Set initial value safely
        if GEMINI_UNIFIED_MODELS and self.p4_wf_tagging_model.get() in GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(self.p4_wf_tagging_model.get())
        elif GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(GEMINI_UNIFIED_MODELS[0])
        self.p4_wf_tagging_model_dropdown.grid(row=2, column=2, columnspan=3, padx=5, pady=2, sticky="ew")

        # Second Pass Checkbox Row
        self.p4_wf_second_pass_check = ttk.Checkbutton(config_frame, text="Enable Second Tagging Pass", variable=self.p4_wf_enable_second_pass, command=self._toggle_second_pass_widgets)
        self.p4_wf_second_pass_check.grid(row=3, column=0, columnspan=5, padx=5, pady=(5,0), sticky="w")

        # Tagging Model (Pass 2) Row (managed visibility)
        self.p4_wf_second_pass_model_label = tk.Label(config_frame, text="Tagging Model (Pass 2):")
        self.p4_wf_second_pass_model_label.grid(row=4, column=0, columnspan=2, padx=5, pady=2, sticky="w")
        self.p4_wf_second_pass_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p4_wf_second_pass_model, values=GEMINI_UNIFIED_MODELS, state="disabled", width=25)
        # Set initial value safely
        if GEMINI_UNIFIED_MODELS and self.p4_wf_second_pass_model.get() in GEMINI_UNIFIED_MODELS: self.p4_wf_second_pass_model_dropdown.set(self.p4_wf_second_pass_model.get())
        elif GEMINI_UNIFIED_MODELS: self.p4_wf_second_pass_model_dropdown.set(GEMINI_UNIFIED_MODELS[0])
        self.p4_wf_second_pass_model_dropdown.grid(row=4, column=2, columnspan=3, padx=5, pady=2, sticky="ew")

        # Text Analysis Config Row (managed visibility)
        self.p4_wf_text_config_frame = ttk.Frame(config_frame)
        self.p4_wf_text_config_frame.grid(row=5, column=0, columnspan=5, sticky="ew")
        tk.Label(self.p4_wf_text_config_frame, text="Text Chunk Size:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        p4_wf_text_chunk_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_chunk_size, width=8)
        p4_wf_text_chunk_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        tk.Label(self.p4_wf_text_config_frame, text="Text API Delay(s):").grid(row=0, column=2, padx=5, pady=2, sticky="w")
        p4_wf_text_delay_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_api_delay, width=6)
        p4_wf_text_delay_entry.grid(row=0, column=3, padx=5, pady=2, sticky="w")

        # Tagging Config Row
        tk.Label(config_frame, text="Tag Batch Size:").grid(row=6, column=0, padx=5, pady=2, sticky="w")
        p4_wf_tag_batch_entry = ttk.Entry(config_frame, textvariable=self.p4_wf_tagging_batch_size, width=8)
        p4_wf_tag_batch_entry.grid(row=6, column=1, padx=5, pady=2, sticky="w")
        tk.Label(config_frame, text="Tag API Delay(s):").grid(row=6, column=2, padx=5, pady=2, sticky="w")
        p4_wf_tag_delay_entry = ttk.Entry(config_frame, textvariable=self.p4_wf_tagging_api_delay, width=6)
        p4_wf_tag_delay_entry.grid(row=6, column=3, padx=5, pady=2, sticky="w")

        # --- Right Column Widgets (Prompts) ---
        # Visual Extraction Prompt
        self.p4_wf_visual_extract_prompt_frame = ttk.LabelFrame(right_frame, text="Visual Extraction Prompt (Step 1)")
        self.p4_wf_visual_extract_prompt_frame.grid(row=0, column=0, padx=0, pady=(0,5), sticky="nsew")
        self.p4_wf_visual_extract_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_visual_extract_prompt_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_visual_extraction_prompt_text = scrolledtext.ScrolledText(self.p4_wf_visual_extract_prompt_frame, wrap=tk.WORD, height=6)
        self.p4_wf_visual_extraction_prompt_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p4_wf_visual_extraction_prompt_text.insert(tk.END, self.p4_wf_visual_extraction_prompt_var.get())
        self.p4_wf_visual_extraction_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_visual_extract)

        # Text Analysis Prompt
        self.p4_wf_text_analysis_prompt_frame = ttk.LabelFrame(right_frame, text="Text Analysis Prompt (Step 1)")
        self.p4_wf_text_analysis_prompt_frame.grid(row=1, column=0, padx=0, pady=(0,5), sticky="nsew")
        self.p4_wf_text_analysis_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_text_analysis_prompt_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_book_processing_prompt_text = scrolledtext.ScrolledText(self.p4_wf_text_analysis_prompt_frame, wrap=tk.WORD, height=6)
        self.p4_wf_book_processing_prompt_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p4_wf_book_processing_prompt_text.insert(tk.END, self.p4_wf_book_processing_prompt_var.get())
        self.p4_wf_book_processing_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_book_process)

        # Tagging Prompt (Pass 1)
        self.p4_wf_tagging_pass1_prompt_frame = ttk.LabelFrame(right_frame, text="Tagging Prompt (Pass 1)")
        self.p4_wf_tagging_pass1_prompt_frame.grid(row=2, column=0, padx=0, pady=5, sticky="nsew")
        self.p4_wf_tagging_pass1_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_tagging_pass1_prompt_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_tagging_prompt_text_editor = scrolledtext.ScrolledText(self.p4_wf_tagging_pass1_prompt_frame, wrap=tk.WORD, height=8)
        self.p4_wf_tagging_prompt_text_editor.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p4_wf_tagging_prompt_text_editor.insert(tk.END, self.p4_wf_tagging_prompt_var.get())
        self.p4_wf_tagging_prompt_text_editor.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag)

        # Tagging Prompt (Pass 2) (managed visibility)
        self.p4_wf_tagging_pass2_prompt_frame = ttk.LabelFrame(right_frame, text="Tagging Prompt (Pass 2)")
        self.p4_wf_tagging_pass2_prompt_frame.grid(row=3, column=0, padx=0, pady=(5,0), sticky="nsew")
        self.p4_wf_tagging_pass2_prompt_frame.grid_rowconfigure(0, weight=1); self.p4_wf_tagging_pass2_prompt_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_second_pass_prompt_text_editor = scrolledtext.ScrolledText(self.p4_wf_tagging_pass2_prompt_frame, wrap=tk.WORD, height=8, state="disabled")
        self.p4_wf_second_pass_prompt_text_editor.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p4_wf_second_pass_prompt_text_editor.insert(tk.END, self.p4_wf_second_pass_prompt_var.get())
        self.p4_wf_second_pass_prompt_text_editor.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag_pass2)

        # --- Bottom Frame Widgets ---
        # Run Button
        self.p4_wf_run_button = tk.Button(bottom_frame, text="Run Workflow", command=self._start_workflow_thread, font=('Arial', 11, 'bold'), bg='lightyellow')
        self.p4_wf_run_button.grid(row=0, column=0, columnspan=2, padx=10, pady=(5, 5), sticky="ew")

        # Status Area
        status_frame = ttk.LabelFrame(bottom_frame, text="Workflow Status")
        status_frame.grid(row=1, column=0, columnspan=2, padx=0, pady=(5,0), sticky="nsew")
        status_frame.grid_rowconfigure(1, weight=1) # Allow log text to expand
        status_frame.grid_columnconfigure(0, weight=1)
        # Progress Bar
        self.p4_wf_progress_bar = ttk.Progressbar(status_frame, variable=self.p4_wf_progress_var, maximum=100)
        self.p4_wf_progress_bar.grid(row=0, column=0, padx=5, pady=(5,2), sticky="ew")
        # Log Text
        self.p4_wf_status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=6, state="disabled")
        self.p4_wf_status_text.grid(row=1, column=0, padx=5, pady=(2,5), sticky="nsew")
        # --- End of UI Building ---


    def _toggle_bulk_mode(self):
        """Updates UI elements based on whether Bulk Mode is enabled."""
        is_bulk = self.p4_wf_is_bulk_mode.get()
        try:
            if is_bulk:
                # Hide single file input, show bulk list/buttons
                if hasattr(self, 'p4_wf_input_label_single'): self.p4_wf_input_label_single.grid_remove()
                if hasattr(self, 'p4_wf_input_file_entry'): self.p4_wf_input_file_entry.grid_remove()
                if hasattr(self, 'p4_wf_browse_button_single'): self.p4_wf_browse_button_single.grid_remove()
                if hasattr(self, 'p4_wf_bulk_input_list_frame'): self.p4_wf_bulk_input_list_frame.grid() # Show bulk frame

                # Force Visual Q&A mode and disable radios
                self.p4_wf_processing_type.set("Visual Q&A (PDF)")
                if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="disabled")
                if hasattr(self, 'p4_wf_text_analysis_radio'): self.p4_wf_text_analysis_radio.config(state="disabled")

                # Force direct save to media and disable checkbox
                self.p4_wf_save_directly_to_media.set(True)
                if hasattr(self, 'p4_wf_save_direct_check'): self.p4_wf_save_direct_check.config(state="disabled")

                # Update run button text
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(text="Run Bulk Visual Workflow")
            else:
                # Show single file input, hide bulk list/buttons
                if hasattr(self, 'p4_wf_input_label_single'): self.p4_wf_input_label_single.grid() # Show single label
                if hasattr(self, 'p4_wf_input_file_entry'): self.p4_wf_input_file_entry.grid() # Show single entry
                if hasattr(self, 'p4_wf_browse_button_single'): self.p4_wf_browse_button_single.grid() # Show single browse
                if hasattr(self, 'p4_wf_bulk_input_list_frame'): self.p4_wf_bulk_input_list_frame.grid_remove() # Hide bulk frame

                # Re-enable radios (respecting PyMuPDF status)
                if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")
                if hasattr(self, 'p4_wf_text_analysis_radio'): self.p4_wf_text_analysis_radio.config(state="normal")

                # Re-enable direct save checkbox
                if hasattr(self, 'p4_wf_save_direct_check'): self.p4_wf_save_direct_check.config(state="normal")

                # Update run button text (will be further updated by _update_ui_for_processing_type)
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(text="Run Workflow")

            # Refresh UI based on potentially changed processing type and media settings
            self._update_ui_for_processing_type()
            self._toggle_media_path_entry() # Ensure media path state is correct

        except tk.TclError as e:
            print(f"P4 WF Bulk Toggle Warning: {e}")
        except AttributeError as e:
            print(f"P4 WF Bulk Toggle Warning (AttributeError): {e}")

    def _update_ui_for_processing_type(self):
        """Shows/hides UI elements based on selected processing type (Visual vs Text)."""
        selected_type = self.p4_wf_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"
        is_bulk = self.p4_wf_is_bulk_mode.get() # Needed for run button text

        try:
            # Update single input label (only if not in bulk mode)
            if not is_bulk and hasattr(self, 'p4_wf_input_label_single'):
                self.p4_wf_input_label_single.config(text="Input PDF:" if is_visual else "Input File (PDF/TXT):")

            # Show/Hide Image Output Frame (use pack/pack_forget for frames managed by pack)
            if hasattr(self, 'p4_wf_image_output_frame') and self.p4_wf_image_output_frame.winfo_exists():
                 if is_visual:
                     # Ensure the frame is packed into the correct parent (left_frame)
                     self.p4_wf_image_output_frame.pack(in_=self.p4_input_frame.master, fill=tk.X, pady=5, before=self.p4_input_frame.master.children.get('!labelframe3', None)) # Place it correctly if packed
                 else:
                     self.p4_wf_image_output_frame.pack_forget() # Hide if not visual

            # Show/Hide Correct Prompt Frames (Right Column - use grid/grid_remove)
            if hasattr(self, 'p4_wf_visual_extract_prompt_frame'):
                 if is_visual: self.p4_wf_visual_extract_prompt_frame.grid()
                 else: self.p4_wf_visual_extract_prompt_frame.grid_remove()
            if hasattr(self, 'p4_wf_text_analysis_prompt_frame'):
                 if not is_visual: self.p4_wf_text_analysis_prompt_frame.grid()
                 else: self.p4_wf_text_analysis_prompt_frame.grid_remove()

            # Update Step 1 Model Label and Dropdown Values
            if hasattr(self, 'p4_wf_step1_model_label'):
                self.p4_wf_step1_model_label.config(text="Extraction/Analysis Model:") # Generic label
            if hasattr(self, 'p4_wf_extraction_model_dropdown'):
                current_model = self.p4_wf_extraction_model.get()
                if is_visual:
                    self.p4_wf_extraction_model_dropdown.config(values=VISUAL_CAPABLE_MODELS)
                    if current_model not in VISUAL_CAPABLE_MODELS and VISUAL_CAPABLE_MODELS:
                        self.p4_wf_extraction_model.set(VISUAL_CAPABLE_MODELS[0])
                    elif not VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model.set("")
                else: # Text Analysis
                    self.p4_wf_extraction_model_dropdown.config(values=GEMINI_UNIFIED_MODELS)
                    if current_model not in GEMINI_UNIFIED_MODELS and GEMINI_UNIFIED_MODELS:
                        self.p4_wf_extraction_model.set(DEFAULT_MODEL if DEFAULT_MODEL in GEMINI_UNIFIED_MODELS else GEMINI_UNIFIED_MODELS[0])
                    elif not GEMINI_UNIFIED_MODELS: self.p4_wf_extraction_model.set("")

            # Show/Hide Text Chunking Config Frame (use grid/grid_remove)
            if hasattr(self, 'p4_wf_text_config_frame') and self.p4_wf_text_config_frame.winfo_exists():
                if not is_visual:
                    self.p4_wf_text_config_frame.grid() # Show
                else:
                    self.p4_wf_text_config_frame.grid_remove() # Hide

            # Update Run Button Text (only if not in bulk mode)
            if not is_bulk and hasattr(self, 'p4_wf_run_button'):
                self.p4_wf_run_button.config(text="Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow")

            # Ensure Visual Q&A radio state is correct (respecting bulk mode disable)
            if not is_bulk and hasattr(self, 'p4_wf_visual_qa_radio'):
                self.p4_wf_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")

        except tk.TclError as e:
            print(f"P4 WF UI Update Warning: {e}")
        except AttributeError as e:
            print(f"P4 WF UI Update Warning (AttributeError): {e}")

    def _toggle_second_pass_widgets(self):
        """Enables/disables second pass model dropdown and prompt frame."""
        is_enabled = self.p4_wf_enable_second_pass.get()
        new_state_widget = tk.NORMAL if is_enabled else tk.DISABLED
        new_state_combo = 'readonly' if is_enabled else tk.DISABLED

        try:
            # Toggle Label State
            if hasattr(self, 'p4_wf_second_pass_model_label'):
                self.p4_wf_second_pass_model_label.config(state=new_state_widget)

            # Toggle Combobox State
            if hasattr(self, 'p4_wf_second_pass_model_dropdown'):
                self.p4_wf_second_pass_model_dropdown.config(state=new_state_combo)

            # Toggle Pass 2 Prompt Frame Visibility and Editor State
            if hasattr(self, 'p4_wf_tagging_pass2_prompt_frame') and self.p4_wf_tagging_pass2_prompt_frame.winfo_exists():
                 if is_enabled:
                     self.p4_wf_tagging_pass2_prompt_frame.grid() # Show frame
                 else:
                     self.p4_wf_tagging_pass2_prompt_frame.grid_remove() # Hide frame

            if hasattr(self, 'p4_wf_second_pass_prompt_text_editor'):
                self.p4_wf_second_pass_prompt_text_editor.config(state=new_state_widget)

            # Log the change
            # self.log_status(f"Second Tagging Pass {'Enabled' if is_enabled else 'Disabled'}.", "info") # Avoid logging during init maybe
        except tk.TclError as e:
            print(f"P4 WF Toggle Second Pass Warning: {e}")
        except AttributeError as e:
            print(f"P4 WF Toggle Second Pass Warning (AttributeError): {e}")

    # --- Prompt Sync Methods ---
    def _sync_prompt_var_from_editor_p4_visual_extract(self, event=None):
        try:
            if hasattr(self, 'p4_wf_visual_extraction_prompt_text') and self.p4_wf_visual_extraction_prompt_text.winfo_exists():
                current_text = self.p4_wf_visual_extraction_prompt_text.get("1.0", tk.END).strip()
                self.p4_wf_visual_extraction_prompt_var.set(current_text)
                self.p4_wf_visual_extraction_prompt_text.edit_modified(False)
        except tk.TclError: pass # Ignore if widget destroyed

    def _sync_prompt_var_from_editor_p4_book_process(self, event=None):
        try:
            if hasattr(self, 'p4_wf_book_processing_prompt_text') and self.p4_wf_book_processing_prompt_text.winfo_exists():
                current_text = self.p4_wf_book_processing_prompt_text.get("1.0", tk.END).strip()
                self.p4_wf_book_processing_prompt_var.set(current_text)
                self.p4_wf_book_processing_prompt_text.edit_modified(False)
        except tk.TclError: pass

    def _sync_prompt_var_from_editor_p4_tag(self, event=None):
        try:
            widget = self.p4_wf_tagging_prompt_text_editor
            if widget and widget.winfo_exists():
                current_text = widget.get("1.0", tk.END).strip()
                self.p4_wf_tagging_prompt_var.set(current_text)
                widget.edit_modified(False)
        except tk.TclError: pass

    def _sync_prompt_var_from_editor_p4_tag_pass2(self, event=None):
        try:
            widget = self.p4_wf_second_pass_prompt_text_editor
            if widget and widget.winfo_exists():
                current_text = widget.get("1.0", tk.END).strip()
                self.p4_wf_second_pass_prompt_var.set(current_text)
                widget.edit_modified(False)
        except tk.TclError: pass

    # --- Logging ---
    def log_status(self, message, level="info"):
        """Logs messages to the status ScrolledText on this page."""
        try:
            if not hasattr(self, 'p4_wf_status_text') or not self.p4_wf_status_text.winfo_exists():
                print(f"P4 WF Status Log (No Widget): {message}") # Fallback print
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
            # Fallback print if TclError occurs (e.g., widget destroyed during log)
            print(f"P4 WF Status Log (backup): {message} (Error: {e})")
        except Exception as e:
            print(f"Unexpected error in P4 WF log_status: {e}")

    # --- File/Directory Selection ---
    def _select_input_file_single(self):
        """Handles browsing for a single input file."""
        selected_type = self.p4_wf_processing_type.get()
        # Determine allowed file types based on selected workflow
        if selected_type == "Visual Q&A (PDF)":
            filetypes = (("PDF files", "*.pdf"), ("All files", "*.*"))
            title = "Select Input PDF for Visual Q&A Workflow"
        else: # Text Analysis
            filetypes = (("Text files", "*.txt"), ("PDF files", "*.pdf"), ("All files", "*.*"))
            title = "Select Input File for Text Analysis Workflow (PDF/TXT)"

        filepath = filedialog.askopenfilename(parent=self, title=title, filetypes=filetypes)
        if filepath:
            # Basic validation
            is_pdf = filepath.lower().endswith(".pdf")
            is_txt = filepath.lower().endswith(".txt")
            if selected_type == "Visual Q&A (PDF)" and not is_pdf:
                show_error_dialog("Invalid File", "Visual Q&A workflow requires a PDF file.", parent=self)
                return
            if selected_type == "Text Analysis (PDF/TXT)" and not (is_pdf or is_txt):
                show_error_dialog("Invalid File", "Text Analysis workflow requires a PDF or TXT file.", parent=self)
                return
            # Dependency check for PDF text analysis
            if selected_type == "Text Analysis (PDF/TXT)" and is_pdf and not PYMUPDF_INSTALLED:
                show_error_dialog("Dependency Missing", "Processing PDF text requires PyMuPDF (fitz).\nPlease install it: pip install PyMuPDF", parent=self)
                return

            # Update variable and log
            self.p4_wf_input_file_path.set(filepath)
            self.log_status(f"Selected input file: {os.path.basename(filepath)}")
        else:
            self.log_status("Input file selection cancelled.")

    def _select_input_files_bulk(self):
        """Handles browsing for multiple PDF files for bulk mode."""
        # Only allow PDF selection
        filepaths = filedialog.askopenfilenames(parent=self, title="Select PDF Files for Bulk Processing", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if filepaths:
            self.p4_wf_input_file_paths = list(filepaths) # Store full paths
            # Update listbox with just basenames
            if hasattr(self, 'p4_wf_bulk_files_listbox'):
                self.p4_wf_bulk_files_listbox.delete(0, tk.END)
                skipped_count = 0
                valid_paths = []
                for fp in self.p4_wf_input_file_paths:
                    if fp.lower().endswith(".pdf"):
                        self.p4_wf_bulk_files_listbox.insert(tk.END, os.path.basename(fp))
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
                 self.log_status(f"Selected {len(self.p4_wf_input_file_paths)} PDF files (listbox not found).")
        else:
            self.log_status("Bulk file selection cancelled.")

    def _clear_bulk_files_list(self):
        """Clears the list of files selected for bulk processing."""
        self.p4_wf_input_file_paths = []
        if hasattr(self, 'p4_wf_bulk_files_listbox'):
            self.p4_wf_bulk_files_listbox.delete(0, tk.END)
        self.log_status("Cleared bulk file list.")

    def _toggle_media_path_entry(self):
        """Enables/disables the Anki media path entry and browse button."""
        try:
            is_direct_save = self.p4_wf_save_directly_to_media.get()
            is_bulk = self.p4_wf_is_bulk_mode.get()

            # Determine state for entry/browse buttons
            media_state = "disabled" # Default to disabled
            if is_direct_save or is_bulk: # Enable if direct save checked OR if in bulk mode
                media_state = "normal"

            # Determine state for detect button (should generally be enabled if visible)
            detect_state = "normal" # **FIX**: Define detect_state unconditionally

            # Apply states
            if hasattr(self, 'p4_wf_anki_media_entry'):
                self.p4_wf_anki_media_entry.config(state=media_state)
            if hasattr(self, 'p4_wf_browse_anki_media_button'):
                self.p4_wf_browse_anki_media_button.config(state=media_state)
            if hasattr(self, 'p4_wf_detect_anki_media_button'):
                # Only configure if the button exists (it might be hidden)
                if self.p4_wf_detect_anki_media_button.winfo_exists():
                     self.p4_wf_detect_anki_media_button.config(state=detect_state)

            # Log and potentially auto-detect path
            if (is_direct_save or is_bulk):
                # Only log if not in bulk mode (bulk mode forces direct save)
                if not is_bulk:
                    self.log_status("Workflow: Direct image save to Anki media enabled.", "info")
                # Attempt auto-detect if path is empty and direct save/bulk is active
                if not self.p4_wf_anki_media_path.get():
                    self._detect_anki_media_path()
            elif not is_bulk: # Log only if not bulk and direct save is off
                self.log_status("Workflow: Direct image save disabled. Images will be saved to a subfolder.", "info")

        except tk.TclError:
            pass # Ignore error if widget is destroyed

    def _select_anki_media_dir(self):
        """Handles browsing for the Anki media directory."""
        initial_dir = self.p4_wf_anki_media_path.get() or guess_anki_media_initial_dir()
        dirpath = filedialog.askdirectory(parent=self, title="Select Anki 'collection.media' Folder (for Workflow)",
                                          initialdir=initial_dir)
        if dirpath:
            if os.path.basename(dirpath).lower() != "collection.media":
                 if ask_yes_no("Confirm Path",
                               f"Selected folder: '{os.path.basename(dirpath)}'.\nThis usually needs to be the 'collection.media' folder.\n\nIs this the correct path?",
                               parent=self):
                     self.p4_wf_anki_media_path.set(dirpath)
                     self.log_status(f"Workflow: Set Anki media path (manual confirm): {dirpath}", "info")
                 else:
                     self.log_status("Workflow: Anki media path selection cancelled.", "info")
            else:
                 self.p4_wf_anki_media_path.set(dirpath)
                 self.log_status(f"Workflow: Selected Anki media path: {dirpath}", "info")
        else:
            self.log_status("Workflow: Anki media path selection cancelled.")

    def _detect_anki_media_path(self):
        """Attempts to detect the Anki media path using AnkiConnect."""
        self.log_status("Workflow: Detecting Anki media path via AnkiConnect...", "info")
        try:
            media_path = detect_anki_media_path(parent_for_dialog=self) # Pass self for dialog parent
            if media_path:
                self.p4_wf_anki_media_path.set(media_path)
                self.log_status(f"Workflow: Detected Anki media path: {media_path}", "info")
                # Ensure widgets are enabled if needed after detection
                if self.p4_wf_save_directly_to_media.get() or self.p4_wf_is_bulk_mode.get():
                    if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state="normal")
                    if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state="normal")
            else:
                # Message handled within detect_anki_media_path if it fails
                 self.log_status("Workflow: AnkiConnect did not return a valid path.", "warning")
        except Exception as e:
             self.log_status(f"Workflow: Failed AnkiConnect path detection: {e}", "error")
             # Optionally show error dialog here as well
             # show_error_dialog("Detection Error", f"Failed to detect path via AnkiConnect:\n{e}", parent=self)


    # --- Workflow Execution ---
    def _start_workflow_thread(self):
        """Validates inputs and starts the appropriate workflow thread."""
        if self.p4_wf_is_processing:
            show_info_dialog("In Progress", "Workflow is already running.", parent=self)
            return

        # --- Get Common Inputs ---
        is_bulk = self.p4_wf_is_bulk_mode.get()
        selected_type = self.p4_wf_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"
        api_key = self.app.gemini_api_key.get()
        step1_model = self.p4_wf_extraction_model.get()
        tag_model_pass1 = self.p4_wf_tagging_model.get()
        tag_prompt_pass1 = self.p4_wf_tagging_prompt_var.get() # Get from variable
        enable_second_pass = self.p4_wf_enable_second_pass.get()
        tag_model_pass2 = self.p4_wf_second_pass_model.get()
        tag_prompt_pass2 = self.p4_wf_second_pass_prompt_var.get() # Get from variable

        # --- Common Validations ---
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            show_error_dialog("Error", "Please enter your Gemini API Key.", parent=self)
            return
        if not step1_model:
            show_error_dialog("Error", f"Please select {'Visual Extraction' if is_visual else 'Text Analysis'} Model.", parent=self)
            return
        if not tag_model_pass1:
            show_error_dialog("Error", "Please select Tagging Model (Pass 1).", parent=self)
            return
        if not tag_prompt_pass1: # Validate variable content
            show_error_dialog("Error", "Tagging prompt (Pass 1) cannot be empty.", parent=self)
            return
        if enable_second_pass:
            if not tag_model_pass2:
                show_error_dialog("Error", "Second Pass is enabled, but Pass 2 model is not selected.", parent=self)
                return
            if not tag_prompt_pass2: # Validate variable content
                show_error_dialog("Error", "Second Pass is enabled, but Pass 2 prompt is empty.", parent=self)
                return
        try:
            tag_batch_size = self.p4_wf_tagging_batch_size.get()
            tag_api_delay = self.p4_wf_tagging_api_delay.get()
            if tag_batch_size <= 0:
                show_error_dialog("Error", "Tagging Batch size must be greater than 0.", parent=self)
                return
            if tag_api_delay < 0:
                self.p4_wf_tagging_api_delay.set(0.0)
                show_info_dialog("Warning", "Tagging API Delay cannot be negative. Setting to 0.", parent=self)
                tag_api_delay=0.0
        except tk.TclError:
            show_error_dialog("Error", "Invalid input for Tagging Batch Size or Delay.", parent=self)
            return

        # --- Mode-Specific Validations & Argument Prep ---
        target_func = None
        args = ()
        if is_bulk:
            # --- Bulk Mode Setup ---
            input_files = self.p4_wf_input_file_paths
            if not input_files:
                show_error_dialog("Error", "Bulk Mode: No PDF files selected in the list.", parent=self)
                return

            # Visual specific settings for bulk mode
            extract_prompt = self.p4_wf_visual_extraction_prompt_var.get() # Get from variable
            anki_media_dir = self.p4_wf_anki_media_path.get()

            if not extract_prompt: # Validate variable content
                show_error_dialog("Error", "Visual Extraction prompt cannot be empty.", parent=self)
                return
            if not PYMUPDF_INSTALLED: # Dependency check
                show_error_dialog("Error", "PyMuPDF (fitz) is required for Bulk Visual Q&A workflow.", parent=self)
                return
            # Media path is mandatory for bulk mode (forced direct save)
            if not anki_media_dir or not os.path.isdir(anki_media_dir):
                show_error_dialog("Error", "Bulk Mode requires a valid Anki media path for direct image saving. Please set it.", parent=self)
                return
            # Optional: Confirm non-standard media path
            if os.path.basename(anki_media_dir).lower() != "collection.media":
                 if not ask_yes_no("Confirm Path", f"Anki media path '{os.path.basename(anki_media_dir)}' doesn't end in 'collection.media'.\nProceed anyway?", parent=self):
                     return

            # Output directory for the final aggregated TSV (use first file's dir)
            output_dir = os.path.dirname(input_files[0]) if input_files else os.getcwd()

            # Prepare arguments for the bulk thread function
            args = (input_files, output_dir, api_key, step1_model, tag_model_pass1, extract_prompt, tag_prompt_pass1, anki_media_dir, tag_batch_size, tag_api_delay,
                    enable_second_pass, tag_model_pass2, tag_prompt_pass2)
            target_func = self._run_bulk_visual_workflow_thread

        else:
            # --- Single File Mode Setup ---
            input_file = self.p4_wf_input_file_path.get()
            if not input_file or not os.path.exists(input_file):
                show_error_dialog("Error", "Please select a valid input file.", parent=self)
                return

            # Output directory derived from input file
            output_dir = os.path.dirname(input_file) if input_file else os.getcwd()
            safe_base_name = sanitize_filename(os.path.splitext(os.path.basename(input_file))[0]) if input_file else "workflow_output"

            if is_visual:
                # --- Single Visual Workflow ---
                extract_prompt = self.p4_wf_visual_extraction_prompt_var.get() # Get from variable
                save_direct = self.p4_wf_save_directly_to_media.get()
                anki_media_dir_from_ui = self.p4_wf_anki_media_path.get()

                if not extract_prompt: # Validate variable content
                    show_error_dialog("Error", "Visual Extraction prompt cannot be empty.", parent=self)
                    return
                if not PYMUPDF_INSTALLED: # Dependency check
                    show_error_dialog("Error", "PyMuPDF (fitz) is required for Visual Q&A workflow.", parent=self)
                    return
                # Validate media path only if direct save is enabled
                if save_direct and (not anki_media_dir_from_ui or not os.path.isdir(anki_media_dir_from_ui)):
                    show_error_dialog("Error", "Direct image save is enabled, but the Anki media path is invalid or not set.", parent=self)
                    return
                # Optional: Confirm non-standard media path if saving directly
                if save_direct and os.path.basename(anki_media_dir_from_ui).lower() != "collection.media":
                     if not ask_yes_no("Confirm Path", f"Direct save path '{os.path.basename(anki_media_dir_from_ui)}' doesn't end in 'collection.media'.\nProceed anyway?", parent=self):
                         return

                # Prepare arguments for single visual thread
                args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model_pass1, extract_prompt, tag_prompt_pass1, save_direct, anki_media_dir_from_ui, tag_batch_size, tag_api_delay,
                         enable_second_pass, tag_model_pass2, tag_prompt_pass2)
                target_func = self._run_single_visual_workflow_thread

            else:
                # --- Single Text Analysis Workflow ---
                analysis_prompt = self.p4_wf_book_processing_prompt_var.get() # Get from variable
                try: # Validate text-specific parameters
                    text_chunk_size = self.p4_wf_text_chunk_size.get()
                    text_api_delay = self.p4_wf_text_api_delay.get()
                    if text_chunk_size <= 0:
                        show_error_dialog("Error", "Text Chunk Size must be greater than 0.", parent=self)
                        return
                    if text_api_delay < 0:
                        self.p4_wf_text_api_delay.set(0.0)
                        show_info_dialog("Warning", "Text API Delay cannot be negative. Setting to 0.", parent=self)
                        text_api_delay=0.0
                except tk.TclError:
                    show_error_dialog("Error", "Invalid input for Text Chunk Size or Delay.", parent=self)
                    return

                if not analysis_prompt: # Validate variable content
                    show_error_dialog("Error", "Text Analysis prompt cannot be empty.", parent=self)
                    return
                # Dependency check for PDF input
                if input_file.lower().endswith(".pdf") and not PYMUPDF_INSTALLED:
                    show_error_dialog("Error", "PyMuPDF (fitz) is required for PDF text analysis.", parent=self)
                    return

                # Prepare arguments for single text analysis thread
                args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model_pass1, analysis_prompt, tag_prompt_pass1, text_chunk_size, text_api_delay, tag_batch_size, tag_api_delay,
                         enable_second_pass, tag_model_pass2, tag_prompt_pass2)
                target_func = self._run_single_text_analysis_workflow_thread

        # --- Start Thread ---
        if target_func:
            self.p4_wf_is_processing = True
            # Update UI to show processing state
            try:
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(state="disabled", text="Workflow Running...")
                # Clear previous status log
                if hasattr(self, 'p4_wf_status_text'):
                    self.p4_wf_status_text.config(state="normal")
                    self.p4_wf_status_text.delete('1.0', tk.END)
                    self.p4_wf_status_text.config(state="disabled")
                if hasattr(self, 'p4_wf_progress_bar'): self.p4_wf_progress_var.set(0)
            except tk.TclError: pass # Ignore if widgets are gone

            self.log_status(f"Starting {'Bulk' if is_bulk else 'Single File'} {selected_type} workflow...")
            # Create and start the background thread
            thread = threading.Thread(target=target_func, args=args, daemon=True)
            thread.start()
        else:
            # Should not happen if logic above is correct, but as a safeguard
            show_error_dialog("Error", "Could not determine workflow function to run.", parent=self)


    def _workflow_finished(self, success=True, final_tsv_path=None, summary_message=None):
        """Called from the main thread after workflow finishes to update UI."""
        self.p4_wf_is_processing = False
        is_bulk = self.p4_wf_is_bulk_mode.get()
        selected_type = self.p4_wf_processing_type.get()
        is_visual = selected_type == "Visual Q&A (PDF)"

        # Determine default button text based on mode
        if is_bulk:
            base_text = "Run Bulk Visual Workflow"
        else:
            base_text = "Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow"

        # Set final button text and color based on success
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
            if summary_message: # Use specific summary if provided (e.g., for bulk)
                self.log_status(summary_message, level="info" if success else "error")
            elif success and final_tsv_path:
                self.log_status(f"Workflow successful. Final Output: {os.path.basename(final_tsv_path)}", level="info")
            elif not success:
                self.log_status(f"Workflow failed. See previous logs for details.", level="error")

            # Update Progress Bar
            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists():
                self.p4_wf_progress_var.set(100 if success else 0) # Full on success, reset on error

        except tk.TclError:
            print("P4 WF Warning: Could not update workflow button/status state on finish.")


    # --- Workflow Thread Targets (Core Logic) ---

    def _run_single_visual_workflow_thread(self, input_pdf_path, output_dir, safe_base_name, api_key,
                                           extract_model_name, tag_model_name_pass1, extract_prompt, tag_prompt_template_pass1,
                                           save_direct_flag, anki_media_dir_from_ui,
                                           tag_batch_size, tag_api_delay,
                                           enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2):
        """Core logic for SINGLE FILE VISUAL Q&A workflow."""
        final_tsv_path = None
        success = False
        uploaded_file_uri = None
        final_image_folder = None
        parsed_data = None
        tagging_success = False # Track if tagging step completed ok
        # Define intermediate path based on output dir and base name
        intermediate_json_path = os.path.join(output_dir, f"{safe_base_name}_intermediate_visual.json")
        final_tsv_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_visual.txt") # Final output

        try:
            start_time = time.time()
            # STEP 1a: Generate Images
            self.after(0, self.log_status, f"Starting Step 1a (Visual): Generating Page Images...", "step")
            self.after(0, self._update_progress_bar, 5)
            # Determine actual image destination (could be Anki media or a subfolder in output_dir)
            image_destination_path = anki_media_dir_from_ui if save_direct_flag else output_dir
            final_image_folder, page_image_map = generate_page_images(
                input_pdf_path, image_destination_path, safe_base_name, save_direct_flag, self.log_status, parent_widget=self, filename_prefix=safe_base_name # Pass prefix
            )
            if final_image_folder is None:
                raise WorkflowStepError("Failed during page image generation.")
            self.after(0, self.log_status, f"Step 1a Complete. Images in: {final_image_folder}", "info")
            self.after(0, self._update_progress_bar, 10)

            # STEP 1b: Gemini Extraction -> JSON
            self.after(0, self.log_status, f"Starting Step 1b (Visual): Gemini JSON Extraction ({extract_model_name})...", "step")
            parsed_data, uploaded_file_uri = call_gemini_visual_extraction(
                input_pdf_path, api_key, extract_model_name, extract_prompt, self.log_status, parent_widget=self
            )
            if parsed_data is None: # Check for failure
                raise WorkflowStepError("Gemini PDF visual extraction failed (check logs/temp files).")
            if not parsed_data: # Handle empty result list
                self.after(0, self.log_status, "No Q&A pairs extracted from the document.", "warning")

            # Add page image map and file prefix to each extracted item (for potential use in generic TSV)
            for item in parsed_data:
                if isinstance(item, dict):
                    item['_page_image_map'] = page_image_map
                    item['_source_pdf_prefix'] = safe_base_name

            # Save the intermediate JSON result (now includes image map and prefix)
            try:
                with open(intermediate_json_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, indent=2)
                self.after(0, self.log_status, f"Saved intermediate JSON: {os.path.basename(intermediate_json_path)}", "info")
            except Exception as json_e:
                raise WorkflowStepError(f"Failed to save intermediate JSON: {json_e}")
            self.after(0, self.log_status, "Step 1b Complete.", "info")
            self.after(0, self._update_progress_bar, 35) # Progress after extraction

            # STEP 2: Tag Intermediate JSON
            if not parsed_data:
                 self.after(0, self.log_status, f"Skipping Tagging Step: No data extracted.", "warning")
                 # Need to generate an empty/header-only TSV if skipping tagging
                 tsv_gen_success = generate_tsv_from_json_data([], final_tsv_path, self.log_status)
                 if not tsv_gen_success: raise WorkflowStepError("Failed to generate empty final TSV.")
                 tagging_success = True # Mark as success for overall status
            else:
                self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging extracted JSON ({tag_model_name_pass1})...", "step")
                # Use the internal helper which calls the correct API function
                final_tagged_data = self._wf_gemini_tag_json( # Use JSON tagging helper
                    intermediate_json_path, # Input is the saved JSON
                    tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                    tag_batch_size, tag_api_delay,
                    enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2
                )
                if final_tagged_data is None: # Check for tagging failure
                    raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")

                tagging_success = True # Mark tagging as successful

                # STEP 3: Generate Final TSV from tagged JSON data
                self.after(0, self.log_status, f"Starting Step 3: Generating Final TSV from tagged data...", "step")
                # Use the generic JSON to TSV converter
                tsv_gen_success = generate_tsv_from_json_data(final_tagged_data, final_tsv_path, self.log_status)
                if not tsv_gen_success:
                    raise WorkflowStepError("Failed to generate final TSV file from tagged data.")
                self.after(0, self.log_status, f"Step 3 Complete: Final tagged file saved: {os.path.basename(final_tsv_path)}", "info")
                self.after(0, self._update_progress_bar, 95) # Progress after tagging/TSV generation

            # Workflow Complete
            end_time = time.time()
            total_time = end_time - start_time
            self.after(0, self.log_status, f"Visual Q&A Workflow finished successfully in {total_time:.2f} seconds!", "info")
            self.after(0, self._update_progress_bar, 100)

            # Prepare and show success message
            success_message = f"Processed '{os.path.basename(input_pdf_path)}'.\nFinal TSV:\n{final_tsv_path}\n\n"
            if save_direct_flag:
                success_message += f"Images Saved Directly To:\n{final_image_folder}"
            else:
                success_message += f"Images Saved To Subfolder:\n{final_image_folder}\n\n"
                success_message += f"IMPORTANT: Manually copy images from\n'{os.path.basename(final_image_folder)}' to Anki's 'collection.media' folder before importing the TSV."
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
            # Cleanup uploaded Gemini file
            if uploaded_file_uri:
                try: cleanup_gemini_file(uploaded_file_uri, api_key, self.log_status)
                except Exception as clean_e: self.after(0, self.log_status, f"Error during cleanup: {clean_e}", "warning")

            # Clean up intermediate JSON file if it exists and workflow was successful
            if success and os.path.exists(intermediate_json_path):
                try:
                    os.remove(intermediate_json_path)
                    self.after(0, self.log_status, f"Cleaned up intermediate JSON: {os.path.basename(intermediate_json_path)}", "debug")
                except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")
            # If workflow failed, still try to remove intermediate JSON
            elif not success and os.path.exists(intermediate_json_path):
                 try:
                    os.remove(intermediate_json_path)
                    self.after(0, self.log_status, f"Cleaned up intermediate JSON (on failure): {os.path.basename(intermediate_json_path)}", "debug")
                 except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")

            # Update UI state
            self.after(0, self._workflow_finished, success, final_tsv_path if success else None)


    def _run_single_text_analysis_workflow_thread(self, input_file_path, output_dir, safe_base_name, api_key,
                                                  analysis_model_name, tag_model_name_pass1, analysis_prompt, tag_prompt_template_pass1,
                                                  text_chunk_size, text_api_delay,
                                                  tag_batch_size, tag_api_delay,
                                                  enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2):
        """Core logic for SINGLE FILE TEXT ANALYSIS workflow."""
        final_tsv_path = None
        success = False
        parsed_data = None
        tagging_success = False # Track tagging step
        # Define intermediate JSON path
        intermediate_json_path = os.path.join(output_dir, f"{safe_base_name}_intermediate_analysis.json")
        final_tsv_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_analysis.txt") # Final output

        try:
            start_time = time.time()
            # STEP 1a: Extract Text
            self.after(0, self.log_status, f"Starting Step 1a (Text): Extracting Text...", "step")
            self.after(0, self._update_progress_bar, 5)
            extracted_text = ""
            file_type = ""
            if input_file_path.lower().endswith(".pdf"):
                extracted_text = extract_text_from_pdf(input_file_path, self.log_status)
                file_type = "PDF"
            elif input_file_path.lower().endswith(".txt"):
                extracted_text = read_text_file(input_file_path, self.log_status)
                file_type = "TXT"
            else: # Should be caught by validation, but double-check
                raise WorkflowStepError("Unsupported file type.")

            if extracted_text is None: # Check for extraction failure
                raise WorkflowStepError(f"Text extraction failed for {file_type}.")
            if not extracted_text.strip(): # Handle empty file
                self.after(0, self.log_status, f"No text content extracted from the {file_type} file. Workflow finished.", "warning")
                # Generate empty TSV and finish successfully
                tsv_gen_success = generate_tsv_from_json_data([], final_tsv_path, self.log_status)
                if not tsv_gen_success: raise WorkflowStepError("Failed to generate empty final TSV.")
                self.after(0, self._workflow_finished, True, final_tsv_path)
                return # Exit thread

            self.after(0, self.log_status, f"Step 1a Complete. Extracted ~{len(extracted_text)} characters.", "info")
            self.after(0, self._update_progress_bar, 10)

            # STEP 1b: Gemini Analysis -> JSON
            self.after(0, self.log_status, f"Starting Step 1b (Text): Gemini Analysis ({analysis_model_name}) in chunks...", "step")
            # This function saves intermediate JSON internally if needed
            parsed_data = call_gemini_text_analysis(
                extracted_text, api_key, analysis_model_name, analysis_prompt, self.log_status,
                output_dir, safe_base_name, # Pass output dir and base name for temp JSON
                text_chunk_size, text_api_delay, parent_widget=self
            )
            if parsed_data is None: # Check for failure
                raise WorkflowStepError("Gemini text analysis failed (check logs/temp files).")
            if not parsed_data: # Handle empty result list
                self.after(0, self.log_status, "No Q&A pairs extracted from text.", "warning")

            # Save the final combined JSON result from the analysis step
            try:
                with open(intermediate_json_path, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, indent=2)
                self.after(0, self.log_status, f"Saved intermediate JSON: {os.path.basename(intermediate_json_path)}", "info")
            except Exception as json_e:
                 raise WorkflowStepError(f"Failed to save intermediate JSON: {json_e}")
            self.after(0, self.log_status, "Step 1b Complete (Gemini chunk processing).", "info")
            self.after(0, self._update_progress_bar, 35) # Progress after analysis

            # STEP 2: Tag Intermediate JSON
            if not parsed_data:
                 self.after(0, self.log_status, f"Skipping Tagging Step: No data extracted.", "warning")
                 # Generate empty/header-only TSV
                 tsv_gen_success = generate_tsv_from_json_data([], final_tsv_path, self.log_status)
                 if not tsv_gen_success: raise WorkflowStepError("Failed to generate empty final TSV.")
                 tagging_success = True # Mark as success for overall status
            else:
                self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging extracted JSON ({tag_model_name_pass1})...", "step")
                # Use the internal helper which calls the correct API function
                final_tagged_data = self._wf_gemini_tag_json( # Use JSON tagging helper
                    intermediate_json_path, # Input is the saved JSON
                    tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                    tag_batch_size, tag_api_delay,
                    enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2
                )
                if final_tagged_data is None: # Check for tagging failure
                    raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")

                tagging_success = True # Mark tagging as successful

                # STEP 3: Generate Final TSV from tagged JSON data
                self.after(0, self.log_status, f"Starting Step 3: Generating Final TSV from tagged data...", "step")
                # Use the generic JSON to TSV converter
                tsv_gen_success = generate_tsv_from_json_data(final_tagged_data, final_tsv_path, self.log_status)
                if not tsv_gen_success:
                    raise WorkflowStepError("Failed to generate final TSV file from tagged data.")
                self.after(0, self.log_status, f"Step 3 Complete: Final tagged file saved: {os.path.basename(final_tsv_path)}", "info")
                self.after(0, self._update_progress_bar, 95) # Progress after tagging/TSV

            # Workflow Complete
            end_time = time.time()
            total_time = end_time - start_time
            self.after(0, self.log_status, f"Text Analysis Workflow finished successfully in {total_time:.2f} seconds!", "info")
            self.after(0, self._update_progress_bar, 100)

            # Prepare and show success message
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
             # Clean up intermediate JSON file if it exists and workflow was successful
            if success and os.path.exists(intermediate_json_path):
                try:
                    os.remove(intermediate_json_path)
                    self.after(0, self.log_status, f"Cleaned up intermediate JSON: {os.path.basename(intermediate_json_path)}", "debug")
                except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")
            # If workflow failed, still try to remove intermediate JSON
            elif not success and os.path.exists(intermediate_json_path):
                 try:
                    os.remove(intermediate_json_path)
                    self.after(0, self.log_status, f"Cleaned up intermediate JSON (on failure): {os.path.basename(intermediate_json_path)}", "debug")
                 except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")

            # Update UI state
            self.after(0, self._workflow_finished, success, final_tsv_path if success else None)


    def _run_bulk_visual_workflow_thread(self, input_pdf_paths, output_dir, api_key,
                                           extract_model_name, tag_model_name_pass1, extract_prompt, tag_prompt_template_pass1,
                                           anki_media_dir,
                                           tag_batch_size, tag_api_delay,
                                           enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2):
        """Core logic for BULK VISUAL Q&A workflow."""
        final_tsv_path = None
        success = False
        uploaded_file_uris = {} # Store URIs for cleanup
        aggregated_json_data = [] # Store successfully extracted JSON objects
        total_files = len(input_pdf_paths)
        processed_files = 0
        success_files = 0
        failed_files = 0
        skipped_files = 0
        start_time = time.time()
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Define intermediate JSON path for aggregated results before tagging
        intermediate_json_path = os.path.join(output_dir, f"bulk_visual_{timestamp_str}_intermediate.json")
        final_tsv_path = os.path.join(output_dir, f"bulk_visual_{timestamp_str}_final_tagged.txt") # Final output

        try:
            # STEP 1: Process Each PDF -> JSON
            self.after(0, self.log_status, f"Starting Step 1: Processing {total_files} PDF files...", "step")
            for pdf_path in input_pdf_paths:
                current_file_success = False
                uploaded_file_uri = None
                parsed_data = None
                processed_files += 1
                file_basename = os.path.basename(pdf_path)
                sanitized_pdf_name = sanitize_filename(os.path.splitext(file_basename)[0])
                self.after(0, self.log_status, f"Processing file {processed_files}/{total_files}: {file_basename}", "info")
                # Update progress bar based on file count (Extraction phase up to 50%)
                self.after(0, self._update_progress_bar, (processed_files / total_files) * 50 if total_files > 0 else 0)

                # Skip non-PDFs (already filtered, but double-check)
                if not pdf_path.lower().endswith(".pdf"):
                    self.after(0, self.log_status, f"Skipping non-PDF file: {file_basename}", "skip")
                    skipped_files += 1
                    continue

                try:
                    # STEP 1a: Generate Images (Directly to Anki media)
                    self.after(0, self.log_status, f"  Step 1a: Generating images for {file_basename}...", "debug")
                    final_image_folder, page_image_map = generate_page_images(
                        pdf_path, anki_media_dir, sanitized_pdf_name, save_direct_flag=True, # Force direct save
                        log_func=self.log_status, parent_widget=self, filename_prefix=sanitized_pdf_name # Use prefix
                    )
                    if final_image_folder is None:
                        raise WorkflowStepError("Image generation failed.")

                    # STEP 1b: Gemini Extraction -> JSON
                    self.after(0, self.log_status, f"  Step 1b: Extracting JSON for {file_basename}...", "debug")
                    parsed_data, uploaded_file_uri = call_gemini_visual_extraction(
                        pdf_path, api_key, extract_model_name, extract_prompt, self.log_status, parent_widget=self
                    )
                    if uploaded_file_uri: # Store URI for later cleanup
                        uploaded_file_uris[pdf_path] = uploaded_file_uri
                    if parsed_data is None: # Check for extraction failure
                        raise WorkflowStepError("Gemini PDF visual extraction failed.")
                    if not parsed_data: # Handle empty result
                        self.after(0, self.log_status, f"Warning: No Q&A pairs extracted from {file_basename}.", "warning")

                    # STEP 1c: Add page image map and file prefix to each extracted item
                    for item in parsed_data:
                        if isinstance(item, dict):
                            item['_page_image_map'] = page_image_map # Store map for this file
                            item['_source_pdf_prefix'] = sanitized_pdf_name # Store prefix

                    # Aggregate successful results
                    if parsed_data:
                        aggregated_json_data.extend(parsed_data)
                        self.after(0, self.log_status, f"  Success: Added {len(parsed_data)} items from {file_basename}.", "debug")

                    success_files += 1
                    current_file_success = True

                except (WorkflowStepError, Exception) as file_e:
                    # Handle errors for a single file
                    self.after(0, self.log_status, f"Failed processing {file_basename}: {file_e}. Attempting to rename...", "error")
                    failed_files += 1
                    current_file_success = False
                    # Attempt to rename the failed file
                    try:
                        pdf_dir = os.path.dirname(pdf_path)
                        new_basename = f"UP_{file_basename}" # Prefix for failed files
                        new_name = os.path.join(pdf_dir, new_basename)
                        counter = 1
                        # Handle potential duplicate 'UP_' files
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
                            # Remove from dict if cleanup successful
                            if pdf_path in uploaded_file_uris: del uploaded_file_uris[pdf_path]
                        except Exception as clean_e:
                            self.after(0, self.log_status, f"Error during immediate cleanup for {file_basename}: {clean_e}", "warning")

            # End of File Processing Loop
            self.after(0, self.log_status, f"Finished processing all {total_files} files. Extracted {len(aggregated_json_data)} total items.", "info")
            self.after(0, self._update_progress_bar, 50) # Mark end of extraction phase

            # STEP 2: Aggregate and Tag
            if not aggregated_json_data: # Check if any data was aggregated
                raise WorkflowStepError("No data successfully extracted from any PDF. Cannot proceed.")

            # Write aggregated intermediate JSON
            self.after(0, self.log_status, f"Writing aggregated intermediate JSON ({len(aggregated_json_data)} items)...", "step")
            try:
                with open(intermediate_json_path, 'w', encoding='utf-8') as f:
                    json.dump(aggregated_json_data, f, indent=2)
                self.after(0, self.log_status, f"Aggregated JSON saved: {os.path.basename(intermediate_json_path)}", "info")
            except IOError as e:
                raise WorkflowStepError(f"Failed to write aggregated intermediate JSON file: {e}")
            self.after(0, self._update_progress_bar, 55) # Progress after saving JSON

            # Tag the aggregated JSON
            self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging aggregated JSON ({tag_model_name_pass1})...", "step")
            # Use the internal helper which calls the correct API function
            final_tagged_data = self._wf_gemini_tag_json( # Use JSON tagging helper
                intermediate_json_path, # Input is the saved aggregated JSON
                tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                tag_batch_size, tag_api_delay,
                enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2
            )
            if final_tagged_data is None: # Check for tagging failure
                raise WorkflowStepError("Gemini tagging step failed for aggregated JSON (check logs/temp files).")

            tagging_success = True # Mark tagging as successful

            # STEP 3: Generate Final TSV from tagged JSON data
            self.after(0, self.log_status, f"Starting Step 3: Generating Final TSV from tagged data...", "step")
            # Use the generic JSON to TSV converter
            # IMPORTANT: This function needs access to the _page_image_map and _source_pdf_prefix
            # stored within each item to correctly generate media links for bulk mode.
            # Ensure generate_tsv_from_json_data handles this.
            tsv_gen_success = generate_tsv_from_json_data(final_tagged_data, final_tsv_path, self.log_status)
            if not tsv_gen_success:
                raise WorkflowStepError("Failed to generate final TSV file from tagged data.")
            self.after(0, self.log_status, f"Step 3 Complete: Final tagged file saved: {os.path.basename(final_tsv_path)}", "info")
            self.after(0, self._update_progress_bar, 95) # Progress after tagging/TSV

            # Workflow Complete
            end_time = time.time()
            total_time = end_time - start_time
            self.after(0, self.log_status, f"Bulk Visual Q&A Workflow finished successfully in {total_time:.2f} seconds!", "info")
            self.after(0, self._update_progress_bar, 100)

            # Prepare and show summary message
            summary = (f"Bulk Processing Complete!\n\n"
                       f"Files Processed: {processed_files}/{total_files}\n"
                       f"Successful: {success_files}\n"
                       f"Failed (Renamed 'UP_'): {failed_files}\n"
                       f"Skipped (Non-PDF): {skipped_files}\n\n"
                       f"Final Tagged File:\n{final_tsv_path}\n\n"
                       f"Images Saved Directly To:\n{anki_media_dir}")
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
            # Final cleanup of any remaining uploaded Gemini files
            for pdf_p, uri in uploaded_file_uris.items():
                try:
                    cleanup_gemini_file(uri, api_key, self.log_status)
                except Exception as clean_e:
                    self.after(0, self.log_status, f"Error during final cleanup for {os.path.basename(pdf_p)}: {clean_e}", "warning")

            # Clean up intermediate JSON file if it exists and workflow was successful
            if success and os.path.exists(intermediate_json_path):
                try:
                    os.remove(intermediate_json_path)
                    self.after(0, self.log_status, f"Cleaned up intermediate JSON: {os.path.basename(intermediate_json_path)}", "debug")
                except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")
            # If workflow failed, still try to remove intermediate JSON
            elif not success and os.path.exists(intermediate_json_path):
                 try:
                    os.remove(intermediate_json_path)
                    self.after(0, self.log_status, f"Cleaned up intermediate JSON (on failure): {os.path.basename(intermediate_json_path)}", "debug")
                 except Exception as rem_e:
                    self.after(0, self.log_status, f"Could not remove intermediate JSON {os.path.basename(intermediate_json_path)}: {rem_e}", "warning")

            # Prepare final summary message for UI update
            final_summary = f"Bulk processing finished. {success_files}/{total_files} successful, {failed_files} failed (renamed 'UP_'), {skipped_files} skipped."
            self.after(0, self._workflow_finished, success, final_tsv_path if success else None, final_summary)


    # --- Internal Helper for Tagging Step (JSON Input/Output) ---
    def _wf_gemini_tag_json(self, input_json_path, system_prompt_pass1, api_key, model_name_pass1,
                           batch_size, api_delay,
                           enable_second_pass, model_name_pass2, system_prompt_pass2):
        """
        Internal helper to run the tagging process on JSON data.
        Reads JSON, calls tagger (which handles 1 or 2 passes), returns final tagged JSON data (list).
        Returns None on failure.
        """
        log_func = self.log_status
        parent = self
        intermediate_json_p1_path = None # Path for saving Pass 1 results if Pass 2 enabled
        intermediate_json_p2_path = None # Path for saving Pass 2 results if enabled
        output_dir = os.path.dirname(input_json_path)
        base_filename = os.path.splitext(os.path.basename(input_json_path))[0]

        try:
            log_func(f"Tagging Step: Reading input JSON {os.path.basename(input_json_path)}", "debug")
            with open(input_json_path, "r", encoding="utf-8") as f:
                input_qa_data = json.load(f)

            if not isinstance(input_qa_data, list):
                log_func("Input JSON for tagging is not a list.", "error")
                return None
            if not input_qa_data:
                log_func("Input JSON for tagging is empty.", "warning")
                return [] # Return empty list if input is empty

            # --- Call the core tagging function from gemini_api ---
            # This function now handles the two passes internally based on flags
            # It expects header+data, so we add a dummy header
            tagged_row_generator = tag_tsv_rows_gemini(
                [{}]+input_qa_data, # Add dummy header for compatibility
                api_key, model_name_pass1, system_prompt_pass1,
                batch_size, api_delay, log_func,
                progress_callback=lambda p: self.after(0, self._update_tagging_progress, p), # Use tagging-specific progress updater
                output_dir=output_dir, # For internal temp files if needed by tagger
                base_filename=base_filename + "_tagging", # Base name for internal temps
                parent_widget=parent,
                enable_second_pass=enable_second_pass, # Pass the flag
                second_pass_model_name=model_name_pass2, # Pass Pass 2 model
                second_pass_prompt=system_prompt_pass2 # Pass Pass 2 prompt
            )

            # Collect the final tagged data (dictionaries) from the generator
            final_tagged_data = list(tagged_row_generator)

            # Check for errors indicated by the generator returning only header or error markers
            if len(final_tagged_data) <= 1 and len(input_qa_data) > 0:
                 if final_tagged_data and isinstance(final_tagged_data[0], list) and "ERROR:" in str(final_tagged_data[0]):
                      raise Exception(f"Tagging failed: {final_tagged_data[0]}")
                 else:
                      raise Exception("Tagging failed (returned no data). Check logs.")

            # Remove the dummy header row we added
            final_tagged_data_actual = final_tagged_data[1:]

            log_func(f"Tagging Step: Finished processing {len(final_tagged_data_actual)} items.", "info")
            return final_tagged_data_actual # Return the list of tagged dictionaries

        except FileNotFoundError:
            log_func(f"Input JSON not found for tagging: {input_json_path}", "error")
            return None
        except Exception as e:
            log_func(f"Error during JSON tagging step: {e}\n{traceback.format_exc()}", "error")
            return None


    def _update_tagging_progress(self, progress_value):
        """Callback specifically for the tagging step's progress within the workflow."""
        # Scale the 0-100 progress from tagging to fit the appropriate range of the workflow bar
        # Extraction/Analysis is roughly 0-35%, Tagging is 35%-95%
        workflow_progress = 35 + (progress_value * 0.60) # 35% base + 60% range for tagging
        self._update_progress_bar(workflow_progress)

    def _update_progress_bar(self, progress_value):
        """Generic callback to update the workflow progress bar."""
        try:
            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists():
                # Ensure value is between 0 and 100
                safe_progress = max(0.0, min(progress_value, 100.0))
                self.p4_wf_progress_var.set(safe_progress)
        except tk.TclError:
            pass # Ignore if widget destroyed
