# ui/page4_workflow.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import traceback
import time # Added for API delay
from datetime import datetime

# Import necessary components using relative paths
try:
    from ..constants import (DEFAULT_VISUAL_MODEL, VISUAL_CAPABLE_MODELS, DEFAULT_MODEL, GEMINI_UNIFIED_MODELS,
                         DEFAULT_VISUAL_EXTRACTION_PROMPT, DEFAULT_BOOK_PROCESSING_PROMPT,
                         DEFAULT_BATCH_TAGGING_PROMPT, PYMUPDF_INSTALLED)
    from ..utils.helpers import (ProcessingError, WorkflowStepError, sanitize_filename,
                               show_error_dialog, show_info_dialog, ask_yes_no)
    from ..core.anki_connect import detect_anki_media_path, guess_anki_media_initial_dir
    from ..core.file_processor import (generate_page_images, extract_text_from_pdf,
                                    read_text_file, generate_tsv_visual,
                                    generate_tsv_text_analysis)
    from ..core.gemini_api import (call_gemini_visual_extraction, call_gemini_text_analysis,
                               cleanup_gemini_file, tag_tsv_rows_gemini, parse_batch_tag_response,
                               configure_gemini) # Added missing imports
except ImportError:
    # Fallback for direct execution
    print("Error: Relative imports failed in page4_workflow.py. Using direct imports.")
    from constants import (DEFAULT_VISUAL_MODEL, VISUAL_CAPABLE_MODELS, DEFAULT_MODEL, GEMINI_UNIFIED_MODELS,
                         DEFAULT_VISUAL_EXTRACTION_PROMPT, DEFAULT_BOOK_PROCESSING_PROMPT,
                         DEFAULT_BATCH_TAGGING_PROMPT, PYMUPDF_INSTALLED)
    from utils.helpers import (ProcessingError, WorkflowStepError, sanitize_filename,
                               show_error_dialog, show_info_dialog, ask_yes_no)
    from core.anki_connect import detect_anki_media_path, guess_anki_media_initial_dir
    from core.file_processor import (generate_page_images, extract_text_from_pdf,
                                    read_text_file, generate_tsv_visual,
                                    generate_tsv_text_analysis)
    from core.gemini_api import (call_gemini_visual_extraction, call_gemini_text_analysis,
                               cleanup_gemini_file, tag_tsv_rows_gemini, parse_batch_tag_response,
                               configure_gemini)


class WorkflowPage(ttk.Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance

        # --- Page 4 Variables ---
        self.p4_wf_processing_type = tk.StringVar(value="Visual Q&A (PDF)")
        self.p4_wf_input_file_path = tk.StringVar()
        self.p4_wf_save_directly_to_media = tk.BooleanVar(value=False)
        self.p4_wf_anki_media_path = tk.StringVar()
        self.p4_wf_extraction_model = tk.StringVar(value=DEFAULT_VISUAL_MODEL)
        self.p4_wf_tagging_model = tk.StringVar(value=DEFAULT_MODEL)
        # Tagging step params
        self.p4_wf_tagging_batch_size = tk.IntVar(value=10) # Renamed for clarity
        self.p4_wf_tagging_api_delay = tk.DoubleVar(value=10.0) # Renamed for clarity
        # NEW: Text Analysis step params
        self.p4_wf_text_chunk_size = tk.IntVar(value=30000)
        self.p4_wf_text_api_delay = tk.DoubleVar(value=5.0)
        # Prompts
        self.p4_wf_visual_extraction_prompt_var = tk.StringVar(value=DEFAULT_VISUAL_EXTRACTION_PROMPT)
        self.p4_wf_book_processing_prompt_var = tk.StringVar(value=DEFAULT_BOOK_PROCESSING_PROMPT)
        self.p4_wf_tagging_prompt_var = tk.StringVar(value=DEFAULT_BATCH_TAGGING_PROMPT)
        # State/Progress
        self.p4_wf_progress_var = tk.DoubleVar(value=0)
        self.p4_wf_is_processing = False

        # --- Build UI ---
        self._build_ui()

        # Initial UI state
        self._update_ui_for_processing_type()
        if not PYMUPDF_INSTALLED:
            if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="disabled")
            if self.p4_wf_processing_type.get() == "Visual Q&A (PDF)":
                self.p4_wf_processing_type.set("Text Analysis (PDF/TXT)")
                self.log_status("PyMuPDF not found. Switched to Text Analysis workflow.", "warning")
                self._update_ui_for_processing_type()
        print("Initialized WorkflowPage")


    def _build_ui(self):
        """Initialize the Full Workflow page."""
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(4, weight=1) # Prompt area row
        main_frame.grid_rowconfigure(6, weight=1) # Status Frame row

        # --- 0. Processing Type Selection ---
        p4_type_frame = ttk.LabelFrame(main_frame, text="0. Select Workflow Type")
        p4_type_frame.grid(row=0, column=0, padx=0, pady=(0,10), sticky="ew")
        self.p4_wf_visual_qa_radio = ttk.Radiobutton(p4_type_frame, text="Visual Q&A (PDF)", variable=self.p4_wf_processing_type, value="Visual Q&A (PDF)", command=self._update_ui_for_processing_type, state="disabled")
        self.p4_wf_visual_qa_radio.pack(side=tk.LEFT, padx=10, pady=5)
        self.p4_wf_text_analysis_radio = ttk.Radiobutton(p4_type_frame, text="Text Analysis (PDF/TXT)", variable=self.p4_wf_processing_type, value="Text Analysis (PDF/TXT)", command=self._update_ui_for_processing_type)
        self.p4_wf_text_analysis_radio.pack(side=tk.LEFT, padx=10, pady=5)

        # --- 1. Input File Selection ---
        p4_input_frame = ttk.LabelFrame(main_frame, text="1. Select Input File")
        p4_input_frame.grid(row=1, column=0, padx=0, pady=(0, 10), sticky="ew")
        p4_input_frame.grid_columnconfigure(1, weight=1) # Make entry expand (changed index)
        self.p4_wf_input_label = tk.Label(p4_input_frame, text="Input File:")
        self.p4_wf_input_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_input_file_entry = tk.Entry(p4_input_frame, textvariable=self.p4_wf_input_file_path, width=70, state="readonly")
        self.p4_wf_input_file_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.p4_wf_browse_button = tk.Button(p4_input_frame, text="Browse...", command=self._select_input_file)
        self.p4_wf_browse_button.grid(row=0, column=2, padx=5, pady=5)

        # --- 2. Image Output Location (Conditional) ---
        self.p4_wf_image_output_frame = ttk.LabelFrame(main_frame, text="2. Image Output Location (Visual Q&A Step)")
        # Managed visibility in _update_ui...
        self.p4_wf_image_output_frame.grid(row=2, column=0, padx=0, pady=5, sticky="ew")
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
        config_frame.grid(row=3, column=0, padx=0, pady=5, sticky="ew")
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
        # Step 2 Model (Tagging)
        tk.Label(config_frame, text="Tagging Model:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.p4_wf_tagging_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p4_wf_tagging_model, values=GEMINI_UNIFIED_MODELS, state="readonly", width=25)
        if GEMINI_UNIFIED_MODELS and self.p4_wf_tagging_model.get() in GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(self.p4_wf_tagging_model.get())
        elif GEMINI_UNIFIED_MODELS: self.p4_wf_tagging_model_dropdown.set(GEMINI_UNIFIED_MODELS[0])
        self.p4_wf_tagging_model_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # --- Step Specific Configs ---
        # Text Analysis Chunking Config (Managed visibility)
        self.p4_wf_text_config_frame = ttk.Frame(config_frame)
        self.p4_wf_text_config_frame.grid(row=3, column=0, columnspan=5, sticky="ew") # Span all columns
        tk.Label(self.p4_wf_text_config_frame, text="Text Chunk Size (chars):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        p4_wf_text_chunk_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_chunk_size, width=10)
        p4_wf_text_chunk_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        tk.Label(self.p4_wf_text_config_frame, text="Text API Delay (s):").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        p4_wf_text_delay_entry = ttk.Entry(self.p4_wf_text_config_frame, textvariable=self.p4_wf_text_api_delay, width=10)
        p4_wf_text_delay_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        # Tagging Batching Config (Always visible, but only applies to step 2)
        tk.Label(config_frame, text="Tagging Batch Size:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        p4_wf_tag_batch_entry = ttk.Entry(config_frame, textvariable=self.p4_wf_tagging_batch_size, width=10)
        p4_wf_tag_batch_entry.grid(row=4, column=1, padx=5, pady=5, sticky="w")
        tk.Label(config_frame, text="Tagging API Delay (s):").grid(row=4, column=2, padx=5, pady=5, sticky="w")
        p4_wf_tag_delay_entry = ttk.Entry(config_frame, textvariable=self.p4_wf_tagging_api_delay, width=10)
        p4_wf_tag_delay_entry.grid(row=4, column=3, padx=5, pady=5, sticky="w")


        # --- 4. Prompts Area ---
        self.p4_wf_prompts_area = ttk.Frame(main_frame)
        self.p4_wf_prompts_area.grid(row=4, column=0, padx=0, pady=5, sticky="nsew")
        self.p4_wf_prompts_area.grid_rowconfigure(0, weight=1); self.p4_wf_prompts_area.grid_columnconfigure(0, weight=1)
        # Visual Q&A Prompts Notebook
        self.p4_wf_visual_prompts_notebook = ttk.Notebook(self.p4_wf_prompts_area)
        p4_vis_extract_frame = ttk.Frame(self.p4_wf_visual_prompts_notebook, padding=5); self.p4_wf_visual_prompts_notebook.add(p4_vis_extract_frame, text="Visual Extraction Prompt (Step 1)")
        p4_vis_extract_frame.grid_rowconfigure(0, weight=1); p4_vis_extract_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_visual_extraction_prompt_text = scrolledtext.ScrolledText(p4_vis_extract_frame, wrap=tk.WORD, height=5); self.p4_wf_visual_extraction_prompt_text.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_visual_extraction_prompt_text.insert(tk.END, self.p4_wf_visual_extraction_prompt_var.get()); self.p4_wf_visual_extraction_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_visual_extract)
        p4_vis_tag_frame = ttk.Frame(self.p4_wf_visual_prompts_notebook, padding=5); self.p4_wf_visual_prompts_notebook.add(p4_vis_tag_frame, text="Tagging Prompt (Step 2)")
        p4_vis_tag_frame.grid_rowconfigure(0, weight=1); p4_vis_tag_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_tagging_prompt_text1 = scrolledtext.ScrolledText(p4_vis_tag_frame, wrap=tk.WORD, height=5); self.p4_wf_tagging_prompt_text1.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_tagging_prompt_text1.insert(tk.END, self.p4_wf_tagging_prompt_var.get()); self.p4_wf_tagging_prompt_text1.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag)
        # Text Analysis Prompts Notebook
        self.p4_wf_text_prompts_notebook = ttk.Notebook(self.p4_wf_prompts_area)
        p4_text_process_frame = ttk.Frame(self.p4_wf_text_prompts_notebook, padding=5); self.p4_wf_text_prompts_notebook.add(p4_text_process_frame, text="Text Analysis Prompt (Step 1)")
        p4_text_process_frame.grid_rowconfigure(0, weight=1); p4_text_process_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_book_processing_prompt_text = scrolledtext.ScrolledText(p4_text_process_frame, wrap=tk.WORD, height=5); self.p4_wf_book_processing_prompt_text.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_book_processing_prompt_text.insert(tk.END, self.p4_wf_book_processing_prompt_var.get()); self.p4_wf_book_processing_prompt_text.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_book_process)
        p4_text_tag_frame = ttk.Frame(self.p4_wf_text_prompts_notebook, padding=5); self.p4_wf_text_prompts_notebook.add(p4_text_tag_frame, text="Tagging Prompt (Step 2)")
        p4_text_tag_frame.grid_rowconfigure(0, weight=1); p4_text_tag_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_tagging_prompt_text2 = scrolledtext.ScrolledText(p4_text_tag_frame, wrap=tk.WORD, height=5); self.p4_wf_tagging_prompt_text2.grid(row=0, column=0, sticky="nsew")
        self.p4_wf_tagging_prompt_text2.insert(tk.END, self.p4_wf_tagging_prompt_var.get()); self.p4_wf_tagging_prompt_text2.bind("<<Modified>>", self._sync_prompt_var_from_editor_p4_tag)

        # --- 5. Workflow Action Button ---
        self.p4_wf_run_button = tk.Button(main_frame, text="Run Workflow", command=self._start_workflow_thread, font=('Arial', 11, 'bold'), bg='lightyellow')
        self.p4_wf_run_button.grid(row=5, column=0, padx=10, pady=(10, 5), sticky="ew")

        # --- 6. Status Area ---
        status_frame = ttk.LabelFrame(main_frame, text="6. Workflow Status")
        status_frame.grid(row=6, column=0, padx=0, pady=5, sticky="nsew")
        status_frame.grid_rowconfigure(1, weight=1); status_frame.grid_columnconfigure(0, weight=1)
        self.p4_wf_progress_bar = ttk.Progressbar(status_frame, variable=self.p4_wf_progress_var, maximum=100)
        self.p4_wf_progress_bar.grid(row=0, column=0, padx=5, pady=(5,2), sticky="ew")
        self.p4_wf_status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=8, state="disabled")
        self.p4_wf_status_text.grid(row=1, column=0, padx=5, pady=(2,5), sticky="nsew")


    def _update_ui_for_processing_type(self):
        """Shows/hides UI elements on Page 4 based on selected workflow type."""
        selected_type = self.p4_wf_processing_type.get(); is_visual = selected_type == "Visual Q&A (PDF)"
        try:
            # Update Input Label
            if hasattr(self, 'p4_wf_input_label'): self.p4_wf_input_label.config(text="Input PDF:" if is_visual else "Input File (PDF/TXT):")

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

            # Update Run Button Text
            if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(text="Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow")

            # Disable Visual Q&A radio if PyMuPDF is not installed
            if hasattr(self, 'p4_wf_visual_qa_radio'): self.p4_wf_visual_qa_radio.config(state="normal" if PYMUPDF_INSTALLED else "disabled")

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
                         other_widget.config(state=tk.NORMAL); other_widget.delete("1.0", tk.END); other_widget.insert("1.0", current_text); other_widget.edit_modified(False)
         except tk.TclError: pass

    # --- Page 4 Logging ---
    def log_status(self, message, level="info"):
        """Logs message to the Page 4 Workflow status area"""
        try:
            if not hasattr(self, 'p4_wf_status_text') or not self.p4_wf_status_text.winfo_exists(): return
            self.p4_wf_status_text.config(state="normal"); prefix_map = {"info": "[INFO] ", "step": "[STEP] ", "warning": "[WARN] ", "error": "[ERROR] ", "upload": "[UPLOAD] ", "debug": "[DEBUG] "}; prefix = prefix_map.get(level, "[INFO] "); timestamp = datetime.now().strftime("%H:%M:%S"); self.p4_wf_status_text.insert(tk.END, f"{timestamp} {prefix}{message}\n"); self.p4_wf_status_text.see(tk.END); self.p4_wf_status_text.config(state="disabled"); self.update_idletasks()
        except tk.TclError as e: print(f"P4 WF Status Log (backup): {message} (Error: {e})")

    # --- Page 4 File Selection & Path Helpers ---
    def _select_input_file(self):
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
    def _toggle_media_path_entry(self):
        try:
            if self.p4_wf_save_directly_to_media.get():
                if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state="normal")
                if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state="normal")
                self.log_status("Workflow: Direct image save to Anki media enabled.", "info");
                if not self.p4_wf_anki_media_path.get(): self._detect_anki_media_path()
            else:
                if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state="disabled")
                if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state="disabled")
                self.log_status("Workflow: Direct image save disabled. Images -> subfolder.", "info")
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
                if self.p4_wf_save_directly_to_media.get():
                    if hasattr(self, 'p4_wf_anki_media_entry'): self.p4_wf_anki_media_entry.config(state="normal")
                    if hasattr(self, 'p4_wf_browse_anki_media_button'): self.p4_wf_browse_anki_media_button.config(state="normal")
            else: self.log_status("Workflow: AnkiConnect did not return a valid path.", "warning")
        except Exception as e: self.log_status(f"Workflow: Failed AnkiConnect path detection: {e}", "error")

    # --- Page 4 Workflow Execution ---
    def _start_workflow_thread(self):
         if self.p4_wf_is_processing: show_info_dialog("In Progress", "Workflow running.", parent=self); return
         selected_type = self.p4_wf_processing_type.get(); is_visual = selected_type == "Visual Q&A (PDF)"
         input_file = self.p4_wf_input_file_path.get(); api_key = self.app.gemini_api_key.get()
         step1_model = self.p4_wf_extraction_model.get(); tag_model = self.p4_wf_tagging_model.get()
         tag_prompt = self.p4_wf_tagging_prompt_var.get()
         output_dir = os.path.dirname(input_file) if input_file else os.getcwd() # Determine output dir early
         safe_base_name = sanitize_filename(os.path.basename(input_file)) if input_file else "workflow_output"

         # --- Common Validations ---
         if not input_file or not os.path.exists(input_file): show_error_dialog("Error", "Select valid input file.", parent=self); return
         if not api_key or api_key == "YOUR_API_KEY_HERE": show_error_dialog("Error", "Enter Gemini API Key.", parent=self); return
         if not step1_model: show_error_dialog("Error", f"Select {'Visual Extraction' if is_visual else 'Text Analysis'} Model.", parent=self); return
         if not tag_model: show_error_dialog("Error", "Select Tagging Model.", parent=self); return
         if not tag_prompt: show_error_dialog("Error", "Tagging prompt empty.", parent=self); return
         try: # Validate tagging params
             tag_batch_s = self.p4_wf_tagging_batch_size.get(); tag_delay = self.p4_wf_tagging_api_delay.get()
             if tag_batch_s <= 0: show_error_dialog("Error", "Tagging Batch size must be > 0.", parent=self); return
             if tag_delay < 0: self.p4_wf_tagging_api_delay.set(0.0); show_info_dialog("Warning", "Tagging API Delay negative. Setting to 0.", parent=self)
         except tk.TclError: show_error_dialog("Error", "Invalid Tagging Batch Size or Delay.", parent=self); return

         # --- Type-Specific Validations ---
         target_func = None; args = ()
         if is_visual:
            extract_prompt = self.p4_wf_visual_extraction_prompt_var.get(); save_direct = self.p4_wf_save_directly_to_media.get(); anki_media_dir = self.p4_wf_anki_media_path.get()
            if not extract_prompt: show_error_dialog("Error", "Visual Extraction prompt empty.", parent=self); return
            if not PYMUPDF_INSTALLED: show_error_dialog("Error", "PyMuPDF (fitz) is required for Visual Q&A workflow.", parent=self); return
            if save_direct and (not anki_media_dir or not os.path.isdir(anki_media_dir)): show_error_dialog("Error", "Direct image save enabled, but Anki media path invalid.", parent=self); return
            if save_direct and os.path.basename(anki_media_dir).lower() != "collection.media":
                 if not ask_yes_no("Confirm Path", f"Direct save path '{os.path.basename(anki_media_dir)}' doesn't end in 'collection.media'.\nProceed anyway?", parent=self): return
            # Pass common params + visual specific
            args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model, extract_prompt, tag_prompt, save_direct, anki_media_dir, tag_batch_s, tag_delay)
            target_func = self._run_visual_workflow_thread
         else: # Text Analysis
            analysis_prompt = self.p4_wf_book_processing_prompt_var.get()
            try: # Validate text chunk/delay
                text_chunk_size = self.p4_wf_text_chunk_size.get(); text_api_delay = self.p4_wf_text_api_delay.get()
                if text_chunk_size <= 0: show_error_dialog("Error", "Text Chunk Size must be > 0.", parent=self); return
                if text_api_delay < 0: self.p4_wf_text_api_delay.set(0.0); show_info_dialog("Warning", "Text API Delay negative. Setting to 0.", parent=self)
            except tk.TclError: show_error_dialog("Error", "Invalid Text Chunk Size or Delay.", parent=self); return
            if not analysis_prompt: show_error_dialog("Error", "Text Analysis prompt empty.", parent=self); return
            if input_file.lower().endswith(".pdf") and not PYMUPDF_INSTALLED: show_error_dialog("Error", "PyMuPDF (fitz) required for PDF text analysis.", parent=self); return
            # Pass common params + text specific
            args = (input_file, output_dir, safe_base_name, api_key, step1_model, tag_model, analysis_prompt, tag_prompt, text_chunk_size, text_api_delay, tag_batch_s, tag_delay)
            target_func = self._run_text_analysis_workflow_thread

         # --- Start Thread ---
         self.p4_wf_is_processing = True
         try:
             if hasattr(self, 'p4_wf_run_button'): self.p4_wf_run_button.config(state="disabled", text="Workflow Running...")
             if hasattr(self, 'p4_wf_status_text'): self.p4_wf_status_text.config(state="normal"); self.p4_wf_status_text.delete('1.0', tk.END); self.p4_wf_status_text.config(state="disabled")
             if hasattr(self, 'p4_wf_progress_bar'): self.p4_wf_progress_var.set(0)
         except tk.TclError: pass
         self.log_status(f"Starting {selected_type} workflow...")
         thread = threading.Thread(target=target_func, args=args, daemon=True); thread.start()

    def _workflow_finished(self, success=True, final_tsv_path=None):
        """Called from the main thread after workflow finishes."""
        self.p4_wf_is_processing = False; selected_type = self.p4_wf_processing_type.get(); is_visual = selected_type == "Visual Q&A (PDF)"; base_text = "Run Visual Q&A Workflow" if is_visual else "Run Text Analysis Workflow"; final_button_text = base_text; final_bg = 'lightyellow'
        if not success: final_button_text = "Workflow Failed (See Log)"; final_bg = 'salmon'
        try:
            if hasattr(self, 'p4_wf_run_button') and self.p4_wf_run_button.winfo_exists(): self.p4_wf_run_button.config(state="normal", text=final_button_text, bg=final_bg)
            if success and final_tsv_path: self.log_status(f"Workflow successful. Final Output: {os.path.basename(final_tsv_path)}", level="info")
            elif not success: self.log_status(f"Workflow failed. See previous logs for details.", level="error")
            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists(): self.p4_wf_progress_var.set(100 if success else 0)
        except tk.TclError: print("P4 WF Warning: Could not update workflow button state.")

    # --- Visual Q&A Workflow Thread ---
    def _run_visual_workflow_thread(self, input_pdf_path, output_dir, safe_base_name, api_key,
                                       extract_model_name, tag_model_name, extract_prompt, tag_prompt_template,
                                       save_direct_flag, anki_media_dir_from_ui,
                                       tag_batch_size, tag_api_delay): # Added tagging params
        """The core logic for the VISUAL Q&A workflow running in a thread."""
        final_output_path = None; success = False; uploaded_file_uri = None; visual_tsv_path = None; final_image_folder = None; parsed_data = None
        try:
            start_time = time.time()
            # === STEP 1a: Generate Page Images ===
            self.after(0, self.log_status, f"Starting Step 1a (Visual): Generating Page Images...", level="step"); self.after(0, self._update_progress_bar, 5)
            if save_direct_flag: image_destination_path = anki_media_dir_from_ui
            else: image_destination_path = os.path.join(output_dir, f"{safe_base_name}_workflow_images_{datetime.now():%Y%m%d_%H%M%S}")
            final_image_folder, page_image_map = generate_page_images(input_pdf_path, image_destination_path, safe_base_name, save_direct_flag, self.log_status, parent_widget=self)
            if final_image_folder is None: raise WorkflowStepError("Failed during page image generation.")
            self.after(0, self.log_status, f"Step 1a Complete.", level="info"); self.after(0, self._update_progress_bar, 15)

            # === STEP 1b: Gemini PDF Visual Extraction (JSON) ===
            self.after(0, self.log_status, f"Starting Step 1b (Visual): Gemini JSON Extraction ({extract_model_name})...", level="step")
            parsed_data, uploaded_file_uri = call_gemini_visual_extraction(input_pdf_path, api_key, extract_model_name, extract_prompt, self.log_status, parent_widget=self)
            if parsed_data is None: raise WorkflowStepError("Gemini PDF visual extraction failed (check logs/temp files).")
            if not parsed_data: raise WorkflowStepError("No Q&A pairs extracted from the document (cannot proceed to tagging).")
            self.after(0, self.log_status, "Step 1b Complete.", level="info"); self.after(0, self._update_progress_bar, 40)

            # === STEP 1c: Generating Visual TSV from JSON ===
            self.after(0, self.log_status, f"Starting Step 1c (Visual): Generating intermediate TSV...", level="step")
            # Generate intermediate TSV based on parsed_data
            visual_tsv_path = generate_tsv_visual(parsed_data, output_dir, safe_base_name + "_intermediate", page_image_map, self.log_status) # Temp name
            if visual_tsv_path is None: raise WorkflowStepError("Failed to generate intermediate visual TSV file.")
            self.after(0, self.log_status, f"Step 1 Complete (Visual): Intermediate TSV saved.", level="info"); self.after(0, self._update_progress_bar, 50)

            # === STEP 2: Tag Intermediate TSV using Gemini ===
            self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging Visual TSV ({tag_model_name})...", level="step")
            final_output_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_visual.txt")
            tagging_success = self._wf_gemini_tag_tsv(visual_tsv_path, final_output_path, tag_prompt_template, api_key, tag_model_name, tag_batch_size, tag_api_delay) # Pass tagging params
            if not tagging_success: raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")
            self.after(0, self.log_status, f"Step 2 Complete (Tagging): Final tagged file saved: {os.path.basename(final_output_path)}", level="info"); self.after(0, self._update_progress_bar, 95)

            # === Workflow Complete ===
            end_time = time.time(); total_time = end_time - start_time; self.after(0, self.log_status, f"Visual Q&A Workflow finished successfully in {total_time:.2f} seconds!", level="info"); self.after(0, self._update_progress_bar, 100)
            success_message = f"Processed '{os.path.basename(input_pdf_path)}'.\nFinal file generated:\n{final_output_path}\n\n";
            if save_direct_flag: success_message += f"Images Saved Directly To:\n{final_image_folder}"
            else: success_message += f"Images Saved To Subfolder:\n{final_image_folder}\n\nIMPORTANT: Manually copy images from\n'{os.path.basename(final_image_folder)}' to Anki's 'collection.media' folder before importing the TSV."
            self.after(0, show_info_dialog, "Workflow Complete", success_message, self); success = True
        except WorkflowStepError as wse: self.after(0, self.log_status, f"Visual Workflow stopped: {wse}", level="error"); self.after(0, show_error_dialog, "Workflow Failed", f"Failed: {wse}\nCheck log and temp files.", self); success = False
        except Exception as e: error_message = f"Unexpected visual workflow error: {type(e).__name__}: {e}"; self.after(0, self.log_status, f"FATAL WORKFLOW ERROR (Visual): {error_message}\n{traceback.format_exc()}", level="error"); self.after(0, show_error_dialog, "Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self); success = False
        finally:
            if uploaded_file_uri:
                 try: cleanup_gemini_file(uploaded_file_uri, api_key, self.log_status)
                 except Exception as clean_e: self.after(0, self.log_status, f"Error during cleanup: {clean_e}", "warning")
            # Optionally clean up intermediate TSV?
            # if visual_tsv_path and os.path.exists(visual_tsv_path) and success:
            #     try: os.remove(visual_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file: {os.path.basename(visual_tsv_path)}", "debug")
            #     except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(visual_tsv_path)}: {rem_e}", "warning")
            self.after(0, self._workflow_finished, success, final_output_path if success else None)

    # --- Text Analysis Workflow Thread ---
    def _run_text_analysis_workflow_thread(self, input_file_path, output_dir, safe_base_name, api_key,
                                               analysis_model_name, tag_model_name, analysis_prompt, tag_prompt_template,
                                               text_chunk_size, text_api_delay, # Text step params
                                               tag_batch_size, tag_api_delay): # Tagging step params
        """The core logic for the TEXT ANALYSIS workflow running in a thread."""
        final_output_path = None; success = False; analysis_tsv_path = None; parsed_data = None
        try:
            start_time = time.time()
            # === STEP 1a: Extract Text Content ===
            self.after(0, self.log_status, f"Starting Step 1a (Text): Extracting Text...", level="step"); self.after(0, self._update_progress_bar, 5)
            extracted_text = ""; file_type = ""
            if input_file_path.lower().endswith(".pdf"): extracted_text = extract_text_from_pdf(input_file_path, self.log_status); file_type = "PDF"
            elif input_file_path.lower().endswith(".txt"): extracted_text = read_text_file(input_file_path, self.log_status); file_type = "TXT"
            if extracted_text is None: raise WorkflowStepError(f"Text extraction failed for {file_type}.")
            if not extracted_text: raise WorkflowStepError(f"No text content extracted from the {file_type} file.")
            self.after(0, self.log_status, f"Step 1a Complete. Extracted ~{len(extracted_text)} characters.", level="info"); self.after(0, self._update_progress_bar, 15)

            # === STEP 1b: Gemini Text Analysis (Chunked) ===
            self.after(0, self.log_status, f"Starting Step 1b (Text): Gemini Analysis ({analysis_model_name}) in chunks...", level="step")
            parsed_data = call_gemini_text_analysis(
                extracted_text, api_key, analysis_model_name, analysis_prompt, self.log_status,
                output_dir, safe_base_name, # For incremental saving
                text_chunk_size, text_api_delay, # Chunking params
                parent_widget=self
            )
            if parsed_data is None: raise WorkflowStepError("Gemini text analysis failed (check logs/temp files).")
            if not parsed_data: raise WorkflowStepError("No Q&A pairs extracted from text (cannot proceed to tagging).")
            self.after(0, self.log_status, "Step 1b Complete (Gemini chunk processing).", level="info"); self.after(0, self._update_progress_bar, 40)

            # === STEP 1c: Generating Text Analysis Intermediate TSV ===
            self.after(0, self.log_status, f"Starting Step 1c (Text): Generating intermediate TSV...", level="step")
            analysis_tsv_path = generate_tsv_text_analysis(parsed_data, output_dir, safe_base_name + "_intermediate", self.log_status) # Temp name
            if analysis_tsv_path is None: raise WorkflowStepError("Failed to write intermediate text analysis TSV.")
            self.after(0, self.log_status, f"Step 1 Complete (Text): Intermediate TSV saved.", level="info"); self.after(0, self._update_progress_bar, 50)

            # === STEP 2: Tag Intermediate TSV using Gemini ===
            self.after(0, self.log_status, f"Starting Step 2 (Tagging): Tagging Analysis TSV ({tag_model_name})...", level="step")
            final_output_path = os.path.join(output_dir, f"{safe_base_name}_final_tagged_analysis.txt")
            tagging_success = self._wf_gemini_tag_tsv(analysis_tsv_path, final_output_path, tag_prompt_template, api_key, tag_model_name, tag_batch_size, tag_api_delay) # Pass tagging params
            if not tagging_success: raise WorkflowStepError("Gemini tagging step failed (check logs/temp files).")
            self.after(0, self.log_status, f"Step 2 Complete (Tagging): Final tagged file saved: {os.path.basename(final_output_path)}", level="info"); self.after(0, self._update_progress_bar, 95)

            # === Workflow Complete ===
            end_time = time.time(); total_time = end_time - start_time; self.after(0, self.log_status, f"Text Analysis Workflow finished successfully in {total_time:.2f} seconds!", level="info"); self.after(0, self._update_progress_bar, 100)
            success_message = f"Processed '{os.path.basename(input_file_path)}'.\nFinal file generated:\n{final_output_path}\n"
            self.after(0, show_info_dialog, "Workflow Complete", success_message, self); success = True
        except WorkflowStepError as wse: self.after(0, self.log_status, f"Text Analysis Workflow stopped: {wse}", level="error"); self.after(0, show_error_dialog, "Workflow Failed", f"Failed: {wse}\nCheck log and temp files.", self); success = False
        except Exception as e: error_message = f"Unexpected text analysis workflow error: {type(e).__name__}: {e}"; self.after(0, self.log_status, f"FATAL WORKFLOW ERROR (Text): {error_message}\n{traceback.format_exc()}", level="error"); self.after(0, show_error_dialog, "Workflow Error", f"Unexpected error:\n{e}\nCheck log.", self); success = False
        finally:
            # Optionally clean up intermediate TSV?
            # if analysis_tsv_path and os.path.exists(analysis_tsv_path) and success:
            #     try: os.remove(analysis_tsv_path); self.after(0, self.log_status, f"Cleaned up intermediate file: {os.path.basename(analysis_tsv_path)}", "debug")
            #     except Exception as rem_e: self.after(0, self.log_status, f"Could not remove intermediate file {os.path.basename(analysis_tsv_path)}: {rem_e}", "warning")
            self.after(0, self._workflow_finished, success, final_output_path if success else None)

    # --- Shared Workflow Helper Method for Tagging ---
    def _wf_gemini_tag_tsv(self, input_tsv_path, output_tsv_path, system_prompt, api_key, model_name,
                          batch_size, api_delay): # Added batch_size, api_delay
        """Reads TSV, tags it using Gemini batches, writes new TSV. Returns True/False."""
        log_func = self.log_status; parent = self # Use page 4's logger and parent
        log_func(f"Tagging Step: Starting for {os.path.basename(input_tsv_path)}", level="info")
        try:
            # Determine output dir and base name for potential incremental saves inside tag_tsv_rows_gemini
            tag_output_dir = os.path.dirname(output_tsv_path)
            tag_base_filename = os.path.splitext(os.path.basename(output_tsv_path))[0] # Get base name of final output

            with open(input_tsv_path, "r", encoding="utf-8") as f: lines = f.readlines()
            if not lines: log_func("Input TSV for tagging is empty.", "warning"); return True # Treat empty input as success for tagging step

            data_rows_with_header = [line.strip().split("\t") for line in lines if line.strip()] # Include header if present
            if len(data_rows_with_header) <= 1: log_func("No data rows found in TSV for tagging (excluding header).", "warning"); return True # Also success

            # Use the generator function from gemini_api, passing necessary params
            tagged_row_generator = tag_tsv_rows_gemini(
                data_rows_with_header, api_key, model_name, system_prompt,
                batch_size, api_delay, log_func, # Pass page 4 logger
                progress_callback=self._update_tagging_progress, # Use specific progress callback
                output_dir=tag_output_dir,          # Pass for incremental save
                base_filename=tag_base_filename,    # Pass for incremental save
                parent_widget=parent
            )

            # Write the final tagged file
            with open(output_tsv_path, "w", encoding="utf-8", newline='') as f:
                for output_row in tagged_row_generator: # Generator now handles yielding header+data
                    f.write("\t".join(map(str, output_row)) + "\n")
                    # Progress bar updated via callback inside tag_tsv_rows_gemini

            log_func(f"Tagging Step: Finished. Output: {os.path.basename(output_tsv_path)}", "info")
            return True

        except FileNotFoundError: log_func(f"Input TSV not found for tagging: {input_tsv_path}", "error"); return False
        except Exception as e: log_func(f"Error during TSV tagging step: {e}\n{traceback.format_exc()}", "error"); return False

    def _update_tagging_progress(self, progress_value):
        """Callback specifically for the tagging step's progress."""
        # Workflow progress is 0-50% for step 1, 50-100% for step 2 (tagging)
        workflow_progress = 50 + (progress_value * 0.5)
        self._update_progress_bar(workflow_progress)

    def _update_progress_bar(self, progress_value):
        """Generic callback to update the workflow progress bar."""
        try:
            if hasattr(self, 'p4_wf_progress_bar') and self.p4_wf_progress_bar.winfo_exists():
                self.p4_wf_progress_var.set(min(progress_value, 100.0)) # Cap at 100
        except tk.TclError: pass