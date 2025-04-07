# core/gemini_api.py
import google.generativeai as genai
import google.api_core.exceptions
import json
import time
import re
import traceback
import os
from tkinter import messagebox
import math

# Use relative imports ONLY
from ..constants import GEMINI_SAFETY_SETTINGS
from ..utils.helpers import ProcessingError, sanitize_filename, save_tsv_incrementally
from ..prompts import BATCH_TAGGING, SECOND_PASS_TAGGING


# --- UPDATED _extract_allowed_tags_from_prompt function ---
def _extract_allowed_tags_from_prompt(prompt_string):
    """Parses the BATCH_TAGGING prompt string to extract all allowed tags."""
    allowed_tags = set()
    # Find content within {} blocks
    brace_blocks = re.findall(r'\{([^{}]*?)\}', prompt_string, re.DOTALL)
    if not brace_blocks:
        print("WARNING: No {} blocks found in prompt for tag extraction. Searching entire prompt.")
        # Fallback: search the entire prompt if no blocks found
        tags_in_block = re.findall(r'(#[A-Za-z0-9_:\-]+)', prompt_string)
        for tag in tags_in_block:
             if tag.startswith('#') and len(tag) > 1:
                 allowed_tags.add(tag.strip())
    else:
        # Process content within each block
        for block_content in brace_blocks:
            tags_in_block = re.findall(r'(#[A-Za-z0-9_:\-]+)', block_content)
            for tag in tags_in_block:
                if tag.startswith('#') and len(tag) > 1:
                    allowed_tags.add(tag.strip())

    if not allowed_tags:
        print("CRITICAL WARNING: No allowed tags extracted. Filtering will remove all tags.")
        # As a last resort, maybe try finding any '#' tags if blocks failed
        fallback_tags = re.findall(r'(#[A-Za-z0-9_:\-]+)', prompt_string)
        for tag in fallback_tags:
            if tag.startswith('#') and len(tag) > 1:
                allowed_tags.add(tag.strip())
        if allowed_tags:
            print("INFO: Using fallback tags found anywhere in the prompt.")

    print(f"INFO: Extracted {len(allowed_tags)} allowed tags.")
    # print(f"DEBUG: Allowed tags: {allowed_tags}") # Uncomment for debugging
    return allowed_tags


# Extract tags when the module loads
ALLOWED_TAGS_SET = _extract_allowed_tags_from_prompt(BATCH_TAGGING)
# Use Pass 1 prompt as fallback if Pass 2 is dummy/empty or fails extraction
ALLOWED_TAGS_SET_PASS_2 = _extract_allowed_tags_from_prompt(SECOND_PASS_TAGGING) if SECOND_PASS_TAGGING else ALLOWED_TAGS_SET

if not ALLOWED_TAGS_SET:
    print("CRITICAL WARNING: ALLOWED_TAGS_SET is empty after initial load!")
if not ALLOWED_TAGS_SET_PASS_2:
     print("WARNING: ALLOWED_TAGS_SET_PASS_2 is empty or using fallback after initial load!")
     if not ALLOWED_TAGS_SET: # If Pass 1 also failed, this is critical
          print("CRITICAL WARNING: Both Pass 1 and Pass 2 tag sets are empty!")


# --- Configuration ---
try:
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", "dummy_key_placeholder"))
except Exception as e:
    print(f"Initial dummy genai configure failed (might be ok if key set later): {e}")


def configure_gemini(api_key):
    """Configures the Gemini library with the provided API key."""
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("Error: API key missing or placeholder.")
        return False
    try:
        genai.configure(api_key=api_key)
        print("Gemini API configured successfully.")
        return True
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        traceback.print_exc()
        return False


# --- Modified parse_batch_tag_response function ---
def parse_batch_tag_response(response_text, batch_size, allowed_tags_set_for_pass):
    """
    Parses Gemini's numbered list response, extracts tags, AND filters them
    against the provided set of allowed tags.
    """
    if not allowed_tags_set_for_pass:
        print("ERROR: Allowed Tag Set for this pass is empty.")
        return [f"ERROR: Allowed Tag List Empty" for _ in range(batch_size)]

    tags_list = [f"ERROR: No Response Parsed" for _ in range(batch_size)]
    lines = response_text.strip().split('\n')
    parsed_count = 0
    last_valid_item_num = -1

    for line in lines:
        line = line.strip()
        if not line: continue

        match = re.match(r'^\s*\[\s*(\d+)\s*\]\s*(.*)$', line)
        if match:
            try:
                item_num = int(match.group(1)) - 1
                raw_tags_string = match.group(2).strip()

                if 0 <= item_num < batch_size:
                    last_valid_item_num = item_num
                    if raw_tags_string:
                        suggested_tags = raw_tags_string.split()
                        filtered_tags = [tag for tag in suggested_tags if tag in allowed_tags_set_for_pass]
                        final_tags_string = " ".join(filtered_tags)
                        tags_list[item_num] = final_tags_string if final_tags_string else "INFO: No Valid Tags Found"
                    else:
                        tags_list[item_num] = "" # Empty response for item
                    parsed_count += 1
                else:
                    print(f"[Tag Parser] Warn: Item number {item_num + 1} out of range (batch size {batch_size}). Line: '{line}'")
            except ValueError:
                print(f"[Tag Parser] Warn: Cannot parse item number in line: '{line}'")
                if 0 <= last_valid_item_num < batch_size and tags_list[last_valid_item_num].startswith("ERROR:"):
                     tags_list[last_valid_item_num] = "ERROR: Parsing Failed (ValueError)"
            except Exception as e:
                print(f"[Tag Parser] Error processing line '{line}': {e}")
                if 0 <= last_valid_item_num < batch_size and tags_list[last_valid_item_num].startswith("ERROR:"):
                    tags_list[last_valid_item_num] = "ERROR: Parsing Failed (Exception)"
        else:
            print(f"[Tag Parser] Warn: Line format mismatch: '{line}'")
            if 0 <= last_valid_item_num < batch_size and tags_list[last_valid_item_num].startswith("ERROR:"):
                 tags_list[last_valid_item_num] = "ERROR: Parsing Failed (Format Mismatch)"

    if parsed_count != batch_size:
        print(f"[Tag Parser] Warn: Parsed {parsed_count} items, expected {batch_size}.")
        for i in range(batch_size):
            if tags_list[i] == "ERROR: No Response Parsed":
                tags_list[i] = "ERROR: Parsing Mismatch/Incomplete"
    return tags_list


# --- Helper for Incremental Saving (JSON) ---
def save_json_incrementally(data_list, output_dir, base_filename, step_name, log_func):
    """Saves the current list of parsed JSON objects to a temporary file."""
    if not data_list:
        log_func(f"No data to save for {step_name}.", "debug")
        return None

    try:
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)
            log_func(f"Created output directory for temp JSON: {output_dir}", "info")
    except OSError as e:
        log_func(f"Error creating directory '{output_dir}': {e}", "error")
        return None

    temp_filename = f"{base_filename}_{step_name}_temp_results.json"
    temp_filepath = os.path.join(output_dir, temp_filename)
    try:
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, indent=2)
        log_func(f"Saved intermediate {step_name} results ({len(data_list)} items) to {temp_filename}", "debug")
        return temp_filepath
    except Exception as e:
        log_func(f"Error saving intermediate {step_name} results to {temp_filepath}: {e}", "error")
        return None


# --- Visual Extraction ---
def call_gemini_visual_extraction(
    pdf_path, api_key, model_name, prompt_text, log_func, parent_widget=None
):
    """Calls Gemini with PDF expecting JSON output. Returns (list_of_parsed_objects, uploaded_file_uri) or (None, uri)."""
    log_func("Calling Gemini for Visual JSON extraction...", "info")
    if not configure_gemini(api_key):
        error_msg = "Failed to configure Gemini API key"
        if parent_widget: messagebox.showerror("API Error", error_msg, parent=parent_widget)
        log_func(f"API Error: {error_msg}", "error")
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
        log_func(f"PDF uploaded ({upload_duration:.1f}s). URI: {uploaded_file_uri}", "info")

        model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS, generation_config=generation_config)
        log_func(f"Sending JSON extraction request to Gemini ({model_name})...", "info")
        api_start_time = time.time()
        response = model.generate_content([prompt_text, uploaded_file])
        api_duration = time.time() - api_start_time
        log_func(f"Received response from Gemini ({api_duration:.1f}s).", "info")

        json_string = None
        try:
            json_string = response.text
            log_func(f"Parsing JSON response (len {len(json_string) if json_string else 0})...", "debug")
            if json_string:
                try:
                    parsed_data = json.loads(json_string)
                    if isinstance(parsed_data, list):
                        all_parsed_objects = parsed_data
                        log_func(f"Parsed JSON response ({len(all_parsed_objects)} items).", "info")
                        temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                    else:
                        log_func("Parsing Error: Parsed JSON is not a list.", "error")
                        all_parsed_objects = None
                except json.JSONDecodeError as e:
                    log_func(f"Initial JSON parsing failed: {e}. Raw snippet:\n{json_string[:1000]}", "error")
                    cleaned_json_string = re.sub(r"^```json\s*", "", json_string.strip(), flags=re.IGNORECASE)
                    cleaned_json_string = re.sub(r"\s*```$", "", cleaned_json_string)
                    if cleaned_json_string != json_string:
                        log_func("Retrying parse after stripping markdown...", "warning")
                        try:
                            parsed_data = json.loads(cleaned_json_string)
                            if isinstance(parsed_data, list):
                                all_parsed_objects = parsed_data
                                log_func(f"Parsed after stripping ({len(all_parsed_objects)} items).", "info")
                                temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                            else:
                                log_func("Parsing Error: Stripped JSON not a list.", "error")
                                all_parsed_objects = None
                        except json.JSONDecodeError as e2:
                            log_func(f"Parsing failed even after stripping: {e2}", "error")
                            all_parsed_objects = None
                    else:
                        all_parsed_objects = None
            else:
                log_func("Warning: Received empty response text from Gemini.", "warning")
                all_parsed_objects = []

        except AttributeError:
            log_func("Parsing Error: Could not access response text (request likely blocked?).", "error")
            log_func(f"Full Response Object: {response}", "debug")
            all_parsed_objects = None
        except Exception as e:
            log_func(f"Unexpected error processing response text: {e}\n{traceback.format_exc()}", "error")
            all_parsed_objects = None

        # --- Check for Safety Blocks ---
        try:
            block_reason_enum = getattr(genai.types, "BlockReason", None)
            block_reason_unspecified = getattr(block_reason_enum, "BLOCK_REASON_UNSPECIFIED", 0) if block_reason_enum else 0
            if response.prompt_feedback: block_reason = response.prompt_feedback.block_reason
            if block_reason == block_reason_unspecified: block_reason = None
        except ValueError: block_reason = None; log_func("Minor error ignored accessing block_reason (ValueError).", "debug")
        except Exception as e: block_reason = None; log_func(f"Minor error accessing block_reason: {e}", "debug")

        # Check finish reason
        finish_reason_val = None
        finish_reason_enum = getattr(genai.types, "FinishReason", None)
        finish_reason_safety = getattr(finish_reason_enum, "SAFETY", 3) if finish_reason_enum else 3
        try:
            if response.candidates: finish_reason_val = response.candidates[0].finish_reason; log_func(f"Gemini finish reason: {finish_reason_val}", "debug")
        except Exception as e: log_func(f"Minor error accessing finish_reason: {e}", "debug")

        # Handle blocks
        if block_reason:
            all_blocked = finish_reason_val == finish_reason_safety
            error_msg = f"Request blocked by safety settings. Reason: {block_reason}"
            if all_blocked:
                log_func(error_msg, level="error")
                if parent_widget: messagebox.showerror("API Safety Error", error_msg, parent=parent_widget)
                return None, uploaded_file_uri
            else:
                log_func(f"Safety block '{block_reason}', finish '{finish_reason_val}'. Proceeding.", "warning")

        # Final check if parsing failed without an explicit block
        if all_parsed_objects is None and not block_reason:
            feedback = "N/A"
            try:
                if response.prompt_feedback:
                    feedback = str(response.prompt_feedback)
            except Exception as feedback_e:
                log_func(f"Minor error accessing/converting prompt_feedback for logging: {feedback_e}", "debug")

            log_func(f"API call finished, but JSON parsing failed. FinishReason={finish_reason_val}. Feedback: {feedback}. Returning failure.", "error")
            return None, uploaded_file_uri

        log_func("Gemini Visual JSON extraction step complete.", "info")
        return all_parsed_objects, uploaded_file_uri

    except google.api_core.exceptions.GoogleAPIError as api_e:
        error_type = type(api_e).__name__; error_message = f"API Error (Visual): {error_type}: {api_e}"
        log_func(error_message, level="error")
        if parent_widget: messagebox.showerror("API Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri
    except FileNotFoundError:
        error_message = f"Input PDF not found: {pdf_path}"
        log_func(error_message, level="error")
        if parent_widget: messagebox.showerror("File Error", error_message, parent=parent_widget)
        return None, None
    except Exception as e:
        error_message = f"Unexpected error (visual call): {type(e).__name__}: {e}"
        log_func(f"FATAL API ERROR (Visual): {error_message}\n{traceback.format_exc()}", "error")
        if parent_widget: messagebox.showerror("Unexpected Error", error_message, parent=parent_widget)
        return None, uploaded_file_uri


# --- Text Analysis ---
def call_gemini_text_analysis(
    text_content, api_key, model_name, prompt, log_func,
    output_dir, base_filename, chunk_size=30000, api_delay=5.0, parent_widget=None
):
    """Calls Gemini with text content in chunks. Saves results incrementally. Returns list or None."""
    log_func(f"Processing text with Gemini ({model_name}) in chunks...", "info")
    if not configure_gemini(api_key):
        error_msg = "Failed to configure Gemini API key"; log_func(f"API Error: {error_msg}", "error")
        if parent_widget: messagebox.showerror("API Error", error_msg, parent=parent_widget)
        return None

    all_parsed_data = []; temp_save_path = None; safe_base_name = sanitize_filename(base_filename)
    had_unrecoverable_error = False; total_len = len(text_content)
    if total_len == 0: log_func("Input text empty. Skipping.", "warning"); return []

    num_chunks = math.ceil(total_len / chunk_size)
    log_func(f"Splitting text ({total_len} chars) into ~{num_chunks} chunks of size {chunk_size}.", "debug")

    block_reason_enum = getattr(genai.types, "BlockReason", None)
    block_reason_unspecified = getattr(block_reason_enum, "BLOCK_REASON_UNSPECIFIED", 0) if block_reason_enum else 0
    finish_reason_enum = getattr(genai.types, "FinishReason", None)
    finish_reason_safety = getattr(finish_reason_enum, "SAFETY", 3) if finish_reason_enum else 3
    finish_reason_stop = getattr(finish_reason_enum, "STOP", 1) if finish_reason_enum else 1
    generation_config = genai.GenerationConfig(response_mime_type="application/json")

    try:
        model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS, generation_config=generation_config)
    except Exception as model_e:
         error_msg = f"Failed to initialize Gemini model '{model_name}': {model_e}"; log_func(error_msg, "error")
         if parent_widget: messagebox.showerror("API Error", error_msg, parent=parent_widget)
         return None

    for i in range(num_chunks):
        chunk_start_time = time.time(); chunk_num = i + 1
        start_index = i * chunk_size; end_index = min((i + 1) * chunk_size, total_len)
        chunk_text = text_content[start_index:end_index]
        log_func(f"Processing chunk {chunk_num}/{num_chunks} ({len(chunk_text)} chars)...", "info")
        if not chunk_text.strip(): log_func(f"Skipping empty chunk {chunk_num}.", "debug"); continue

        chunk_parsed_successfully = False
        try:
            full_prompt = f"{prompt}\n\n--- Text Chunk ---\n{chunk_text}"
            log_func(f"Sending chunk {chunk_num} request...", "debug")
            api_start_time = time.time()
            response = model.generate_content(full_prompt)
            api_duration = time.time() - api_start_time
            log_func(f"Received response chunk {chunk_num} ({api_duration:.1f}s).", "debug")

            raw_response_text = ""; block_reason = None; finish_reason_val = None
            try:
                if hasattr(response, "text"): raw_response_text = response.text.strip()
                elif hasattr(response, "parts") and response.parts: raw_response_text = "".join(part.text for part in response.parts if hasattr(part, "text")).strip()
            except Exception as e: log_func(f"Could not extract text (chunk {chunk_num}): {e}", "warning")

            try:
                if response.prompt_feedback: block_reason = response.prompt_feedback.block_reason
                if block_reason == block_reason_unspecified: block_reason = None
            except Exception as e: log_func(f"Minor error accessing block_reason (chunk {chunk_num}): {e}", "debug")
            try:
                if response.candidates: finish_reason_val = response.candidates[0].finish_reason; log_func(f"Chunk {chunk_num} finish reason: {finish_reason_val}", "debug")
            except Exception as e: log_func(f"Minor error accessing finish_reason (chunk {chunk_num}): {e}", "debug")

            if block_reason:
                all_blocked = finish_reason_val == finish_reason_safety; error_msg = f"Chunk {chunk_num} blocked. Reason: {block_reason}"
                if all_blocked: log_func(error_msg, level="error"); continue
                else: log_func(f"Chunk {chunk_num} block '{block_reason}', finish '{finish_reason_val}'. Proceeding.", "warning")

            parsed_chunk_data = None
            if raw_response_text:
                try:
                    cleaned_json_string = re.sub(r"^```json\s*", "", raw_response_text, flags=re.IGNORECASE)
                    cleaned_json_string = re.sub(r"\s*```$", "", cleaned_json_string)
                    if not cleaned_json_string: log_func(f"Warning: Cleaned response chunk {chunk_num} empty.", "warning")
                    else:
                        parsed_chunk_data = json.loads(cleaned_json_string)
                        if isinstance(parsed_chunk_data, list):
                            valid_items = [item for item in parsed_chunk_data if isinstance(item, dict) and "question" in item and "answer" in item]
                            invalid_count = len(parsed_chunk_data) - len(valid_items)
                            if invalid_count > 0: log_func(f"Skipped {invalid_count} invalid items chunk {chunk_num}.", "warning")
                            if valid_items:
                                all_parsed_data.extend(valid_items); chunk_parsed_successfully = True
                                log_func(f"Parsed {len(valid_items)} valid items chunk {chunk_num}.", "debug")
                                temp_save_path = save_json_incrementally(all_parsed_data, output_dir, safe_base_name, "text_analysis", log_func)
                            else: log_func(f"No valid Q&A items chunk {chunk_num}.", "warning")
                        else: log_func(f"Parsing Error: Chunk {chunk_num} JSON not list.", "error")
                except json.JSONDecodeError as e: log_func(f"Parsing Error: Failed JSON decode chunk {chunk_num}: {e}", "error"); log_func(f"--- Invalid Raw Response (Chunk {chunk_num}) ---\n{raw_response_text[:1000]}\n---", "debug")
                except Exception as e: log_func(f"Unexpected error parsing chunk {chunk_num} JSON: {e}", "error")
            elif not block_reason:
                log_func(f"Warning: Empty response chunk {chunk_num}.", "warning")
                candidates_exist = hasattr(response, "candidates") and response.candidates and response.candidates[0] is not None
                if not candidates_exist or finish_reason_val != finish_reason_stop:
                     # *** Start of Refactored Section ***
                     feedback = "N/A" # Default feedback
                     try:
                         # Check if prompt_feedback exists and try converting to string
                         if response.prompt_feedback:
                             feedback = str(response.prompt_feedback)
                         # If prompt_feedback is missing or empty, feedback remains "N/A"
                     except Exception as feedback_e:
                         # Log error if conversion fails, feedback remains "N/A"
                         log_func(f"Minor error accessing/converting prompt_feedback for logging (chunk {chunk_num}): {feedback_e}", "debug")
                     # *** End of Refactored Section ***

                     log_func(f"Chunk {chunk_num} empty, finish={finish_reason_val}. Feedback: {feedback}. Potential Error.", "error")


        except google.api_core.exceptions.GoogleAPIError as api_e:
            error_type = type(api_e).__name__; error_message = f"API Error (Chunk {chunk_num}): {error_type}: {api_e}"
            log_func(error_message, level="error")
            if "rate limit" not in str(api_e).lower(): had_unrecoverable_error = True; log_func("Unrecoverable API error. Stopping.", "error"); break
            else: log_func("Rate limit likely hit, continuing after delay...", "warning")
        except Exception as e:
            error_message = f"Unexpected error chunk {chunk_num}: {type(e).__name__}: {e}"
            log_func(f"FATAL CHUNK ERROR: {error_message}\n{traceback.format_exc()}", "error"); had_unrecoverable_error = True; break

        chunk_end_time = time.time()
        log_func(f"Finished chunk {chunk_num}. Parsed OK: {chunk_parsed_successfully}. Time: {chunk_end_time - chunk_start_time:.2f}s", "debug")
        if chunk_num < num_chunks and api_delay > 0: log_func(f"Waiting {api_delay:.1f}s...", "debug"); time.sleep(api_delay)

    log_func("Text analysis Gemini calls complete.", "info")
    if had_unrecoverable_error:
        log_func("Unrecoverable error occurred. Returning None.", "error")
        if parent_widget: messagebox.showerror("Processing Error", "Unrecoverable error during text analysis. Check logs.", parent=parent_widget)
        return None

    final_save_path = save_json_incrementally(all_parsed_data, output_dir, safe_base_name, "text_analysis_final", log_func)
    if final_save_path: log_func(f"Final combined results saved to {os.path.basename(final_save_path)}", "info")
    elif all_parsed_data: log_func("Error saving final combined results.", "error")
    if not all_parsed_data: log_func("Warning: No data extracted.", "warning"); return []
    return all_parsed_data


# --- REFACTORED Tagging Function (Handles JSON input) ---
def tag_tsv_rows_gemini(
    input_data, # Now expects list of dictionaries (JSON objects)
    api_key,
    model_name_pass1,
    system_prompt_pass1,
    batch_size,
    api_delay,
    log_func,
    progress_callback=None,
    output_dir=None, # For saving intermediate JSON if needed
    base_filename=None, # For naming intermediate JSON
    parent_widget=None,
    enable_second_pass=False,
    second_pass_model_name=None,
    second_pass_prompt=None,
):
    """
    Tags JSON data items using Gemini batches (1 or 2 passes).
    Input: List of dictionaries.
    Yields: Header list, then original dictionaries updated with a 'Tags' key.
    Handles intermediate saving of tagged JSON.
    """
    if not input_data:
        log_func("No data items provided for tagging.", "warning")
        yield ["Question", "Answer", "Tags"] # Yield default header for empty input
        return

    # --- Determine Header ---
    priority_cols = ["Question", "question_text", "Answer", "answer_text", "Tags", "QuestionMedia", "AnswerMedia"]
    # Use keys from the first *actual* data item
    first_item_keys = list(input_data[0].keys()) if input_data else []
    output_header = [col for col in priority_cols if col in first_item_keys]
    remaining_keys = sorted([key for key in first_item_keys if key not in priority_cols and not key.startswith('_')])
    output_header.extend(remaining_keys)
    if "Tags" not in output_header:
        output_header.append("Tags")
    yield output_header # Yield the determined header first

    total_items = len(input_data)
    if total_items == 0: # Double check after header determination
        log_func("No data items to tag.", "warning")
        return

    processed_items_count = 0
    total_batches = math.ceil(total_items / batch_size)
    log_func(f"Starting Gemini tagging: {total_items} items, {total_batches} batches. Pass 2: {'Enabled' if enable_second_pass else 'Disabled'}", "info")

    # --- Configure API Key ---
    if not configure_gemini(api_key):
        error_msg = "Failed to configure Gemini API key"; log_func(f"API Error: {error_msg}", "error")
        if parent_widget: messagebox.showerror("API Error", error_msg, parent=parent_widget)
        # Yield original items with error tag
        for item in input_data: item['Tags'] = "ERROR: API Key Config Failed"; yield item
        return

    # --- Initialize Models ---
    model_pass1 = None; model_pass2 = None
    try:
        model_pass1 = genai.GenerativeModel(model_name_pass1, safety_settings=GEMINI_SAFETY_SETTINGS)
        log_func(f"Pass 1 model '{model_name_pass1}' initialized.", "info")
    except Exception as e:
        log_func(f"FATAL: Error initializing Pass 1 model '{model_name_pass1}': {e}. Cannot proceed.", "error")
        for item in input_data: item['Tags'] = f"ERROR: Model Init Failed ({model_name_pass1})"; yield item
        return

    if enable_second_pass:
        if second_pass_model_name and second_pass_prompt:
            try:
                model_pass2 = genai.GenerativeModel(second_pass_model_name, safety_settings=GEMINI_SAFETY_SETTINGS)
                log_func(f"Pass 2 model '{second_pass_model_name}' initialized.", "info")
            except Exception as e:
                log_func(f"Error initializing Pass 2 model '{second_pass_model_name}': {e}. Disabling Pass 2.", "error")
                enable_second_pass = False
        else:
            log_func("Pass 2 enabled but model/prompt missing. Disabling Pass 2.", "warning")
            enable_second_pass = False

    # --- Setup for Intermediate Saving ---
    safe_base_name = sanitize_filename(base_filename) if base_filename else "tagging_output"
    intermediate_json_p1_path = os.path.join(output_dir, f"{safe_base_name}_pass1_temp.json") if output_dir else None
    intermediate_json_p2_path = os.path.join(output_dir, f"{safe_base_name}_pass2_temp.json") if output_dir and enable_second_pass else None
    all_tagged_items_pass1 = []

    # --- Process Passes ---
    current_pass = 1
    while current_pass <= (2 if enable_second_pass else 1):
        log_func(f"--- Starting Tagging Pass {current_pass} ---", "step")
        items_to_process = input_data if current_pass == 1 else all_tagged_items_pass1
        current_model = model_pass1 if current_pass == 1 else model_pass2
        current_prompt = system_prompt_pass1 if current_pass == 1 else second_pass_prompt
        current_allowed_tags = ALLOWED_TAGS_SET if current_pass == 1 else ALLOWED_TAGS_SET_PASS_2
        current_intermediate_save_path = intermediate_json_p1_path if current_pass == 1 else intermediate_json_p2_path
        current_step_name = f"tagging_pass{current_pass}"
        all_tagged_items_current_pass = []
        processed_items_count = 0 # Reset count for each pass

        # --- Process Batches for Current Pass ---
        for i in range(0, total_items, batch_size):
            batch_start_time = time.time()
            batch_num = i // batch_size + 1
            current_batch_items = items_to_process[i : min(i + batch_size, total_items)]
            actual_batch_size = len(current_batch_items)
            log_func(f"Pass {current_pass} - Processing Batch {batch_num}/{total_batches} ({actual_batch_size} items)...", "debug")

            # --- Format Batch for Prompt ---
            batch_prompt_lines = []
            for idx, item_dict in enumerate(current_batch_items):
                q_text = item_dict.get("question_text", item_dict.get("Question", ""))
                a_text = item_dict.get("answer_text", item_dict.get("Answer", ""))
                prompt_line = f"[{idx + 1}] Q: {q_text} A: {a_text}"
                if current_pass == 2:
                    initial_tags = item_dict.get("Tags", "")
                    if initial_tags and not initial_tags.startswith("ERROR:"): # Only include non-error tags
                        prompt_line += f" Initial Tags: {initial_tags}"
                batch_prompt_lines.append(prompt_line)

            batch_prompt_content = "\n".join(batch_prompt_lines)
            full_prompt = f"{current_prompt}\n\n{batch_prompt_content}"

            # --- Call Gemini ---
            response_text = f"ERROR: API Call Failed (Batch {batch_num})" # Default error for whole batch
            try:
                api_start_time = time.time()
                response = current_model.generate_content(full_prompt)
                api_duration = time.time() - api_start_time
                log_func(f"Pass {current_pass} - Batch {batch_num} API call duration: {api_duration:.2f}s", "debug")

                block_reason, finish_reason_val = None, None
                try: # Safe access to safety feedback
                    block_reason_enum = getattr(genai.types, "BlockReason", None)
                    block_reason_unspecified = getattr(block_reason_enum, "BLOCK_REASON_UNSPECIFIED", 0) if block_reason_enum else 0
                    if response.prompt_feedback: block_reason = response.prompt_feedback.block_reason
                    if block_reason == block_reason_unspecified: block_reason = None
                    finish_reason_enum = getattr(genai.types, "FinishReason", None)
                    finish_reason_safety = getattr(finish_reason_enum, "SAFETY", 3) if finish_reason_enum else 3
                    if response.candidates: finish_reason_val = response.candidates[0].finish_reason
                except Exception as e: log_func(f"Minor error accessing safety info (Batch {batch_num}, Pass {current_pass}): {e}", "debug")

                if block_reason:
                    error_msg = f"Pass {current_pass} - Batch {batch_num} blocked. Reason: {block_reason}"
                    log_func(error_msg, "error")
                    response_text = "\n".join([f"[{n+1}] ERROR: Blocked by API ({block_reason})" for n in range(actual_batch_size)])
                else:
                    # Ensure response.text exists before accessing
                    if hasattr(response, 'text'):
                        response_text = response.text
                    else:
                        # Handle cases where response might be empty or lack text (e.g., some blocks)
                        log_func(f"Warning: Response for Pass {current_pass} - Batch {batch_num} has no 'text' attribute. Response: {response}", "warning")
                        response_text = "\n".join([f"[{n+1}] ERROR: No Text in API Response" for n in range(actual_batch_size)])


            except google.api_core.exceptions.GoogleAPIError as api_e:
                log_func(f"API Error (Pass {current_pass}, Batch {batch_num}): {api_e}", "error")
                response_text = "\n".join([f"[{n+1}] ERROR: API Call Failed ({type(api_e).__name__})" for n in range(actual_batch_size)])
            except Exception as e:
                log_func(f"Unexpected Error during API call (Pass {current_pass}, Batch {batch_num}): {e}\n{traceback.format_exc()}", "error")
                response_text = "\n".join([f"[{n+1}] ERROR: Unexpected API Call Failure" for n in range(actual_batch_size)])

            # --- Parse Response and Update Items ---
            parsed_tags_list = parse_batch_tag_response(response_text, actual_batch_size, current_allowed_tags)

            for idx, item_dict in enumerate(current_batch_items):
                # Make a copy to store results for this pass without modifying input for next pass (if applicable)
                current_item_copy = item_dict.copy()
                current_item_copy['Tags'] = parsed_tags_list[idx]
                all_tagged_items_current_pass.append(current_item_copy)
                processed_items_count += 1

                # --- Update Progress ---
                # *** ADDED PROGRESS CALLBACK CALL HERE ***
                if progress_callback:
                    # Calculate overall progress based on current pass and items within the pass
                    base_progress = 0 if current_pass == 1 else 50 # Pass 1 is 0-50%, Pass 2 is 50-100% (approx)
                    pass_range = 50 # Each pass covers roughly 50% of the progress bar
                    current_pass_progress = (processed_items_count / total_items) * 100 if total_items > 0 else 0
                    # Scale the current pass progress into the overall range
                    total_progress = base_progress + (current_pass_progress * (pass_range / 100))
                    # Call the callback function provided by the UI, passing the processed count and total
                    progress_callback(processed_items_count, total_items) # Pass processed count and total

            # --- Intermediate Save ---
            if current_intermediate_save_path:
                save_json_incrementally(all_tagged_items_current_pass, output_dir, safe_base_name, current_step_name, log_func)

            batch_end_time = time.time()
            log_func(f"Pass {current_pass} - Batch {batch_num} finished. Time: {batch_end_time - batch_start_time:.2f}s", "debug")

            # --- Delay ---
            if batch_num < total_batches and api_delay > 0:
                log_func(f"Waiting {api_delay:.1f}s...", "debug")
                time.sleep(api_delay)
        # --- End of Batch Loop for Current Pass ---

        # Prepare for next pass or finish
        if current_pass == 1:
            all_tagged_items_pass1 = all_tagged_items_current_pass # Store results for Pass 2 input
            if not enable_second_pass: break # Exit loop if only one pass
        # Increment pass counter only after finishing the loop for the current pass
        current_pass += 1
        # *** End of While Loop for Passes ***

    # --- Yield Final Results ---
    final_results = all_tagged_items_current_pass # Results from the last completed pass
    log_func(f"Tagging complete. Yielding {len(final_results)} items.", "info")
    for tagged_item in final_results:
        yield tagged_item


# --- Cleanup Function ---
def cleanup_gemini_file(file_name_uri, api_key, log_func):
    """Deletes an uploaded file from Gemini."""
    if not file_name_uri:
        log_func("Cleanup: No file URI provided.", "debug")
        return
    if not configure_gemini(api_key):
        log_func("Cleanup Error: Failed to configure API key.", "error")
        return

    try:
        log_func(f"Attempting to delete uploaded file: {file_name_uri}", "debug")
        file_id_match = re.search(r'files/([a-zA-Z0-9_-]+)$', file_name_uri)
        if file_id_match:
            file_name_for_delete = f"files/{file_id_match.group(1)}"
            genai.delete_file(name=file_name_for_delete)
            log_func(f"Successfully deleted file: {file_name_for_delete}", "info")
        else:
            log_func(f"Could not extract valid file ID from URI: {file_name_uri}", "warning")

    except Exception as e:
        log_func(f"Error deleting file {file_name_uri}: {e}", "warning")
