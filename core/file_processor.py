# core/file_processor.py
import os
import time
import traceback
import json # Keep for the new function
from datetime import datetime
from tkinter import messagebox
import csv # Import csv module for robust TSV writing

# Use relative imports
from ..constants import PYMUPDF_INSTALLED, fitz
from ..utils.helpers import ProcessingError, sanitize_filename

# --- Image Generation (No change) ---
def generate_page_images(pdf_path, image_destination_path, sanitized_base_name,
                         save_direct_flag, log_func, parent_widget=None,
                         filename_prefix=None):
    """Generates JPG images for each page of a PDF."""
    log_func(f"Generating page images for '{os.path.basename(pdf_path)}'...", "info")
    page_image_map = {}
    doc = None
    final_image_folder_path = image_destination_path

    if not PYMUPDF_INSTALLED:
        raise ProcessingError("PyMuPDF (fitz) is required for image generation.")

    if not save_direct_flag:
        # Create a subfolder within the destination path if not saving directly
        # Note: image_destination_path is the TSV output dir in this case
        subfolder_name = f"{sanitized_base_name}_images_{datetime.now():%Y%m%d_%H%M%S}"
        final_image_folder_path = os.path.join(image_destination_path, subfolder_name)
        if not os.path.exists(final_image_folder_path):
            try:
                os.makedirs(final_image_folder_path)
                log_func(f"Created image subfolder: {subfolder_name}", "info")
            except OSError as e:
                log_func(f"Error creating image subfolder '{final_image_folder_path}': {e}", "error")
                return None, {}
    elif not os.path.isdir(final_image_folder_path):
         # If saving directly, the path must already exist (Anki media folder)
         log_func(f"Error: Target Anki media path does not exist or is not a directory: {final_image_folder_path}", "error")
         return None, {}
    else:
        log_func(f"Saving images directly into: {final_image_folder_path}", "info")

    try:
        doc = fitz.open(pdf_path)
        num_pages = len(doc)
        log_func(f"PDF has {num_pages} pages.", "info")
        pad_width = max(3, len(str(num_pages))) # Determine padding based on number of pages

        for i in range(num_pages):
            page_num = i + 1
            # Consistent image naming convention
            page_part_name = f"page_{page_num:0{pad_width}d}.jpg"
            # Use prefix if provided (e.g., for bulk mode to avoid collisions)
            image_filename = f"{filename_prefix}_{page_part_name}" if filename_prefix else f"{sanitized_base_name}_{page_part_name}"
            image_filepath = os.path.join(final_image_folder_path, image_filename)

            perform_save = True
            if os.path.exists(image_filepath):
                 # If saving directly to Anki media, log overwrite.
                 if save_direct_flag:
                     log_func(f"Overwriting existing image in Anki media: {image_filename}", "info")
                 # If saving to subfolder, ask user via GUI if possible.
                 elif parent_widget:
                     if not messagebox.askyesno("Overwrite Confirmation",
                                                f"Image file already exists:\n{image_filename}\n\nIn directory:\n{os.path.basename(final_image_folder_path)}\n\nOverwrite?",
                                                parent=parent_widget):
                        log_func(f"Skipped overwriting existing image: {image_filename}", "warning")
                        page_image_map[page_num] = image_filename # Still map the existing file
                        perform_save = False
                     else:
                        log_func(f"Overwriting existing image: {image_filename}", "info")
                 # Fallback if no parent widget (e.g., CLI usage) - just log overwrite.
                 else:
                     log_func(f"Overwriting existing image (no UI confirmation): {image_filename}", "info")

            if perform_save:
                try:
                    page = doc.load_page(i)
                except Exception as load_e:
                    log_func(f"Error loading PDF page {page_num}: {load_e}", "error")
                    continue # Skip this page

                zoom = 1.5 # Adjust zoom factor as needed
                mat = fitz.Matrix(zoom, zoom)
                try:
                    pix = page.get_pixmap(matrix=mat)
                except Exception as pixmap_e:
                    log_func(f"Error creating image for page {page_num}: {pixmap_e}", "error")
                    continue # Skip this page

                try:
                    pix.save(image_filepath, "jpeg") # Save as JPG
                except Exception as save_e:
                    log_func(f"Error saving image file '{image_filename}': {save_e}", "error")
                    continue # Skip this page

            page_image_map[page_num] = image_filename # Map page number to the final filename

            # Log progress periodically
            if page_num % 10 == 0 or page_num == num_pages:
                log_func(f"Generated image for page {page_num}/{num_pages}...", "debug")

        log_func(f"Image generation complete. Processed {len(page_image_map)} images.", "info")
        return final_image_folder_path, page_image_map

    except Exception as e:
        log_func(f"Error in image generation step: {e}\n{traceback.format_exc()}", "error")
        return None, {}
    finally:
       # Ensure the document is closed even if errors occur
       if doc:
        try:
            doc.close()
        except Exception:
            pass # Ignore errors during close

# --- Text Extraction (No change) ---
def extract_text_from_pdf(pdf_path, log_func):
    """Extracts plain text from a PDF file using PyMuPDF."""
    log_func(f"Extracting text from PDF: {os.path.basename(pdf_path)}", "debug")
    if not PYMUPDF_INSTALLED or not fitz:
        log_func("PyMuPDF (fitz) is not available.", "error")
        return None

    text = ""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text += page.get_text("text") + "\n\n" # Add newline between pages
        log_func(f"Finished extracting text from {len(doc)} pages.", "debug")
        return text.strip()
    except Exception as e:
        log_func(f"Error extracting text from PDF '{os.path.basename(pdf_path)}': {e}", "error")
        return None
    finally:
        if doc:
            try:
                doc.close()
            except Exception:
                pass

def read_text_file(txt_path, log_func):
    """Reads content from a plain text file."""
    log_func(f"Reading text file: {os.path.basename(txt_path)}", "debug")
    try:
        # Try common encodings if default utf-8 fails
        encodings_to_try = ['utf-8', 'latin-1', 'windows-1252']
        content = None
        for enc in encodings_to_try:
            try:
                with open(txt_path, 'r', encoding=enc) as f:
                    content = f.read()
                log_func(f"Successfully read text file with encoding: {enc}", "debug")
                break # Stop trying if successful
            except UnicodeDecodeError:
                log_func(f"Failed to read with encoding {enc}, trying next...", "debug")
        if content is None:
            raise ValueError("Could not decode the file with common encodings.")
        log_func(f"Finished reading text file.", "debug")
        return content
    except FileNotFoundError:
        log_func(f"Error: Text file not found '{os.path.basename(txt_path)}'", "error")
        return None
    except Exception as e:
        log_func(f"Error reading text file '{os.path.basename(txt_path)}': {e}", "error")
        return None


# --- TSV Generation Functions ---

def generate_tsv_visual(parsed_data, page_image_map, log_func, return_rows=False, tsv_output_dir='.', sanitized_base_name='output'):
    """
    Generates TSV data for Visual Q&A from parsed JSON data.
    Includes Question, QuestionMedia, Answer, AnswerMedia columns.
    Can return rows or write to file.
    """
    log_func("Generating Visual Q&A TSV data from JSON...", "info")
    header = ["Question", "QuestionMedia", "Answer", "AnswerMedia"]
    output_rows = [header] # Start with header

    if not isinstance(parsed_data, list):
         log_func("TSV Generation Error: Input data is not a list.", "error")
         return None if not return_rows else []

    try:
        for i, pair in enumerate(parsed_data):
            if not isinstance(pair, dict):
                log_func(f"TSV Generation Warning: Skipping item {i+1} as it's not a dictionary.", "warning")
                continue

            # Initialize values for the current row
            row_values = {h: "" for h in header}

            # Process Question Text
            q_text_raw = pair.get("question_text", "")
            row_values["Question"] = q_text_raw.replace("\n", "<br>").replace("\t", " ")

            # Process Answer Text
            a_text_raw = pair.get("answer_text", "")
            row_values["Answer"] = a_text_raw.replace("\n", "<br>").replace("\t", " ")

            # --- Process Media Tags ---
            q_media_tags = set()
            a_media_tags = set()

            def get_img_tag_for_page(page_number):
                """Helper to safely get the image tag for a given page number."""
                try:
                    pg_num = int(page_number)
                    if pg_num in page_image_map:
                        img_src = page_image_map[pg_num].replace('"', '&quot;') # Basic HTML entity encoding for quotes
                        return f'<img src="{img_src}">'
                    else:
                        log_func(f"Warning: Image map missing for page {pg_num} (Pair {i+1}).", "warning")
                except (ValueError, TypeError):
                     log_func(f"Warning: Invalid page number '{page_number}' encountered in JSON (Pair {i+1}).", "warning")
                return None

            # Question Media: Add image from question_page and relevant_question_image_pages
            q_page_num = pair.get("question_page")
            q_context_tag = get_img_tag_for_page(q_page_num)
            if q_context_tag:
                q_media_tags.add(q_context_tag)

            rel_q_pages = pair.get("relevant_question_image_pages", [])
            if isinstance(rel_q_pages, list):
                for pg in rel_q_pages:
                    tag = get_img_tag_for_page(pg)
                    if tag:
                        q_media_tags.add(tag)
            else:
                log_func(f"Warning: 'relevant_question_image_pages' is not a list for pair {i+1}. Value: {rel_q_pages}", "warning")

            # Answer Media: Add image from answer_page and relevant_answer_image_pages
            a_page_num = pair.get("answer_page")
            a_context_tag = get_img_tag_for_page(a_page_num)
            if a_context_tag:
                a_media_tags.add(a_context_tag)

            rel_a_pages = pair.get("relevant_answer_image_pages", [])
            if isinstance(rel_a_pages, list):
                for pg in rel_a_pages:
                    tag = get_img_tag_for_page(pg)
                    if tag:
                        a_media_tags.add(tag)
            else:
                 log_func(f"Warning: 'relevant_answer_image_pages' is not a list for pair {i+1}. Value: {rel_a_pages}", "warning")

            # Combine media tags into space-separated strings
            row_values["QuestionMedia"] = " ".join(sorted(list(q_media_tags)))
            row_values["AnswerMedia"] = " ".join(sorted(list(a_media_tags)))

            # Create the final row in the correct header order
            row_to_append = [row_values.get(h, "") for h in header]
            output_rows.append(row_to_append)

        log_func(f"Generated TSV data for {len(output_rows)-1} pairs.", "info")

        if return_rows:
            # Return only data rows (excluding header)
            return output_rows[1:] if len(output_rows) > 1 else []
        else:
            # Write to file
            tsv_filename = f"{sanitized_base_name}_visual_anki.txt" # Use .txt for Anki compatibility
            if not tsv_output_dir or not os.path.isdir(tsv_output_dir):
                log_func(f"Warning: Invalid output directory '{tsv_output_dir}'. Using current directory '.'", "warning")
                tsv_output_dir = '.'
            tsv_filepath = os.path.join(tsv_output_dir, tsv_filename)
            try:
                with open(tsv_filepath, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
                    writer.writerows(output_rows) # Write all rows including header
                log_func(f"Saved Visual TSV file to: {tsv_filepath}", "info")
                return tsv_filepath
            except IOError as e:
                log_func(f"Error writing TSV file '{tsv_filepath}': {e}", "error")
                return None

    except Exception as e:
        log_func(f"Unexpected error generating Visual TSV data from JSON: {e}\n{traceback.format_exc()}", "error")
        return None if not return_rows else []


def generate_tsv_text_analysis(parsed_data, tsv_output_dir, sanitized_base_name, log_func):
    """
    Generates a simple TSV for Text Analysis output (Question & Answer only).
    Writes directly to file.
    """
    log_func("Generating Text Analysis TSV file (Question/Answer only)...", "info")
    # Use intermediate suffix for clarity if called from workflow
    tsv_filename = f"{sanitized_base_name}_text_analysis.txt"
    tsv_filepath = os.path.join(tsv_output_dir, tsv_filename)

    header = ["Question", "Answer"]

    if not isinstance(parsed_data, list):
        log_func("TSV Generation Error: Input data is not a list.", "error")
        parsed_data = [] # Treat as empty list to create empty file

    if not parsed_data:
        log_func("No data provided for text analysis TSV generation. Creating file with header only.", "warning")

    try:
        with open(tsv_filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(header) # Write header
            for item in parsed_data:
                if isinstance(item, dict):
                    # Extract, clean (replace newlines, tabs), and prepare row
                    question = item.get("question", "").replace("\n", "<br>").replace("\t", " ")
                    answer = item.get("answer", "").replace("\n", "<br>").replace("\t", " ")
                    row_values = [question, answer]
                    writer.writerow(row_values)
                else:
                    log_func(f"Warning: Skipping non-dictionary item in text analysis data: {item}", "warning")
        log_func(f"Saved Text Analysis TSV file to '{tsv_filename}'. Processed {len(parsed_data)} items.", "info")
        return tsv_filepath
    except IOError as e:
        log_func(f"Error writing Text Analysis TSV file '{tsv_filepath}': {e}", "error")
        return None
    except Exception as e:
        log_func(f"Unexpected error generating Text Analysis TSV: {e}\n{traceback.format_exc()}", "error")
        return None


# --- NEW FUNCTION to replace the missing import ---
def generate_tsv_from_json_data(json_data, tsv_output_path, log_func):
    """
    Generates a TSV file from a list of JSON objects (dictionaries).
    Dynamically determines columns based on keys in the first object,
    giving priority to common Anki fields like 'Question', 'Answer', 'Tags'.
    """
    log_func(f"Generating generic TSV from JSON data to {os.path.basename(tsv_output_path)}...", "info")

    if not isinstance(json_data, list):
        log_func("TSV Generation Error: Input data is not a list.", "error")
        return False
    if not json_data:
        log_func("Warning: Input JSON data is empty. Creating TSV with header only.", "warning")
        # Decide on default header or try to infer if possible (tricky if empty)
        header = ["Question", "Answer", "Tags"] # Sensible default
    else:
        # Determine header dynamically from keys of the first object
        first_item_keys = list(json_data[0].keys())
        # Prioritize common Anki fields
        priority_cols = ["Question", "Answer", "Tags", "QuestionMedia", "AnswerMedia"]
        header = [col for col in priority_cols if col in first_item_keys]
        # Add remaining keys, sorted alphabetically
        remaining_keys = sorted([key for key in first_item_keys if key not in priority_cols])
        header.extend(remaining_keys)
        log_func(f"Determined TSV header: {header}", "debug")

    try:
        with open(tsv_output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(header) # Write the determined header

            for i, item in enumerate(json_data):
                if isinstance(item, dict):
                    row_values = []
                    for col in header:
                        value = item.get(col, "") # Get value or empty string if key missing
                        # Basic cleaning: replace newlines and tabs
                        cleaned_value = str(value).replace("\n", "<br>").replace("\t", " ")
                        row_values.append(cleaned_value)
                    writer.writerow(row_values)
                else:
                    log_func(f"Warning: Skipping non-dictionary item at index {i} in JSON data.", "warning")

        log_func(f"Successfully generated TSV file with {len(json_data)} data rows.", "info")
        return True # Indicate success
    except IOError as e:
        log_func(f"Error writing TSV file '{tsv_output_path}': {e}", "error")
        return False
    except Exception as e:
        log_func(f"Unexpected error generating TSV from JSON: {e}\n{traceback.format_exc()}", "error")
        return False
