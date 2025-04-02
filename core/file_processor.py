# core/file_processor.py
import os
import time
import traceback
from datetime import datetime
from tkinter import messagebox # Keep for overwrite confirmation

# Import constants and fitz safely using relative paths
try:
    from ..constants import PYMUPDF_INSTALLED, fitz
    from ..utils.helpers import ProcessingError
except ImportError:
    # Fallback for direct execution or different structure
    from constants import PYMUPDF_INSTALLED, fitz
    from utils.helpers import ProcessingError


def generate_page_images(pdf_path, image_destination_path, sanitized_base_name,
                         save_direct_flag, log_func, parent_widget=None):
    """Generates JPG images for each page of a PDF."""
    log_func(f"Generating page images for '{os.path.basename(pdf_path)}'...", "info")
    page_image_map = {}
    doc = None
    final_image_folder_path = image_destination_path # Base path

    if not PYMUPDF_INSTALLED:
        raise ProcessingError("PyMuPDF (fitz) is required for image generation.")

    if not save_direct_flag:
        # Create subfolder if it doesn't exist
        if not os.path.exists(final_image_folder_path):
            try:
                os.makedirs(final_image_folder_path)
                log_func(f"Created image subfolder: {os.path.basename(final_image_folder_path)}", "info")
            except OSError as e:
                log_func(f"Error creating image subfolder '{final_image_folder_path}': {e}", "error")
                return None, {}
    elif not os.path.isdir(final_image_folder_path):
         log_func(f"Error: Target image path does not exist or is not a directory: {final_image_folder_path}", "error")
         return None, {}
    else: # Direct save path exists
         log_func(f"Saving images directly into: {final_image_folder_path}", "info")

    try:
        doc = fitz.open(pdf_path)
        num_pages = len(doc)
        log_func(f"PDF has {num_pages} pages.", "info")
        pad_width = max(3, len(str(num_pages))) # For consistent naming

        for i in range(num_pages):
            page_num = i + 1
            image_filename = f"{sanitized_base_name}_page_{page_num:0{pad_width}d}.jpg"
            image_filepath = os.path.join(final_image_folder_path, image_filename)

            # Overwrite check logic (requires parent_widget for messagebox)
            perform_save = True
            if os.path.exists(image_filepath):
                 if not save_direct_flag: # Only ask if NOT saving direct (direct assumes overwrite is ok)
                     if parent_widget: # Only show dialog if we have a parent
                         if not messagebox.askyesno("Overwrite Confirmation",
                                                f"Image file already exists:\n{image_filename}\n\n"
                                                f"In directory:\n{os.path.basename(final_image_folder_path)}\n\nOverwrite?",
                                                parent=parent_widget):
                            log_func(f"Skipped overwriting existing image: {image_filename}", "warning")
                            page_image_map[page_num] = image_filename # Still map existing file
                            perform_save = False
                         else:
                            log_func(f"Overwriting existing image: {image_filename}", "info")
                     else: # No parent widget, log overwrite intention
                          log_func(f"Overwriting existing image (no UI confirmation): {image_filename}", "info")
                 else: # Direct save, just log the overwrite
                      log_func(f"Overwriting existing image in Anki media: {image_filename}", "info")

            if perform_save:
                try:
                    page = doc.load_page(i)
                except Exception as load_e:
                    log_func(f"Error loading PDF page {page_num}: {load_e}", "error")
                    continue # Skip this page

                zoom = 1.5 # Or make this configurable?
                mat = fitz.Matrix(zoom, zoom)
                try:
                    pix = page.get_pixmap(matrix=mat)
                except Exception as pixmap_e:
                    log_func(f"Error creating image for page {page_num}: {pixmap_e}", "error")
                    continue

                try:
                    pix.save(image_filepath, "jpeg") # Save as JPG
                except Exception as save_e:
                    log_func(f"Error saving image file '{image_filename}': {save_e}", "error")
                    continue # Skip mapping if save failed

            page_image_map[page_num] = image_filename # Map page number to filename

            if page_num % 10 == 0 or page_num == num_pages:
                log_func(f"Generated image for page {page_num}/{num_pages}...", "debug")

        log_func(f"Image generation complete. Processed {len(page_image_map)} images.", "info")
        return final_image_folder_path, page_image_map

    except Exception as e:
        log_func(f"Error in image generation step: {e}\n{traceback.format_exc()}", "error")
        return None, {}
    finally:
        if doc:
            try:
                doc.close()
            except Exception:
                pass # Ignore errors during close

def extract_text_from_pdf(pdf_path, log_func):
    """Extracts plain text from a PDF file using PyMuPDF."""
    log_func(f"Extracting text from PDF: {os.path.basename(pdf_path)}", "debug")
    if not PYMUPDF_INSTALLED or not fitz:
        log_func("PyMuPDF (fitz) is not available for PDF text extraction.", "error")
        return None
    text = ""
    doc = None
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text += page.get_text("text") + "\n\n" # Add space between pages
        log_func(f"Finished extracting text from {len(doc)} pages.", "debug")
        return text.strip()
    except Exception as e:
        log_func(f"Error extracting text from PDF '{os.path.basename(pdf_path)}': {e}", "error")
        return None
    finally:
        if doc:
            try: doc.close()
            except Exception: pass

def read_text_file(txt_path, log_func):
    """Reads content from a plain text file."""
    log_func(f"Reading text file: {os.path.basename(txt_path)}", "debug")
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        log_func(f"Finished reading text file.", "debug")
        return content
    except Exception as e:
        log_func(f"Error reading text file '{os.path.basename(txt_path)}': {e}", "error")
        return None

def generate_tsv_visual(parsed_data, tsv_output_dir, sanitized_base_name, page_image_map, log_func):
    """Generates the TSV file for Visual Q&A from parsed JSON data."""
    log_func("Generating Anki-compatible TSV file from JSON data...", "info")
    tsv_filename = f"{sanitized_base_name}_visual_anki.txt"
    tsv_filepath = os.path.join(tsv_output_dir, tsv_filename)
    header = ["Question", "QuestionMedia", "Answer", "AnswerMedia"]

    if not isinstance(parsed_data, list):
         log_func("TSV Generation Error: Input data is not a list.", "error")
         return None

    try:
        with open(tsv_filepath, 'w', encoding='utf-8', newline='') as f:
            f.write("\t".join(header) + "\n")
            for i, pair in enumerate(parsed_data):
                if not isinstance(pair, dict):
                    log_func(f"TSV Generation Warning: Skipping item {i+1} as it's not a dictionary.", "warning")
                    continue

                row_values = {"Question": "", "QuestionMedia": "", "Answer": "", "AnswerMedia": ""}

                q_text_raw = pair.get("question_text", "")
                row_values["Question"] = q_text_raw.replace("\n", "<br>").replace("\t", " ")

                a_text_raw = pair.get("answer_text", "")
                row_values["Answer"] = a_text_raw.replace("\n", "<br>").replace("\t", " ")

                q_media_tags = set(); a_media_tags = set()

                def get_img_tag_for_page(page_number):
                    try:
                        pg_num = int(page_number)
                        if pg_num in page_image_map:
                            return f'<img src="{page_image_map[pg_num]}">'
                        else:
                            log_func(f"Warning: Image map missing for page {pg_num} (Pair {i+1}).", "warning")
                    except (ValueError, TypeError):
                         log_func(f"Warning: Invalid page number '{page_number}' encountered in JSON (Pair {i+1}).", "warning")
                    return None

                # Get images for question
                q_page_num = pair.get("question_page")
                q_context_tag = get_img_tag_for_page(q_page_num)
                if q_context_tag: q_media_tags.add(q_context_tag)

                rel_q_pages = pair.get("relevant_question_image_pages", [])
                if isinstance(rel_q_pages, list):
                    for pg in rel_q_pages:
                        tag = get_img_tag_for_page(pg)
                        if tag: q_media_tags.add(tag)
                else:
                    log_func(f"Warning: 'relevant_question_image_pages' is not a list for pair {i+1}. Value: {rel_q_pages}", "warning")

                # Get images for answer
                a_page_num = pair.get("answer_page")
                a_context_tag = get_img_tag_for_page(a_page_num)
                if a_context_tag: a_media_tags.add(a_context_tag)

                rel_a_pages = pair.get("relevant_answer_image_pages", [])
                if isinstance(rel_a_pages, list):
                    for pg in rel_a_pages:
                        tag = get_img_tag_for_page(pg)
                        if tag: a_media_tags.add(tag)
                else:
                     log_func(f"Warning: 'relevant_answer_image_pages' is not a list for pair {i+1}. Value: {rel_a_pages}", "warning")

                row_values["QuestionMedia"] = " ".join(sorted(list(q_media_tags)))
                row_values["AnswerMedia"] = " ".join(sorted(list(a_media_tags)))
                # Use the defined header order
                row_to_write = [row_values.get(h, "") for h in header]
                f.write("\t".join(row_to_write) + "\n")

        log_func(f"Saved Visual TSV file to '{tsv_filename}'.", "info")
        return tsv_filepath
    except IOError as e: log_func(f"Error writing TSV file '{tsv_filepath}': {e}", "error"); return None
    except Exception as e: log_func(f"Unexpected error generating TSV from JSON data: {e}\n{traceback.format_exc()}", "error"); return None


def generate_tsv_text_analysis(parsed_data, tsv_output_dir, sanitized_base_name, log_func):
    """Generates a simple TSV for Text Analysis output (Question & Answer only)."""
    log_func("Generating Text Analysis TSV file (Question/Answer only)...", "info")
    tsv_filename = f"{sanitized_base_name}_text_analysis.txt"
    tsv_filepath = os.path.join(tsv_output_dir, tsv_filename)

    # --- MODIFICATION START ---
    # Explicitly define the desired header
    header = ["Question", "Answer"]
    # --- MODIFICATION END ---

    if not parsed_data:
        log_func("No data provided for text analysis TSV generation. Creating empty file.", "warning")
        parsed_data = [] # Ensure loop doesn't run but file gets created

    try:
        with open(tsv_filepath, 'w', encoding='utf-8', newline='') as f:
            f.write("\t".join(header) + "\n") # Write the fixed header
            for item in parsed_data:
                if isinstance(item, dict):
                    # Extract only the values for the fixed header columns
                    row_values = [
                        item.get("question", ""),
                        item.get("answer", "")
                    ]
                    f.write("\t".join(map(str, row_values)) + "\n")
                else:
                    log_func(f"Warning: Skipping non-dictionary item in text analysis data: {item}", "warning")
        log_func(f"Saved Text Analysis TSV file to '{tsv_filename}'.", "info")
        return tsv_filepath
    except IOError as e:
        log_func(f"Error writing Text Analysis TSV file '{tsv_filepath}': {e}", "error")
        return None
    except Exception as e:
        log_func(f"Unexpected error generating Text Analysis TSV: {e}\n{traceback.format_exc()}", "error")
        return None