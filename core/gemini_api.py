# core/gemini_api.py
import google.generativeai as genai
import google.api_core.exceptions
import json
import time
import re
import traceback
import os  # Added for os.path.basename, path.join
from tkinter import messagebox  # For showing API errors directly if needed
import math  # For calculating text chunks

# Use relative imports (PRIMARY)
try:
    from ..constants import GEMINI_SAFETY_SETTINGS
    from ..utils.helpers import ProcessingError, sanitize_filename, save_tsv_incrementally
    from ..prompts import BATCH_TAGGING  # Import BATCH_TAGGING prompt
# Fallback imports using relative paths (SECONDARY)
except ImportError:
    print("Error: Relative imports failed in gemini_api.py. Using fallback relative imports.")
    # Use .. to go up one level from core to the main package directory
    from ..constants import GEMINI_SAFETY_SETTINGS # Changed to relative
    from ..utils.helpers import ProcessingError, sanitize_filename, save_tsv_incrementally # Changed to relative
    try:
        from ..prompts import BATCH_TAGGING # Changed to relative
    except ImportError:
        print("CRITICAL ERROR: Could not import BATCH_TAGGING prompt for tag extraction.")
        BATCH_TAGGING = ""  # fallback so that name is defined


# --- UPDATED _extract_allowed_tags_from_prompt function ---
def _extract_allowed_tags_from_prompt(prompt_string):
    """
    Parses the BATCH_TAGGING prompt string to extract all allowed tags.

    Args:
        prompt_string (str): The BATCH_TAGGING prompt content.

    Returns:
        set: A set containing all unique allowed tags (strings starting with '#').
    """
    allowed_tags = set()
    # Find all blocks enclosed in {} first
    brace_blocks = re.findall(r'\{([^{}]*?)\}', prompt_string, re.DOTALL)
    for block_content in brace_blocks:
        # Updated regex: captures tags with letters, digits, underscores, colons, or hyphens
        tags_in_block = re.findall(r'(#[A-Za-z0-9_:\-]+)', block_content)
        for tag in tags_in_block:
            if tag.startswith('#') and len(tag) > 1:
                allowed_tags.add(tag.strip())
    if not allowed_tags:
        print("WARNING: No allowed tags extracted from the BATCH_TAGGING prompt. Filtering will remove all tags.")
        # Fallback: use same refined regex on the entire prompt_string
        fallback_tags = re.findall(r'(#[A-Za-z0-9_:\-]+)', prompt_string)
        for tag in fallback_tags:
            if tag.startswith('#') and len(tag) > 1:
                allowed_tags.add(tag.strip())
        if allowed_tags:
            print("INFO: Using fallback tags found outside of {} blocks.")
    return allowed_tags


# Create a global set of allowed tags on module load
ALLOWED_TAGS_SET = _extract_allowed_tags_from_prompt(BATCH_TAGGING)
if not ALLOWED_TAGS_SET:
    print("CRITICAL WARNING: ALLOWED_TAGS_SET is empty after initialization!")

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
        return True
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        return False


# --- Modified parse_batch_tag_response function ---
def parse_batch_tag_response(response_text, batch_size):
    """
    Parses Gemini's numbered list response to extract tags AND filters
    them against the globally defined ALLOWED_TAGS_SET.
    """
    global ALLOWED_TAGS_SET
    if not ALLOWED_TAGS_SET:
        print("ERROR: ALLOWED_TAGS_SET is empty. Cannot filter tags.")
        return [f"ERROR: Allowed Tag List Empty" for _ in range(batch_size)]

    tags_list = [f"ERROR: No Response Parsed" for _ in range(batch_size)]
    lines = response_text.strip().split('\n')
    parsed_count = 0
    item_num = -1  # Initialize item_num to handle potential NameError

    # print(f"DEBUG: Filtering against {len(ALLOWED_TAGS_SET)} allowed tags.")  # Optional debug
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^\s*\[\s*(\d+)\s*\]\s*(.*)$', line)
        if match:
            try:
                item_num = int(match.group(1)) - 1
                raw_tags_string = match.group(2).strip()
                # --- Filtering Logic ---
                if raw_tags_string:
                    suggested_tags = raw_tags_string.split()  # Split by whitespace
                    filtered_tags = [tag for tag in suggested_tags if tag in ALLOWED_TAGS_SET]
                    final_tags_string = " ".join(filtered_tags)
                else:
                    final_tags_string = ""
                # --- End Filtering Logic ---
                if 0 <= item_num < batch_size:
                    # Store the filtered tags, or a specific message if filtering removed everything
                    tags_list[item_num] = final_tags_string if final_tags_string else "INFO: No Valid Tags Found"
                    parsed_count += 1
                else:
                    print(f"[Tag Parser] Warning: Item number {item_num + 1} out of range ({batch_size}). Line: '{line}'")
            except ValueError:
                print(f"[Tag Parser] Warning: Cannot parse number: '{line}'")
                if 0 <= item_num < batch_size:
                    tags_list[item_num] = "ERROR: Parsing Failed (ValueError)"
            except Exception as e:
                print(f"[Tag Parser] Error processing line '{line}': {e}")
                if 0 <= item_num < batch_size:
                    tags_list[item_num] = "ERROR: Parsing Failed (Exception)"
        else:
            print(f"[Tag Parser] Warning: Line format mismatch: '{line}'")
            # Attempt to mark the last valid item_num as error if format mismatch occurs
            if 0 <= item_num < batch_size and tags_list[item_num] == "ERROR: No Response Parsed":
                tags_list[item_num] = "ERROR: Parsing Failed (Format Mismatch)"

    if parsed_count != batch_size:
        print(f"[Tag Parser] Warning: Parsed {parsed_count}/{batch_size} items. Check output.")
        for i in range(batch_size):
            if tags_list[i] == "ERROR: No Response Parsed":
                tags_list[i] = "ERROR: Parsing Mismatch/Incomplete"
    return tags_list


# --- Helper for Incremental Saving (JSON) ---
def save_json_incrementally(data_list, output_dir, base_filename, step_name, log_func):
    """Saves the current list of parsed JSON objects to a temporary file."""
    if not data_list:
        return None  # Don't save if empty

    temp_filename = f"{base_filename}_{step_name}_temp_results.json"
    temp_filepath = os.path.join(output_dir, temp_filename)
    try:
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, indent=2)  # Save as a standard JSON array
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
        if parent_widget:
            messagebox.showerror("API Error", "Failed to configure Gemini API key.", parent=parent_widget)
        else:
            log_func("API Error: Failed to configure Gemini API key.", "error")
        return None, None

    uploaded_file = None
    uploaded_file_uri = None
    all_parsed_objects = None
    block_reason = None
    temp_save_path = None
    output_dir = os.path.dirname(pdf_path) or os.getcwd()
    safe_base_name = sanitize_filename(os.path.basename(pdf_path))

    generation_config = genai.GenerationConfig(response_mime_type="application/json")

    try:
        log_func(f"Uploading PDF '{os.path.basename(pdf_path)}'...", "upload")
        upload_start_time = time.time()
        display_name = f"visual-extract-{os.path.basename(pdf_path)}-{time.time()}"
        uploaded_file = genai.upload_file(path=pdf_path, display_name=display_name)
        uploaded_file_uri = uploaded_file.name
        upload_duration = time.time() - upload_start_time
        log_func(f"PDF uploaded successfully ({upload_duration:.1f}s). URI: {uploaded_file_uri}", "info")

        model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS, generation_config=generation_config)
        log_func(f"Sending JSON extraction request to Gemini ({model_name})...", "info")
        api_start_time = time.time()
        response = model.generate_content([prompt_text, uploaded_file])
        api_duration = time.time() - api_start_time
        log_func(f"Received response from Gemini ({api_duration:.1f}s).", "info")

        # --- Process Response ---
        json_string = None
        try:
            json_string = response.text
            log_func(f"Attempting to parse JSON response (length {len(json_string) if json_string else 0})...", "debug")
            if json_string:
                try:
                    parsed_data = json.loads(json_string)
                    if isinstance(parsed_data, list):
                        all_parsed_objects = parsed_data
                        log_func(f"Successfully parsed entire JSON response ({len(all_parsed_objects)} items).", "info")
                        temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                    else:
                        log_func("Parsing Error: Parsed JSON is not a list.", "error")
                        all_parsed_objects = None
                except json.JSONDecodeError as e:
                    log_func(f"Initial JSON parsing failed: {e}. Raw snippet:\n{json_string[:1000]}", "error")
                    cleaned_json_string = re.sub(r'^```json\s*', '', json_string.strip(), flags=re.IGNORECASE)
                    cleaned_json_string = re.sub(r'\s*```$', '', cleaned_json_string)
                    if cleaned_json_string != json_string:
                        log_func("Retrying parse after stripping markdown...", "warning")
                        try:
                            parsed_data = json.loads(cleaned_json_string)
                            if isinstance(parsed_data, list):
                                all_parsed_objects = parsed_data
                                log_func(f"Successfully parsed after stripping markdown ({len(all_parsed_objects)} items).", "info")
                                temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                            else:
                                log_func("Parsing Error: Stripped JSON is not a list.", "error")
                                all_parsed_objects = None
                        except json.JSONDecodeError as e2:
                            log_func(f"Parsing failed even after stripping: {e2}", "error")
                            all_parsed_objects = None
                    else:
                        all_parsed_objects = None
            else:
                log_func("Warning: Received empty response text.", "warning")
                all_parsed_objects = []
        except AttributeError:
            log_func("Parsing Error: Could not access response text (blocked?).", "error")
            log_func(f"Full Response: {response}", "debug")
            all_parsed_objects = None
        except Exception as e:
            log_func(f"Unexpected error processing response text: {e}\n{traceback.format_exc()}", "error")
            all_parsed_objects = None

        # Check blocking reasons AFTER trying to parse
        try:
            block_reason_enum = getattr(genai.types, 'BlockReason', None)
            block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
            if response.prompt_feedback:
                block_reason = response.prompt_feedback.block_reason
            if block_reason == block_reason_unspecified:
                block_reason = None
        except ValueError:
            log_func("Minor error ignored during attribute access (ValueError).", "debug")  # Linter Fix
        except Exception as e:
            log_func(f"Minor error accessing block_reason: {e}", "debug")

        finish_reason_val = None
        finish_reason_enum = getattr(genai.types, 'FinishReason', None)
        finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3
        try:
            if response.candidates:
                finish_reason_val = response.candidates[0].finish_reason
                log_func(f"Gemini finish reason: {finish_reason_val}", "debug")
        except Exception as e:
            log_func(f"Minor error accessing finish_reason: {e}", "debug")

        if block_reason:
            all_blocked = finish_reason_val == finish_reason_safety
            error_msg = f"Request blocked by API. Reason: {block_reason}" # Define error_msg here
            if all_blocked:
                log_func(error_msg, level="error")
                if parent_widget:
                    messagebox.showerror("API Error", error_msg, parent=parent_widget)
                return None, uploaded_file_uri # Return None on block
            else:
                log_func(f"Safety block '{block_reason}' present, but finish reason is '{finish_reason_val}'. Proceeding.", "warning")


        if all_parsed_objects is None and not block_reason:
            feedback = "N/A"
            try:
                feedback = str(response.prompt_feedback) if response.prompt_feedback else "N/A"
            except Exception:
                pass
            log_func(f"API call finished, but JSON parsing failed. Finish={finish_reason_val}. Feedback: {feedback}. Treating as error.", level="error")
            return None, uploaded_file_uri

        log_func("Gemini Visual JSON extraction step complete.", "info")
        # Ensure we return an empty list if no objects were parsed but no error occurred
        return all_parsed_objects if all_parsed_objects is not None else [], uploaded_file_uri


    except google.api_core.exceptions.GoogleAPIError as api_e:
        error_type = type(api_e).__name__
        error_message = f"Gemini API Error (Visual): {error_type}: {api_e}"
        log_func(error_message, level="error")
        if parent_widget:
            messagebox.showerror("API Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri # Return None on API error
    except FileNotFoundError:
        error_message = f"Input PDF not found: {pdf_path}"
        log_func(error_message, level="error")
        if parent_widget:
            messagebox.showerror("File Error", error_message, parent=parent_widget)
        return None, None # Return None, None if file not found
    except Exception as e:
        error_message = f"Unexpected error during Gemini visual call: {type(e).__name__}: {e}"
        log_func(f"FATAL API ERROR (Visual): {error_message}\n{traceback.format_exc()}", "error")
        if parent_widget:
            messagebox.showerror("Unexpected Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri # Return None on other errors

# --- Modified Text Analysis ---
def call_gemini_text_analysis(
    text_content,
    api_key,
    model_name,
    prompt,
    log_func,
    output_dir,
    base_filename,
    chunk_size=30000,
    api_delay=5.0,
    parent_widget=None,
):
    """
    Calls Gemini with plain text content, processing in chunks. Saves results incrementally.
    Returns the final list of parsed JSON objects or None.
    """
    log_func(f"Processing text content with Gemini ({model_name}) in chunks...", "info")
    if not configure_gemini(api_key):
        if parent_widget:
            messagebox.showerror("API Error", "Failed to configure Gemini API key.", parent=parent_widget)
        else:
            log_func("API Error: Failed to configure Gemini API key.", "error")
        return None

    all_parsed_data = []
    temp_save_path = None
    safe_base_name = sanitize_filename(base_filename)
    had_unrecoverable_error = False
    total_len = len(text_content)
    num_chunks = math.ceil(total_len / chunk_size)
    log_func(f"Splitting text ({total_len} chars) into ~{num_chunks} chunks of size {chunk_size}.", "debug")
    block_reason_enum = getattr(genai.types, 'BlockReason', None)
    block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
    finish_reason_enum = getattr(genai.types, 'FinishReason', None)
    finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3
    finish_reason_stop = getattr(finish_reason_enum, 'STOP', 1) if finish_reason_enum else 1

    generation_config = genai.GenerationConfig(response_mime_type="application/json")
    model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS, generation_config=generation_config)

    for i in range(num_chunks):
        chunk_start_time = time.time()
        chunk_num = i + 1
        start_index = i * chunk_size
        end_index = min((i + 1) * chunk_size, total_len)
        chunk_text = text_content[start_index:end_index]
        log_func(f"Processing chunk {chunk_num}/{num_chunks} ({len(chunk_text)} chars)...", "info")
        if not chunk_text.strip():
            log_func(f"Skipping empty chunk {chunk_num}.", "debug")
            continue

        chunk_parsed_successfully = False
        try:
            # Simplified prompt structure for text-only model
            full_prompt = f"{prompt}\n\n--- Text Chunk ---\n{chunk_text}"
            log_func(f"Sending chunk {chunk_num} analysis request...", "debug")
            api_start_time = time.time()
            # Use generate_content directly with text
            response = model.generate_content(full_prompt, generation_config=generation_config)
            api_duration = time.time() - api_start_time
            log_func(f"Received response for chunk {chunk_num} ({api_duration:.1f}s).", "debug")

            raw_response_text = ""
            try:
                if hasattr(response, 'text'):
                    raw_response_text = response.text.strip()
                elif hasattr(response, 'parts') and response.parts:
                    raw_response_text = "".join(part.text for part in response.parts if hasattr(part, 'text')).strip()
            except ValueError as e:
                log_func(f"Error accessing response text/parts (chunk {chunk_num}): {e}. Response: {response}", "warning")
            except Exception as e:
                log_func(f"Could not extract text from response (chunk {chunk_num}): {e}", "warning")

            block_reason = None
            try:
                if response.prompt_feedback:
                    block_reason = response.prompt_feedback.block_reason
                if block_reason == block_reason_unspecified:
                    block_reason = None
            except ValueError:
                log_func("Minor error ignored during attribute access (ValueError).", "debug")  # Linter Fix
            except Exception as e:
                log_func(f"Minor error accessing block_reason (chunk {chunk_num}): {e}", "debug")
            finish_reason_val = None
            try:
                if response.candidates:
                    finish_reason_val = response.candidates[0].finish_reason
                    log_func(f"Chunk {chunk_num} finish reason: {finish_reason_val}", "debug")
            except Exception as e:
                log_func(f"Minor error accessing finish_reason (chunk {chunk_num}): {e}", "debug")

            if block_reason:
                all_blocked = finish_reason_val == finish_reason_safety
                error_msg = f"Chunk {chunk_num} blocked by API. Reason: {block_reason}" # Define error_msg
                if all_blocked:
                    log_func(error_msg, level="error")
                    continue # Skip this chunk on block
                else:
                    log_func(f"Chunk {chunk_num} had block '{block_reason}' but finish reason is '{finish_reason_val}'. Proceeding.", "warning")


            parsed_chunk_data = None
            if raw_response_text:
                try:
                    cleaned_json_string = re.sub(r'^```json\s*', '', raw_response_text, flags=re.IGNORECASE)
                    cleaned_json_string = re.sub(r'\s*```$', '', cleaned_json_string)
                    if not cleaned_json_string:
                        log_func(f"Warning: Cleaned response for chunk {chunk_num} is empty.", "warning")
                    else:
                        parsed_chunk_data = json.loads(cleaned_json_string)
                        if isinstance(parsed_chunk_data, list):
                            valid_items = []
                            for item in parsed_chunk_data:
                                if isinstance(item, dict) and "question" in item and "answer" in item:
                                    valid_items.append(item)
                                else:
                                    log_func(f"Skipping invalid item in chunk {chunk_num}: {str(item)[:100]}...", "warning")
                            if valid_items:
                                all_parsed_data.extend(valid_items)
                                chunk_parsed_successfully = True
                                log_func(f"Parsed {len(valid_items)} items from chunk {chunk_num}.", "debug")
                                temp_save_path = save_json_incrementally(all_parsed_data, output_dir, safe_base_name, "text_analysis", log_func)
                            else:
                                log_func(f"No valid Q&A items found in chunk {chunk_num} JSON.", "warning")
                        else:
                            log_func(f"Parsing Error: Chunk {chunk_num} JSON is not a list.", "error")
                except json.JSONDecodeError as e:
                    log_func(f"Parsing Error: Failed JSON decode chunk {chunk_num}: {e}", "error")
                    log_func(f"--- Invalid Raw Response (Chunk {chunk_num}) ---\n{raw_response_text[:1000]}\n---", "debug")
                except Exception as e:
                    log_func(f"Unexpected error parsing chunk {chunk_num} JSON: {e}", "error")
            elif not block_reason: # Only log empty response as error if not blocked
                log_func(f"Warning: Received empty response text for chunk {chunk_num}.", "warning")
                candidates_exist = hasattr(response, 'candidates') and response.candidates and response.candidates[0] is not None
                if not candidates_exist or finish_reason_val != finish_reason_stop:
                    feedback = "N/A"
                    try:
                        feedback = str(response.prompt_feedback) if response.prompt_feedback else "N/A"
                    except Exception:
                        pass
                    log_func(f"Chunk {chunk_num} empty response, finish={finish_reason_val}. Feedback: {feedback}. Treating as error.", "error")


        except google.api_core.exceptions.GoogleAPIError as api_e:
            error_type = type(api_e).__name__
            error_message = f"Gemini API Error (Chunk {chunk_num}): {error_type}: {api_e}"
            log_func(error_message, level="error")
            # Decide if this is recoverable or not. For now, let's try to continue.
            # If it's a rate limit error, the delay might help next time.
            # If it's auth, it will likely fail again.
            if "rate limit" not in str(api_e).lower():
                 had_unrecoverable_error = True
                 break # Stop processing chunks on non-rate-limit API errors
        except Exception as e:
            error_message = f"Unexpected error processing chunk {chunk_num}: {type(e).__name__}: {e}"
            log_func(f"FATAL CHUNK ERROR: {error_message}\n{traceback.format_exc()}", "error")
            had_unrecoverable_error = True
            break # Stop processing chunks on unexpected errors

        chunk_end_time = time.time()
        log_func(f"Finished chunk {chunk_num}. Parsed OK: {chunk_parsed_successfully}. Time: {chunk_end_time - chunk_start_time:.2f}s", "debug")
        if chunk_num < num_chunks and api_delay > 0:
            log_func(f"Waiting {api_delay:.1f}s...", "debug")
            time.sleep(api_delay)

    log_func("Text analysis Gemini calls complete.", "info")
    if had_unrecoverable_error:
        log_func("Unrecoverable error occurred. Returning None.", "error")
        return None
    if not all_parsed_data:
        log_func("Warning: No data extracted from any text chunk.", "warning")
        final_save_path = save_json_incrementally([], output_dir, safe_base_name, "text_analysis_final", log_func)
        return [] # Return empty list if no data but no fatal error
    final_save_path = save_json_incrementally(all_parsed_data, output_dir, safe_base_name, "text_analysis_final", log_func)
    if final_save_path:
        log_func(f"Final combined results saved to {os.path.basename(final_save_path)}", "info")
    else:
        log_func("Error saving final combined results.", "error")
    return all_parsed_data


# --- REFACTORED Tagging Function (Two-Pass Logic) ---
def tag_tsv_rows_gemini(data_rows_with_header, api_key, model_name_pass1, system_prompt_pass1,
                       batch_size, api_delay, log_func, progress_callback=None,
                       output_dir=None, base_filename=None,  # Added for incremental saving
                       parent_widget=None,
                       # --- NEW PARAMETERS ---
                       enable_second_pass=False,
                       second_pass_model_name=None,
                       second_pass_prompt=None):
    """
    Tags TSV data rows using Gemini batches, optionally using a second pass.
    Yields tagged rows (list). Includes incremental saving.
    """
    if not data_rows_with_header:
        log_func("No data rows provided for tagging.", "warning")
        yield []
        return
    header = data_rows_with_header[0]
    data_rows = data_rows_with_header[1:]
    total_rows = len(data_rows)
    processed_rows_count = 0
    if total_rows == 0:
        log_func("No data rows (excluding header) to tag.", "warning")
        yield header
        return

    total_passes = 2 if enable_second_pass else 1
    total_batches = (total_rows + batch_size - 1) // batch_size
    total_api_calls = total_batches * total_passes
    current_api_call = 0

    log_func(f"Starting Gemini tagging: {total_rows} rows, {total_batches} batches per pass. Total Passes: {total_passes}", "info")

    # Configure Gemini API Key
    if not configure_gemini(api_key):
        if parent_widget: messagebox.showerror("API Error", "Failed to configure Gemini API key for tagging.", parent=parent_widget)
        else: log_func("API Error: Failed to configure Gemini API key for tagging.", "error")
        # Yield original rows with error message
        output_header = header[:]
        tags_col_exists = "Tags" in output_header
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

    # Use consistent safety settings
    safety_settings = GEMINI_SAFETY_SETTINGS

    # --- Sanitize base filename ---
    safe_base_name = sanitize_filename(base_filename) if base_filename else None

    # --- Initialize Models ---
    try:
        model_pass1 = genai.GenerativeModel(model_name_pass1, safety_settings=safety_settings)
        log_func(f"Pass 1 model '{model_name_pass1}' initialized.", "info")
    except Exception as e:
        log_func(f"FATAL: Error initializing Pass 1 model '{model_name_pass1}': {e}. Cannot proceed.", "error")
        # Yield error rows if model init fails
        output_header = header[:]
        tags_col_exists = "Tags" in output_header
        if not tags_col_exists: output_header.append("Tags")
        yield output_header
        for row in data_rows:
            output_row = row[:]
            error_tag = f"ERROR: Model Init Failed ({model_name_pass1})"
            if tags_col_exists:
                try: tags_col_index = header.index("Tags"); output_row[tags_col_index] = error_tag
                except (ValueError, IndexError): output_row.append(error_tag)
            else: output_row.append(error_tag)
            yield output_row
        return

    model_pass2 = None
    if enable_second_pass and second_pass_model_name and second_pass_prompt:
        try:
            model_pass2 = genai.GenerativeModel(second_pass_model_name, safety_settings=safety_settings)
            log_func(f"Pass 2 model '{second_pass_model_name}' initialized.", "info")
        except Exception as e:
            log_func(f"Error initializing Pass 2 model '{second_pass_model_name}': {e}. Disabling second pass.", "error")
            enable_second_pass = False
            model_pass2 = None
            total_passes = 1 # Update total passes
            total_api_calls = total_batches # Update total API calls
    elif enable_second_pass:
        log_func("Second pass enabled but model name or prompt is missing. Disabling second pass.", "warning")
        enable_second_pass = False
        total_passes = 1
        total_api_calls = total_batches

    # --- Prepare Output Header ---
    output_header = header[:]
    tags_col_exists = "Tags" in output_header
    tags_col_index = -1
    if tags_col_exists:
        try: tags_col_index = header.index("Tags")
        except ValueError: tags_col_exists = False
    if not tags_col_exists:
        output_header.append("Tags")
        tags_col_index = len(output_header) - 1 # It's the last column now
    yield output_header  # Yield header first

    # --- Get Block/Finish Reason Enums ---
    block_reason_enum = getattr(genai.types, 'BlockReason', None)
    block_reason_unspecified = getattr(block_reason_enum, 'BLOCK_REASON_UNSPECIFIED', 0) if block_reason_enum else 0
    finish_reason_enum = getattr(genai.types, 'FinishReason', None)
    finish_reason_safety = getattr(finish_reason_enum, 'SAFETY', 3) if finish_reason_enum else 3

    # --- Process Data in Batches ---
    current_pass_data = data_rows # Start with original data for Pass 1
    final_tagged_rows = [] # Store results after all passes

    for pass_num in range(1, total_passes + 1):
        log_func(f"--- Starting Tagging Pass {pass_num}/{total_passes} ---", "info")
        pass_model = model_pass1 if pass_num == 1 else model_pass2
        pass_prompt = system_prompt_pass1 if pass_num == 1 else second_pass_prompt
        pass_output_data = [] # Store results of the current pass
        pass_total_rows = len(current_pass_data)
        pass_total_batches = (pass_total_rows + batch_size - 1) // batch_size
        pass_processed_rows = 0

        if not pass_model or not pass_prompt:
            log_func(f"Skipping Pass {pass_num} due to missing model or prompt.", "warning")
            pass_output_data = current_pass_data # Pass through data if pass skipped
            continue # Go to next pass or finish

        for i in range(pass_total_batches):
            batch_start_index = i * batch_size
            batch_end_index = min((i + 1) * batch_size, pass_total_rows)
            batch_data = current_pass_data[batch_start_index:batch_end_index]
            current_batch_size = len(batch_data)
            batch_num = i + 1
            log_func(f"Pass {pass_num}, Batch {batch_num}/{pass_total_batches} ({current_batch_size} rows)...", "info")

            # --- Prepare Batch Input ---
            batch_input_text = ""
            original_indices = list(range(batch_start_index, batch_end_index)) # Track original index if needed
            for j, row in enumerate(batch_data):
                # Construct input based on header (assuming Q/A are first cols, or find them)
                # This assumes Q/A are the first two columns, adjust if needed
                question = row[0] if len(row) > 0 else ""
                answer = row[1] if len(row) > 1 else ""
                initial_tags = ""
                if pass_num == 2 and tags_col_exists and tags_col_index < len(row):
                    initial_tags = row[tags_col_index] # Get tags from Pass 1

                # Format for the prompt (adjust based on actual prompt needs)
                if pass_num == 1:
                     batch_input_text += f"[{j+1}] Q: {question}\nA: {answer}\n\n"
                else: # Pass 2 includes initial tags
                     batch_input_text += f"[{j+1}] Q: {question}\nA: {answer}\nInitial Tags: {initial_tags}\n\n"

            # --- Call Gemini ---
            current_api_call += 1
            tags_for_batch = [f"ERROR: API Call Failed (Pass {pass_num})" for _ in range(current_batch_size)] # Default error
            try:
                full_prompt_for_batch = f"{pass_prompt}\n\n--- Batch Items ---\n{batch_input_text}"
                log_func(f"Sending Pass {pass_num}, Batch {batch_num} request...", "debug")
                api_start_time = time.time()
                response = pass_model.generate_content(full_prompt_for_batch)
                api_duration = time.time() - api_start_time
                log_func(f"Received Pass {pass_num}, Batch {batch_num} response ({api_duration:.1f}s).", "debug")

                # --- Process Response ---
                raw_response_text = ""
                try:
                    if hasattr(response, 'text'): raw_response_text = response.text.strip()
                    elif hasattr(response, 'parts') and response.parts: raw_response_text = "".join(part.text for part in response.parts if hasattr(part, 'text')).strip()
                except Exception as e: log_func(f"Could not extract text from response (Pass {pass_num}, Batch {batch_num}): {e}", "warning")

                block_reason = None
                try:
                    if response.prompt_feedback: block_reason = response.prompt_feedback.block_reason
                    if block_reason == block_reason_unspecified: block_reason = None
                except Exception as e: log_func(f"Minor error accessing block_reason (Pass {pass_num}, Batch {batch_num}): {e}", "debug")

                finish_reason_val = None
                try:
                    if response.candidates: finish_reason_val = response.candidates[0].finish_reason
                except Exception as e: log_func(f"Minor error accessing finish_reason (Pass {pass_num}, Batch {batch_num}): {e}", "debug")

                if block_reason:
                    all_blocked = finish_reason_val == finish_reason_safety
                    error_msg = f"Pass {pass_num}, Batch {batch_num} blocked by API. Reason: {block_reason}"
                    if all_blocked:
                        log_func(error_msg, level="error")
                        tags_for_batch = [f"ERROR: Blocked by API ({block_reason})" for _ in range(current_batch_size)]
                    else:
                        log_func(f"Pass {pass_num}, Batch {batch_num} had block '{block_reason}' but finish reason is '{finish_reason_val}'. Parsing response.", "warning")
                        # Attempt parsing even if partially blocked
                        if raw_response_text: tags_for_batch = parse_batch_tag_response(raw_response_text, current_batch_size)
                        else: tags_for_batch = [f"ERROR: Partially Blocked & Empty Text" for _ in range(current_batch_size)]
                elif raw_response_text:
                    tags_for_batch = parse_batch_tag_response(raw_response_text, current_batch_size)
                else:
                    log_func(f"Warning: Received empty response text for Pass {pass_num}, Batch {batch_num}.", "warning")
                    tags_for_batch = [f"ERROR: Empty Response (Pass {pass_num})" for _ in range(current_batch_size)]

            except google.api_core.exceptions.GoogleAPIError as api_e:
                error_type = type(api_e).__name__
                error_message = f"Gemini API Error (Pass {pass_num}, Batch {batch_num}): {error_type}: {api_e}"
                log_func(error_message, level="error")
                tags_for_batch = [f"ERROR: API Call Failed ({error_type})" for _ in range(current_batch_size)]
            except Exception as e:
                error_message = f"Unexpected error processing Pass {pass_num}, Batch {batch_num}: {type(e).__name__}: {e}"
                log_func(f"FATAL BATCH ERROR: {error_message}\n{traceback.format_exc()}", "error")
                tags_for_batch = [f"ERROR: Unexpected ({type(e).__name__})" for _ in range(current_batch_size)]

            # --- Update Rows with Tags ---
            for j, original_row in enumerate(batch_data):
                output_row = original_row[:] # Make a copy
                new_tags = tags_for_batch[j] if j < len(tags_for_batch) else "ERROR: Tag Index Mismatch"

                if tags_col_exists:
                    if tags_col_index < len(output_row):
                        output_row[tags_col_index] = new_tags # Overwrite/set tags
                    else:
                        # Handle case where row is shorter than expected header
                        output_row.extend([""] * (tags_col_index - len(output_row) + 1))
                        output_row[tags_col_index] = new_tags
                else:
                    output_row.append(new_tags) # Append if Tags col didn't exist

                pass_output_data.append(output_row)
                pass_processed_rows += 1

            # --- Update Progress ---
            if progress_callback:
                overall_progress = (current_api_call / total_api_calls) * 100
                try:
                    progress_callback(overall_progress) # Use the calculated overall progress
                except Exception as p_e:
                    log_func(f"Error in progress callback: {p_e}", "warning")

            # --- Incremental Save (after each batch of the current pass) ---
            if output_dir and safe_base_name: # Use safe_base_name here
                 # Save header + all processed rows so far in this pass
                 save_tsv_incrementally([output_header] + pass_output_data, output_dir, safe_base_name, f"pass{pass_num}", log_func)

            # --- API Delay ---
            if i < pass_total_batches - 1 and api_delay > 0:
                log_func(f"Waiting {api_delay:.1f}s...", "debug")
                time.sleep(api_delay)

        # --- End of Batch Loop for Current Pass ---
        current_pass_data = pass_output_data # Use the output of this pass as input for the next
        log_func(f"--- Finished Tagging Pass {pass_num}/{total_passes} ---", "info")

    # --- End of Pass Loop ---
    final_tagged_rows = current_pass_data # The result after all passes

    # --- Yield Final Tagged Rows ---
    for final_row in final_tagged_rows:
        yield final_row

    log_func(f"Gemini tagging process complete. Processed {total_rows} rows.", "info")


def cleanup_gemini_file(file_name_uri, api_key, log_func):
    """Deletes an uploaded file from Gemini."""
    if not file_name_uri:
        return
    if not configure_gemini(api_key):
        log_func("Cleanup Error: Failed to configure API key.", "error")
        return
    try:
        log_func(f"Attempting to delete uploaded file: {file_name_uri}", "debug")
        genai.delete_file(file_name_uri)
        log_func(f"Successfully deleted file: {file_name_uri}", "info")
    except Exception as e:
        log_func(f"Error deleting file {file_name_uri}: {e}", "warning")
