# ui/page4_workflow.py
import tkinter as tk
# Added BooleanVar, StringVar, IntVar
from tkinter import ttk, filedialog, messagebox, scrolledtext, BooleanVar, StringVar, IntVar
import os
import threading
import traceback
import time # Added for API delay
from datetime import datetime
import shutil # Added for file operations in bulk mode

# Import necessary components using relative paths
try:
    # Added DEFAULT_SECOND_PASS_MODEL, DEFAULT_SECOND_PASS_TAGGING_PROMPT
    from ..constants import (DEFAULT_VISUAL_MODEL, VISUAL_CAPABLE_MODELS, DEFAULT_MODEL, GEMINI_UNIFIED_MODELS,
                           DEFAULT_VISUAL_EXTRACTION_PROMPT, DEFAULT_BOOK_PROCESSING_PROMPT,
                           DEFAULT_BATCH_TAGGING_PROMPT, PYMUPDF_INSTALLED, DEFAULT_SECOND_PASS_MODEL)
    # Added SECOND_PASS_TAGGING (using the actual name from prompts.py)
    from ..prompts import (VISUAL_EXTRACTION, BOOK_PROCESSING, BATCH_TAGGING, SECOND_PASS_TAGGING)
    from ..utils.helpers import (ProcessingError, WorkflowStepError, sanitize_filename,
                           show_error_dialog, show_info_dialog, ask_yes_no, save_tsv_incrementally) # Added save_tsv_incrementally
    from ..core.anki_connect import detect_anki_media_path, guess_anki_media_initial_dir
    from ..core.file_processor import (generate_page_images, extract_text_from_pdf,
                                   read_text_file, generate_tsv_visual,
                                   generate_tsv_text_analysis)
    from ..core.gemini_api import (call_gemini_visual_extraction, call_gemini_text_analysis,
                           cleanup_gemini_file, tag_tsv_rows_gemini, # Removed parse_batch_tag_response (not directly used here)
                           configure_gemini) # Added missing imports
except ImportError:
    # Fallback for direct execution
    print("Error: Relative imports failed in page4_workflow.py. Using direct imports.")
    # Added DEFAULT_SECOND_PASS_MODEL
    from ..constants import (DEFAULT_VISUAL_MODEL, VISUAL_CAPABLE_MODELS, DEFAULT_MODEL, GEMINI_UNIFIED_MODELS,
                           DEFAULT_VISUAL_EXTRACTION_PROMPT, DEFAULT_BOOK_PROCESSING_PROMPT,
                           DEFAULT_BATCH_TAGGING_PROMPT, PYMUPDF_INSTALLED, DEFAULT_SECOND_PASS_MODEL)
    # Added SECOND_PASS_TAGGING
    from ..prompts import (VISUAL_EXTRACTION, BOOK_PROCESSING, BATCH_TAGGING, SECOND_PASS_TAGGING)
    from ..utils.helpers import (ProcessingError, WorkflowStepError, sanitize_filename,
                           show_error_dialog, show_info_dialog, ask_yes_no, save_tsv_incrementally) # Added save_tsv_incrementally
    from ..core.anki_connect import detect_anki_media_path, guess_anki_media_initial_dir
    from ..core.file_processor import (generate_page_images, extract_text_from_pdf,
                                   read_text_file, generate_tsv_visual,
                                   generate_tsv_text_analysis)
    from ..core.gemini_api import (call_gemini_visual_extraction, call_gemini_text_analysis,
                           cleanup_gemini_file, tag_tsv_rows_gemini,
                           configure_gemini)


class WorkflowPage(ttk.Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance

        # --- Page 4 Variables ---
        self.p4_wf_processing_type = StringVar(value="Visual Q&A (PDF)")
        # Single file path (kept for non-bulk mode)
        self.p4_wf_input_file_path = StringVar()
        # Bulk mode variables
        self.p4_wf_is_bulk_mode = BooleanVar(value=False)
        self.p4_wf_input_file_paths = [] # List to store multiple file paths for bulk mode
        # Common variables
        self.p4_wf_save_directly_to_media = BooleanVar(value=False)
        self.p4_wf_anki_media_path = StringVar()
        self.p4_wf_extraction_model = StringVar(value=DEFAULT_VISUAL_MODEL)
        self.p4_wf_tagging_model = StringVar(value=DEFAULT_MODEL) # Renamed to reflect Pass 1
        # Tagging step params (Shared for Pass 1 & 2)
        self.p4_wf_tagging_batch_size = IntVar(value=10)
        self.p4_wf_tagging_api_delay = tk.DoubleVar(value=10.0) # Shared delay
        # Text Analysis step params
        self.p4_wf_text_chunk_size = IntVar(value=30000)
        self.p4_wf_text_api_delay = tk.DoubleVar(value=5.0)
        # Prompts
        self.p4_wf_visual_extraction_prompt_var = StringVar(value=VISUAL_EXTRACTION) # Use imported constant
        self.p4_wf_book_processing_prompt_var = StringVar(value=BOOK_PROCESSING) # Use imported constant
        self.p4_wf_tagging_prompt_var = StringVar(value=BATCH_TAGGING) # Pass 1 tagging prompt
        # --- NEW Second Pass Variables ---
        self.p4_wf_enable_second_pass = BooleanVar(value=False)
        self.p4_wf_second_pass_model = StringVar(value=DEFAULT_SECOND_PASS_MODEL)
        self.p4_wf_second_pass_prompt_var = StringVar(value=SECOND_PASS_TAGGING) # Use the imported prompt
        # State/Progress
        self.p4_wf_progress_var = tk.DoubleVar(value=0)
        self.p4_wf_is_processing = False

        # --- Build UI ---
        self._build_ui()

        # Initial UI state
        self._toggle_bulk_mode() # Call this to set initial visibility based on bulk mode OFF
        self._update_ui_for_processing_type() # Update based on initial processing type
        if not PYMUPDF_INSTALLED:
            if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="disabled")
            if self.p4_wf_processing_type.get() == "Visual Q&A (PDF)":
                self.p4_wf_processing_type.set("Text Analysis (PDF/TXT)")
                self.log_status("PyMuPDF not found. Switched to Text Analysis workflow.", "warning")
                self._update_ui_for_processing_type()
        # Call toggle for second pass widgets AFTER UI is built
        self._toggle_second_pass_widgets()
        print("Initialized WorkflowPage")


    def _build_ui(self):
        """Initialize the Full Workflow page."""
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(5, weight=1) # Prompt area row (adjusted index)
        main_frame.grid_rowconfigure(7, weight=1) # Status Frame row (adjusted index)

        # --- -1. Bulk Mode Toggle ---
        bulk_toggle_frame = ttk.Frame(main_frame)
        bulk_toggle_frame.grid(row=0, column=0, padx=0, pady=(0,10), sticky="ew")
        self.p4_wf_bulk_mode_check = ttk.Checkbutton(
            bulk_toggle_frame,
            text="Enable Bulk PDF Processing Mode",
            variable=self.p4_wf_is_bulk_mode,
            command=self._toggle_bulk_mode # Command to update UI
        )
        self.p4_wf_bulk_mode_check.pack(side=tk.LEFT, padx=5, pady=5)

        # --- 0. Processing Type Selection ---
        self.p4_type_frame = ttk.LabelFrame(main_frame, text="0. Select Workflow Type")
        self.p4_type_frame.grid(row=1, column=0, padx=0, pady=(0,10), sticky="ew")
        self.p4_wf_visual_qa_radio = ttk.Radiobutton(self.p4_type_frame, text="Visual Q&A (PDF)", variable=self.p4_wf_processing_type, value="Visual Q&A (PDF)", command=self._update_ui_for_processing_type, state="disabled")
        self.p4_wf_visual_qa_radio.pack(side=tk.LEFT, padx=10, pady=5)
        self.p4_wf_text_analysis_radio = ttk.Radiobutton(self.p4_type_frame, text="Text Analysis (PDF/TXT)", variable=self.p4_wf_processing_type, value="Text Analysis (PDF/TXT)", command=self._update_ui_for_processing_type)
        self.p4_wf_text_analysis_radio.pack(side=tk.LEFT, padx=10, pady=5)

        # --- 1. Input File Selection ---
        self.p4_input_frame = ttk.LabelFrame(main_frame, text="1. Select Input File(s)")
        self.p4_input_frame.grid(row=2, column=0, padx=0, pady=(0, 10), sticky="ew")
        self.p4_input_frame.grid_columnconfigure(1, weight=1) # Make entry/listbox expand

        # Single File Input Widgets (Managed by _toggle_bulk_mode)
        self.p4_wf_input_label_single = tk.Label(self.p4_input_frame, text="Input File:")
        self.p4_wf_input_label_single.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_input_file_entry = tk.Entry(self.p4_input_frame, textvariable=self.p4_wf_input_file_path, width=70, state="readonly")
        self.p4_wf_input_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.p4_wf_browse_button_single = tk.Button(self.p4_input_frame, text="Browse...", command=self._select_input_file_single)
        self.p4_wf_browse_button_single.grid(row=0, column=2, padx=5, pady=5)

        # Bulk File Input Widgets (Managed by _toggle_bulk_mode)
        self.p4_wf_bulk_input_list_frame = ttk.Frame(self.p4_input_frame)
        self.p4_wf_bulk_input_list_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        self.p4_wf_bulk_input_list_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_bulk_input_list_frame.grid_rowconfigure(0, weight=1)

        self.p4_wf_bulk_files_listbox = tk.Listbox(self.p4_wf_bulk_input_list_frame, selectmode=tk.EXTENDED, height=5)
        self.p4_wf_bulk_files_listbox.grid(row=0, column=0, sticky="nsew")
        bulk_scrollbar = ttk.Scrollbar(self.p4_wf_bulk_input_list_frame, orient=tk.VERTICAL, command=self.p4_wf_bulk_files_listbox.yview)
        bulk_scrollbar.grid(row=0, column=1, sticky="ns")
        self.p4_wf_bulk_files_listbox.config(yscrollcommand=bulk_scrollbar.set)

        bulk_button_frame = ttk.Frame(self.p4_wf_bulk_input_list_frame)
        bulk_button_frame.grid(row=0, column=2, sticky="ns", padx=(5,0))
        self.p4_wf_browse_button_bulk = tk.Button(bulk_button_frame, text="Select PDFs...", command=self._select_input_files_bulk)
        self.p4_wf_browse_button_bulk.pack(pady=5, fill=tk.X)
        self.p4_wf_clear_button_bulk = tk.Button(bulk_button_frame, text="Clear List", command=self._clear_bulk_files_list)
        self.p4_wf_clear_button_bulk.pack(pady=5, fill=tk.X)

        # --- 2. Image Output Location (Conditional) ---
        self.p4_wf_image_output_frame = ttk.LabelFrame(main_frame, text="2. Image Output Location (Visual Q&A Step)")
        self.p4_wf_image_output_frame.grid(row=3, column=0, padx=0, pady=5, sticky="ew")
        self.p4_wf_image_output_frame.grid_columnconfigure(1, weight=1)
        self.p4_wf_save_direct_check = tk.Checkbutton(self.p4_wf_image_output_frame, text="Save Images Directly to Anki collection.media folder", variable=self.p4_wf_save_directly_to_media, command=self._toggle_media_path_entry)
        self.p4_wf_save_direct_check.grid(row=0, column=0, columnspan=3, padx=5, pady=(5,0), sticky="w")
        self.p4_wf_anki_media_label = tk.Label(self.p4_wf_image_output_frame, text="Anki Media Path:")
        self.p4_wf_anki_media_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_anki_media_entry = tk.Entry(self.p4_wf_image_output_frame, textvariable=self.p4_wf_anki_media_path, width=60, state="disabled")
        self.p4_wf_anki_media_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.p4_wf_browse_anki_media_button = tk.Button(self.p4_wf_image_output_frame, text="Browse...", command=self._select_anki_media_dir, state="disabled")
        self.p4_wf_browse_anki_media_button.grid(row=1, column=2, padx=5, pady=5)
        self.p4_wf_detect_anki_media_button = tk.Button(self.p4_wf_image_output_frame, text="Detect via AnkiConnect", command=self._detect_anki_media_path, state="normal")
        self.p4_wf_detect_anki_media_button.grid(row=2, column=1, padx=5, pady=(0,5), sticky="w")

        # --- 3. Workflow Configuration ---
        config_frame = ttk.LabelFrame(main_frame, text="3. Workflow Configuration")
        config_frame.grid(row=4, column=0, padx=0, pady=5, sticky="ew")
        config_frame.grid_columnconfigure(1, weight=1)
        # API Key (Common)
        tk.Label(config_frame, text="Gemini API Key:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_api_key_entry = tk.Entry(config_frame, textvariable=self.app.gemini_api_key, width=50, show="*")
        self.p4_wf_api_key_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky="ew")
        self.p4_wf_show_key_button = tk.Button(config_frame, text="Show/Hide", command=self.app.toggle_api_key_visibility)
        self.p4_wf_show_key_button.grid(row=0, column=4, padx=5, pady=5)
        # Step 1 Model
        self.p4_wf_step1_model_label = tk.Label(config_frame, text="Extraction/Analysis Model:")
        self.p4_wf_step1_model_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_extraction_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p4_wf_extraction_model, values=VISUAL_CAPABLE_MODELS, state="readonly", width=25)
        current_extract_model = self.p4_wf_extraction_model.get(); # Set initial value below
        if current_extract_model in VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model_dropdown.set(current_extract_model)
        elif VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model_dropdown.set(VISUAL_CAPABLE_MODELS[0])
        self.p4_wf_extraction_model_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        # Step 2 Model (Tagging Pass 1)
        tk.Label(config_frame, text="Tagging Model (Pass 1):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_tagging_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p4_wf_tagging_model, values=GEMINI_UNIFIED_MODELS, state="readonly", width=25)
        if GEMINI_UNIFIED_MODELS and self.p4_wf_tagging_model.get() in GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(self.p4_wf_tagging_model.get())
        elif GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(GEMINI_UNIFIED_MODELS[0])
        self.p4_wf_tagging_model_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # --- NEW: Second Pass Tagging Config ---
        # Checkbutton to enable/disable
        self.p4_wf_second_pass_check = ttk.Checkbutton(config_frame, text="Enable Second Tagging Pass (Refinement/Verification)", variable=self.p4_wf_enable_second_pass, command=self._toggle_second_pass_widgets)
        self.p4_wf_second_pass_check.grid(row=3, column=0, columnspan=5, padx=5, pady=(10,0), sticky="w")
        # Label and Combobox for second pass model
        self.p4_wf_second_pass_model_label = tk.Label(config_frame, text="Tagging Model (Pass 2):")
        self.p4_wf_second_pass_model_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_second_pass_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p4_wf_second_pass_model, values=GEMINI_UNIFIED_MODELS, state="disabled", width=25) # Initially disabled
        if GEMINI_UNIFIED_MODELS and self.p4_wf_second_pass_model.get() in GEMINI_UNIFIED_MODELS: self.p4_wf_second_pass_model_dropdown.set(self.p4_wf_second_pass_model.get())
        elif GEMINI_UNIFIED_MODELS: self.p4_wf_second_pass_model_dropdown.set(GEMINI_UNIFIED_MODELS[0]) # Use first available as fallback
        self.p4_wf_second_pass_model_dropdown.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
        # Note: Batch size and delay are reused from first pass, no new widgets needed here.

        # --- Step Specific Configs ---
        # Text Analysis Chunking Config (Managed visibility) - Row index adjusted
        self.p4_wf_text_config_frame = ttk.Frame(config_frame)
        self.p4_wf_text_config_frame.grid(row=5, column=0, columnspan=5, sticky="ew") # Span all columns - Adjusted row index
        tk.Label(self.p4_wf_text_config_frame, text="Text Chunk Size (chars):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        p4_wf_text_chunk_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_chunk_size, width=10)
        p4_wf_text_chunk_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        tk.Label(self.p4_wf_text_config_frame, text="Text API Delay (s):").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        p4_wf_text_delay_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_api_delay, width=10)
        p4_wf_text_delay_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        # Tagging Batching Config (Always visible, applies to Pass 1 and reused for Pass 2) - Row index adjusted
        tk.Label(config_frame, text="Tagging Batch Size (Pass 1 & 2):").grid(row=6, column=0, padx=5, pady=5, sticky="w") # Adjusted row index
        p4_wf_tag_batch_entry = ttk.Entry(config_frame, textvariable=self.p4_wf_tagging_batch_size, width=10)
        p4_wf_tag_batch_entry.grid(row=6, column=1, padx=5, pady=5, sticky="w") # Adjusted row index
        tk.Label(config_frame, text="Tagging API Delay (s) (Pass 1 & 2):").grid(row=6, column=2, padx=5, pady=5, sticky="w") # Adjusted row index
        p4_wf_tag_delay_entry = ttk.Entry(config_frame, textvariable=self.p4_wf_tagging_api_delay, width=10)
        p4_wf_tag_delay_entry.grid(row=6, column=3, padx=5, pady=5, sticky="w") # Adjusted row index


        # --- 4. Prompts Area ---
        self.p4_wf_prompts_area = ttk.Frame(main_frame)
        self.p4_wf_prompts_area.grid(row=5, column=0, padx=0, pady=5, sticky="nsew")
        self.p4_wf_prompts_area.grid_rowconfigure(0, weight=1); self.p4_wf_prompts_area.grid_columnconfigure(0, weight=1)
        # Visual Q&A Prompts Notebook
        self.p4_wf_visual_prompts_notebook = ttk.Notebook(self.p4_wf_prompts_area)
        p4_vis_extract_frame = ttk.Frame(self.p4_wf_visual_prompts_notebook, padding=5); self.p4_wf_visual_prompts_notebook.add(p4_vis_extract_frame, text="Visual Extraction Prompt (Step 1)")
        p4_vis_extract_frame.grid_rowconfigure(0, weight=1); p4_vis_extract_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_visual_extraction_prompt_text = scrolledtext.ScrolledText(p4_vis_extract_frame, wrap=tk.WORD, height=5); self.p4_wf_visual_extraction_prompt_text.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_visual_extraction_prompt_text.insert(tk.END, self.p4_wf_visual_extraction_prompt_var.get()); self.p4_wf_visual_extraction_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_visual_extract)
        p4_vis_tag_frame = ttk.Frame(self.p4_wf_visual_prompts_notebook, padding=5); self.p4_wf_visual_prompts_notebook.add(p4_vis_tag_frame, text="Tagging Prompt (Pass 1)") # Renamed Tab
        p4_vis_tag_frame.grid_rowconfigure(0, weight=1); p4_vis_tag_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_tagging_prompt_text1 = scrolledtext.ScrolledText(p4_vis_tag_frame, wrap=tk.WORD, height=5); self.p4_wf_tagging_prompt_text1.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_tagging_prompt_text1.insert(tk.END, self.p4_wf_tagging_prompt_var.get()); self.p4_wf_tagging_prompt_text1.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag)
        # NEW: Second Pass Prompt Tab (Visual)
        p4_vis_tag2_frame = ttk.Frame(self.p4_wf_visual_prompts_notebook, padding=5); self.p4_wf_visual_prompts_notebook.add(p4_vis_tag2_frame, text="Tagging Prompt (Pass 2)", state="disabled") # Initially disabled
        p4_vis_tag2_frame.grid_rowconfigure(0, weight=1); p4_vis_tag2_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_second_pass_prompt_text1 = scrolledtext.ScrolledText(p4_vis_tag2_frame, wrap=tk.WORD, height=5, state="disabled"); self.p4_wf_second_pass_prompt_text1.grid(row=0, column=0, sticky="nsew") # Initially disabled
        self.p4_wf_second_pass_prompt_text1.insert(tk.END, self.p4_wf_second_pass_prompt_var.get()); self.p4_wf_second_pass_prompt_text1.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag_pass2)

        # Text Analysis Prompts Notebook
        self.p4_wf_text_prompts_notebook = ttk.Notebook(self.p4_wf_prompts_area)
        p4_text_process_frame = ttk.Frame(self.p4_wf_text_prompts_notebook, padding=5); self.p4_wf_text_prompts_notebook.add(p4_text_process_frame, text="Text Analysis Prompt (Step 1)")
        p4_text_process_frame.grid_rowconfigure(0, weight=1); p4_text_process_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_book_processing_prompt_text = scrolledtext.ScrolledText(p4_text_process_frame, wrap=tk.WORD, height=5); self.p4_wf_book_processing_prompt_text.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_book_processing_prompt_text.insert(tk.END, self.p4_wf_book_processing_prompt_var.get()); self.p4_wf_book_processing_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_book_process)
        p4_text_tag_frame = ttk.Frame(self.p4_wf_text_prompts_notebook, padding=5); self.p4_wf_text_prompts_notebook.add(p4_text_tag_frame, text="Tagging Prompt (Pass 1)") # Renamed Tab
        p4_text_tag_frame.grid_rowconfigure(0, weight=1); p4_text_tag_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_tagging_prompt_text2 = scrolledtext.ScrolledText(p4_text_tag_frame, wrap=tk.WORD, height=5); self.p4_wf_tagging_prompt_text2.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_tagging_prompt_text2.insert(tk.END, self.p4_wf_tagging_prompt_var.get()); self.p4_wf_tagging_prompt_text2.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag)
        # NEW: Second Pass Prompt Tab (Text)
        p4_text_tag2_frame = ttk.Frame(self.p4_wf_text_prompts_notebook, padding=5); self.p4_wf_text_prompts_notebook.add(p4_text_tag2_frame, text="Tagging Prompt (Pass 2)", state="disabled") # Initially disabled
        p4_text_tag2_frame.grid_rowconfigure(0, weight=1); p4_text_tag2_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_second_pass_prompt_text2 = scrolledtext.ScrolledText(p4_text_tag2_frame, wrap=tk.WORD, height=5, state="disabled"); self.p4_wf_second_pass_prompt_text2.grid(row=0, column=0, sticky="nsew") # Initially disabled
        self.p4_wf_second_pass_prompt_text2.insert(tk.END, self.p4_wf_second_pass_prompt_var.get()); self.p4_wf_second_pass_prompt_text2.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag_pass2)

        # --- 5. Workflow Action Button ---
        self.p4_wf_run_button = tk.Button(main_frame, text="Run Workflow", command=self._start_workflow_thread, font=('Arial', 11, 'bold'), bg='lightyellow')
        self.p4_wf_run_button.grid(row=6, column=0, padx=10, pady=(10, 5), sticky="ew") # Adjusted row

        # --- 6. Status Area ---
        status_frame = ttk.LabelFrame(main_frame, text="6. Workflow Status")
        status_frame.grid(row=7, column=0, padx=0, pady=5, sticky="nsew") # Adjusted row
        status_frame.grid_rowconfigure(1, weight=1); status_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_progress_bar = ttk.Progressbar(status_frame, variable=self.p4_wf_progress_var, maximum=100)
        self.p4_wf_progress_bar.grid(row=0, column=0, padx=5, pady=(5,2), sticky="ew")
        self.p4_wf_status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=8, state="disabled")
        self.p4_wf_status_text.grid(row=1, column=0, padx=5, pady=(2,5), sticky="nsew")


    def _toggle_bulk_mode(self):
        """Updates UI elements based on the Bulk Mode checkbox state."""
        is_bulk = self.p4_wf_is_bulk_mode.get()
        try:
            # Manage Input Widgets Visibility
            if is_bulk:
                # Hide single file widgets
                if hasattr(self, 'p4_wf_input_label_single'): self.p4_wf_input_label_single.grid_remove()
                if hasattr(self, 'p4_wf_input_file_entry'): self.p4_wf_input_file_entry.grid_remove()
                if hasattr(self, 'p4_wf_browse_button_single'): self.p4_wf_browse_button_single.grid_remove()
                # Show bulk file widgets
                if hasattr(self, 'p4_wf_bulk_input_list_frame'): self.p4_wf_bulk_input_list_frame.grid()
                # Set processing type to Visual and disable radio buttons
                self.p4_wf_processing_type.set("Visual Q&A (PDF)")
                if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="disabled")
                if hasattr(self, 'p4_wf_text_analysis_radio'): self.p4_wf_text_analysis_radio.config(state="disabled")
                # Force direct save and disable checkbox
                self.p4_wf_save_directly_to_media.set(True)
                if hasattr(self, 'p4_wf_save_direct_check'): self.p4_wf_save_direct_check.config(state="disabled")
                self._toggle_media_path_entry() # Update dependent media path widgets
                # Update Run button text
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(text="Run Bulk Visual Workflow")
            else:
                # Show single file widgets
                if hasattr(self, 'p4_wf_input_label_single'): self.p4_wf_input_label_single.grid()
                if hasattr(self, 'p4_wf_input_file_entry'): self.p4_wf_input_file_entry.grid()
                if hasattr(self, 'p4_wf_browse_button_single'): self.p4_wf_browse_button_single.grid()
                # Hide bulk file widgets
                if hasattr(self, 'p4_wf_bulk_input_list_frame'): self.p4_wf_bulk_input_list_frame.grid_remove()
                # Re-enable radio buttons
                if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")
                if hasattr(self, 'p4_wf_text_analysis_radio'): self.p4_wf_text_analysis_radio.config(state="normal")
                # Re-enable direct save checkbox
                if hasattr(self, 'p4_wf_save_direct_check'): self.p4_wf_save_direct_check.config(state="normal")
                self._toggle_media_path_entry() # Update dependent media path widgets based on checkbox state
                # Update Run button text (will be further updated by _update_ui_for_processing_type)
                if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(text="Run Workflow")

            # Update other UI elements based on the (potentially forced) processing type
            self._update_ui_for_processing_type()

        except tk.TclError as e: print(f"P4 WF Bulk Toggle Warning: {e}")
        except AttributeError as e: print(f"P4 WF Bulk Toggle Warning (AttributeError): {e}")


    def _update_ui_for_processing_type(self):
        """Shows/hides UI elements on Page 4 based on selected workflow type."""
        # This function now respects the disabled state set by bulk mode
        selected_type = self.p4_wf_processing_type.get(); is_visual = selected_type == "Visual Q&A (PDF)"
        is_bulk = self.p4_wf_is_bulk_mode.get()

        try:
            # Update Input Label (only for single mode)
            if not is_bulk and hasattr(self, 'p4_wf_input_label_single'):
                self.p4_wf_input_label_single.config(text="Input PDF:" if is_visual else "Input File (PDF/TXT):")

            # Show/Hide Image Output Frame
            if hasattr(self, 'p4_wf_image_output_frame') and self.p4_wf_image_output_frame.winfo_exists():
                if is_visual: self.p4_wf_image_output_frame.grid() # Use grid()
                else: self.p4_wf_image_output_frame.grid_remove()

            # Update Step 1 Model Label and Dropdown Values
            if hasattr(self, 'p4_wf_step1_model_label'): self.p4_wf_step1_model_label.config(text="Visual Extraction Model:" if is_visual else "Text Analysis Model:")
            if hasattr(self, 'p4_wf_extraction_model_dropdown'):
                current_model = self.p4_wf_extraction_model.get()
                if is_visual:
                    self.p4_wf_extraction_model_dropdown.config(values=VISUAL_CAPABLE_MODELS)
                    if current_model not in VISUAL_CAPABLE_MODELS and VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model.set(VISUAL_CAPABLE_MODELS[0])
                    elif not VISUAL_CAPABLE_MODELS: self.p4_wf_extraction_model.set("")
                else: # Text Analysis
                    self.p4_wf_extraction_model_dropdown.config(values=GEMINI_UNIFIED_MODELS) # Show all models
                    if current_model not in GEMINI_UNIFIED_MODELS and GEMINI_UNIFIED_MODELS: self.p4_wf_extraction_model.set(DEFAULT_MODEL if DEFAULT_MODEL in GEMINI_UNIFIED_MODELS else GEMINI_UNIFIED_MODELS[0])
                    elif not GEMINI_UNIFIED_MODELS: self.p4_wf_extraction_model.set("")

            # Show/Hide Text Chunking Config Frame
            if hasattr(self, 'p4_wf_text_config_frame') and self.p4_wf_text_config_frame.winfo_exists():
                if not is_visual: self.p4_wf_text_config_frame.grid() # Use grid()
                else: self.p4_wf_text_config_frame.grid_remove()

            # Show/Hide Correct Prompts Notebook
            if hasattr(self, 'p4_wf_visual_prompts_notebook') and self.p4_wf_visual_prompts_notebook.winfo_exists():
                if is_visual: self.p4_wf_visual_prompts_notebook.grid(row=0, column=0, sticky="nsew")
                else: self.p4_wf_visual_prompts_notebook.grid_remove()
            if hasattr(self, 'p4_wf_text_prompts_notebook') and self.p4_wf_text_prompts_notebook.winfo_exists():
                if not is_visual: self.p4_wf_text_prompts_notebook.grid(row=0, column=0, sticky="nsew")
                else: self.p4_wf_text_prompts_notebook.grid_remove()

            # Update Run Button Text (only if not in bulk mode, bulk mode sets its own text)
            if not is_bulk and hasattr(self, 'p4_wf_run_button'):
                 self.p4_wf_run_button.config(text="Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow")

            # Disable Visual Q&A radio if PyMuPDF is not installed (respect bulk mode disable)
            if not is_bulk and hasattr(self, 'p4_wf_visual_qa_radio'):
                 self.p4_wf_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")

        except tk.TclError as e: print(f"P4 WF UI Update Warning: {e}")
        except AttributeError as e: print(f"P4 WF UI Update Warning (AttributeError): {e}")

    # --- Page 4 Sync Methods ---
    def _sync_prompt_var_from_editor_p4_visual_extract(self, event=None):
        try:
            if hasattr(self, 'p4_wf_visual_extraction_prompt_text') and self.p4_wf_visual_extraction_prompt_text.winfo_exists():
                current_text = self.p4_wf_visual_extraction_prompt_text.get("1.0", tk.END).strip(); self.p4_wf_visual_extraction_prompt_var.set(current_text); self.p4_wf_visual_extraction_prompt_text.edit_modified(False)
        except tk.TclError: pass
    def _sync_prompt_var_from_editor_p4_book_process(self, event=None):
        try:
            if hasattr(self, 'p4_wf_book_processing_prompt_text') and self.p4_wf_book_processing_prompt_text.winfo_exists():
                current_text = self.p4_wf_book_processing_prompt_text.get("1.0", tk.END).strip(); self.p4_wf_book_processing_prompt_var.set(current_text); self.p4_wf_book_processing_prompt_text.edit_modified(False)
        except tk.TclError: pass
    def _sync_prompt_var_from_editor_p4_tag(self, event=None):
        try:
            widget = event.widget;
            if widget and widget.winfo_exists():
                current_text = widget.get("1.0", tk.END).strip(); self.p4_wf_tagging_prompt_var.set(current_text); widget.edit_modified(False)
                other_widget = None
                if hasattr(self, 'p4_wf_tagging_prompt_text1') and widget == self.p4_wf_tagging_prompt_text2: other_widget = self.p4_wf_tagging_prompt_text1
                elif hasattr(self, 'p4_wf_tagging_prompt_text2') and widget == self.p4_wf_tagging_prompt_text1: other_widget = self.p4_wf_tagging_prompt_text2
                if other_widget and other_widget.winfo_exists():
                    if other_widget.get("1.0", tk.END).strip() != current_text:
                        # Determine current state before modifying
                        current_state = other_widget.cget('state')
                        other_widget.config(state=tk.NORMAL); other_widget.delete("1.0", tk.END); other_widget.insert("1.0", current_text); other_widget.edit_modified(False); other_widget.config(state=current_state) # Restore original state
        except tk.TclError: pass

    # --- NEW: Sync method for second pass prompt ---
    def _sync_prompt_var_from_editor_p4_tag_pass2(self, event=None):
        """Syncs the second pass prompt variable from its editor widgets."""
        try:
            widget = event.widget
            if widget and widget.winfo_exists():
                current_text = widget.get("1.0", tk.END).strip()
                self.p4_wf_second_pass_prompt_var.set(current_text)
                widget.edit_modified(False)
                # Sync between the two notebook tabs if needed
                other_widget = None
                if hasattr(self, 'p4_wf_second_pass_prompt_text1') and widget == self.p4_wf_second_pass_prompt_text2:
                    other_widget = self.p4_wf_second_pass_prompt_text1
                elif hasattr(self, 'p4_wf_second_pass_prompt_text2') and widget == self.p4_wf_second_pass_prompt_text1:
                    other_widget = self.p4_wf_second_pass_prompt_text2

                if other_widget and other_widget.winfo_exists():
                    if other_widget.get("1.0", tk.END).strip() != current_text:
                        # Determine current state before modifying
                        current_state = other_widget.cget('state')
                        other_widget.config(state=tk.NORMAL)
                        other_widget.delete("1.0", tk.END)
                        other_widget.insert("1.0", current_text)
                        other_widget.edit_modified(False)
                        # Re-apply original state
                        other_widget.config(state=current_state)
        except tk.TclError:
            pass

    # --- Page 4 Logging ---
    def log_status(self, message, level="info"):
        """Logs message to the Page 4 Workflow status area"""
        try:
            if not hasattr(self, 'p4_wf_status_text') or not self.p4_wf_status_text.winfo_exists(): return
            self.p4_wf_status_text.config(state="normal"); prefix_map = {"info": "[INFO] ", "step": "[STEP] ", "warning": "[WARN] ", "error": "[ERROR] ", "upload": "[UPLOAD] ", "debug": "[DEBUG] ", "skip": "[SKIP] "}; prefix = prefix_map.get(level, "[INFO] "); timestamp = datetime.now().strftime("%H:%M:%S"); self.p4_wf_status_text.insert(tk.END, f"{timestamp} {prefix}{message}\n"); self.p4_wf_status_text.see(tk.END); self.p4_wf_status_text.config(state="disabled"); self.update_idletasks()
        except tk.TclError as e: print(f"P4 WF Status Log (backup): {message} (Error: {e})")

    # --- Page 4 File Selection & Path Helpers ---
    def _select_input_file_single(self):
        """Selects a single input file (non-bulk mode)."""
        selected_type = self.p4_wf_processing_type.get()
        if selected_type == "Visual Q&A (PDF)": filetypes = (("PDF files", "*.pdf"), ("All files", "*.*")); title = "Select Input PDF for Visual Q&A Workflow"
        else: filetypes = (("Text files", "*.txt"), ("PDF files", "*.pdf"), ("All files", "*.*")); title = "Select Input File for Text Analysis Workflow (PDF/TXT)"
        filepath = filedialog.askopenfilename(parent=self, title=title, filetypes=filetypes)
        if filepath:
            is_pdf = filepath.lower().endswith(".pdf"); is_txt = filepath.lower().endswith(".txt")
            if selected_type == "Visual Q&A (PDF)" and not is_pdf: show_error_dialog("Invalid File", "Visual Q&A workflow requires a PDF file.", parent=self); return
            if selected_type == "Text Analysis (PDF/TXT)" and not (is_pdf or is_txt): show_error_dialog("Invalid File", "Text Analysis workflow requires a PDF or TXT file.", parent=self); return
            if selected_type == "Text Analysis (PDF/TXT)" and is_pdf and not PYMUPDF_INSTALLED: show_error_dialog("Dependency Missing", "Processing PDF text requires PyMuPDF (fitz).\nPlease install it: pip install PyMuPDF", parent=self); return
            self.p4_wf_input_file_path.set(filepath); self.log_status(f"Selected input file: {os.path.basename(filepath)}")
        else: self.log_status("Input file selection cancelled.")

    def _select_input_files_bulk(self):
        """Selects multiple PDF files for bulk mode."""
        filepaths = filedialog.askopenfilenames(
            parent=self,
            title="Select PDF Files for Bulk Processing",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if filepaths:
            self.p4_wf_input_file_paths = list(filepaths) # Store as list
            # Update listbox
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
            self.p4_wf_input_file_paths = valid_paths # Keep only valid PDFs
            self.log_status(f"Selected {len(self.p4_wf_input_file_paths)} PDF files for bulk processing." + (f" Skipped {skipped_count} non-PDF files." if skipped_count else ""))
        else:
            self.log_status("Bulk file selection cancelled.")

    def _clear_bulk_files_list(self):
        """Clears the bulk file list and listbox."""
        self.p4_wf_input_file_paths = []
        if hasattr(self, 'p4_wf_bulk_files_listbox'):
            self.p4_wf_bulk_files_listbox.delete(0, tk.END)
        self.log_status("Cleared bulk file list.")

    def _toggle_media_path_entry(self):
        try:
            is_direct_save = self.p4_wf_save_directly_to_media.get()
            is_bulk = self.p4_wf_is_bulk_mode.get()
            # Media path entry/browse enabled only if direct save is checked (and not disabled by bulk mode)
            media_state = "normal" if is_direct_save else "disabled"
            if is_bulk: media_state = "normal" # Force normal state in bulk mode as direct save is forced

            # Detect button always enabled unless direct save is off (and not in bulk mode)
            detect_state = "normal" # Always enabled, detection is useful regardless of saving preference

            if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state=media_state)
            if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state=media_state)
            if hasattr(self, 'p4_wf_detect_anki_media_button'): self.p4_wf_detect_anki_media_button.config(state=detect_state)

            # Log state changes
            if is_direct_save and not is_bulk:
                self.log_status("Workflow: Direct image save to Anki media enabled.", "info");
                if not self.p4_wf_anki_media_path.get(): self._detect_anki_media_path()
            elif not is_direct_save and not is_bulk:
                self.log_status("Workflow: Direct image save disabled. Images -> subfolder.", "info")
            # Bulk mode log is handled in _toggle_bulk_mode

        except tk.TclError: pass

    def _select_anki_media_dir(self):
        initial_dir = self.p4_wf_anki_media_path.get() or guess_anki_media_initial_dir()
        dirpath = filedialog.askdirectory(parent=self, title="Select Anki 'collection.media' Folder (for Workflow)", initialdir=initial_dir)
        if dirpath:
            if os.path.basename(dirpath).lower() != "collection.media":
                 if ask_yes_no("Confirm Path", f"Selected folder: '{os.path.basename(dirpath)}'.\nUsually needs to be 'collection.media'.\n\nIs this correct?", parent=self):
                     self.p4_wf_anki_media_path.set(dirpath); self.log_status(f"Workflow: Set Anki media path (manual confirm): {dirpath}", "info")
                 else: self.log_status("Workflow: Anki media path selection cancelled.", "info")
            else: self.p4_wf_anki_media_path.set(dirpath); self.log_status(f"Workflow: Selected Anki media path: {dirpath}", "info")
    def _detect_anki_media_path(self):
        self.log_status("Workflow: Detecting Anki media path via AnkiConnect...", "info")
        try:
            media_path = detect_anki_media_path(parent_for_dialog=self)
            if media_path:
                self.p4_wf_anki_media_path.set(media_path); self.log_status(f"Workflow: Detected Anki media path: {media_path}", "info")
                # Enable entry/browse only if direct save is also checked (and not in bulk mode)
                if self.p4_wf_save_directly_to_media.get() or self.p4_wf_is_bulk_mode.get(): # Enable if direct save checked OR if in bulk mode
                    if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state="normal")
                    if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state="normal")
            else: self.log_status("Workflow: AnkiConnect did not return a valid path.", "warning")
        except Exception as e: self.log_status(f"Workflow: Failed AnkiConnect path detection: {e}", "error")

    # --- NEW: Toggle Second Pass Widgets ---
    def _toggle_second_pass_widgets(self):
        """Enables/disables second pass model dropdown and prompt tabs/editors."""
        is_enabled = self.p4_wf_enable_second_pass.get()
        new_state_widget = tk.NORMAL if is_enabled else tk.DISABLED
        new_state_combo = 'readonly' if is_enabled else tk.DISABLED
        new_state_tab = 'normal' if is_enabled else 'disabled' # State for notebook tabs

        try:
            # Toggle Model Label and Dropdown
            if hasattr(self, 'p4_wf_second_pass_model_label'):
                self.p4_wf_second_pass_model_label.config(state=new_state_widget)
            if hasattr(self, 'p4_wf_second_pass_model_dropdown'):
                self.p4_wf_second_pass_model_dropdown.config(state=new_state_combo)

            # Toggle Prompt Tabs and Editors
            if hasattr(self, 'p4_wf_visual_prompts_notebook'):
                try:
                    # Find the tab index by text (more robust than hardcoding index 2)
                    tab_index = -1
                    for i in range(self.p4_wf_visual_prompts_notebook.index('end')):
                        if self.p4_wf_visual_prompts_notebook.tab(i, 'text') == "Tagging Prompt (Pass 2)":
                            tab_index = i
                            break
                    if tab_index != -1:
                        self.p4_wf_visual_prompts_notebook.tab(tab_index, state=new_state_tab)
                except tk.TclError: pass # Ignore error if tab doesn't exist
            if hasattr(self, 'p4_wf_second_pass_prompt_text1'):
                self.p4_wf_second_pass_prompt_text1.config(state=new_state_widget)

            if hasattr(self, 'p4_wf_text_prompts_notebook'):
                try:
                    tab_index = -1
                    for i in range(self.p4_wf_text_prompts_notebook.index('end')):
                         if self.p4_wf_text_prompts_notebook.tab(i, 'text') == "Tagging Prompt (Pass 2)":
                             tab_index = i
                             break
                    if tab_index != -1:
                        self.p4_wf_text_prompts_notebook.tab(tab_index, state=new_state_tab)
                except tk.TclError: pass # Ignore error
            if hasattr(self, 'p4_wf_second_pass_prompt_text2'):
                self.p4_wf_second_pass_prompt_text2.config(state=new_state_widget)

            self.log_status(f"Second Tagging Pass {'Enabled' if is_enabled else 'Disabled'}.", "info")

        except tk.TclError as e:
            print(f"P4 WF Toggle Second Pass Warning: {e}")
        except AttributeError as e:
            print(f"P4 WF Toggle Second Pass Warning (AttributeError): {e}")


    # --- Page 4 Workflow Execution ---
    def _start_workflow_thread(self):
        """Validates inputs and starts the appropriate workflow thread."""
        if self.p4_wf_is_processing: show_info_dialog("In Progress", "Workflow running.", parent=self); return

        is_bulk = self.p4_wf_is_bulk_mode.get()
        selected_type = self.p4_wf_processing_type.get() # This is forced to Visual in bulk mode
        is_visual = selected_type == "Visual Q&A (PDF)" # Will be true in bulk mode
        api_key = self.app.gemini_api_key.get()
        step1_model = self.p4_wf_extraction_model.get()
        tag_model_pass1 = self.p4_wf_tagging_model.get() # Renamed for clarity
        tag_prompt_pass1 = self.p4_wf_tagging_prompt_var.get() # Pass 1 prompt

        # --- Get Second Pass Config ---
        enable_second_pass = self.p4_wf_enable_second_pass.get()
        tag_model_pass2 = self.p4_wf_second_pass_model.get() # Renamed for clarity
        tag_prompt_pass2 = self.p4_wf_second_pass_prompt_var.get() # Pass 2 prompt

        # --- Common Validations ---
        if not api_key or api_key == "YOUR_API_KEY_HERE": show_error_dialog("Error", "Enter Gemini API Key.", parent=self); return
        if not step1_model: show_error_dialog("Error", f"Select {'Visual Extraction' if is_visual else 'Text Analysis'} Model.", parent=self); return
        if not tag_model_pass1: show_error_dialog("Error", "Select Tagging Model (Pass 1).", parent=self); return
        if not tag_prompt_pass1: show_error_dialog("Error", "Tagging prompt (Pass 1) empty.", parent=self); return
        # --- Second Pass Validations (only if enabled) ---
        if enable_second_pass:
            if not tag_model_pass2: show_error_dialog("Error", "Second Pass enabled, but Pass 2 model not selected.", parent=self); return
            if not tag_prompt_pass2: show_error_dialog("Error", "Second Pass enabled, but Pass 2 prompt is empty.", parent=self); return
        try: # Validate tagging params (shared)
            tag_batch_size = self.p4_wf_tagging_batch_size.get(); tag_api_delay = self.p4_wf_tagging_api_delay.get()
            if tag_batch_size <= 0: show_error_dialog("Error", "Tagging Batch size must be > 0.", parent=self); return
            if tag_api_delay < 0: self.p4_wf_tagging_api_delay.set(0.0); show_info_dialog("Warning", "Tagging API Delay negative. Setting to 0.", parent=self); tag_api_delay=0.0 # Use updated value
        except tk.TclError: show_error_dialog("Error", "Invalid Tagging Batch Size or Delay.", parent=self); return

        # --- Mode-Specific Validations & Argument Prep ---
        target_func = None; args = ()
        if is_bulk:
            input_files = self.p4_wf_input_file_paths
            if not input_files: show_error_dialog("Error", "Bulk Mode: No PDF files selected.", parent=self); return
            # Bulk mode forces Visual Q&A and Direct Save
            extract_prompt = self.p4_wf_visual_extraction_prompt_var.get(); save_direct = True; anki_media_dir = self.p4_wf_anki_media_path.get()
            if not extract_prompt: show_error_dialog("Error", "Visual Extraction prompt empty.", parent=self); return
            if not PYMUPDF_INSTALLED: show_error_dialog("Error", "PyMuPDF (fitz) is required for Bulk Visual Q&A workflow.", parent=self); return # Should be disabled anyway
            if not anki_media_dir or not os.path.isdir(anki_media_dir): show_error_dialog("Error", "Bulk Mode requires a valid Anki media path for direct image saving.", parent=self); return
            if os.path.basename(anki_media_dir).lower() != "collection.media":
                 if not ask_yes_no("Confirm Path", f"Anki media path '{os.path.basename(anki_media_dir)}' doesn't end in 'collection.media'.\nProceed anyway?", parent=self): return
            # Determine output dir for the final aggregated TSV (e.g., based on first input file's dir)
            output_dir = os.path.dirname(input_files[0]) if input_files else os.getcwd()
            # Pass list of files and bulk-specific params, including second pass
            args = (input_files, output_dir, api_key, step1_model, tag_model_pass1, extract_prompt, tag_prompt_pass1, anki_media_dir, tag_batch_size, tag_api_delay,
                    enable_second_pass, tag_model_pass2, tag_prompt_pass2) # Pass second pass args
            target_func = self._run_bulk_visual_workflow_thread
        else: # Single File Mode
            input_file = self.p4_wf_input_file_path.get()
            if not input_file or not os.path.exists(input_file): show_error_dialog("Error", "Select valid input file.", parent=self); return
            output_dir = os.path.dirname(input_file) if input_file else os.getcwd()
            safe_base_name = sanitize_filename(os.path.splitext(os.path.basename(input_file))[0]) if input_file else "workflow_output" # Use splitext

            if is_visual:
                extract_prompt = self.p4_wf_visual_extraction_prompt_var.get(); save_direct = self.p4_wf_save_directly_to_media.get(); anki_media_dir = self.p4_wf_anki_media_path.get()
                if not extract_prompt: show_error_dialog("Error", "Visual Extraction prompt empty.", parent=self); return
                if not PYMUPDF_INSTALLED: show_error_dialog("Error", "PyMuPDF (fitz) is required for Visual Q&A workflow.", parent=self); return
                if save_direct and (not anki_media_dir or not os.path.isdir(anki_media_dir)): show_error_dialog("Error", "Direct image save enabled, but Anki media path invalid.", parent=self); return
                if save_direct and os.path.basename(anki_media_dir).lower() != "collection.media":
                     if not ask_yes_no("Confirm Path", f"Direct save path '{os.path.basename(anki_media_dir)}' doesn't end in 'collection.media'.\nProceed anyway?", parent=self): return
                # Pass common params + visual specific, including second pass
                args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model_pass1, extract_prompt, tag_prompt_pass1, save_direct, anki_media_dir, tag_batch_size, tag_api_delay,
                         enable_second_pass, tag_model_pass2, tag_prompt_pass2) # Pass second pass args
                target_func = self._run_single_visual_workflow_thread # Use renamed single file function
            else: # Text Analysis
                analysis_prompt = self.p4_wf_book_processing_prompt_var.get()
                try: # Validate text chunk/delay
                    text_chunk_size = self.p4_wf_text_chunk_size.get(); text_api_delay = self.p4_wf_text_api_delay.get()
                    if text_chunk_size <= 0: show_error_dialog("Error", "Text Chunk Size must be > 0.", parent=self); return
                    if text_api_delay < 0: self.p4_wf_text_api_delay.set(0.0); show_info_dialog("Warning", "Text API Delay negative. Setting to 0.", parent=self); text_api_delay=0.0 # Use updated value
                except tk.TclError: show_error_dialog("Error", "Invalid Text Chunk Size or Delay.", parent=self); return
                if not analysis_prompt: show_error_dialog("Error", "Text Analysis prompt empty.", parent=self); return
                if input_file.lower().endswith(".pdf") and not PYMUPDF_INSTALLED: show_error_dialog("Error", "PyMuPDF (fitz) required for PDF text analysis.", parent=self); return
                # Pass common params + text specific, including second pass
                args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model_pass1, analysis_prompt, tag_prompt_pass1, text_chunk_size, text_api_delay, tag_batch_size, tag_api_delay,
                         enable_second_pass, tag_model_pass2, tag_prompt_pass2) # Pass second pass args
                target_func = self._run_single_text_analysis_workflow_thread # Use renamed single file function

        # --- Start Thread ---
        self.p4_wf_is_processing = True
        try:
            if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(state="disabled", text="Workflow Running...")
            if hasattr(self, 'p4_wf_status_text'): self.p4_wf_status_text.config(state="normal"); self.p4_wf_status_text.delete('1.0', tk.END); self.p4_wf_status_text.config(state="disabled")
            if hasattr(self, 'p4_wf_progress_bar'): self.p4_wf_progress_var.set(0)
        except tk.TclError: pass
        self.log_status(f"Starting {'Bulk' if is_bulk else 'Single File'} {selected_type} workflow...")
        thread = threading.Thread(target=target_func, args=args, daemon=True); thread.start()

    def _workflow_finished(self, success=True, final_tsv_path=None, summary_message=None):
        """Called from the main thread after workflow finishes."""
        self.p4_wf_is_processing = False
        is_bulk = self.p4_wf_is_bulk_mode.get()
        selected_type = self.p4_wf_processing_type.get() # Will be Visual in bulk mode
        is_visual = selected_type == "Visual Q&A (PDF)"

        if is_bulk:
            base_text = "Run Bulk Visual Workflow"
        else:
            base_text = "Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow"

        final_button_text = base_text
        final_bg = 'lightyellow'
        if not success:
            final_button_text = "Workflow Failed (See Log)"
            final_bg = 'salmon'

        try:
            if hasattr(self, 'p4_wf_run_button') and self.p4_wf_run_button.winfo_exists():
                self.p4_wf_run_button.config(state="normal", text=final_button_text, bg=final_bg)

            if summary_message: # Use provided summary if available (for bulk)
                 self.log_status(summary_message, level="info" if success else "error")
            elif success and final_tsv_path:
                 self.log_status(f"Workflow successful. Final Output: {os.path.basename(final_tsv_path)}", level="info")
            elif not success:
                 self.log_status(f"Workflow failed. See previous logs for details.", level="error")

            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists():
                self.p4_wf_progress_var.set(100 if success else 0)
        except tk.TclError:
            print("P4 WF Warning: Could not update workflow button state.")

    # --- Single Visual Q&A Workflow Thread (Accepts Pass 2 Args) ---
    def _run_single_visual_workflow_thread(self, input_pdf_path, output_dir, safe_base_name, api_key,
                                          extract_model_name, tag_model_name_pass1, extract_prompt, tag_prompt_template_pass1,
                                          save_direct_flag, anki_media_dir_from_ui,
                                          tag_batch_size, tag_api_delay,
                                          enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2): # Added Pass 2 args
        """The core logic for the SINGLE FILE VISUAL Q&A workflow running in a thread."""
        final_output_path = None; success = False; uploaded_file_uri = None; visual_tsv_path = None; final_image_folder = None; parsed_data = None; tagging_success = False
        try:
            start_time = time.time()
            # === STEP 1a: Generate Page Images ===
            self.after(0, self.log_status, f"Starting Step 1a (Visual): Generating Page Images...", "step"); self.after(0, self._update_progress_bar, 5)
            if save_direct_flag: image_destination_path = anki_media_dir_from_ui
            else: image_destination_path = os.path.join(output_dir, f"{safe_base_name}_workflow_images_{datetime.now():%Y%m%d_%H%M%S}")
            final_image_folder, page_image_map = generate_page_images(input_pdf_path, image_destination_path, safe_base_name, save_direct_flag, self.log_status, parent_widget=self, filename_prefix=None)
            if final_image_folder is None: raise WorkflowStepError("Failed during page image generation.")
            self.after(0, self.log_status, f"Step 1a Complete.", "info"); self.after(0, self._update_progress_bar, 15)

            # === STEP 1b: Gemini PDF Visual Extraction (JSON) ===
            self.after(0, self.log_status, f"Starting Step 1b (Visual): Gemini JSON Extraction ({extract_model_name})...", "step")
            parsed_data, uploaded_file_uri = call_gemini_visual_extraction(input_pdf_path, api_key, extract_model_name, extract_prompt, self.log_status, parent_widget=self)
            if parsed_data is None: raise WorkflowStepError("Gemini PDF visual extraction failed (check logs/temp files).")
            if not parsed_data: self.after(0, self.log_status, "No Q&A pairs extracted from the document.", "warning")
            self.after(0, self.log_status, "Step 1b Complete.", "info"); self.after(0, self._update_progress_bar, 40)

            # === STEP 1c: Generating Visual TSV from JSON ===
            self.after(0, self.log_status, f"Starting Step 1c (Visual): Generating intermediate TSV...", "step")
            visual_tsv_rows = generate_tsv_visual(parsed_data, page_image_map, self.log_status, return_rows=True)
            if visual_tsv_rows is None: raise WorkflowStepError("Failed to generate intermediate visual TSV data.")
            visual_tsv_path = os.path.join(output_dir, f"{safe_base_name}_intermediate_visual.tsv")
            try:
                with open(visual_tsv_path, 'w', encoding='utf-8', newline='') as f:
                    f.write("\t".join(["Question", "QuestionMedia", "Answer", "AnswerMedia"]) + "\n")
                    for row in visual_tsv_rows: f.write("\t".join(map(str, row)) + "\n")
            except IOError as e: raise WorkflowStepError(f"Failed to write intermediate visual TSV file: {e}")
            self.after(0, self.log_status, f"Step 1 Complete (Visual): Intermediate TSV saved.", "info"); self.after(0, self._update_progress_bar, 50)

            # === STEP 2: Tag Intermediate TSV using Gemini ===
            if not visual_tsv_rows:
                 self.after(0, self.log_status, f"Skipping Tagging Step: No data rows in intermediate TSV.", "warning")
                 final_output_path = visual_tsv_path # Use the intermediate path as final
                 tagging_success = True # Mark as success for cleanup logic
            else:
                self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging Visual TSV ({tag_model_name_pass1})...", "step")
                final_output_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_visual.txt")
                # Pass second pass args to tagging helper
                tagging_success = self._wf_gemini_tag_tsv(
                    visual_tsv_path, final_output_path, tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                    tag_batch_size, tag_api_delay,
                    enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2 # Pass 2 args
                )
                if not tagging_success: raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")
                self.after(0, self.log_status, f"Step 2 Complete (Tagging): Final tagged file saved: {os.path.basename(final_output_path)}", "info"); self.after(0, self._update_progress_bar, 95)

            # === Workflow Complete ===
            end_time = time.time(); total_time = end_time - start_time; self.after(0, self.log_status, f"Visual Q&A Workflow finished successfully in {total_time:.2f} seconds!", "info"); self.after(0, self._update_progress_bar, 100)
            success_message = f"Processed '{os.path.basename(input_pdf_path)}'.\nFinal file generated:\n{final_output_path}\n\n";
            if save_direct_flag: success_message += f"Images Saved Directly To:\n{final_image_folder}"
            else: success_message += f"Images Saved To Subfolder:\n{final_image_folder}\n\nIMPORTANT: Manually copy images from\n'{os.path.basename(final_image_folder)}' to Anki's 'collection.media' folder before importing the TSV."
            self.after(0, show_info_dialog, "Workflow Complete", success_message, self); success = True
        except WorkflowStepError as wse: self.after(0, self.log_status, f"Visual Workflow stopped: {wse}", "error"); self.after(0, show_error_dialog, "Workflow Failed", f"Failed: {wse}\nCheck log and temp files.", self); success = False
        except Exception as e: error_message = f"Unexpected visual workflow error: {type(e).__name__}: {e}"; self.after(0, self.log_status, f"FATAL WORKFLOW ERROR (Visual): {error_message}\n{traceback.format_exc()}", "error"); self.after(0, show_error_dialog, "Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self); success = False
        finally:
            if uploaded_file_uri:
                 try: cleanup_gemini_file(uploaded_file_uri, api_key, self.log_status)
                 except Exception as clean_e: self.after(0, self.log_status, f"Error during cleanup: {clean_e}", "warning")
            # Clean up intermediate file if it exists and tagging succeeded (or was skipped) AND second pass was NOT enabled
            if tagging_success and not enable_second_pass and visual_tsv_path and os.path.exists(visual_tsv_path):
                 try: os.remove(visual_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file: {os.path.basename(visual_tsv_path)}", "debug")
                 except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(visual_tsv_path)}: {rem_e}", "warning")
            # If tagging failed, intermediate file is cleaned inside _wf_gemini_tag_tsv if pass 2 enabled, otherwise here
            elif not tagging_success and visual_tsv_path and os.path.exists(visual_tsv_path):
                 try: os.remove(visual_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file (on failure): {os.path.basename(visual_tsv_path)}", "debug")
                 except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(visual_tsv_path)}: {rem_e}", "warning")
            self.after(0, self._workflow_finished, success, final_output_path if success else None)


    # --- Single Text Analysis Workflow Thread (Accepts Pass 2 Args) ---
    def _run_single_text_analysis_workflow_thread(self, input_file_path, output_dir, safe_base_name, api_key,
                                                 analysis_model_name, tag_model_name_pass1, analysis_prompt, tag_prompt_template_pass1,
                                                 text_chunk_size, text_api_delay, # Text step params
                                                 tag_batch_size, tag_api_delay, # Tagging step params
                                                 enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2): # Added Pass 2 args
        """The core logic for the SINGLE FILE TEXT ANALYSIS workflow running in a thread."""
        final_output_path = None; success = False; analysis_tsv_path = None; parsed_data = None; tagging_success = False
        try:
            start_time = time.time()
            # === STEP 1a: Extract Text Content ===
            self.after(0, self.log_status, f"Starting Step 1a (Text): Extracting Text...", "step"); self.after(0, self._update_progress_bar, 5)
            extracted_text = ""; file_type = ""
            if input_file_path.lower().endswith(".pdf"): extracted_text = extract_text_from_pdf(input_file_path, self.log_status); file_type = "PDF"
            elif input_file_path.lower().endswith(".txt"): extracted_text = read_text_file(input_file_path, self.log_status); file_type = "TXT"
            if extracted_text is None: raise WorkflowStepError(f"Text extraction failed for {file_type}.")
            if not extracted_text: self.after(0, self.log_status, f"No text content extracted from the {file_type} file. Workflow finished.", "warning"); self.after(0, self._workflow_finished, True, None); return
            self.after(0, self.log_status, f"Step 1a Complete. Extracted ~{len(extracted_text)} characters.", "info"); self.after(0, self._update_progress_bar, 15)

            # === STEP 1b: Gemini Text Analysis (Chunked) ===
            self.after(0, self.log_status, f"Starting Step 1b (Text): Gemini Analysis ({analysis_model_name}) in chunks...", "step")
            parsed_data = call_gemini_text_analysis(
                extracted_text, api_key, analysis_model_name, analysis_prompt, self.log_status,
                output_dir, safe_base_name, # For incremental saving
                text_chunk_size, text_api_delay, # Chunking params
                parent_widget=self
            )
            if parsed_data is None: raise WorkflowStepError("Gemini text analysis failed (check logs/temp files).")
            if not parsed_data: self.after(0, self.log_status, "No Q&A pairs extracted from text.", "warning")
            self.after(0, self.log_status, "Step 1b Complete (Gemini chunk processing).", "info"); self.after(0, self._update_progress_bar, 40)

            # === STEP 1c: Generating Text Analysis Intermediate TSV ===
            self.after(0, self.log_status, f"Starting Step 1c (Text): Generating intermediate TSV...", "step")
            analysis_tsv_path = generate_tsv_text_analysis(parsed_data, output_dir, safe_base_name + "_intermediate", self.log_status) # Temp name
            if analysis_tsv_path is None: raise WorkflowStepError("Failed to write intermediate text analysis TSV.")
            self.after(0, self.log_status, f"Step 1 Complete (Text): Intermediate TSV saved.", "info"); self.after(0, self._update_progress_bar, 50)

            # === STEP 2: Tag Intermediate TSV using Gemini ===
            if not parsed_data:
                 self.after(0, self.log_status, f"Skipping Tagging Step: No data rows from text analysis.", "warning")
                 final_output_path = analysis_tsv_path # Use intermediate as final
                 tagging_success = True # Mark as success for cleanup logic
            else:
                self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging Analysis TSV ({tag_model_name_pass1})...", "step")
                final_output_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_analysis.txt")
                # Pass second pass args to tagging helper
                tagging_success = self._wf_gemini_tag_tsv(
                    analysis_tsv_path, final_output_path, tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                    tag_batch_size, tag_api_delay,
                    enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2 # Pass 2 args
                )
                if not tagging_success: raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")
                self.after(0, self.log_status, f"Step 2 Complete (Tagging): Final tagged file saved: {os.path.basename(final_output_path)}", "info"); self.after(0, self._update_progress_bar, 95)

            # === Workflow Complete ===
            end_time = time.time(); total_time = end_time - start_time; self.after(0, self.log_status, f"Text Analysis Workflow finished successfully in {total_time:.2f} seconds!", "info"); self.after(0, self._update_progress_bar, 100)
            success_message = f"Processed '{os.path.basename(input_file_path)}'.\nFinal file generated:\n{final_output_path}\n"
            self.after(0, show_info_dialog, "Workflow Complete", success_message, self); success = True
        except WorkflowStepError as wse: self.after(0, self.log_status, f"Text Analysis Workflow stopped: {wse}", "error"); self.after(0, show_error_dialog, "Workflow Failed", f"Failed: {wse}\nCheck log and temp files.", self); success = False
        except Exception as e: error_message = f"Unexpected text analysis workflow error: {type(e).__name__}: {e}"; self.after(0, self.log_status, f"FATAL WORKFLOW ERROR (Text): {error_message}\n{traceback.format_exc()}", "error"); self.after(0, show_error_dialog, "Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self); success = False
        finally:
            # Clean up intermediate file if it exists and tagging succeeded (or was skipped) AND second pass was NOT enabled
            if tagging_success and not enable_second_pass and analysis_tsv_path and os.path.exists(analysis_tsv_path):
                 try: os.remove(analysis_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file: {os.path.basename(analysis_tsv_path)}", "debug")
                 except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(analysis_tsv_path)}: {rem_e}", "warning")
            # If tagging failed, intermediate file is cleaned inside _wf_gemini_tag_tsv if pass 2 enabled, otherwise here
            elif not tagging_success and analysis_tsv_path and os.path.exists(analysis_tsv_path):
                 try: os.remove(analysis_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file (on failure): {os.path.basename(analysis_tsv_path)}", "debug")
                 except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(analysis_tsv_path)}: {rem_e}", "warning")
            self.after(0, self._workflow_finished, success, final_output_path if success else None)


    # --- Bulk Visual Q&A Workflow Thread (Accepts Pass 2 Args) ---
    def _run_bulk_visual_workflow_thread(self, input_pdf_paths, output_dir, api_key,
                                          extract_model_name, tag_model_name_pass1, extract_prompt, tag_prompt_template_pass1,
                                          anki_media_dir, # Direct save is forced ON
                                          tag_batch_size, tag_api_delay,
                                          enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2): # Added Pass 2 args
        """The core logic for the BULK VISUAL Q&A workflow running in a thread."""
        final_output_path = None; success = False; intermediate_tsv_path = None; tagging_success = False
        uploaded_file_uris = {} # Track URIs per input file for cleanup
        aggregated_tsv_rows = [["Question", "QuestionMedia", "Answer", "AnswerMedia"]] # Start with header
        total_files = len(input_pdf_paths)
        processed_files = 0; success_files = 0; failed_files = 0; skipped_files = 0
        start_time = time.time()

        try:
            # --- File Processing Loop ---
            for pdf_path in input_pdf_paths:
                current_file_success = False # Track success for this specific file
                processed_files += 1
                file_basename = os.path.basename(pdf_path)
                self.after(0, self.log_status, f"Processing file {processed_files}/{total_files}: {file_basename}", "step")
                self.after(0, self._update_progress_bar, (processed_files / total_files) * 50) # 0-50% for file processing

                if not pdf_path.lower().endswith(".pdf"):
                    self.after(0, self.log_status, f"Skipping non-PDF file: {file_basename}", "skip"); skipped_files += 1; continue

                sanitized_pdf_name = sanitize_filename(os.path.splitext(file_basename)[0])
                page_image_map = None; parsed_data = None; visual_tsv_rows_for_file = None; uploaded_file_uri = None

                try:
                    # === STEP 1a: Generate Page Images (Direct Save, Prefixed) ===
                    self.after(0, self.log_status, f"  Step 1a: Generating images for {file_basename}...", "debug")
                    final_image_folder, page_image_map = generate_page_images(pdf_path, anki_media_dir, sanitized_pdf_name, save_direct_flag=True, log_func=self.log_status, parent_widget=self, filename_prefix=sanitized_pdf_name)
                    if final_image_folder is None: raise WorkflowStepError("Image generation failed.")

                    # === STEP 1b: Gemini PDF Visual Extraction (JSON) ===
                    self.after(0, self.log_status, f"  Step 1b: Extracting JSON for {file_basename}...", "debug")
                    parsed_data, uploaded_file_uri = call_gemini_visual_extraction(pdf_path, api_key, extract_model_name, extract_prompt, self.log_status, parent_widget=self)
                    if uploaded_file_uri: uploaded_file_uris[pdf_path] = uploaded_file_uri
                    if parsed_data is None: raise WorkflowStepError("Gemini PDF visual extraction failed.")
                    if not parsed_data: self.after(0, self.log_status, f"Warning: No Q&A pairs extracted from {file_basename}.", "warning")

                    # === STEP 1c: Generating Visual TSV Rows from JSON ===
                    self.after(0, self.log_status, f"  Step 1c: Generating TSV rows for {file_basename}...", "debug")
                    visual_tsv_rows_for_file = generate_tsv_visual(parsed_data, page_image_map, self.log_status, return_rows=True)
                    if visual_tsv_rows_for_file is None: raise WorkflowStepError("Failed to generate TSV data rows.")

                    if visual_tsv_rows_for_file: aggregated_tsv_rows.extend(visual_tsv_rows_for_file); self.after(0, self.log_status, f"  Success: Added {len(visual_tsv_rows_for_file)} rows from {file_basename}.", "debug")
                    else: self.after(0, self.log_status, f"  Info: No data rows generated for {file_basename}.", "debug")
                    success_files += 1; current_file_success = True

                except (WorkflowStepError, Exception) as file_e:
                    self.after(0, self.log_status, f"Failed processing {file_basename}: {file_e}. Attempting to rename...", "error"); failed_files += 1; current_file_success = False
                    try:
                        pdf_dir = os.path.dirname(pdf_path); new_basename = f"UP_{file_basename}"; new_name = os.path.join(pdf_dir, new_basename); counter = 1
                        while os.path.exists(new_name): name, ext = os.path.splitext(new_basename); new_name = os.path.join(pdf_dir, f"{name}_{counter}{ext}"); counter += 1
                        os.rename(pdf_path, new_name); self.after(0, self.log_status, f"Renamed failed file to: {os.path.basename(new_name)}", "warning")
                    except OSError as rename_e: self.after(0, self.log_status, f"Could not rename failed file {file_basename}: {rename_e}", "error")
                    except Exception as rename_gen_e: self.after(0, self.log_status, f"Unexpected error renaming file {file_basename}: {rename_gen_e}", "error")

            # --- End of File Loop ---
            self.after(0, self.log_status, f"Finished processing all {total_files} files.", "info"); self.after(0, self._update_progress_bar, 50)

            # === STEP 2: Aggregate and Tag ===
            if len(aggregated_tsv_rows) <= 1: raise WorkflowStepError("No data rows were successfully extracted from any PDF. Cannot proceed to tagging.")

            intermediate_tsv_filename = f"bulk_visual_{datetime.now():%Y%m%d_%H%M%S}_intermediate.tsv"
            intermediate_tsv_path = os.path.join(output_dir, intermediate_tsv_filename)
            self.after(0, self.log_status, f"Writing aggregated intermediate TSV ({len(aggregated_tsv_rows)-1} data rows)...", "step")
            try:
                with open(intermediate_tsv_path, 'w', encoding='utf-8', newline='') as f:
                    for row in aggregated_tsv_rows: f.write("\t".join(map(str, row)) + "\n")
            except IOError as e: raise WorkflowStepError(f"Failed to write aggregated intermediate TSV file: {e}")
            self.after(0, self.log_status, f"Intermediate TSV saved: {intermediate_tsv_filename}", "info"); self.after(0, self._update_progress_bar, 55)

            self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging aggregated TSV ({tag_model_name_pass1})...", "step")
            final_output_filename = f"bulk_visual_{datetime.now():%Y%m%d_%H%M%S}_final_tagged.txt"
            final_output_path = os.path.join(output_dir, final_output_filename)
            # Pass second pass args to tagging helper
            tagging_success = self._wf_gemini_tag_tsv(
                intermediate_tsv_path, final_output_path, tag_prompt_template_pass1, api_key, tag_model_name_pass1,
                tag_batch_size, tag_api_delay,
                enable_second_pass, tag_model_name_pass2, tag_prompt_template_pass2 # Pass 2 args
            )
            if not tagging_success: raise WorkflowStepError("Gemini tagging step failed for aggregated TSV (check logs/temp files).")
            self.after(0, self.log_status, f"Step 2 Complete (Tagging): Final tagged file saved: {final_output_filename}", "info"); self.after(0, self._update_progress_bar, 95)

            # === Workflow Complete ===
            end_time = time.time(); total_time = end_time - start_time; self.after(0, self.log_status, f"Bulk Visual Q&A Workflow finished successfully in {total_time:.2f} seconds!", "info"); self.after(0, self._update_progress_bar, 100)
            summary = f"Bulk Processing Complete!\n\nFiles Processed: {processed_files}/{total_files}\nSuccessful: {success_files}\nFailed (Renamed 'UP_'): {failed_files}\nSkipped (Non-PDF): {skipped_files}\n\nFinal Tagged File:\n{final_output_path}\n\nImages Saved Directly To:\n{anki_media_dir}"
            self.after(0, show_info_dialog, "Bulk Workflow Complete", summary, self); success = True

        except WorkflowStepError as wse: self.after(0, self.log_status, f"Bulk Workflow stopped: {wse}", "error"); self.after(0, show_error_dialog, "Bulk Workflow Failed", f"Failed: {wse}\nCheck log and temp files.", self); success = False
        except Exception as e: error_message = f"Unexpected bulk workflow error: {type(e).__name__}: {e}"; self.after(0, self.log_status, f"FATAL BULK WORKFLOW ERROR: {error_message}\n{traceback.format_exc()}", "error"); self.after(0, show_error_dialog, "Bulk Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self); success = False
        finally:
            for pdf_p, uri in uploaded_file_uris.items():
                 try: cleanup_gemini_file(uri, api_key, self.log_status)
                 except Exception as clean_e: self.after(0, self.log_status, f"Error during cleanup for {os.path.basename(pdf_p)}: {clean_e}", "warning")
            # Clean up intermediate TSV if it exists and tagging succeeded AND second pass was NOT enabled
            if tagging_success and not enable_second_pass and intermediate_tsv_path and os.path.exists(intermediate_tsv_path):
                try: os.remove(intermediate_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file: {os.path.basename(intermediate_tsv_path)}", "debug")
                except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(intermediate_tsv_path)}: {rem_e}", "warning")
            # If tagging failed, intermediate file is cleaned inside _wf_gemini_tag_tsv if pass 2 enabled, otherwise here
            elif not tagging_success and intermediate_tsv_path and os.path.exists(intermediate_tsv_path):
                 try: os.remove(intermediate_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file (on failure): {os.path.basename(intermediate_tsv_path)}", "debug")
                 except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(intermediate_tsv_path)}: {rem_e}", "warning")
            final_summary = f"Bulk processing finished. {success_files}/{total_files} successful, {failed_files} failed (renamed 'UP_'), {skipped_files} skipped."
            self.after(0, self._workflow_finished, success, final_output_path if success else None, final_summary)


    # --- Shared Workflow Helper Method for Tagging (Accepts Pass 2 Args) ---
    def _wf_gemini_tag_tsv(self, input_tsv_path, output_tsv_path, system_prompt_pass1, api_key, model_name_pass1,
                           batch_size, api_delay,
                           enable_second_pass, model_name_pass2, system_prompt_pass2): # Added pass 2 args
        """Reads TSV, tags it using Gemini batches (potentially 2 passes), writes new TSV. Returns True/False."""
        log_func = self.log_status; parent = self # Use page 4's logger and parent
        pass1_output_path = None # Initialize here for cleanup in except block
        try:
            log_func(f"Tagging Step: Starting for {os.path.basename(input_tsv_path)}", level="info")
            tag_output_dir = os.path.dirname(output_tsv_path)
            base_filename = os.path.splitext(os.path.basename(output_tsv_path))[0]
            pass1_output_path = output_tsv_path # Default if no second pass
            if enable_second_pass:
                pass1_output_path = os.path.join(tag_output_dir, f"{base_filename}_pass1_temp.tsv")
                log_func(f"Second pass enabled. Pass 1 outputting to temporary file: {os.path.basename(pass1_output_path)}", "debug")

            with open(input_tsv_path, "r", encoding="utf-8") as f: lines = f.readlines()
            if not lines: log_func("Input TSV for tagging is empty.", "warning"); return True
            data_rows_with_header = [line.strip().split("\t") for line in lines if line.strip()]
            if len(data_rows_with_header) <= 1: log_func("No data rows found in TSV for tagging (excluding header).", "warning"); return True

            # --- Call tag_tsv_rows_gemini (which now handles both passes) ---
            log_func(f"Calling core tagging function (Pass 1 Model: {model_name_pass1})...", "info")
            tagged_row_generator = tag_tsv_rows_gemini(
                data_rows_with_header, api_key, model_name_pass1, system_prompt_pass1,
                batch_size, api_delay, log_func, # Pass page 4 logger
                progress_callback=lambda p: self._update_tagging_progress(p, pass_num=1, total_passes=2 if enable_second_pass else 1), # Use pass 1 progress for now
                output_dir=tag_output_dir,
                base_filename=f"{base_filename}_inc", # Incremental save name
                parent_widget=parent,
                # Pass second pass parameters
                enable_second_pass=enable_second_pass,
                second_pass_model_name=model_name_pass2,
                second_pass_prompt=system_prompt_pass2
            )

            # Write the final tagged file (output from the generator)
            with open(output_tsv_path, "w", encoding="utf-8", newline='') as f:
                for output_row in tagged_row_generator:
                    f.write("\t".join(map(str, output_row)) + "\n")

            log_func(f"Tagging Step: Finished. Final Output: {os.path.basename(output_tsv_path)}", "info")
            # Note: Intermediate file cleanup (if pass 2 was enabled) should happen inside tag_tsv_rows_gemini now.
            return True # Overall success

        except FileNotFoundError: log_func(f"Input TSV not found for tagging: {input_tsv_path}", "error"); return False
        except Exception as e:
            log_func(f"Error during TSV tagging step: {e}\n{traceback.format_exc()}", "error")
            # Cleanup temp pass1 file if it exists and error occurred (though it should be handled internally now)
            if enable_second_pass and pass1_output_path and os.path.exists(pass1_output_path):
                 try: os.remove(pass1_output_path); log_func("Cleaned up temporary Pass 1 file (on error).", "debug")
                 except Exception as rem_e: log_func(f"Could not remove temp Pass 1 file: {rem_e}", "warning")
            return False

    def _update_tagging_progress(self, progress_value, pass_num=1, total_passes=1):
        """Callback specifically for the tagging step's progress, handling multiple passes."""
        # Workflow progress is 0-50% for step 1, 50-100% for step 2 (tagging)
        progress_per_pass = 50.0 / total_passes
        base_progress = 50.0 + (progress_per_pass * (pass_num - 1))
        current_pass_progress = (progress_value / 100.0) * progress_per_pass
        workflow_progress = base_progress + current_pass_progress
        self._update_progress_bar(workflow_progress)

    def _update_progress_bar(self, progress_value):
        """Generic callback to update the workflow progress bar."""
        try:
            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists():
                self.p4_wf_progress_var.set(min(progress_value, 100.0)) # Cap at 100
        except tk.TclError: pass