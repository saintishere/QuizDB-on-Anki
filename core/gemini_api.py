# core/gemini_api.py
import google.generativeai as genai
import google.api_core.exceptions
import json
import time
import re
import traceback
import os # Added for os.path.basename, path.join
from tkinter import messagebox # For showing API errors directly if needed
import math # For calculating text chunks

# Use relative imports
try:
    from ..constants import GEMINI_SAFETY_SETTINGS
    from ..utils.helpers import ProcessingError, sanitize_filename # Use custom exception, add sanitize_filename
except ImportError:
    # Fallback for direct execution or different structure
    from constants import GEMINI_SAFETY_SETTINGS
    from utils.helpers import ProcessingError, sanitize_filename

# --- Configuration ---
# Configure initially with a dummy key. The actual key will be set by configure_gemini.
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
        # print("Gemini API configured successfully.") # Make less verbose
        return True
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        return False

def parse_batch_tag_response(response_text, batch_size):
    """Parses Gemini's numbered list response to extract tags."""
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

# --- NEW Helper for Incremental Saving ---
def save_json_incrementally(data_list, output_dir, base_filename, step_name, log_func):
    """Saves the current list of parsed JSON objects to a temporary file."""
    if not data_list:
        return None # Don't save if empty

    temp_filename = f"{base_filename}_{step_name}_temp_results.json"
    temp_filepath = os.path.join(output_dir, temp_filename)
    try:
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, indent=2) # Save as a standard JSON array
        log_func(f"Saved intermediate {step_name} results ({len(data_list)} items) to {temp_filename}", "debug")
        return temp_filepath
    except Exception as e:
        log_func(f"Error saving intermediate {step_name} results to {temp_filepath}: {e}", "error")
        return None

# --- Modified Visual Extraction ---
def call_gemini_visual_extraction(pdf_path, api_key, model_name, prompt_text, log_func, parent_widget=None):
    """
    Calls Gemini with PDF expecting JSON output.
    Implements robust parsing and incremental saving of the single response.
    Returns (list_of_parsed_objects, uploaded_file_uri) or (None, uri).
    None indicates an unrecoverable error preventing further processing for this file.
    An empty list [] indicates success but no data extracted.
    """
    log_func("Calling Gemini for Visual JSON extraction...", "info")
    if not configure_gemini(api_key):
        # Return None here as API key failure is unrecoverable for this call
        if parent_widget: messagebox.showerror("API Error", "Failed to configure Gemini API key.", parent=parent_widget)
        else: log_func("API Error: Failed to configure Gemini API key.", "error")
        return None, None

    uploaded_file = None
    uploaded_file_uri = None
    all_parsed_objects = None # Initialize to None to distinguish from empty list []
    block_reason = None
    output_dir = os.path.dirname(pdf_path) or os.getcwd()
    safe_base_name = sanitize_filename(os.path.basename(pdf_path))
    temp_save_path = None # Track path to incrementally saved results

    generation_config = genai.GenerationConfig(
        response_mime_type="application/json" # Request JSON directly
    )

    try:
        log_func(f"Uploading PDF '{os.path.basename(pdf_path)}'...", "upload")
        upload_start_time = time.time()
        display_name = f"visual-extract-{os.path.basename(pdf_path)}-{time.time()}"
        uploaded_file = genai.upload_file(path=pdf_path, display_name=display_name)
        uploaded_file_uri = uploaded_file.name
        upload_duration = time.time() - upload_start_time
        log_func(f"PDF uploaded successfully ({upload_duration:.1f}s). URI: {uploaded_file_uri}", "info")

        model = genai.GenerativeModel(
            model_name,
            safety_settings=GEMINI_SAFETY_SETTINGS,
            generation_config=generation_config
        )
        log_func(f"Sending JSON extraction request to Gemini ({model_name})...", "info")
        api_start_time = time.time()
        response = model.generate_content([prompt_text, uploaded_file]) # Assuming config set on model is sufficient
        api_duration = time.time() - api_start_time
        log_func(f"Received response from Gemini ({api_duration:.1f}s).", "info")

        # --- Process Response ---
        json_string = None
        try:
            json_string = response.text
            log_func(f"Attempting to parse JSON response (length {len(json_string) if json_string else 0})...", "debug")
            if json_string:
                # log_func(f"JSON Snippet:\n---\n{json_string[:500]}\n---", "debug") # Reduce verbosity
                try:
                    parsed_data = json.loads(json_string)
                    if isinstance(parsed_data, list):
                        all_parsed_objects = parsed_data # Successfully parsed list
                        log_func(f"Successfully parsed entire JSON response ({len(all_parsed_objects)} items).", "info")
                        temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                    else:
                         log_func("Parsing Error: Parsed JSON is not a list.", "error")
                         all_parsed_objects = None # Parsing failed (not a list)
                except json.JSONDecodeError as e:
                    log_func(f"Initial JSON parsing failed (response_mime_type='application/json'): {e}. Raw response snippet:\n{json_string[:1000]}", "error")
                    # Try stripping potential markdown
                    cleaned_json_string = re.sub(r'^```json\s*', '', json_string.strip(), flags=re.IGNORECASE)
                    cleaned_json_string = re.sub(r'\s*```$', '', cleaned_json_string)
                    if cleaned_json_string != json_string:
                        log_func("Retrying parse after stripping potential markdown...", "warning")
                        try:
                            parsed_data = json.loads(cleaned_json_string)
                            if isinstance(parsed_data, list):
                                all_parsed_objects = parsed_data # Success after stripping
                                log_func(f"Successfully parsed JSON after stripping markdown ({len(all_parsed_objects)} items).", "info")
                                temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                            else:
                                log_func("Parsing Error: Stripped JSON is not a list.", "error")
                                all_parsed_objects = None # Parsing failed (not a list)
                        except json.JSONDecodeError as e2:
                            log_func(f"Parsing failed even after stripping markdown: {e2}", "error")
                            all_parsed_objects = None # Parsing failed
                    else:
                         all_parsed_objects = None # Parsing failed (no markdown found)
            else:
                 log_func("Warning: Received empty response text from Gemini.", "warning")
                 all_parsed_objects = [] # Treat empty response as success with no data

        except AttributeError:
             log_func("Parsing Error: Could not access response text (blocked or empty?).", "error")
             log_func(f"Full Response: {response}", "debug")
             all_parsed_objects = None # Error state
        except Exception as e:
             log_func(f"Unexpected error processing response text: {e}\n{traceback.format_exc()}", "error")
             all_parsed_objects = None # Error state

        # Check blocking reasons AFTER trying to parse
        try:
            block_reason_enum = getattr(genai.types, 'BlockReason', None)
            block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
            if response.prompt_feedback:
                block_reason = response.prompt_feedback.block_reason
                if block_reason == block_reason_unspecified: block_reason = None
        except ValueError: pass
        except Exception as e: log_func(f"Minor error accessing block_reason: {e}", "debug")

        finish_reason_val = None
        finish_reason_enum = getattr(genai.types, 'FinishReason', None)
        finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3
        try:
            if response.candidates: finish_reason_val = response.candidates[0].finish_reason
            log_func(f"Gemini finish reason: {finish_reason_val}", "debug")
        except Exception as e: log_func(f"Minor error accessing finish_reason: {e}", "debug")

        if block_reason:
            all_blocked = finish_reason_val == finish_reason_safety
            if all_blocked:
                error_msg = f"Request blocked by API. Reason: {block_reason}"
                log_func(error_msg, level="error")
                if parent_widget: messagebox.showerror("API Error", error_msg, parent=parent_widget)
                return None, uploaded_file_uri # Unrecoverable block
            else:
                log_func(f"Safety block '{block_reason}' present, but finish reason is '{finish_reason_val}'. Proceeding with potentially partial data.", level="warning")
                # If parsing failed earlier, all_parsed_objects is already None, which signals failure
                # If parsing succeeded, we proceed with the parsed data

        # If parsing failed (is None) and there wasn't an explicit block, it's an unrecoverable error for this file
        if all_parsed_objects is None and not block_reason:
             feedback = "N/A"
             try: feedback = str(response.prompt_feedback) if response.prompt_feedback else "N/A"
             except Exception: pass
             log_func(f"API call finished, but JSON parsing failed/unusable. Finish={finish_reason_val}. Feedback: {feedback}. Treating as error for this file.", level="error")
             return None, uploaded_file_uri # Unrecoverable parsing failure

        log_func("Gemini Visual JSON extraction step complete.", "info")
        # Return the list (could be empty) or None (if error occurred)
        return all_parsed_objects, uploaded_file_uri

    except google.api_core.exceptions.GoogleAPIError as api_e:
        error_type = type(api_e).__name__; error_message = f"Gemini API Error (Visual): {error_type}: {api_e}"
        log_func(error_message, level="error")
        if parent_widget: messagebox.showerror("API Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri # API error is unrecoverable for this file
    except FileNotFoundError:
        error_message = f"Input PDF not found: {pdf_path}"
        log_func(error_message, level="error")
        if parent_widget: messagebox.showerror("File Error", error_message, parent=parent_widget)
        return None, None # File not found, no URI
    except Exception as e:
        error_message = f"Unexpected error during Gemini visual call: {type(e).__name__}: {e}"
        log_func(f"FATAL API ERROR (Visual): {error_message}\n{traceback.format_exc()}", level="error")
        if parent_widget: messagebox.showerror("Unexpected Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri # Unrecoverable error

# --- Modified Text Analysis ---
def call_gemini_text_analysis(text_content, api_key, model_name, prompt, log_func,
                              output_dir, base_filename, # Added for incremental saving
                              chunk_size=30000, api_delay=5.0, # Added chunking params
                              parent_widget=None):
    """
    Calls Gemini with plain text content, processing in chunks.
    Saves accumulated results incrementally.
    Returns the final list of parsed JSON objects or None.
    None indicates an unrecoverable error. An empty list [] indicates success but no data extracted.
    """
    log_func(f"Processing text content with Gemini ({model_name}) in chunks...", "info")
    if not configure_gemini(api_key):
        if parent_widget: messagebox.showerror("API Error", "Failed to configure Gemini API key.", parent=parent_widget)
        else: log_func("API Error: Failed to configure Gemini API key.", "error")
        return None # Unrecoverable

    all_parsed_data = [] # Accumulate results from all chunks
    temp_save_path = None # Track path to incrementally saved results
    safe_base_name = sanitize_filename(base_filename)
    had_unrecoverable_error = False # Flag for overall failure

    total_len = len(text_content)
    num_chunks = math.ceil(total_len / chunk_size)
    log_func(f"Splitting text ({total_len} chars) into ~{num_chunks} chunks of size {chunk_size}.", "debug")

    block_reason_enum = getattr(genai.types, 'BlockReason', None)
    block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
    finish_reason_enum = getattr(genai.types, 'FinishReason', None)
    finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3
    finish_reason_stop = getattr(finish_reason_enum, 'STOP', 1) if finish_reason_enum else 1

    generation_config = genai.GenerationConfig(
        response_mime_type="application/json"
    )
    model = genai.GenerativeModel(
        model_name,
        safety_settings=GEMINI_SAFETY_SETTINGS,
        generation_config=generation_config
        )

    for i in range(num_chunks):
        chunk_start_time = time.time()
        chunk_num = i + 1
        start_index = i * chunk_size
        end_index = min((i + 1) * chunk_size, total_len)
        chunk_text = text_content[start_index:end_index]
        log_func(f"Processing chunk {chunk_num}/{num_chunks} ({len(chunk_text)} chars)...", "info")

        if not chunk_text.strip():
            log_func(f"Skipping empty chunk {chunk_num}.", "debug"); continue

        chunk_parsed_successfully = False
        try:
            full_prompt = [
                {"role": "user", "parts": [prompt]},
                {"role": "model", "parts": ["Okay, I understand. Provide the text chunk."]},
                {"role": "user", "parts": [chunk_text]}
            ]

            log_func(f"Sending chunk {chunk_num} analysis request to Gemini...", "debug")
            api_start_time = time.time()
            response = model.generate_content(full_prompt, generation_config=generation_config)
            api_duration = time.time() - api_start_time
            log_func(f"Received response for chunk {chunk_num} ({api_duration:.1f}s).", "debug")

            raw_response_text = ""
            try:
                if hasattr(response, 'text'): raw_response_text = response.text.strip()
                elif hasattr(response,'parts') and response.parts: raw_response_text = "".join(part.text for part in response.parts if hasattr(part, 'text')).strip()
            except ValueError as e: log_func(f"Error accessing response text/parts (chunk {chunk_num}): {e}. Response: {response}", "warning")
            except Exception as e: log_func(f"Could not extract text from response (chunk {chunk_num}): {e}", "warning")

            # Check Blocking/Finish Reasons
            block_reason = None
            try:
                if response.prompt_feedback:
                    block_reason = response.prompt_feedback.block_reason
                    if block_reason == block_reason_unspecified: block_reason = None
            except ValueError: pass
            except Exception as e: log_func(f"Minor error accessing block_reason (chunk {chunk_num}): {e}", "debug")

            finish_reason_val = None
            try:
                if response.candidates: finish_reason_val = response.candidates[0].finish_reason
                log_func(f"Chunk {chunk_num} finish reason: {finish_reason_val}", "debug")
            except Exception as e: log_func(f"Minor error accessing finish_reason (chunk {chunk_num}): {e}", "debug")

            if block_reason:
                all_blocked = finish_reason_val == finish_reason_safety
                if all_blocked:
                    error_msg = f"Chunk {chunk_num} blocked by API. Reason: {block_reason}"
                    log_func(error_msg, level="error"); continue # Skip this chunk, not fatal for whole process
                else:
                    log_func(f"Chunk {chunk_num} had block '{block_reason}' but finish reason is '{finish_reason_val}'. Proceeding.", level="warning")

            # Parse JSON Response
            parsed_chunk_data = None
            if raw_response_text:
                try:
                    cleaned_json_string = re.sub(r'^```json\s*', '', raw_response_text, flags=re.IGNORECASE)
                    cleaned_json_string = re.sub(r'\s*```$', '', cleaned_json_string)
                    if not cleaned_json_string: log_func(f"Warning: Cleaned response text for chunk {chunk_num} is empty.", "warning")
                    else:
                        parsed_chunk_data = json.loads(cleaned_json_string)
                        if isinstance(parsed_chunk_data, list):
                            valid_items = []
                            for item in parsed_chunk_data:
                                if isinstance(item, dict) and "question" in item and "answer" in item: valid_items.append(item)
                                else: log_func(f"Skipping invalid item in chunk {chunk_num} response: {str(item)[:100]}...", "warning")
                            if valid_items:
                                all_parsed_data.extend(valid_items)
                                chunk_parsed_successfully = True # Mark success for this chunk
                                log_func(f"Successfully parsed {len(valid_items)} items from chunk {chunk_num}.", "debug")
                                temp_save_path = save_json_incrementally(all_parsed_data, output_dir, safe_base_name, "text_analysis", log_func)
                            else: log_func(f"No valid Q&A items found in chunk {chunk_num} JSON response.", "warning")
                        else: log_func(f"Parsing Error: Chunk {chunk_num} JSON is not a list.", "error")
                except json.JSONDecodeError as e:
                    log_func(f"Parsing Error: Failed to decode JSON for chunk {chunk_num}: {e}", "error")
                    log_func(f"--- Invalid Raw Response (Chunk {chunk_num}) ---\n{raw_response_text[:1000]}\n---", "debug")
                except Exception as e: log_func(f"Unexpected error parsing chunk {chunk_num} JSON: {e}", "error")

            elif not block_reason: # Empty response, no block
                 log_func(f"Warning: Received empty response text for chunk {chunk_num}.", "warning")
                 candidates_exist = hasattr(response, 'candidates') and response.candidates and response.candidates[0] is not None
                 if not candidates_exist or finish_reason_val != finish_reason_stop:
                      feedback = "N/A"
                      try: feedback = str(response.prompt_feedback) if response.prompt_feedback else "N/A"
                      except Exception: pass
                      log_func(f"Chunk {chunk_num} empty response, finish_reason={finish_reason_val}. Feedback: {feedback}. Treating as error for this chunk.", level="error")
                      # Don't set had_unrecoverable_error here, just skip the chunk

        except google.api_core.exceptions.GoogleAPIError as api_e:
            error_type = type(api_e).__name__; error_message = f"Gemini API Error (Chunk {chunk_num}): {error_type}: {api_e}"
            log_func(error_message, level="error")
            # Consider if API errors should be fatal for the whole process
            # For now, let's treat them as chunk failures
            # had_unrecoverable_error = True
            # break # Optionally stop processing further chunks on API error
        except Exception as e:
            error_message = f"Unexpected error processing chunk {chunk_num}: {type(e).__name__}: {e}"
            log_func(f"FATAL CHUNK ERROR: {error_message}\n{traceback.format_exc()}", level="error")
            # Treat unexpected errors as potentially fatal
            had_unrecoverable_error = True
            break # Stop processing further chunks

        chunk_end_time = time.time()
        log_func(f"Finished processing chunk {chunk_num}. Parsed OK: {chunk_parsed_successfully}. Time: {chunk_end_time - chunk_start_time:.2f}s", "debug")
        if chunk_num < num_chunks and api_delay > 0:
            log_func(f"Waiting {api_delay:.1f}s before next chunk...", "debug"); time.sleep(api_delay)

    log_func("Text analysis Gemini calls complete.", "info")

    if had_unrecoverable_error:
        log_func("Unrecoverable error occurred during text analysis. Returning None.", "error")
        return None

    if not all_parsed_data:
        log_func("Warning: No data was successfully extracted from any text chunk.", "warning");
        # Save empty final file to indicate completion without data
        final_save_path = save_json_incrementally([], output_dir, safe_base_name, "text_analysis_final", log_func)
        return [] # Return empty list for success with no data

    final_save_path = save_json_incrementally(all_parsed_data, output_dir, safe_base_name, "text_analysis_final", log_func)
    if final_save_path: log_func(f"Final combined results saved to {os.path.basename(final_save_path)}", "info")
    else: log_func("Error saving final combined results.", "error") # Non-fatal, return data anyway
    return all_parsed_data


# --- Modified Tagging Function ---
def tag_tsv_rows_gemini(data_rows_with_header, api_key, model_name, system_prompt,
                       batch_size, api_delay, log_func, progress_callback=None,
                       output_dir=None, base_filename=None, # Added for incremental saving
                       parent_widget=None):
    """
    Tags TSV data rows using Gemini batches. Yields tagged rows (list).
    Includes incremental saving of tagged results.
    """
    if not data_rows_with_header: log_func("No data rows provided for tagging.", "warning"); yield []; return # Yield empty list if no input
    header = data_rows_with_header[0]; data_rows = data_rows_with_header[1:]
    total_rows = len(data_rows); processed_rows_count = 0
    if total_rows == 0: log_func("No data rows (excluding header) to tag.", "warning"); yield header; return # Yield only header if no data

    total_batches = (total_rows + batch_size - 1) // batch_size
    log_func(f"Starting Gemini tagging: {total_rows} rows, {total_batches} batches.", "info")

    if not configure_gemini(api_key):
        if parent_widget: messagebox.showerror("API Error", "Failed to configure Gemini API key for tagging.", parent=parent_widget)
        else: log_func("API Error: Failed to configure Gemini API key for tagging.", "error")
        # Yield original rows with error message appended/replaced
        output_header = header[:]; tags_col_exists = "Tags" in output_header
        if not tags_col_exists: output_header.append("Tags")
        yield output_header
        for row in data_rows:
            output_row = row[:]
            error_tag = "ERROR: API Key Config Failed"
            if tags_col_exists:
                try: tags_col_index = header.index("Tags"); output_row[tags_col_index] = error_tag
                except (ValueError, IndexError): output_row.append(error_tag)
            else: output_row.append(error_tag)
            yield output_row
        return

    model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS)
    output_header = header[:]; tags_col_exists = "Tags" in output_header; tags_col_index = -1
    if tags_col_exists:
        try: tags_col_index = header.index("Tags")
        except ValueError: tags_col_exists = False
    if not tags_col_exists: output_header.append("Tags")
    yield output_header # Yield header first

    block_reason_enum = getattr(genai.types, 'BlockReason', None)
    block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
    finish_reason_enum = getattr(genai.types, 'FinishReason', None)
    finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3

    all_tagged_rows_data = [] # Accumulate only data rows for saving
    safe_base_name = sanitize_filename(base_filename) if base_filename else "tagging_output"
    temp_save_path = None

    for i in range(0, total_rows, batch_size):
        batch_start_time = time.time(); batch_num = i // batch_size + 1
        log_func(f"Tagging Batch {batch_num}/{total_batches}...", "debug")
        if progress_callback:
            progress = (processed_rows_count / total_rows) * 100 if total_rows > 0 else 0
            progress_callback(progress)

        batch = data_rows[i:min(i + batch_size, total_rows)]
        batch_prompt_content_lines = [f"[{idx + 1}] {' | '.join(map(str, row))}" for idx, row in enumerate(batch)]
        batch_prompt_content = "\n".join(batch_prompt_content_lines); tag_responses = []

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
                    if block_reason == block_reason_unspecified: block_reason = None
            except ValueError: pass
            except Exception as e: log_func(f"Minor error accessing block_reason: {e}", "debug")

            if block_reason:
                 finish_reason_val = getattr(response.candidates[0], 'finish_reason', None) if response.candidates else None
                 all_blocked = finish_reason_val == finish_reason_safety
                 if all_blocked: tag_responses = [f"ERROR: Blocked ({block_reason})" for _ in batch]; log_func(f"Batch {batch_num} blocked by API: {block_reason}", "error")
                 else: tag_responses = parse_batch_tag_response(response_text, len(batch)); log_func(f"Batch {batch_num} had block '{block_reason}' but parsed.", "warning")
            elif not response_text: tag_responses = ["ERROR: Empty Response" for _ in batch]; log_func(f"Batch {batch_num} received empty response.", "warning")
            else: tag_responses = parse_batch_tag_response(response_text, len(batch))

        except google.api_core.exceptions.GoogleAPIError as api_e:
            error_type = type(api_e).__name__; error_message = str(api_e); log_func(f"API Error batch {batch_num}: {error_type}: {error_message}", "error"); tag_responses = [f"ERROR: API Call Failed ({error_type})" for _ in batch]
        except Exception as e:
             error_type = type(e).__name__; log_func(f"Unexpected error batch {batch_num}: {error_type}: {e}\n{traceback.format_exc()}", "error"); tag_responses = [f"ERROR: Processing Failed ({error_type})" for _ in batch]

        batch_tagged_rows_data = [] # Store data rows for this batch for saving
        for row_index, row in enumerate(batch):
            tags = tag_responses[row_index] if row_index < len(tag_responses) else "ERROR: Tag Index Error"
            output_row_list = row[:]
            if tags_col_exists:
                if tags_col_index != -1 and tags_col_index < len(output_row_list): output_row_list[tags_col_index] = tags
                else: log_func(f"Warning: Could not place tag in existing column index {tags_col_index}. Appending.", "warning"); output_row_list.append(tags)
            else: output_row_list.append(tags)
            # Ensure row length matches header length before yielding
            if len(output_row_list) < len(output_header): output_row_list.extend([""] * (len(output_header) - len(output_row_list)))
            elif len(output_row_list) > len(output_header): output_row_list = output_row_list[:len(output_header)]
            yield output_row_list # Yield row immediately
            batch_tagged_rows_data.append(output_row_list) # Add to batch save list

        all_tagged_rows_data.extend(batch_tagged_rows_data) # Add batch to overall save list
        processed_rows_count += len(batch)

        # Save incrementally after each batch
        if output_dir and base_filename:
            rows_to_save = [output_header] + all_tagged_rows_data # Add header for saving
            temp_save_path = save_tsv_incrementally(rows_to_save, output_dir, safe_base_name, "tagging", log_func)

        batch_end_time = time.time()
        log_func(f"Batch {batch_num} tagged. Time: {batch_end_time - batch_start_time:.2f}s", "debug")
        if i + batch_size < total_rows and api_delay > 0:
            log_func(f"Waiting {api_delay:.1f}s...", "debug"); time.sleep(api_delay)

    if progress_callback: progress_callback(100); log_func("Gemini tagging finished.", "info")


# --- NEW Helper for Incremental TSV Saving ---
def save_tsv_incrementally(rows_list, output_dir, base_filename, step_name, log_func):
    """Saves the current list of rows (including header) to a temporary TSV file."""
    if not rows_list: return None
    temp_filename = f"{base_filename}_{step_name}_temp_results.tsv"; temp_filepath = os.path.join(output_dir, temp_filename)
    try:
        with open(temp_filepath, 'w', encoding='utf-8', newline='') as f:
            for row in rows_list: f.write("\t".join(map(str, row)) + "\n")
        # Reduce verbosity of incremental saves unless debugging
        # log_func(f"Saved intermediate {step_name} results ({len(rows_list)-1} data rows) to {temp_filename}", "debug")
        return temp_filepath
    except Exception as e: log_func(f"Error saving intermediate {step_name} TSV results to {temp_filepath}: {e}", "error"); return None

def cleanup_gemini_file(uploaded_file_uri, api_key, log_func):
    """Deletes a file previously uploaded to Gemini."""
    if not uploaded_file_uri: return
    log_func(f"Attempting to clean up uploaded file: {uploaded_file_uri}", "info")
    try:
        if not configure_gemini(api_key): log_func("Cleanup failed: Could not configure API key.", "warning"); return
        # Extract the file ID part from the URI (e.g., 'files/abc123def')
        file_name_to_delete = uploaded_file_uri
        if '/' in file_name_to_delete: file_name_to_delete = file_name_to_delete.split('/')[-1]
        # Use the correct format for deletion: 'files/file_id'
        genai.delete_file(name=f"files/{file_name_to_delete}")
        log_func(f"Successfully deleted Gemini file: {file_name_to_delete}", "info")
    except Exception as delete_e: log_func(f"Cleanup failed for '{uploaded_file_uri}': {delete_e}", "warning")

