# core/gemini_api.py
import google.generativeai as genai
import google.api_core.exceptions
import json
import time
import re
import traceback
import os # Added for os.path.basename
from tkinter import messagebox # For showing API errors directly if needed

# Use relative imports
try:
    from ..constants import GEMINI_SAFETY_SETTINGS
    from ..utils.helpers import ProcessingError # Use custom exception
except ImportError:
    # Fallback for direct execution or different structure
    from constants import GEMINI_SAFETY_SETTINGS
    from utils.helpers import ProcessingError

# --- Configuration ---
# Configure initially with a dummy key. The actual key will be set by configure_gemini.
# This prevents errors if the module is imported before the key is available.
try:
    genai.configure(api_key="dummy")
except Exception as e:
    print(f"Initial dummy genai configure failed (might be ok): {e}")


def configure_gemini(api_key):
    """Configures the Gemini library with the provided API key."""
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("Error configuring Gemini: API key is missing or placeholder.")
        return False
    try:
        genai.configure(api_key=api_key)
        print("Gemini API configured successfully.")
        return True
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        # Optionally show a message box here or let the caller handle it
        return False

def parse_batch_tag_response(response_text, batch_size):
    """Parses Gemini's numbered list response to extract tags."""
    # (Copied directly from AnkiTagProcessor14.py - no changes needed)
    tags_list = [f"ERROR: No Response Parsed" for _ in range(batch_size)]
    lines = response_text.strip().split('\n')
    parsed_count = 0
    for line in lines:
        line = line.strip()
        if not line: continue
        match = re.match(r'^\s*\[\s*(\d+)\s*\]\s*(.*)$', line)
        if match:
            try:
                item_num = int(match.group(1)) - 1
                tags = match.group(2).strip()
                tags = re.sub(r'\s+', ' ', tags) # Consolidate whitespace
                if 0 <= item_num < batch_size:
                    tags_list[item_num] = tags if tags else "INFO: No tags generated"
                    parsed_count += 1
                else: print(f"[Tag Parser] Warning: Item number {item_num + 1} out of range ({batch_size}). Line: '{line}'")
            except ValueError: print(f"[Tag Parser] Warning: Cannot parse number: '{line}'")
        else: print(f"[Tag Parser] Warning: Line format mismatch: '{line}'")
    if parsed_count != batch_size:
         print(f"[Tag Parser] Warning: Parsed {parsed_count}/{batch_size} items. Check output.")
         for i in range(batch_size):
              if tags_list[i] == "ERROR: No Response Parsed": tags_list[i] = "ERROR: Parsing Mismatch"
    return tags_list


def call_gemini_visual_extraction(pdf_path, api_key, model_name, prompt_text, log_func, parent_widget=None):
    """Calls Gemini with PDF expecting JSON output. Returns (parsed_data, uploaded_file_uri) or (None, uri)."""
    log_func("Calling Gemini for JSON extraction...", "info")
    if not configure_gemini(api_key):
        messagebox.showerror("API Error", "Failed to configure Gemini API key.", parent=parent_widget)
        return None, None

    uploaded_file = None
    uploaded_file_uri = None
    parsed_data = None
    block_reason = None

    generation_config = genai.GenerationConfig(
        response_mime_type="application/json"
    )

    try:
        log_func(f"Uploading PDF '{os.path.basename(pdf_path)}'...", "upload")
        upload_start_time = time.time()
        # Use a display name for easier identification in Google AI Studio
        display_name = f"visual-extract-{os.path.basename(pdf_path)}-{time.time()}"
        uploaded_file = genai.upload_file(path=pdf_path, display_name=display_name)
        uploaded_file_uri = uploaded_file.name # Use the unique name/URI
        upload_duration = time.time() - upload_start_time
        log_func(f"PDF uploaded successfully ({upload_duration:.1f}s). URI: {uploaded_file_uri}", "info")

        model = genai.GenerativeModel(
            model_name,
            safety_settings=GEMINI_SAFETY_SETTINGS,
            generation_config=generation_config
        )
        log_func(f"Sending JSON extraction request to Gemini ({model_name})...", "info")
        api_start_time = time.time()
        response = model.generate_content([prompt_text, uploaded_file])
        api_duration = time.time() - api_start_time
        log_func(f"Received response from Gemini ({api_duration:.1f}s).", "info")

        # --- Process Response ---
        json_string = None
        try:
            # With JSON mime type, the response text should be the JSON
            json_string = response.text
            log_func(f"Attempting to parse JSON response (length {len(json_string) if json_string else 0})...", "debug")
            if json_string:
                log_func(f"JSON Snippet:\n---\n{json_string[:500]}\n---", "debug")
                parsed_data = json.loads(json_string)
                log_func("Successfully parsed JSON response.", "info")
                if not isinstance(parsed_data, list):
                     log_func("Parsing Error: Parsed JSON is not a list.", "error")
                     parsed_data = None # Mark as failed
            else:
                 log_func("Warning: Received empty response text from Gemini.", "warning")
                 parsed_data = [] # Empty list for empty response

        except json.JSONDecodeError as e:
            log_func(f"Parsing Error: Failed to decode JSON: {e}", "error")
            log_func(f"--- Invalid JSON Received ---\n{getattr(response, 'text', 'N/A')}\n---", "debug")
            parsed_data = None
        except AttributeError:
             log_func("Parsing Error: Could not access response text (blocked or empty?).", "error")
             log_func(f"Full Response: {response}", "debug")
             parsed_data = None
        except Exception as e:
             log_func(f"Unexpected error processing response text: {e}\n{traceback.format_exc()}", "error")
             parsed_data = None

        # Check blocking reasons (useful even if parsing failed)
        try:
            # Use genai.types constants if available and preferred
            block_reason_enum = getattr(genai.types, 'BlockReason', None)
            block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0

            if response.prompt_feedback:
                block_reason = response.prompt_feedback.block_reason
                if block_reason == block_reason_unspecified:
                    block_reason = None # Treat unspecified as no block for logic below
        except ValueError: pass # Handle potential enum issues
        except Exception as e: log_func(f"Minor error accessing block_reason: {e}", "debug")

        finish_reason_val = None
        finish_reason_enum = getattr(genai.types, 'FinishReason', None)
        finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3
        try:
            if response.candidates: finish_reason_val = response.candidates[0].finish_reason
            log_func(f"Gemini finish reason: {finish_reason_val}", "debug")
        except Exception as e: log_func(f"Minor error accessing finish_reason: {e}", "debug")

        # Use more specific block reason checking if possible
        if block_reason:
            # Check if *all* candidates were blocked due to safety
            all_blocked = finish_reason_val == finish_reason_safety
            if all_blocked:
                error_msg = f"Request blocked by API. Reason: {block_reason}"
                log_func(error_msg, level="error")
                messagebox.showerror("API Error", error_msg, parent=parent_widget)
                return None, uploaded_file_uri # Return None for data, but keep URI for cleanup
            else:
                log_func(f"Safety block '{block_reason}' present, but finish reason is '{finish_reason_val}'. Proceeding.", level="warning")

        # If parsing failed or returned None earlier, ensure None is returned
        if parsed_data is None and not block_reason:
             feedback = "N/A"
             try: feedback = str(response.prompt_feedback) if response.prompt_feedback else "N/A"
             except Exception: pass
             log_func(f"API call finished, but JSON parsing failed/unusable. Finish={finish_reason_val}. Feedback: {feedback}", level="error")
             return None, uploaded_file_uri

        log_func("Gemini JSON extraction step complete.", "info")
        # Return the parsed list (can be empty []) or None if errors occurred
        return parsed_data, uploaded_file_uri

    except google.api_core.exceptions.GoogleAPIError as api_e:
        error_type = type(api_e).__name__
        error_message = f"Gemini API Error (Visual): {error_type}: {api_e}"
        log_func(error_message, level="error")
        messagebox.showerror("API Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri # Keep URI if upload succeeded
    except FileNotFoundError:
        error_message = f"Input PDF not found: {pdf_path}"
        log_func(error_message, level="error")
        messagebox.showerror("File Error", error_message, parent=parent_widget)
        return None, None
    except Exception as e:
        error_message = f"Unexpected error during Gemini visual call: {type(e).__name__}: {e}"
        log_func(f"FATAL API ERROR (Visual): {error_message}\n{traceback.format_exc()}", level="error")
        messagebox.showerror("Unexpected Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri # Keep URI if upload might have succeeded

def call_gemini_text_analysis(text_content, api_key, model_name, prompt, log_func, parent_widget=None):
    """Calls Gemini with plain text content. Returns response text or None."""
    log_func(f"Processing text content with Gemini ({model_name})...", "info")
    if not configure_gemini(api_key):
        messagebox.showerror("API Error", "Failed to configure Gemini API key.", parent=parent_widget)
        return None

    try:
        model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS)
        full_prompt = [
            {"role": "user", "parts": [prompt]},
            {"role": "model", "parts": ["Okay, I understand. Provide the text content."]},
            {"role": "user", "parts": [text_content]}
        ]

        log_func("Sending text analysis request to Gemini...", "info")
        api_start_time = time.time()
        response = model.generate_content(full_prompt)
        api_duration = time.time() - api_start_time
        log_func(f"Received response from Gemini ({api_duration:.1f}s).", "info")

        raw_response_text = ""
        try:
            # Consolidate checks for text extraction
            if hasattr(response, 'text'):
                 raw_response_text = response.text.strip()
            elif hasattr(response,'parts') and response.parts:
                 raw_response_text = "".join(part.text for part in response.parts if hasattr(part, 'text')).strip()
        except ValueError as e:
             log_func(f"Error accessing response text/parts: {e}. Response: {response}", "warning")
        except Exception as e:
             log_func(f"Could not extract text from response: {e}", "warning")

        # --- Check Blocking/Finish Reasons (similar to visual extraction) ---
        block_reason = None
        block_reason_enum = getattr(genai.types, 'BlockReason', None)
        block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
        try:
            if response.prompt_feedback:
                block_reason = response.prompt_feedback.block_reason
                if block_reason == block_reason_unspecified:
                    block_reason = None
        except ValueError: pass
        except Exception as e: log_func(f"Minor error accessing block_reason: {e}", "debug")

        finish_reason_val = None
        finish_reason_enum = getattr(genai.types, 'FinishReason', None)
        finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3
        finish_reason_stop = getattr(finish_reason_enum, 'STOP', 2) if finish_reason_enum else 2
        try:
            if response.candidates: finish_reason_val = response.candidates[0].finish_reason
            log_func(f"Gemini finish reason: {finish_reason_val}", "debug")
        except Exception as e: log_func(f"Minor error accessing finish_reason: {e}", "debug")

        if block_reason:
            all_blocked = finish_reason_val == finish_reason_safety
            if all_blocked:
                error_msg = f"Request blocked by API. Reason: {block_reason}"
                log_func(error_msg, level="error")
                messagebox.showerror("API Error", error_msg, parent=parent_widget)
                return None
            else:
                log_func(f"Safety block '{block_reason}' present, but finish reason is '{finish_reason_val}'. Proceeding.", level="warning")

        # Check if response is empty despite no block
        if not raw_response_text and not block_reason:
             candidates_exist = hasattr(response, 'candidates') and response.candidates and response.candidates[0] is not None
             # Check if finish reason is STOP - if not, something likely went wrong
             if not candidates_exist or finish_reason_val != finish_reason_stop:
                  feedback = "N/A"
                  try: feedback = str(response.prompt_feedback) if response.prompt_feedback else "N/A"
                  except Exception: pass
                  error_msg = f"API call returned no text, finish_reason={finish_reason_val}. Feedback: {feedback}"
                  log_func(error_msg, level="error")
                  # Optionally show error to user?
                  # messagebox.showwarning("API Warning", "Gemini returned an empty response.", parent=parent_widget)
                  return None # Return None to indicate failure/unusable response

        log_func("Text analysis Gemini call complete.", "info")
        return raw_response_text

    except google.api_core.exceptions.GoogleAPIError as api_e:
        error_type = type(api_e).__name__
        error_message = f"Gemini API Error (Text): {error_type}: {api_e}"
        log_func(error_message, level="error")
        messagebox.showerror("API Error", error_message, parent=parent_widget)
        return None
    except Exception as e:
        error_message = f"Unexpected error during Gemini text call: {type(e).__name__}: {e}"
        log_func(f"FATAL API ERROR (Text): {error_message}\n{traceback.format_exc()}", level="error")
        messagebox.showerror("Unexpected Error", error_message, parent=parent_widget)
        return None

def tag_tsv_rows_gemini(data_rows_with_header, api_key, model_name, system_prompt,
                       batch_size, api_delay, log_func, progress_callback=None, parent_widget=None):
    """Tags TSV data rows using Gemini batches. Yields tagged rows (list)."""
    if not data_rows_with_header:
        log_func("No data rows provided for tagging.", "warning")
        return # Return or yield nothing

    header = data_rows_with_header[0]
    data_rows = data_rows_with_header[1:]
    total_rows = len(data_rows)
    processed_rows = 0
    total_batches = (total_rows + batch_size - 1) // batch_size
    log_func(f"Starting Gemini tagging: {total_rows} rows, {total_batches} batches.", "info")

    if not configure_gemini(api_key):
        messagebox.showerror("API Error", "Failed to configure Gemini API key for tagging.", parent=parent_widget)
        # Yield rows with errors?
        for row in data_rows:
            yield row + ["ERROR: API Key Config Failed"]
        return

    model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS)

    # Prepare output header
    output_header = header[:]
    tags_col_exists = "Tags" in output_header
    tags_col_index = -1
    if tags_col_exists:
        try:
            tags_col_index = header.index("Tags")
        except ValueError: # Should not happen if exists, but handle anyway
             tags_col_exists = False
    if not tags_col_exists:
        output_header.append("Tags")

    yield output_header # Yield header first

    block_reason_enum = getattr(genai.types, 'BlockReason', None)
    block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
    finish_reason_enum = getattr(genai.types, 'FinishReason', None)
    finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3

    for i in range(0, total_rows, batch_size):
        batch_start_time = time.time()
        batch_num = i // batch_size + 1
        log_func(f"Tagging Batch {batch_num}/{total_batches}...", "debug")
        if progress_callback:
            progress = 50 + (processed_rows / total_rows) * 45 if total_rows > 0 else 50 # Simulate progress if needed
            progress_callback(progress) # Update progress bar if callback provided

        batch = data_rows[i:min(i + batch_size, total_rows)]
        batch_prompt_content_lines = [f"[{idx + 1}] {' | '.join(map(str, row))}" for idx, row in enumerate(batch)]
        batch_prompt_content = "\n".join(batch_prompt_content_lines)
        tag_responses = []

        try:
            response = model.generate_content(
                 [{"role": "user", "parts": [system_prompt]},
                  {"role": "model", "parts": ["Okay, I understand. Provide the batch."]},
                  {"role": "user", "parts": [batch_prompt_content]}],
             )
            response_text = "".join(part.text for part in response.parts if hasattr(part, 'text')).strip() if hasattr(response, 'parts') else ""

            block_reason = None
            try:
                if response.prompt_feedback:
                    block_reason = response.prompt_feedback.block_reason
                    if block_reason == block_reason_unspecified:
                        block_reason = None
            except ValueError: pass
            except Exception as e: log_func(f"Minor error accessing block_reason: {e}", "debug")

            if block_reason:
                 finish_reason_val = getattr(response.candidates[0], 'finish_reason', None) if response.candidates else None
                 all_blocked = finish_reason_val == finish_reason_safety
                 if all_blocked:
                     tag_responses = [f"ERROR: Blocked ({block_reason})" for _ in batch]
                     log_func(f"Batch {batch_num} blocked by API: {block_reason}", "error")
                 else:
                     tag_responses = parse_batch_tag_response(response_text, len(batch))
                     log_func(f"Batch {batch_num} had block '{block_reason}' but parsed.", "warning")
            elif not response_text:
                 tag_responses = ["ERROR: Empty Response" for _ in batch]
                 log_func(f"Batch {batch_num} received empty response.", "warning")
            else:
                 tag_responses = parse_batch_tag_response(response_text, len(batch))

        except google.api_core.exceptions.GoogleAPIError as api_e:
            error_type = type(api_e).__name__; error_message = str(api_e)
            log_func(f"API Error batch {batch_num}: {error_type}: {error_message}", "error")
            # Add error message here if needed for UI
            # messagebox.showerror(...) # Maybe too noisy? Let log handle it.
            tag_responses = [f"ERROR: API Call Failed ({error_type})" for _ in batch]
            # Decide: stop workflow or mark errors? Mark errors for now.
        except Exception as e:
             error_type = type(e).__name__
             log_func(f"Unexpected error batch {batch_num}: {error_type}: {e}\n{traceback.format_exc()}", "error")
             tag_responses = [f"ERROR: Processing Failed ({error_type})" for _ in batch]

        # Yield tagged rows for this batch
        for row_index, row in enumerate(batch):
            tags = tag_responses[row_index] if row_index < len(tag_responses) else "ERROR: Tag Index Error"
            output_row_list = row[:] # Copy original row

            if tags_col_exists:
                if tags_col_index != -1 and tags_col_index < len(output_row_list):
                     output_row_list[tags_col_index] = tags
                else: # Fallback if index somehow invalid or row too short
                     log_func(f"Warning: Could not place tag in existing column index {tags_col_index} for row {processed_rows + row_index + 1}. Appending.", "warning")
                     output_row_list.append(tags) # Append tag if index failed
            else:
                 output_row_list.append(tags) # Append if Tags col is new

            # Ensure final row matches output header length
            if len(output_row_list) < len(output_header):
                 output_row_list.extend([""] * (len(output_header) - len(output_row_list)))
            elif len(output_row_list) > len(output_header):
                 output_row_list = output_row_list[:len(output_header)]

            yield output_row_list

        processed_rows += len(batch)
        batch_end_time = time.time()
        log_func(f"Batch {batch_num} tagged. Time: {batch_end_time - batch_start_time:.2f}s", "debug")

        # API Delay
        if i + batch_size < total_rows and api_delay > 0:
            log_func(f"Waiting {api_delay:.1f}s...", "debug")
            time.sleep(api_delay)

    log_func("Gemini tagging finished.", "info")


def cleanup_gemini_file(uploaded_file_uri, api_key, log_func):
    """Deletes a file previously uploaded to Gemini."""
    if not uploaded_file_uri:
        return
    log_func(f"Attempting to clean up uploaded file: {uploaded_file_uri}", "info")
    try:
        if not configure_gemini(api_key):
             log_func("Cleanup failed: Could not configure API key.", "warning")
             return
        # Extract just the file ID part if URI format is 'files/...'
        file_name_to_delete = uploaded_file_uri
        if '/' in file_name_to_delete:
            file_name_to_delete = file_name_to_delete.split('/')[-1]

        genai.delete_file(name=f"files/{file_name_to_delete}")
        log_func(f"Successfully deleted Gemini file: {file_name_to_delete}", "info")
    except Exception as delete_e:
        log_func(f"Cleanup failed for '{uploaded_file_uri}': {delete_e}", "warning")
