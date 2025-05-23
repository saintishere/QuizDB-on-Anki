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
from typing import Optional, List # Keep List for schema definition
from pydantic import BaseModel, Field, ValidationError # Added Pydantic

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
         print("CRITICAL WARNING: Both Pass 1 and Pass 2 tag sets are empty!") # Indent this print


# --- Pydantic Models for Structured Output ---

class VisualExtractionItem(BaseModel):
    """Pydantic model for the expected structure from VISUAL_EXTRACTION prompt."""
    question_page: int = Field(..., description="Page number where the main question text STARTS")
    question_text: str = Field(..., description="FULL question text, consolidated (newlines replaced with spaces, prefixes removed)")
    relevant_question_image_pages: list[int] = Field(..., description="Array of page numbers containing images relevant ONLY to the QUESTION.")
    answer_page: int = Field(..., description="Page number where the main answer text or primary answer visual STARTS, skipping buffer slides.")
    answer_text: str = Field(..., description="FULL answer text, consolidated (newlines replaced with spaces, prefixes removed)")
    relevant_answer_image_pages: list[int] = Field(..., description="Array of page numbers containing images relevant ONLY to the ANSWER.")

class BookProcessingItem(BaseModel):
    """Pydantic model for the expected structure from BOOK_PROCESSING prompt."""
    source_page_approx: int = Field(..., description="Approximate page number where this Q&A pair is found.")
    question: str = Field(..., description="The FULL, VERBATIM question text extracted directly.")
    answer: str = Field(..., description="The FULL, VERBATIM answer text extracted directly.")

# --- Configuration --- # Ensure this starts at the top level
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
                        # Split robustly, handling multiple spaces
                        suggested_tags = [tag for tag in raw_tags_string.split(' ') if tag]
                        # Filter against the allowed set for the current pass
                        filtered_tags = [tag for tag in suggested_tags if tag in allowed_tags_set_for_pass]
                        final_tags_string = " ".join(sorted(filtered_tags)) # Sort for consistency
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
        # Ensure data_list contains dictionaries, not Pydantic models, before saving
        dict_list = [item.model_dump() if isinstance(item, BaseModel) else item for item in data_list]
        with open(temp_filepath, 'w', encoding='utf-8') as f:
            json.dump(dict_list, f, indent=2)
        log_func(f"Saved intermediate {step_name} results ({len(dict_list)} items) to {temp_filename}", "debug")
        return temp_filepath
    except Exception as e:
        log_func(f"Error saving intermediate {step_name} results to {temp_filepath}: {e}", "error")
        return None


# --- Visual Extraction (Refactored for Structured Output) ---
# ... (call_gemini_visual_extraction function remains unchanged) ...
def call_gemini_visual_extraction(
    pdf_path, api_key, model_name, prompt_text, log_func, parent_widget=None
):
    """Calls Gemini with PDF expecting structured JSON output based on a dictionary schema."""
    log_func("Calling Gemini for Visual JSON extraction (Structured Output - Dict Schema)...", "info")
    if not configure_gemini(api_key):
        error_msg = "Failed to configure Gemini API key"
        if parent_widget: messagebox.showerror("API Error", error_msg, parent=parent_widget)
        log_func(f"API Error: {error_msg}", "error")
        return None, None

    uploaded_file = None
    uploaded_file_uri = None
    all_parsed_objects = None # This will store list of dicts
    block_reason = None
    temp_save_path = None
    output_dir = os.path.dirname(pdf_path) or os.getcwd()
    safe_base_name = sanitize_filename(os.path.basename(pdf_path))

    # Define the schema as a dictionary based on OpenAPI subset
    visual_extraction_schema_dict = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "question_page": {"type": "INTEGER"},
                "question_text": {"type": "STRING"},
                "relevant_question_image_pages": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"}
                },
                "answer_page": {"type": "INTEGER"},
                "answer_text": {"type": "STRING"},
                "relevant_answer_image_pages": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"}
                }
            },
            "required": [
                "question_page", "question_text", "relevant_question_image_pages",
                "answer_page", "answer_text", "relevant_answer_image_pages"
            ]
        }
    }

    generation_config_dict = {
        'response_mime_type': 'application/json',
        'response_schema': visual_extraction_schema_dict
    }

    try:
        log_func(f"Uploading PDF '{os.path.basename(pdf_path)}'...", "upload")
        upload_start_time = time.time()
        display_name = f"visual-extract-{os.path.basename(pdf_path)}-{time.time()}"
        uploaded_file = genai.upload_file(path=pdf_path, display_name=display_name)
        uploaded_file_uri = uploaded_file.name
        upload_duration = time.time() - upload_start_time
        log_func(f"PDF uploaded ({upload_duration:.1f}s). URI: {uploaded_file_uri}", "info")

        # Initialize model WITHOUT generation config initially
        model = genai.GenerativeModel(model_name, safety_settings=GEMINI_SAFETY_SETTINGS)

        log_func(f"Sending JSON extraction request to Gemini ({model_name}) with dictionary schema...", "info")
        api_start_time = time.time()

        # Pass the generation_config_dict directly to generate_content
        response = model.generate_content(
            [prompt_text, uploaded_file],
            generation_config=generation_config_dict
        )
        api_duration = time.time() - api_start_time
        log_func(f"Received response from Gemini ({api_duration:.1f}s).", "info")

        # --- Refactored Response Handling ---
        try:
            # Attempt to use response.parsed first (SDK tries to parse based on schema)
            if hasattr(response, 'parsed') and response.parsed is not None:
                log_func("Attempting to use response.parsed...", "debug")
                parsed_list = response.parsed
                if isinstance(parsed_list, list):
                    # Convert Pydantic models back to dictionaries if necessary
                    # Note: The SDK might return dicts directly with dictionary schema
                    all_parsed_objects = []
                    for item in parsed_list:
                        if isinstance(item, BaseModel):
                             all_parsed_objects.append(item.model_dump())
                        elif isinstance(item, dict):
                             all_parsed_objects.append(item)
                        else:
                            log_func(f"Warning: Unexpected item type in response.parsed list: {type(item)}", "warning")

                    log_func(f"Successfully used response.parsed ({len(all_parsed_objects)} items).", "info")
                    temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                else:
                    log_func("Warning: response.parsed was not None, but not a list as expected.", "warning")
                    all_parsed_objects = None # Fallback to text parsing

            # Fallback to parsing response.text if .parsed didn't work or wasn't available
            if all_parsed_objects is None and hasattr(response, 'text'):
                json_string = response.text
                log_func(f"Falling back to parsing response.text (len {len(json_string) if json_string else 0})...", "debug")
                if json_string:
                    parsed_data = None # Initialize parsed_data for this block
                    try:
                        parsed_data = json.loads(json_string)
                    except json.JSONDecodeError as e:
                        log_func(f"Direct JSON parsing failed: {e}. Trying to strip markdown...", "warning")
                        cleaned_json_string = re.sub(r"^```json\s*", "", json_string.strip(), flags=re.IGNORECASE)
                        cleaned_json_string = re.sub(r"\s*```$", "", cleaned_json_string)
                        if cleaned_json_string != json_string:
                            try:
                                parsed_data = json.loads(cleaned_json_string)
                                log_func("Parsing successful after stripping markdown.", "info")
                            except json.JSONDecodeError as e2:
                                log_func(f"Parsing failed even after stripping: {e2}", "error")
                                parsed_data = None # Ensure it's None on failure

                    # Validate the structure if parsing succeeded
                    if parsed_data is not None:
                        if isinstance(parsed_data, list):
                            # Validate items against the expected dictionary structure (simplified check)
                            validated_items = []
                            required_keys = visual_extraction_schema_dict["items"]["required"]
                            for i, item_data in enumerate(parsed_data):
                                if isinstance(item_data, dict) and all(key in item_data for key in required_keys):
                                    validated_items.append(item_data) # Append the dictionary directly
                                else:
                                    log_func(f"Validation Error for item {i}: Missing keys or not a dict. Skipping item.", "warning")

                            if validated_items:
                                all_parsed_objects = validated_items
                                log_func(f"Validated JSON from response.text ({len(all_parsed_objects)} items).", "info")
                                temp_save_path = save_json_incrementally(all_parsed_objects, output_dir, safe_base_name, "visual_extract", log_func)
                            else:
                                log_func("No valid items found after validating parsed JSON from text.", "warning")
                                all_parsed_objects = []
                        else:
                            log_func("Parsing Error: Parsed JSON from text is not a list.", "error")
                            all_parsed_objects = None
                    # else: # Parsing failed
                    #    all_parsed_objects = None # Already None or set to None above
                else:
                    log_func("Warning: Received empty response text from Gemini.", "warning")
                    all_parsed_objects = [] # Treat empty text as empty list

            # Handle case where neither .parsed nor .text worked
            elif all_parsed_objects is None:
                 log_func("Error: Could not get structured data from response.parsed or response.text.", "error")

        except AttributeError as attr_err:
            log_func(f"Parsing Error: Attribute error accessing response parts ({attr_err}). Request likely blocked or malformed response.", "error")
            log_func(f"Full Response Object: {response}", "debug")
            all_parsed_objects = None
        except Exception as e:
            log_func(f"Unexpected error processing response: {e}\n{traceback.format_exc()}", "error")
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
        # Ensure returning list of dicts
        return all_parsed_objects if isinstance(all_parsed_objects, list) else None, uploaded_file_uri

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


# --- Text Analysis (Refactored for Structured Output) ---
# ... (call_gemini_text_analysis function remains unchanged) ...
def call_gemini_text_analysis(
    text_content, api_key, model_name, prompt, log_func,
    output_dir, base_filename, chunk_size=30000, api_delay=5.0, parent_widget=None
):
    """Calls Gemini with text content in chunks expecting structured JSON output based on BookProcessingItem schema."""
    log_func(f"Processing text with Gemini ({model_name}) in chunks (Structured Output)...", "info")
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

    # --- Define Pydantic schema for generation_config ---
    # Note: The SDK expects the schema itself, not a dictionary representation here
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=List[BookProcessingItem] # Use the Pydantic model directly
    )

    try:
        # Pass the config during model initialization
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
        try: # Outer try block for the entire chunk processing including API call and parsing
            # Keep prompt simple, schema defines structure
            full_prompt = f"{prompt}\n\n--- Text Chunk ---\n{chunk_text}"
            log_func(f"Sending chunk {chunk_num} request with structured output schema...", "debug")
            api_start_time = time.time()
            # Pass config to generate_content (redundant if set on model, but safe)
            response = model.generate_content(full_prompt, generation_config=generation_config)
            api_duration = time.time() - api_start_time
            log_func(f"Received response chunk {chunk_num} ({api_duration:.1f}s).", "debug")

            # --- Refactored Response Handling ---
            block_reason = None; finish_reason_val = None; chunk_items_list = None

            # Check safety feedback first
            try:
                if response.prompt_feedback: block_reason = response.prompt_feedback.block_reason
                if block_reason == block_reason_unspecified: block_reason = None
            except Exception as e: log_func(f"Minor error accessing block_reason (chunk {chunk_num}): {e}", "debug")
            try:
                if response.candidates: finish_reason_val = response.candidates[0].finish_reason; log_func(f"Chunk {chunk_num} finish reason: {finish_reason_val}", "debug")
            except Exception as e: log_func(f"Minor error accessing finish_reason (chunk {chunk_num}): {e}", "debug")

            if block_reason:
                all_blocked = finish_reason_val == finish_reason_safety; error_msg = f"Chunk {chunk_num} blocked. Reason: {block_reason}"
                if all_blocked: log_func(error_msg, level="error"); continue # Skip this chunk
                else: log_func(f"Chunk {chunk_num} safety block '{block_reason}', finish '{finish_reason_val}'. Proceeding.", "warning")

            # Attempt to parse structured output only if not blocked
            if not block_reason:
                try: # Inner try for parsing/validation
                    # Try response.parsed first
                    if hasattr(response, 'parsed') and response.parsed is not None:
                        log_func(f"Attempting to use response.parsed for chunk {chunk_num}...", "debug")
                        parsed_list = response.parsed
                        if isinstance(parsed_list, list):
                            # Convert Pydantic models back to dictionaries
                            chunk_items_list = [item.model_dump() for item in parsed_list if isinstance(item, BookProcessingItem)]
                            log_func(f"Successfully used response.parsed ({len(chunk_items_list)} items) for chunk {chunk_num}.", "info")
                        else:
                            log_func(f"Warning: response.parsed (chunk {chunk_num}) was not None, but not a list.", "warning")
                            chunk_items_list = None # Fallback

                    # Fallback to response.text if .parsed failed or wasn't available
                    if chunk_items_list is None and hasattr(response, 'text'):
                        raw_response_text = response.text.strip()
                        log_func(f"Falling back to parsing response.text for chunk {chunk_num} (len {len(raw_response_text)})...", "debug")
                        if raw_response_text:
                            parsed_data = None # Initialize for this block
                            try:
                                parsed_data = json.loads(raw_response_text)
                            except json.JSONDecodeError:
                                # Try stripping markdown
                                cleaned_json_string = re.sub(r"^```json\s*", "", raw_response_text, flags=re.IGNORECASE)
                                cleaned_json_string = re.sub(r"\s*```$", "", cleaned_json_string)
                                if cleaned_json_string != raw_response_text:
                                    try:
                                        parsed_data = json.loads(cleaned_json_string)
                                        log_func("Parsing successful after stripping markdown.", "info")
                                    except json.JSONDecodeError as e2:
                                        log_func(f"Parsing Error: Failed JSON decode chunk {chunk_num} even after stripping: {e2}", "error")
                                        # parsed_data remains None
                                # else: parsed_data remains None

                            # Validate structure if parsing succeeded
                            if parsed_data is not None:
                                if isinstance(parsed_data, list):
                                    validated_items = []
                                    for i_item, item_data in enumerate(parsed_data):
                                        try:
                                            # Validate against Pydantic model and convert back to dict
                                            validated_model = BookProcessingItem(**item_data)
                                            validated_items.append(validated_model.model_dump())
                                        except ValidationError as val_err:
                                            log_func(f"Validation Error chunk {chunk_num}, item {i_item}: {val_err}. Skipping.", "warning")
                                        except Exception as item_err:
                                            log_func(f"Error processing item {i_item} chunk {chunk_num}: {item_err}. Skipping.", "warning")
                                    chunk_items_list = validated_items
                                    log_func(f"Validated JSON from response.text ({len(chunk_items_list)} items) chunk {chunk_num}.", "info")
                                else:
                                    log_func(f"Parsing Error: Chunk {chunk_num} JSON from text not list.", "error")
                                    chunk_items_list = None # Indicate failure
                            else: # Parsing failed
                                 log_func(f"Parsing Error: Failed JSON decode chunk {chunk_num}.", "error")
                                 chunk_items_list = None # Indicate failure
                        else: # Empty raw_response_text
                             log_func(f"Warning: Empty response text chunk {chunk_num}.", "warning")
                             chunk_items_list = [] # Treat empty text as empty list

                    # If we successfully got a list (even empty) from either method
                    if chunk_items_list is not None:
                        if chunk_items_list: # Only extend if list is not empty
                            all_parsed_data.extend(chunk_items_list)
                            chunk_parsed_successfully = True
                            temp_save_path = save_json_incrementally(all_parsed_data, output_dir, safe_base_name, "text_analysis", log_func)
                        else:
                             log_func(f"No valid Q&A items found/parsed for chunk {chunk_num}.", "warning")
                             chunk_parsed_successfully = True # Consider empty valid response a success for the chunk
                    else: # Failed to parse from either .parsed or .text
                     log_func(f"Error: Could not parse valid JSON for chunk {chunk_num} from response.", "error")
                     # chunk_parsed_successfully remains False

                # --- Add except block for the parsing try ---
                except Exception as parse_e:
                    log_func(f"Unexpected error during response parsing/validation for chunk {chunk_num}: {parse_e}", "error")
                    # chunk_parsed_successfully remains False
                # --- End of Inner Parsing Try/Except ---

                # Log potential errors if parsing failed and it wasn't a safety block
                if chunk_items_list is None and not block_reason: # Check after trying both .parsed and .text
                    log_func(f"Warning: Empty or unparseable response for chunk {chunk_num}, and not blocked.", "warning")
                    candidates_exist = hasattr(response, "candidates") and response.candidates and response.candidates[0] is not None
                    # Check finish reason only if candidates exist
                    finish_reason_ok = True # Assume ok unless proven otherwise
                    if candidates_exist and hasattr(response.candidates[0], 'finish_reason'):
                        finish_reason_ok = (response.candidates[0].finish_reason == finish_reason_stop)

                    if not candidates_exist or not finish_reason_ok:
                         feedback = "N/A" # Default feedback
                         try:
                             # Check if prompt_feedback exists and try converting to string
                             if response.prompt_feedback:
                                 feedback = str(response.prompt_feedback)
                         except Exception as feedback_e:
                             log_func(f"Minor error accessing/converting prompt_feedback for logging (chunk {chunk_num}): {feedback_e}", "debug")

                         log_func(f"Chunk {chunk_num} empty/unparseable, finish={finish_reason_val}. Feedback: {feedback}. Potential Error.", "error")

        # --- Handle API/General Errors for the Chunk (Outer Try) ---
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
    # Ensure returning list of dicts
    return all_parsed_data if isinstance(all_parsed_data, list) else None


# --- REFACTORED Tagging Function (Handles JSON input) ---
def tag_tsv_rows_gemini(
    input_data, # Now expects list of dictionaries (JSON objects)
    api_key,
    model_name_pass1, # Renamed for clarity, used for the current pass
    system_prompt_pass1, # Renamed for clarity, used for the current pass
    batch_size,
    api_delay,
    log_func,
    progress_callback=None,
    output_dir=None, # For saving intermediate JSON if needed
    base_filename=None, # For naming intermediate JSON
    parent_widget=None,
    enable_second_pass=False, # Flag indicating if this call is for Pass 2 (triggers merge)
    second_pass_model_name=None, # Keep for consistency, though not used directly here
    second_pass_prompt=None, # Keep for consistency, though not used directly here
):
    """
    Tags JSON data items using Gemini batches. If enable_second_pass is True,
    it merges the new tags with existing 'Tags' found in the input_data items.
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
    first_item_keys = list(input_data[0].keys()) if input_data else []
    output_header = [col for col in priority_cols if col in first_item_keys]
    remaining_keys = sorted([key for key in first_item_keys if not key.startswith('_') and key not in output_header])
    output_header.extend(remaining_keys)
    if "Tags" not in output_header: output_header.append("Tags")
    yield output_header # Yield the determined header first

    total_items = len(input_data)
    if total_items == 0: log_func("No data items to tag.", "warning"); return

    processed_items_count = 0
    total_batches = math.ceil(total_items / batch_size)
    current_pass_num = 2 if enable_second_pass else 1 # Determine pass number for logging/logic
    log_func(f"Starting Gemini tagging (Pass {current_pass_num}): {total_items} items, {total_batches} batches.", "info")

    # --- Configure API Key ---
    if not configure_gemini(api_key):
        error_msg = "Failed to configure Gemini API key"; log_func(f"API Error: {error_msg}", "error")
        if parent_widget: messagebox.showerror("API Error", error_msg, parent=parent_widget)
        for item in input_data: item['Tags'] = "ERROR: API Key Config Failed"; yield item
        return

    # --- Initialize Model ---
    current_model = None
    current_model_name = model_name_pass1 # Use the model name passed for this specific call
    current_prompt = system_prompt_pass1 # Use the prompt passed for this specific call
    current_allowed_tags = ALLOWED_TAGS_SET_PASS_2 if enable_second_pass else ALLOWED_TAGS_SET # Choose allowed tags based on pass

    try:
        current_model = genai.GenerativeModel(current_model_name, safety_settings=GEMINI_SAFETY_SETTINGS)
        log_func(f"Pass {current_pass_num} model '{current_model_name}' initialized.", "info")
    except Exception as e:
        log_func(f"FATAL: Error initializing Pass {current_pass_num} model '{current_model_name}': {e}. Cannot proceed.", "error")
        for item in input_data: item['Tags'] = f"ERROR: Model Init Failed ({current_model_name})"; yield item
        return

    # --- Setup for Intermediate Saving ---
    safe_base_name = sanitize_filename(base_filename) if base_filename else f"tagging_pass{current_pass_num}_output"
    current_intermediate_save_path = os.path.join(output_dir, f"{safe_base_name}_temp.json") if output_dir else None
    current_step_name = f"tagging_pass{current_pass_num}"
    all_tagged_items_current_pass = [] # Store results for the CURRENT pass

    # --- Process Batches for Current Pass ---
    for i in range(0, total_items, batch_size):
        batch_start_time = time.time()
        batch_num = i // batch_size + 1
        current_batch_items = input_data[i : min(i + batch_size, total_items)] # Slice the input data directly
        actual_batch_size = len(current_batch_items)
        log_func(f"Pass {current_pass_num} - Processing Batch {batch_num}/{total_batches} ({actual_batch_size} items)...", "debug")

        # --- Format Batch for Prompt ---
        batch_prompt_lines = []
        for idx, item_dict in enumerate(current_batch_items):
            q_text = item_dict.get("question_text", item_dict.get("Question", ""))
            a_text = item_dict.get("answer_text", item_dict.get("Answer", ""))
            prompt_line = f"[{idx + 1}] Q: {q_text} A: {a_text}"
            # Only add initial tags to prompt if it's Pass 2 (merging enabled)
            if enable_second_pass: # Check the flag passed to the function
                initial_tags = item_dict.get("Tags", "") # Get tags from Pass 1 input item
                if initial_tags and not initial_tags.startswith("ERROR:"):
                    prompt_line += f" Initial Tags: {initial_tags}"
            batch_prompt_lines.append(prompt_line)

        batch_prompt_content = "\n".join(batch_prompt_lines)
        full_prompt = f"{current_prompt}\n\n{batch_prompt_content}"

        # --- Call Gemini ---
        response_text = f"ERROR: API Call Failed (Batch {batch_num})" # Default error
        try:
            api_start_time = time.time()
            response = current_model.generate_content(full_prompt)
            api_duration = time.time() - api_start_time
            log_func(f"Pass {current_pass_num} - Batch {batch_num} API call duration: {api_duration:.2f}s", "debug")

            block_reason, finish_reason_val = None, None
            try: # Safe access to safety feedback
                block_reason_enum = getattr(genai.types, "BlockReason", None)
                block_reason_unspecified = getattr(block_reason_enum, "BLOCK_REASON_UNSPECIFIED", 0) if block_reason_enum else 0
                if response.prompt_feedback: block_reason = response.prompt_feedback.block_reason
                if block_reason == block_reason_unspecified: block_reason = None
                finish_reason_enum = getattr(genai.types, "FinishReason", None)
                finish_reason_safety = getattr(finish_reason_enum, "SAFETY", 3) if finish_reason_enum else 3
                if response.candidates: finish_reason_val = response.candidates[0].finish_reason
            except Exception as e: log_func(f"Minor error accessing safety info (Batch {batch_num}, Pass {current_pass_num}): {e}", "debug")

            if block_reason:
                error_msg = f"Pass {current_pass_num} - Batch {batch_num} blocked. Reason: {block_reason}"
                log_func(error_msg, "error")
                response_text = "\n".join([f"[{n+1}] ERROR: Blocked by API ({block_reason})" for n in range(actual_batch_size)])
            else:
                if hasattr(response, 'text'):
                    response_text = response.text
                else:
                    log_func(f"Warning: Response for Pass {current_pass_num} - Batch {batch_num} has no 'text' attribute. Response: {response}", "warning")
                    response_text = "\n".join([f"[{n+1}] ERROR: No Text in API Response" for n in range(actual_batch_size)])

        except google.api_core.exceptions.GoogleAPIError as api_e:
            log_func(f"API Error (Pass {current_pass_num}, Batch {batch_num}): {api_e}", "error")
            response_text = "\n".join([f"[{n+1}] ERROR: API Call Failed ({type(api_e).__name__})" for n in range(actual_batch_size)])
        except Exception as e:
            log_func(f"Unexpected Error during API call (Pass {current_pass_num}, Batch {batch_num}): {e}\n{traceback.format_exc()}", "error")
            response_text = "\n".join([f"[{n+1}] ERROR: Unexpected API Call Failure" for n in range(actual_batch_size)])

        # --- Parse Response and Update Items ---
        # Use the allowed tags specific to this pass for filtering
        parsed_tags_list = parse_batch_tag_response(response_text, actual_batch_size, current_allowed_tags)

        for idx, item_dict in enumerate(current_batch_items):
            # Make a copy to store results for this pass
            current_item_copy = item_dict.copy()
            # These are the new tags suggested by the LLM for *this* pass, already filtered
            new_tags_string_this_pass = parsed_tags_list[idx]

            # --- Modified Merge Logic ---
            if enable_second_pass: # If this function call is for Pass 2
                # Get tags from the input item (which should be Pass 1 results)
                existing_tags_string = item_dict.get('Tags', '')

                # Split into sets, handling potential errors and empty strings
                set_existing = set(tag for tag in existing_tags_string.split() if tag and not tag.startswith("ERROR:"))
                set_new_this_pass = set(tag for tag in new_tags_string_this_pass.split() if tag and not tag.startswith("ERROR:"))

                # Perform the union
                merged_valid_set = set_existing.union(set_new_this_pass)
                merged_valid_tags = " ".join(sorted(list(merged_valid_set)))

                # Preserve/Combine any error tags from both sources
                error_tags_existing = " ".join(tag for tag in existing_tags_string.split() if tag.startswith("ERROR:"))
                error_tags_new = " ".join(tag for tag in new_tags_string_this_pass.split() if tag.startswith("ERROR:"))
                # Combine unique error tags
                all_error_tags_set = set(error_tags_existing.split()) | set(error_tags_new.split())
                all_errors = " ".join(sorted(list(all_error_tags_set)))

                # Combine valid merged tags and error tags
                final_tags = f"{merged_valid_tags} {all_errors}".strip()
                current_item_copy['Tags'] = final_tags # Assign MERGED tags

            else: # This function call is for Pass 1
                # Just assign the new (filtered) tags for this pass
                current_item_copy['Tags'] = new_tags_string_this_pass
            # --- End Modified Merge Logic ---

            all_tagged_items_current_pass.append(current_item_copy)
            processed_items_count += 1

            # --- Update Progress ---
            if progress_callback:
                # Progress calculation should be handled by the caller (_wf_gemini_tag_json)
                # based on which pass this is. Here, just report items processed.
                # We can pass the pass number back if needed, or rely on caller context.
                progress_callback(processed_items_count, total_items) # Simple progress for now

        # --- Intermediate Save ---
        if current_intermediate_save_path:
            # Save the results accumulated *so far* in this pass
            save_json_incrementally(all_tagged_items_current_pass, output_dir, safe_base_name, current_step_name, log_func)

        batch_end_time = time.time()
        log_func(f"Pass {current_pass_num} - Batch {batch_num} finished. Time: {batch_end_time - batch_start_time:.2f}s", "debug")

        # --- Delay ---
        if batch_num < total_batches and api_delay > 0:
            log_func(f"Waiting {api_delay:.1f}s...", "debug")
            time.sleep(api_delay)
    # --- End of Batch Loop ---

    # --- Yield Final Results ---
    log_func(f"Tagging Pass {current_pass_num} complete. Yielding {len(all_tagged_items_current_pass)} items.", "info")
    for tagged_item in all_tagged_items_current_pass:
        yield tagged_item


# --- Cleanup Function ---
# ... (cleanup_gemini_file function remains unchanged) ...
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
