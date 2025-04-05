# ui/page3_tag_tsv.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import traceback
import time
import json # Added for JSON handling
from datetime import datetime

# --- Use relative imports ONLY ---
from ..constants import DEFAULT_MODEL, GEMINI_UNIFIED_MODELS, DEFAULT_BATCH_TAGGING_PROMPT, DEFAULT_SECOND_PASS_MODEL
from ..prompts import BATCH_TAGGING, SECOND_PASS_TAGGING
from ..utils.helpers import show_error_dialog, show_info_dialog, sanitize_filename # Added sanitize_filename
# Import the corrected/newly added function from file_processor
from ..core.file_processor import generate_tsv_from_json_data
# Import tagging function from gemini_api
from ..core.gemini_api import tag_tsv_rows_gemini, configure_gemini


class TagTsvPage(ttk.Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance

        # --- Page 3 Variables ---
        self.p3_input_file_var = tk.StringVar() # Now expects JSON
        self.p3_batch_size = tk.IntVar(value=10)
        self.p3_progress_var = tk.DoubleVar(value=0)
        self.p3_system_prompt_text = tk.StringVar(value=BATCH_TAGGING) # Pass 1
        self.p3_api_delay = tk.DoubleVar(value=10.0)
        self.p3_gemini_selected_model = tk.StringVar(value=DEFAULT_MODEL) # Pass 1
        self.p3_is_processing = False
        self.p3_enable_second_pass = tk.BooleanVar(value=False)
        self.p3_second_pass_model = tk.StringVar(value=DEFAULT_SECOND_PASS_MODEL)
        self.p3_second_pass_prompt_var = tk.StringVar(value=SECOND_PASS_TAGGING)

        # --- Build UI ---
        self._build_ui()
        self._toggle_second_pass_widgets() # Ensure initial state is correct
        print("Initialized TagTsvPage (JSON Workflow)")

    def _build_ui(self):
        """Creates the UI elements for Page 3."""
        # --- UI Building Logic (No changes needed here) ---
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1) # Allow prompt area to expand

        # Configuration Section
        config_frame = ttk.LabelFrame(main_frame, text="Configuration")
        config_frame.grid(row=0, column=0, padx=0, pady=(0, 10), sticky="ew")
        config_frame.grid_columnconfigure(1, weight=1) # Allow entry to expand

        # Prompt Section Container
        prompt_frame_container = ttk.Frame(main_frame)
        prompt_frame_container.grid(row=1, column=0, padx=0, pady=5, sticky="nsew")
        prompt_frame_container.grid_rowconfigure(0, weight=1) # Pass 1 prompt expands
        prompt_frame_container.grid_rowconfigure(1, weight=1) # Pass 2 prompt expands
        prompt_frame_container.grid_columnconfigure(0, weight=1)

        # Status Section
        status_frame = ttk.LabelFrame(main_frame, text="Status & Progress")
        status_frame.grid(row=2, column=0, padx=0, pady=5, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1) # Allow progress bar to expand

        # Action Button Section
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=3, column=0, padx=0, pady=(5, 0), sticky="ew")

        # --- Configuration Frame Widgets ---
        # Input File (JSON)
        ttk.Label(config_frame, text="Input JSON File:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.p3_input_file_entry = ttk.Entry(config_frame, textvariable=self.p3_input_file_var, width=60, state='readonly') # Readonly better for browse
        self.p3_input_file_entry.grid(row=0, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=5)
        ttk.Button(config_frame, text="Browse", command=self._browse_input_file).grid(row=0, column=4, padx=5, pady=5)

        # API Key
        ttk.Label(config_frame, text="Gemini API Key:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.p3_api_key_entry = ttk.Entry(config_frame, textvariable=self.app.gemini_api_key, width=60, show="*")
        self.p3_api_key_entry.grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=5)
        self.p3_show_key_button = ttk.Button(config_frame, text="S/H", command=self.app.toggle_api_key_visibility, width=4) # Smaller button
        self.p3_show_key_button.grid(row=1, column=4, padx=5, pady=5)

        # Model (Pass 1)
        ttk.Label(config_frame, text="Model (Pass 1):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.p3_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p3_gemini_selected_model, values=GEMINI_UNIFIED_MODELS, state="readonly", width=57)
        # Set initial value safely
        if GEMINI_UNIFIED_MODELS and self.p3_gemini_selected_model.get() in GEMINI_UNIFIED_MODELS:
             self.p3_model_dropdown.set(self.p3_gemini_selected_model.get())
        elif GEMINI_UNIFIED_MODELS: # If current invalid, set to first in list
             self.p3_gemini_selected_model.set(GEMINI_UNIFIED_MODELS[0])
        self.p3_model_dropdown.grid(row=2, column=1, columnspan=4, sticky=tk.EW, padx=5, pady=5)

        # Batch Size & API Delay
        ttk.Label(config_frame, text="Batch Size:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        p3_batch_size_entry = ttk.Entry(config_frame, textvariable=self.p3_batch_size, width=10)
        p3_batch_size_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(config_frame, text="API Delay (sec):").grid(row=3, column=2, sticky=tk.W, padx=(20, 5), pady=5)
        self.p3_api_delay_entry = ttk.Entry(config_frame, textvariable=self.p3_api_delay, width=10)
        self.p3_api_delay_entry.grid(row=3, column=3, sticky=tk.W, padx=5, pady=5)

        # Second Pass Config
        self.p3_second_pass_check = ttk.Checkbutton(config_frame, text="Enable Second Tagging Pass", variable=self.p3_enable_second_pass, command=self._toggle_second_pass_widgets)
        self.p3_second_pass_check.grid(row=4, column=0, columnspan=5, padx=5, pady=(10,0), sticky="w")
        self.p3_second_pass_model_label = tk.Label(config_frame, text="Model (Pass 2):") # Use tk.Label for consistency
        self.p3_second_pass_model_label.grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.p3_second_pass_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p3_second_pass_model, values=GEMINI_UNIFIED_MODELS, state="disabled", width=57)
        # Set initial value safely
        if GEMINI_UNIFIED_MODELS and self.p3_second_pass_model.get() in GEMINI_UNIFIED_MODELS:
            self.p3_second_pass_model_dropdown.set(self.p3_second_pass_model.get())
        elif GEMINI_UNIFIED_MODELS: # If current invalid, set to first in list
            self.p3_second_pass_model.set(GEMINI_UNIFIED_MODELS[0])
        self.p3_second_pass_model_dropdown.grid(row=5, column=1, columnspan=4, sticky=tk.EW, padx=5, pady=5)

        # --- Prompt Frames ---
        # Pass 1 Prompt
        prompt_frame_pass1 = ttk.LabelFrame(prompt_frame_container, text="System Prompt (Tagging Pass 1)")
        prompt_frame_pass1.grid(row=0, column=0, padx=0, pady=(0,5), sticky="nsew")
        prompt_frame_pass1.grid_rowconfigure(0, weight=1); prompt_frame_pass1.grid_columnconfigure(0, weight=1)
        self.p3_system_prompt_editor = scrolledtext.ScrolledText(prompt_frame_pass1, height=8, wrap=tk.WORD)
        self.p3_system_prompt_editor.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p3_system_prompt_editor.insert(tk.END, self.p3_system_prompt_text.get())
        self.p3_system_prompt_editor.bind("<<Modified>>", self._sync_prompt_var_from_editor)

        # Pass 2 Prompt (Initially hidden/disabled)
        self.p3_prompt_frame_pass2 = ttk.LabelFrame(prompt_frame_container, text="System Prompt (Tagging Pass 2)")
        # Don't grid initially, handled by _toggle_second_pass_widgets
        # self.p3_prompt_frame_pass2.grid(row=1, column=0, padx=0, pady=(5,0), sticky="nsew")
        self.p3_prompt_frame_pass2.grid_rowconfigure(0, weight=1); self.p3_prompt_frame_pass2.grid_columnconfigure(0, weight=1)
        self.p3_second_pass_prompt_editor = scrolledtext.ScrolledText(self.p3_prompt_frame_pass2, height=8, wrap=tk.WORD, state="disabled")
        self.p3_second_pass_prompt_editor.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.p3_second_pass_prompt_editor.insert(tk.END, self.p3_second_pass_prompt_var.get()) # Initial insert
        self.p3_second_pass_prompt_editor.bind("<<Modified>>", self._sync_prompt_var_from_editor_p3_tag_pass2)

        # --- Status Frame ---
        ttk.Label(status_frame, text="Progress:").pack(anchor=tk.W, padx=5, pady=(5,0))
        self.p3_progress_bar = ttk.Progressbar(status_frame, variable=self.p3_progress_var, maximum=100)
        self.p3_progress_bar.pack(fill=tk.X, padx=5, pady=(0,5))
        self.p3_status_label = ttk.Label(status_frame, text="Ready")
        self.p3_status_label.pack(anchor=tk.W, padx=5, pady=(0,5))

        # --- Action Frame ---
        self.p3_process_button = ttk.Button(action_frame, text="Tag JSON File & Generate TSV", command=self._start_gemini_processing)
        self.p3_process_button.pack(side=tk.RIGHT, padx=5, pady=5)
        # --- End of UI Building ---

    # --- Methods specific to Page 3 ---

    def log_status(self, message, level="info"):
        """Logs messages to the status label on this page."""
        try:
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                prefix_map = {"info": "", "step": "", "warning": "WARN: ", "error": "ERROR: ", "debug": "DEBUG: "}
                prefix = prefix_map.get(level, "")
                timestamp = datetime.now().strftime("%H:%M:%S")
                short_message = message.split('\n')[0]
                short_message = short_message[:100] + "..." if len(short_message) > 100 else short_message
                self.p3_status_label.config(text=f"{timestamp} {prefix}{short_message}")
                self.update_idletasks()
        except tk.TclError:
            print(f"P3 Log Warning: Could not update status label ({message})")
        except Exception as e:
            print(f"Unexpected error in P3 log_status: {e}")

    def _sync_prompt_var_from_editor(self, event=None):
         """Syncs Pass 1 prompt editor content to its variable."""
         try:
             if hasattr(self, 'p3_system_prompt_editor') and self.p3_system_prompt_editor.winfo_exists():
                 current_text = self.p3_system_prompt_editor.get("1.0", tk.END).strip()
                 self.p3_system_prompt_text.set(current_text)
                 self.p3_system_prompt_editor.edit_modified(False)
         except tk.TclError: pass

    def _sync_prompt_var_from_editor_p3_tag_pass2(self, event=None):
        """Syncs Pass 2 prompt editor content to its variable."""
        try:
            widget = self.p3_second_pass_prompt_editor
            if widget and widget.winfo_exists():
                current_text = widget.get("1.0", tk.END).strip()
                self.p3_second_pass_prompt_var.set(current_text)
                widget.edit_modified(False)
        except tk.TclError: pass

    def _browse_input_file(self):
        """Opens file dialog to select input JSON file."""
        file_path = filedialog.askopenfilename(
             parent=self, title="Select Input JSON File",
             filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            if not file_path.lower().endswith(".json"):
                show_error_dialog("Invalid File Type", "Please select a JSON file (.json) containing the Q&A data.", parent=self)
                return
            self.p3_input_file_entry.config(state='normal')
            self.p3_input_file_var.set(file_path)
            self.p3_input_file_entry.config(state='readonly')
            self.log_status(f"Selected input JSON: {os.path.basename(file_path)}")
        else:
            self.log_status("Input JSON file selection cancelled.")

    def _toggle_second_pass_widgets(self):
        """Enables/disables second pass model dropdown and prompt frame."""
        is_enabled = self.p3_enable_second_pass.get()
        new_state_widget = tk.NORMAL if is_enabled else tk.DISABLED
        new_state_combo = 'readonly' if is_enabled else tk.DISABLED

        try:
            if hasattr(self, 'p3_second_pass_model_label'):
                self.p3_second_pass_model_label.config(state=new_state_widget)
            if hasattr(self, 'p3_second_pass_model_dropdown'):
                self.p3_second_pass_model_dropdown.config(state=new_state_combo)

            editor = getattr(self, 'p3_second_pass_prompt_editor', None)
            frame = getattr(self, 'p3_prompt_frame_pass2', None)

            if frame and frame.winfo_exists():
                 if is_enabled:
                     if not frame.winfo_ismapped():
                         frame.grid(row=1, column=0, padx=0, pady=(5,0), sticky="nsew") # Ensure it's visible
                     if editor and editor.winfo_exists():
                         editor.config(state=tk.NORMAL)
                         # --- Force text update ---
                         editor.delete('1.0', tk.END)
                         editor.insert('1.0', self.p3_second_pass_prompt_var.get())
                         editor.edit_modified(False) # Reset modified flag after insert
                         # --- End force text update ---
                 else:
                     if frame.winfo_ismapped():
                         frame.grid_remove() # Hide frame
                     if editor and editor.winfo_exists():
                         editor.config(state=tk.DISABLED)

            # Avoid logging during initial setup if possible, or make it less intrusive
            # self.log_status(f"Second Tagging Pass {'Enabled' if is_enabled else 'Disabled'}.", "info")
        except tk.TclError as e:
            print(f"P3 Toggle Second Pass Warning: {e}")
        except AttributeError as e:
            print(f"P3 Toggle Second Pass Warning (AttributeError): {e}")


    def _start_gemini_processing(self):
        """Validates inputs and starts the Gemini batch processing in a thread."""
        if self.p3_is_processing:
            show_info_dialog("In Progress", "Processing is already running.", parent=self)
            return

        # --- Get Inputs ---
        input_file = self.p3_input_file_var.get()
        api_key = self.app.gemini_api_key.get()
        model_name_pass1 = self.p3_gemini_selected_model.get()
        system_prompt_pass1 = self.p3_system_prompt_text.get() # Get from variable
        enable_second_pass = self.p3_enable_second_pass.get()
        model_name_pass2 = self.p3_second_pass_model.get()
        system_prompt_pass2 = self.p3_second_pass_prompt_var.get() # Get from variable

        # --- Validations ---
        if not input_file or not os.path.exists(input_file):
            show_error_dialog("Error", "Please select a valid input JSON file.", parent=self)
            return
        if not input_file.lower().endswith(".json"): # Re-validate extension
            show_error_dialog("Error", "Input file must be a .json file.", parent=self)
            return
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            show_error_dialog("Error", "Please enter your Gemini API Key.", parent=self)
            return
        if not model_name_pass1:
            show_error_dialog("Error", "Please select a Gemini model (Pass 1).", parent=self)
            return
        if not system_prompt_pass1: # Check variable content
            show_error_dialog("Error", "System prompt (Pass 1) cannot be empty.", parent=self)
            return
        if enable_second_pass:
            if not model_name_pass2:
                show_error_dialog("Error", "Second Pass is enabled, but Pass 2 model is not selected.", parent=self)
                return
            if not system_prompt_pass2: # Check variable content
                show_error_dialog("Error", "Second Pass is enabled, but Pass 2 prompt is empty.", parent=self)
                return
        try:
            batch_s = self.p3_batch_size.get()
            delay = self.p3_api_delay.get()
            if batch_s <= 0:
                show_error_dialog("Error", "Batch size must be greater than 0.", parent=self)
                return
            if delay < 0:
                show_info_dialog("Warning", "API Delay cannot be negative. Using 0 seconds.", parent=self)
                self.p3_api_delay.set(0.0)
                delay=0.0
        except tk.TclError:
            show_error_dialog("Error", "Invalid input for Batch Size or API Delay.", parent=self)
            return

        # --- Determine Output File Paths ---
        output_dir = os.path.dirname(input_file)
        base_name_input = os.path.splitext(os.path.basename(input_file))[0]
        # Clean up potential suffixes from previous steps for a cleaner final name
        base_name = base_name_input
        suffixes_to_remove = ["_extracted", "_visual_extract_temp_results", "_text_analysis_temp_results", "_text_analysis_final", "_visual_extract", "_intermediate_visual", "_intermediate_analysis"]
        for suffix in suffixes_to_remove:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break # Remove only one suffix if multiple match

        # Define paths for intermediate JSON and final TSV
        final_tsv_output_file = os.path.join(output_dir, f"{base_name}_tagged_final.txt") # Use .txt for Anki
        intermediate_json_p1 = os.path.join(output_dir, f"{base_name}_tagged_p1.json")
        intermediate_json_p2 = os.path.join(output_dir, f"{base_name}_tagged_p2.json") if enable_second_pass else None

        # --- Read Input JSON ---
        input_qa_data = None
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                input_qa_data = json.load(f)
            if not isinstance(input_qa_data, list):
                raise ValueError("Input JSON content is not a list.")
            if not input_qa_data:
                # Allow processing empty list, but log warning
                self.log_status("Input JSON file is empty.", "warning")
                # No need to show error dialog, processing thread will handle empty list
            elif not isinstance(input_qa_data[0], dict):
                 raise ValueError("Items in the JSON list are not dictionaries (objects).")
            # Optional: Check for expected keys in first item
            # elif 'question' not in input_qa_data[0] and 'question_text' not in input_qa_data[0]:
            #     raise ValueError("First item missing expected 'question' or 'question_text' key.")

        except FileNotFoundError:
            show_error_dialog("Error", f"Input JSON file not found:\n{input_file}", parent=self)
            return
        except json.JSONDecodeError as e:
            show_error_dialog("Error", f"Failed to decode input JSON file:\n{input_file}\nError: {e}", parent=self)
            return
        except ValueError as ve:
            show_error_dialog("Error", f"Invalid JSON structure:\n{ve}", parent=self)
            return
        except Exception as e:
            show_error_dialog("Error", f"Failed to read input JSON:\n{e}\n\n{traceback.format_exc()}", parent=self)
            return

        # --- Start Thread ---
        self.p3_is_processing = True
        try:
            if hasattr(self, 'p3_process_button'): self.p3_process_button.config(state=tk.DISABLED)
            if hasattr(self, 'p3_status_label'): self.p3_status_label.config(text="Starting processing...")
            if hasattr(self, 'p3_progress_bar'): self.p3_progress_var.set(0)
        except tk.TclError: pass
        self.log_status("Starting JSON tagging and TSV generation...")

        # Pass necessary arguments to the thread function
        processing_thread = threading.Thread(
            target=self._process_json_tagging_thread,
            args=(input_qa_data, api_key, model_name_pass1, system_prompt_pass1,
                  enable_second_pass, model_name_pass2, system_prompt_pass2,
                  intermediate_json_p1, intermediate_json_p2, final_tsv_output_file),
            daemon=True)
        processing_thread.start()

    def _process_json_tagging_thread(self, input_qa_data, api_key, model_name_pass1, system_prompt_pass1,
                                     enable_second_pass, model_name_pass2, system_prompt_pass2,
                                     intermediate_json_p1_path, intermediate_json_p2_path, final_tsv_output_path):
        """Worker thread for JSON tagging and final TSV conversion."""
        batch_size = self.p3_batch_size.get()
        api_delay = self.p3_api_delay.get()
        success = False
        final_data_to_convert = None
        tagging_pass1_success = False
        tagging_pass2_success = False # Only relevant if enabled

        try:
            # Handle empty input data gracefully
            if not input_qa_data:
                self.after(0, self.log_status, "Input JSON was empty. Generating empty TSV file.", "warning")
                # Call generate_tsv_from_json_data with empty list to create header-only file
                tsv_success = generate_tsv_from_json_data([], final_tsv_output_path, self.log_status)
                if not tsv_success: raise Exception("Failed to generate empty TSV file.")
                self.after(0, self._update_progress_bar, 100)
                success = True
                self.after(0, self._show_completion_message, final_tsv_output_path)
                return # Exit thread early

            # --- Pass 1 Tagging ---
            self.after(0, self.log_status, "Step 1: Tagging Pass 1...", "step")
            self.after(0, self._update_progress_bar, 5) # Initial progress

            # *** Call the MODIFIED tag_tsv_rows_gemini ***
            # It now takes the list of dicts directly
            tagged_data_p1_generator = tag_tsv_rows_gemini(
                input_qa_data, # Pass the list of dicts directly
                api_key, model_name_pass1, system_prompt_pass1,
                batch_size, api_delay, self.log_status,
                # Update progress for pass 1 (0% to 50% or 0% to 90% if only 1 pass)
                progress_callback=lambda p: self.after(0, self._update_progress_bar, p / (2 if enable_second_pass else 1.1)), # Scale progress
                output_dir=os.path.dirname(intermediate_json_p1_path), # For potential internal temp files
                base_filename=os.path.splitext(os.path.basename(intermediate_json_p1_path))[0],
                parent_widget=self,
                enable_second_pass=False # This call is specifically for Pass 1
            )

            # Collect results (header + tagged dicts) from generator
            tagged_data_p1_with_header = list(tagged_data_p1_generator)

            # Basic check for validity (should have header + data)
            if len(tagged_data_p1_with_header) < 1: # Check if at least header was yielded
                 raise Exception("Tagging Pass 1 failed (generator yielded nothing). Check logs.")
            elif len(tagged_data_p1_with_header) == 1 and len(input_qa_data) > 0:
                 # Only header yielded, likely an error occurred during first batch
                 raise Exception("Tagging Pass 1 failed (only header yielded). Check logs.")

            # Extract actual data (skip header)
            tagged_data_p1_actual = tagged_data_p1_with_header[1:]
            tagging_pass1_success = True # Assume success if no exception

            # Save Pass 1 intermediate JSON
            self.after(0, self.log_status, "Step 1: Saving Pass 1 JSON results...", "step")
            try:
                with open(intermediate_json_p1_path, 'w', encoding='utf-8') as f:
                    json.dump(tagged_data_p1_actual, f, indent=2)
                self.after(0, self.log_status, f"Saved Pass 1 results to {os.path.basename(intermediate_json_p1_path)}", "info")
            except Exception as e:
                raise Exception(f"Failed to save Pass 1 JSON: {e}")

            final_data_to_convert = tagged_data_p1_actual # Default to Pass 1 data
            self.after(0, self._update_progress_bar, 50 if enable_second_pass else 90) # Update progress

            # --- Pass 2 Tagging (Optional) ---
            if enable_second_pass:
                self.after(0, self.log_status, "Step 2: Tagging Pass 2...", "step")

                tagged_data_p2_generator = tag_tsv_rows_gemini(
                    tagged_data_p1_actual, # Input is Pass 1 data (list of dicts)
                    api_key, model_name_pass2, system_prompt_pass2,
                    batch_size, api_delay, self.log_status,
                    # Update progress for pass 2 (50% to 90%)
                    progress_callback=lambda p: self.after(0, self._update_progress_bar, 50 + (p * 0.4)), # Scale 0-100 to 50-90
                    output_dir=os.path.dirname(intermediate_json_p2_path),
                    base_filename=os.path.splitext(os.path.basename(intermediate_json_p2_path))[0],
                    parent_widget=self,
                    enable_second_pass=True # Indicate this is the second pass call internally if needed
                )

                # Collect results from generator
                tagged_data_p2_with_header = list(tagged_data_p2_generator)
                if len(tagged_data_p2_with_header) < 1:
                     raise Exception("Tagging Pass 2 failed (generator yielded nothing). Check logs.")
                elif len(tagged_data_p2_with_header) == 1 and len(tagged_data_p1_actual) > 0:
                     raise Exception("Tagging Pass 2 failed (only header yielded). Check logs.")

                tagged_data_p2_actual = tagged_data_p2_with_header[1:] # Remove header
                tagging_pass2_success = True

                # Save Pass 2 intermediate JSON
                self.after(0, self.log_status, "Step 2: Saving Pass 2 JSON results...", "step")
                try:
                    with open(intermediate_json_p2_path, 'w', encoding='utf-8') as f:
                        json.dump(tagged_data_p2_actual, f, indent=2)
                    self.after(0, self.log_status, f"Saved Pass 2 results to {os.path.basename(intermediate_json_p2_path)}", "info")
                except Exception as e:
                    raise Exception(f"Failed to save Pass 2 JSON: {e}")

                final_data_to_convert = tagged_data_p2_actual # Use Pass 2 data for final conversion
                self.after(0, self._update_progress_bar, 90) # Update progress after pass 2

            # --- Final TSV Generation ---
            self.after(0, self.log_status, "Step 3: Generating Final TSV...", "step")
            if final_data_to_convert is None: # Check if data exists (e.g., if Pass 1 failed and Pass 2 skipped)
                raise Exception("No final tagged data available for TSV conversion.")

            # Use the generic JSON to TSV generator function
            tsv_success = generate_tsv_from_json_data(final_data_to_convert, final_tsv_output_path, self.log_status)
            if not tsv_success:
                raise Exception("Failed to generate final TSV file.")

            self.after(0, self._update_progress_bar, 100)
            success = True
            self.after(0, self._show_completion_message, final_tsv_output_path)

        except Exception as e:
            error_msg = f"Error in P3 processing thread:\n{type(e).__name__}: {e}"
            # Avoid showing full traceback in dialog, log it instead
            print(f"P3 Thread Error Traceback:\n{traceback.format_exc()}")
            self.after(0, self.log_status, f"P3 Thread Error: {error_msg}", "error") # Log error
            self.after(0, self._show_error_status, error_msg) # Show short error in UI
            success = False
        finally:
            # Optionally clean up intermediate JSON files if successful
            if success:
                if intermediate_json_p1_path and os.path.exists(intermediate_json_p1_path):
                    # try: os.remove(intermediate_json_p1_path); self.after(0, self.log_status, f"Cleaned up {os.path.basename(intermediate_json_p1_path)}", "debug")
                    # except Exception as rem_e: self.after(0, self.log_status, f"Could not remove {os.path.basename(intermediate_json_p1_path)}: {rem_e}", "warning")
                    pass # ADDED: Placeholder for the now-empty 'if' block
                if intermediate_json_p2_path and os.path.exists(intermediate_json_p2_path):
                     # try: os.remove(intermediate_json_p2_path); self.after(0, self.log_status, f"Cleaned up {os.path.basename(intermediate_json_p2_path)}", "debug")
                     # except Exception as rem_e: self.after(0, self.log_status, f"Could not remove {os.path.basename(intermediate_json_p2_path)}: {rem_e}", "warning")
                     pass # ADDED: Placeholder for the now-empty 'if' block

            # This line MUST remain outside the commented section and 'if success' block
            self.after(0, self._processing_finished, success)

            self.after(0, self._processing_finished, success)


    def _update_progress_bar(self, progress_value):
        """Callback to update the progress bar from the thread."""
        try:
            if hasattr(self, 'p3_progress_bar') and self.p3_progress_bar.winfo_exists():
                # Ensure value is between 0 and 100
                safe_progress = max(0.0, min(progress_value, 100.0))
                self.p3_progress_var.set(safe_progress)
        except tk.TclError:
            pass # Ignore if widget destroyed

    def _update_status_label(self, text):
        """Updates the status label (convenience wrapper for log_status)."""
        self.log_status(text) # Use log_status for consistency

    def _show_completion_message(self, output_file):
        """Shows the final success message."""
        try:
            # Ensure parent widget exists before showing dialog
            if self.winfo_exists():
                show_info_dialog("Success", f"Processing complete.\nFinal TSV Output:\n{output_file}", parent=self)
            # Update status label
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                self.p3_status_label.config(text="Processing complete. Ready.")
        except tk.TclError:
            print("P3 Warning: Could not show completion message.")

    def _show_error_status(self, error_message):
        """Shows error status in the UI."""
        # Log the full error internally
        print(f"P3 Error Displayed: {error_message}")
        try:
            # Show short error in the status label
            short_error = error_message.split('\n')[0]
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                self.p3_status_label.config(text=f"Error: {short_error}. See msg box.")
            # Show error dialog (ensure parent exists)
            if self.winfo_exists():
                show_error_dialog("Processing Error", f"An error occurred:\n{error_message}", parent=self)
        except tk.TclError:
            print("P3 Warning: Could not show error status.")

    def _processing_finished(self, success=True):
        """Updates UI elements when processing finishes."""
        self.p3_is_processing = False
        try:
            # Re-enable button
            if hasattr(self, 'p3_process_button') and self.p3_process_button.winfo_exists():
                self.p3_process_button.config(state=tk.NORMAL)
            # Update status label
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                 self.p3_status_label.config(text="Processing complete. Ready." if success else "Processing failed. Check logs/dialog.")
            # Set progress bar final state
            if hasattr(self, 'p3_progress_bar') and self.p3_progress_bar.winfo_exists():
                self.p3_progress_var.set(100 if success else 0) # Full or reset on error
        except tk.TclError:
            print("P3 Warning: Could not update UI elements on processing finish.")
