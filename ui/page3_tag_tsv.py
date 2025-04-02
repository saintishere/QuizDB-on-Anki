# ui/page3_tag_tsv.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import traceback
import time # Added for API delay
from datetime import datetime # Added for logging timestamp

# Import necessary components using relative paths
try:
    from ..constants import DEFAULT_MODEL, GEMINI_UNIFIED_MODELS, DEFAULT_BATCH_TAGGING_PROMPT
    from ..utils.helpers import show_error_dialog, show_info_dialog # Use helpers
    from ..core.gemini_api import tag_tsv_rows_gemini, configure_gemini # Import core functions
except ImportError:
    # Fallback for direct execution
    print("Error: Relative imports failed in page3_tag_tsv.py. Using direct imports.")
    from constants import DEFAULT_MODEL, GEMINI_UNIFIED_MODELS, DEFAULT_BATCH_TAGGING_PROMPT
    from utils.helpers import show_error_dialog, show_info_dialog
    from core.gemini_api import tag_tsv_rows_gemini, configure_gemini

class TagTsvPage(ttk.Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance

        # --- Page 3 Variables ---
        self.p3_input_file_var = tk.StringVar()
        self.p3_batch_size = tk.IntVar(value=10)
        self.p3_progress_var = tk.DoubleVar(value=0)
        self.p3_system_prompt_text = tk.StringVar(value=DEFAULT_BATCH_TAGGING_PROMPT)
        self.p3_api_delay = tk.DoubleVar(value=10.0)
        self.p3_gemini_selected_model = tk.StringVar(value=DEFAULT_MODEL)
        self.p3_is_processing = False

        # --- Build UI ---
        self._build_ui()
        print("Initialized TagTsvPage")

    def _build_ui(self):
        """Creates the UI elements for Page 3."""
        config_frame = ttk.LabelFrame(self, text="Configuration")
        config_frame.pack(fill=tk.X, padx=10, pady=10)
        prompt_frame = ttk.LabelFrame(self, text="System Prompt (Tagging Instructions)")
        prompt_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        status_frame = ttk.LabelFrame(self, text="Status & Progress")
        status_frame.pack(fill=tk.X, padx=10, pady=(0,10))
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=10, pady=10)

        # --- Configuration Frame ---
        ttk.Label(config_frame, text="Input TSV File:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.p3_input_file_entry = ttk.Entry(config_frame, textvariable=self.p3_input_file_var, width=60)
        self.p3_input_file_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        ttk.Button(config_frame, text="Browse", command=self._browse_input_file).grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(config_frame, text="Gemini API Key:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.p3_api_key_entry = ttk.Entry(config_frame, textvariable=self.app.gemini_api_key, width=60, show="*") # Shared key
        self.p3_api_key_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.p3_show_key_button = ttk.Button(config_frame, text="Show/Hide", command=self.app.toggle_api_key_visibility) # Shared toggle
        self.p3_show_key_button.grid(row=1, column=3, padx=5, pady=5)

        ttk.Label(config_frame, text="Select Model:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.p3_model_dropdown = ttk.Combobox(config_frame, textvariable=self.p3_gemini_selected_model, values=GEMINI_UNIFIED_MODELS, state="readonly", width=57)
        # Set initial value defensively
        if GEMINI_UNIFIED_MODELS and self.p3_gemini_selected_model.get() in GEMINI_UNIFIED_MODELS:
             self.p3_model_dropdown.set(self.p3_gemini_selected_model.get())
        elif GEMINI_UNIFIED_MODELS:
             self.p3_gemini_selected_model.set(GEMINI_UNIFIED_MODELS[0])
        self.p3_model_dropdown.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)

        ttk.Label(config_frame, text="Batch Size:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        p3_batch_size_entry = ttk.Entry(config_frame, textvariable=self.p3_batch_size, width=10)
        p3_batch_size_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(config_frame, text="API Delay (sec):").grid(row=3, column=2, sticky=tk.W, padx=(20, 5), pady=5)
        self.p3_api_delay_entry = ttk.Entry(config_frame, textvariable=self.p3_api_delay, width=10)
        self.p3_api_delay_entry.grid(row=3, column=3, sticky=tk.W, padx=5, pady=5)

        config_frame.grid_columnconfigure(1, weight=1) # Make entry column expandable

        # --- Prompt Frame ---
        self.p3_system_prompt_editor = scrolledtext.ScrolledText(prompt_frame, height=10, wrap=tk.WORD)
        self.p3_system_prompt_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.p3_system_prompt_editor.insert(tk.END, self.p3_system_prompt_text.get())
        self.p3_system_prompt_editor.bind("<<Modified>>", self._sync_prompt_var_from_editor)

        # --- Status Frame ---
        ttk.Label(status_frame, text="Progress:").pack(anchor=tk.W, padx=5, pady=(5,0))
        self.p3_progress_bar = ttk.Progressbar(status_frame, variable=self.p3_progress_var, maximum=100)
        self.p3_progress_bar.pack(fill=tk.X, padx=5, pady=(0,5))
        self.p3_status_label = ttk.Label(status_frame, text="Ready")
        self.p3_status_label.pack(anchor=tk.W, padx=5, pady=(0,5))

        # --- Action Frame ---
        self.p3_process_button = ttk.Button(action_frame, text="Process TSV with Gemini Tags", command=self._start_gemini_processing)
        self.p3_process_button.pack(side=tk.RIGHT, padx=5, pady=5)

    def log_status(self, message, level="info"):
        """Logs messages to the status label on this page."""
        # Simplified logging for Page 3, just updates the label
        try:
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                prefix_map = {"info": "", "step": "", "warning": "WARN: ", "error": "ERROR: ", "debug": "DEBUG: "}
                prefix = prefix_map.get(level, "")
                timestamp = datetime.now().strftime("%H:%M:%S")
                # Keep message short for label
                short_message = message.split('\n')[0]
                if len(short_message) > 100: # Truncate long messages
                    short_message = short_message[:97] + "..."
                self.p3_status_label.config(text=f"{timestamp} {prefix}{short_message}")
                self.update_idletasks() # Ensure UI updates
        except tk.TclError:
            print(f"P3 Log Warning: Could not update status label ({message})")
        except Exception as e:
            print(f"Unexpected error in P3 log_status: {e}")

    def _sync_prompt_var_from_editor(self, event=None):
         """Syncs the prompt editor text to the variable."""
         try:
             if hasattr(self, 'p3_system_prompt_editor') and self.p3_system_prompt_editor.winfo_exists():
                 current_text = self.p3_system_prompt_editor.get("1.0", tk.END).strip()
                 self.p3_system_prompt_text.set(current_text)
                 self.p3_system_prompt_editor.edit_modified(False) # Reset modified flag
         except tk.TclError: pass # Ignore if widget destroyed

    def _browse_input_file(self):
        """Opens file dialog to select input TSV file."""
        file_path = filedialog.askopenfilename(
             parent=self, title="Select Input TSV File",
             filetypes=[("Text files", "*.txt"), ("TSV files", "*.tsv"), ("All files", "*.*")]
        )
        if file_path:
            self.p3_input_file_var.set(file_path)
            self.log_status(f"Selected input file: {os.path.basename(file_path)}")

    def _start_gemini_processing(self):
        """Validates inputs and starts the Gemini batch processing in a thread."""
        if self.p3_is_processing:
            show_info_dialog("In Progress", "Tagging already running.", parent=self)
            return

        input_file = self.p3_input_file_var.get()
        api_key = self.app.gemini_api_key.get() # Use shared key
        model_name = self.p3_gemini_selected_model.get()
        system_prompt = self.p3_system_prompt_text.get() # Get from variable

        # --- Validations ---
        if not input_file or not os.path.exists(input_file):
            show_error_dialog("Error", "Select valid input TSV.", parent=self); return
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            show_error_dialog("Error", "Enter Gemini API Key.", parent=self); return
        if not model_name:
            show_error_dialog("Error", "Select Gemini model.", parent=self); return
        if not system_prompt:
            show_error_dialog("Error", "System prompt cannot be empty.", parent=self); return
        try:
            batch_s = self.p3_batch_size.get()
            delay = self.p3_api_delay.get()
            if batch_s <= 0:
                show_error_dialog("Error", "Batch size must be > 0.", parent=self); return
            if delay < 0:
                show_info_dialog("Warning", "API Delay negative. Using 0.", parent=self); self.p3_api_delay.set(0.0)
        except tk.TclError:
            show_error_dialog("Error", "Invalid Batch Size or Delay.", parent=self); return

        # Determine output file path
        base_name, _ = os.path.splitext(input_file)
        output_file = f"{base_name}_tagged.txt"

        # --- Read and Prepare Data ---
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                show_error_dialog("Error", "Input file empty.", parent=self); return

            # Simple header detection (assumes first line is header)
            header = lines[0].strip().split("\t")
            data_rows = [line.strip().split("\t") for line in lines[1:] if line.strip()]

            if not data_rows:
                show_error_dialog("Error", "No data rows found (excluding header).", parent=self); return

            # Combine header and data for the processing function
            data_rows_with_header = [header] + data_rows

        except FileNotFoundError:
            show_error_dialog("Error", f"Input file not found: {input_file}", parent=self); return
        except Exception as e:
            show_error_dialog("Error", f"Failed to read/prepare file:\n{e}\n\n{traceback.format_exc()}", parent=self); return

        # --- Start Thread ---
        self.p3_is_processing = True
        try:
            if hasattr(self, 'p3_process_button'): self.p3_process_button.config(state=tk.DISABLED)
            if hasattr(self, 'p3_status_label'): self.p3_status_label.config(text="Starting processing...")
            if hasattr(self, 'p3_progress_bar'): self.p3_progress_var.set(0)
        except tk.TclError: pass # Ignore if widgets destroyed

        self.log_status("Starting Gemini batch tagging...")

        processing_thread = threading.Thread(
            target=self._process_batches_threaded,
            args=(data_rows_with_header, api_key, model_name, system_prompt, output_file),
            daemon=True)
        processing_thread.start()

    def _process_batches_threaded(self, data_rows_with_header, api_key, model_name, system_prompt, output_file):
        """Worker thread for batch processing with Gemini."""
        batch_size = self.p3_batch_size.get()
        api_delay = self.p3_api_delay.get()
        total_rows = len(data_rows_with_header) - 1 # Exclude header row
        processed_rows_count = 0
        success = False
        print(f"[P3 Tagging Thread] Start: Model={model_name}, Batch={batch_size}, Delay={api_delay}")

        try:
            # Use the generator function from gemini_api
            tagged_row_generator = tag_tsv_rows_gemini(
                data_rows_with_header, api_key, model_name, system_prompt,
                batch_size, api_delay, self.log_status, # Pass log_status
                progress_callback=self._update_progress_bar, # Pass progress callback
                parent_widget=self # Pass self for potential dialogs from API module
            )

            with open(output_file, "w", encoding="utf-8", newline='') as f:
                first_row = True
                for output_row in tagged_row_generator:
                    if first_row:
                        # Write header (yielded first by the generator)
                        f.write("\t".join(map(str, output_row)) + "\n")
                        first_row = False
                    else:
                        # Write data row
                        f.write("\t".join(map(str, output_row)) + "\n")
                        processed_rows_count += 1
                        # Update progress label periodically (less frequently than progress bar)
                        if processed_rows_count % (batch_size * 2) == 0 or processed_rows_count == total_rows:
                             self.after(0, self._update_status_label, f"Processed {processed_rows_count}/{total_rows} rows...")

            # If loop completes without error, assume success
            success = True
            self.after(0, self._update_status_label, f"Processing complete. {processed_rows_count}/{total_rows} notes processed.")
            self.after(0, self._show_completion_message, output_file)

        except Exception as e:
            error_msg = f"Error in P3 tagging thread:\n{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
            print(error_msg)
            # Use after() to schedule the error dialog on the main thread
            self.after(0, self._show_error_status, error_msg)
            success = False # Ensure success is False on error
        finally:
            # Ensure UI is re-enabled on the main thread
            self.after(0, self._processing_finished, success)

    def _update_progress_bar(self, progress_value):
        """Callback to update the progress bar from the thread."""
        # Assumes progress_value is 0-100
        try:
            if hasattr(self, 'p3_progress_bar') and self.p3_progress_bar.winfo_exists():
                self.p3_progress_var.set(progress_value)
        except tk.TclError: pass # Ignore if widget destroyed

    def _update_status_label(self, text):
        """Helper to update status label safely from thread via self.after."""
        self.log_status(text) # Use the main log_status method

    def _show_completion_message(self, output_file):
        """Shows completion message box safely from thread via self.after."""
        try:
            if self.winfo_exists(): # Check if the page itself exists
                show_info_dialog("Success", f"Processing complete.\nOutput: {output_file}", parent=self)
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                self.p3_status_label.config(text="Processing complete. Ready.")
        except tk.TclError:
            print("P3 Warning: Could not show completion message.")

    def _show_error_status(self, error_message):
        """Shows error message box safely from thread via self.after."""
        print(f"P3 Error Displayed: {error_message}")
        try:
            short_error = error_message.split('\n')[0]
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                self.p3_status_label.config(text=f"Error: {short_error}. See msg box.")
            if self.winfo_exists():
                show_error_dialog("Processing Error", f"Error:\n{error_message}", parent=self)
        except tk.TclError:
            print("P3 Warning: Could not show error status.")

    def _processing_finished(self, success=True):
        """Updates UI when processing ends (called via self.after)."""
        self.p3_is_processing = False
        try:
            if hasattr(self, 'p3_process_button') and self.p3_process_button.winfo_exists():
                self.p3_process_button.config(state=tk.NORMAL)
            if hasattr(self, 'p3_status_label') and self.p3_status_label.winfo_exists():
                 if success:
                     self.p3_status_label.config(text="Processing complete. Ready.")
                 else:
                     self.p3_status_label.config(text="Processing failed. Check logs/dialog.")
            if hasattr(self, 'p3_progress_bar') and self.p3_progress_bar.winfo_exists():
                 self.p3_progress_var.set(100 if success else 0) # Show full or reset on fail
        except tk.TclError:
            print("P3 Warning: Could not update UI elements on processing finish.")
