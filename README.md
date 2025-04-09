# AnkiTagProcessor

## Overview

AnkiTagProcessor is a Python application designed to streamline the creation and tagging of Anki flashcards using the Google Gemini AI API. It provides a user-friendly graphical interface built with Tkinter, facilitating several key workflows:

1.  **Exporting Notes from Anki (Page 1):** Extracts notes from selected Anki decks into a Tab Separated Values (TSV) format, allowing fine-grained control over included/excluded tags and specific fields.
2.  **Processing Files to Intermediate JSON (Page 2):** Converts content from individual PDF and TXT files into a structured **intermediate JSON format** suitable for the tagging step. This includes two modes:
    * **Visual Q&A (PDF):** Leverages the Gemini API's visual capabilities (requires visual-capable models) to extract question/answer pairs from PDF documents (like presentations). It generates images for relevant pages and saves image references in the JSON. Requires PyMuPDF.
    * **Text Analysis (PDF/TXT):** Utilizes the Gemini API to analyze text content extracted from PDF or TXT files to identify and extract Q&A pairs. Processes text in configurable chunks. PDF text extraction requires PyMuPDF.
    * Both modes save their extracted Q&A data as an intermediate `.json` file.
3.  **Tagging JSON & Generating TSV (Page 3):** Takes an **intermediate JSON file** (generated by Page 2 or the Workflow page) as input. It automatically categorizes and tags the Q&A items using the Gemini API based on customizable prompts. Features configurable batch processing, API delays, and an optional second tagging pass. Finally, it generates the **final TSV file** ready for Anki import, including the extracted data and the generated tags.
4.  **Workflow Automation (Page 4):** Combines file processing (Visual Q&A or Text Analysis for single files) and tagging into a streamlined, multi-step process within a single interface, producing a final tagged TSV file.
5.  **Bulk Process Mode (Page 4):** Processes multiple PDF files using the Visual Q&A approach in a batch. It automatically creates images saved to a timestamped subfolder in the input directory, aggregates the extracted Q&A data into an intermediate JSON, tags the aggregated data, and generates a final, combined, tagged TSV file.

## Features

* **Graphical User Interface:** Easy-to-use interface built with Tkinter.
* **Anki Integration:** Exports notes directly from Anki via AnkiConnect (Page 1). Detects Anki media folder path for streamlined image handling in Visual Q&A workflows.
* **Gemini AI Integration:** Leverages Google Gemini models for:
    * Visual Q&A extraction from PDFs (structured JSON output).
    * Text-based Q&A extraction from PDFs/TXTs (structured JSON output).
    * Automated content tagging based on customizable prompts (supports single or dual-pass tagging).
* **Flexible File Processing:** Handles PDF and TXT inputs for Q&A generation.
* **Intermediate JSON Workflow:** Decouples file processing (Q&A extraction) from tagging, using intermediate JSON files.
* **Configurable API Usage:** Allows selection of different Gemini models for extraction/analysis and tagging steps (including separate models for first and second tagging passes). Adjustable batch sizes and API call delays manage usage and costs.
* **Resilience:** Incorporates incremental saving during file processing (chunked text analysis) and tagging steps (intermediate JSON saves) to minimize data loss. Failed files in Bulk Mode are skipped and renamed.
* **Customizable Prompts:** Allows users to edit the prompts used for interacting with the Gemini API for extraction and tagging (separate prompts for visual extraction, text analysis, first tagging pass, and optional second tagging pass).
* **Structured Codebase:** Refactored architecture with clear separation of UI, core logic, and utilities.
* **Bulk PDF Processing:** Dedicated mode for efficiently processing multiple PDFs using the visual Q&A method, aggregating results, tagging, and producing a single output TSV.

## Bulk Process Mode (Workflow Tab Feature)

This mode, enabled via a checkbox on the "Workflow" tab, is specifically designed for batch processing **multiple PDF files** using the **Visual Q&A** method.

* **Input:** Select multiple PDF files using the dedicated button. Non-PDF files will be skipped.
* **Processing:**
    * The application iterates through each selected PDF.
    * For each PDF, it performs the **Visual Q&A extraction** (Steps 1a, 1b of the visual workflow).
    * **Image Handling:** Images are automatically generated for each PDF page and **saved into a timestamped subfolder** (e.g., `Bulk_Visual_YYYYMMDD_HHMMSS`) within the **same directory as the input PDFs**. Image filenames are prefixed with the sanitized PDF filename. A valid Anki media path is *still required* to correctly generate the `<img>` tags in the final TSV, even though images aren't saved there directly in this mode.
    * Extracted Q&A data (as JSON objects) from each successfully processed PDF is aggregated in memory.
    * Files that fail during processing are skipped, and an attempt is made to rename the original file by adding a "UP_" prefix (e.g., `UP_failed_document.pdf`).
* **Intermediate Save:** The aggregated JSON data from all successful files is saved to an intermediate file (e.g., `bulk_visual_YYYYMMDD_HHMMSS_intermediate.json`).
* **Tagging:** The aggregated intermediate JSON data is then tagged using the Gemini API according to the configured tagging settings (model(s), prompt(s), batch size, delay, second pass option).
* **Output:** A single, final TSV file (e.g., `bulk_visual_YYYYMMDD_HHMMSS_final_tagged.txt`) containing the aggregated and tagged data from all successfully processed PDFs is generated in the same directory as the input PDFs.
* **Post-Processing:** Users must **manually copy the generated image subfolder** (e.g., `Bulk_Visual_YYYYMMDD_HHMMSS`) into their Anki `collection.media` directory before importing the final TSV file into Anki.
* **Limitations:** Currently, Bulk Process Mode only supports the Visual Q&A (PDF) workflow.

## Technical Aspects

* **Language:** Python 3.7+
* **GUI:** Tkinter
* **Core Libraries:**
    * `google-generativeai`: For Gemini API interaction.
    * `PyMuPDF (fitz)`: **Required** for all PDF processing (image generation, text extraction, Visual Q&A, Bulk Mode). Features requiring it are disabled if not installed.
    * `Pydantic`: Used for defining and validating structured data models for Gemini API responses (optional, but recommended for robustness if modifying core logic).
    * `Pillow`: Image handling (may be required by PyMuPDF or future features).
    * `requests`: (Implicit dependency, often included with other packages).
* **API Key:** Requires a Google Gemini API Key.
* **Anki Integration:** Uses the AnkiConnect add-on for direct Anki interaction (Export, Media Path Detection).
* **Structure:**
    ```
    AnkiTagProcessor/
    ├── AnkiTagProcessor_main.py  # Main application entry point
    ├── constants.py             # API keys, model names, settings
    ├── prompts.py               # Default Gemini prompts
    │
    ├── ui/                      # UI modules for each tab/page
    │   ├── page1_anki_export.py
    │   ├── page2_process_file.py
    │   ├── page3_tag_tsv.py
    │   ├── page4_workflow.py
    │   └── __init__.py
    │
    ├── core/                    # Core logic modules
    │   ├── anki_connect.py      # AnkiConnect interaction
    │   ├── gemini_api.py        # Gemini API calls, parsing, tagging
    │   ├── file_processor.py    # PDF/TXT handling, image gen, TSV gen
    │   └── __init__.py
    │
    └── utils/                   # Utility functions
        ├── helpers.py           # Dialogs, sanitization, checks
        └── __init__.py
    ```
    *(Note: `gemini_interactions` folder is intentionally omitted as requested)*

## Prerequisites

* **Python:** Version 3.7 or later.
* **Python Libraries:** Install using pip:
    ```bash
    pip install google-generativeai PyMuPDF Pillow requests pydantic
    ```
    * `google-generativeai`: For Gemini API.
    * `PyMuPDF`: **Required** for PDF processing (Visual Q&A, PDF Text Analysis, Bulk Mode).
    * `Pillow`: Image handling.
    * `requests`: HTTP requests (often a dependency).
    * `pydantic`: Data validation (used internally).
* **Gemini API Key:** Obtain from Google AI Studio or Google Cloud Console.
* **Anki & AnkiConnect:**
    * Anki application installed and running.
    * AnkiConnect Add-on installed and enabled in Anki. Required for 'Export from Anki' (Page 1) and Anki media path detection features.

## Running the Application

1.  **Set API Key:**
    * Set the `GEMINI_API_KEY` environment variable OR
    * Enter the key directly into the application's API Key field(s).
2.  **Run the Script:**
    * **Recommended (as a module):** Open a terminal in the directory *containing* the `AnkiTagProcessor` folder and run:
        ```bash
        python -m AnkiTagProcessor.AnkiTagProcessor_main
        ```
    * **(Alternative) Directly:** Navigate *into* the `AnkiTagProcessor` directory and run:
        ```bash
        python AnkiTagProcessor_main.py
        ```
        (Note: May show non-fatal relative import errors in the console using this method).

## Configuration & Usage

* **API Key:** Enter your Gemini API Key in the UI (shared across relevant tabs). Use the "S/H" (Show/Hide) button to toggle visibility.
* **Model Selection:** Choose appropriate Gemini models for extraction/analysis and tagging steps. Visual Q&A modes require visual-capable models. Separate models can be chosen for the first and optional second tagging passes.
* **Input/Output:**
    * Page 2: Select input PDF/TXT, output directory for intermediate JSON.
    * Page 3: Select input intermediate JSON file. Final TSV is saved in the same directory.
    * Page 4: Select input file(s) (single or bulk). Final TSV is saved in the same directory as the input.
* **Anki Media Path (Visual Q&A / Bulk Mode):**
    * For workflows involving image generation (`Visual Q&A`, `Bulk Process Mode`), you need to specify the path to your Anki `collection.media` folder so the application can generate correct `<img>` tags in the TSV.
    * Use "Detect via AnkiConnect" or "Browse" to set the path.
    * **Single File Visual Q&A:** You can optionally check "Save Images Directly..." to save images directly into the specified Anki media path. If unchecked, images are saved to a subfolder in the intermediate JSON output directory, and you must copy them manually.
    * **Bulk Mode:** Images are *always* saved to a timestamped subfolder in the input directory. You *must* manually copy this subfolder to your Anki `collection.media` folder afterwards. The Anki media path setting is still required for correct tag generation.
* **Chunking/Delay (Text Analysis & Tagging):** Adjust "Chunk Size", "Batch Size", and "API Delay" settings to manage API calls, especially for large inputs or to avoid rate limits.
* **Prompts:** Edit the default prompts in the text boxes if needed for specific extraction or tagging requirements.
* **Second Tagging Pass:** Enable the checkbox on Page 3 or Page 4 to perform an additional tagging pass using a separate model and prompt, merging the results with the first pass.
* **Bulk Mode (Page 4):** Enable via the checkbox. Select multiple PDFs using the dedicated "Select PDFs..." button. Ensure the Anki Media Path is set correctly.

## Notes

* **Status Logs:** Monitor the text areas/labels on each page for progress updates and error messages. Check the console output for more detailed debug information.
* **Error Handling:** Critical errors usually trigger pop-up dialogs. Check logs for details. Failed files in Bulk Mode are skipped and renamed (`UP_...`).
* **Resilience & Intermediate Files:** The application saves intermediate JSON results during processing (`_intermediate_visual.json`, `_intermediate_analysis.json`, `_tagged_p1.json`, etc.) in the output/input directory. These can potentially be used for recovery or inspection if the application crashes or a step fails. These files are generally kept even on successful completion for review but can be manually deleted.
* **PyMuPDF Dependency:** PDF-related features (Visual Q&A, Text Analysis on PDFs, Bulk Mode) **will not function** without PyMuPDF installed. The application attempts to disable relevant UI elements if the library is missing.
* **API Costs:** Be mindful of potential costs associated with using the Gemini API, especially with large files, large batches, or enabling the second tagging pass. Adjust batch sizes and delays accordingly.
* **Tag Filtering:** The tagging process filters the tags generated by the Gemini API against a predefined list extracted from the `prompts.py` file. Only tags matching the allowed list are included in the final output. Ensure your tagging prompts contain the desired tags formatted correctly (e.g., `#Category::SubCategory::Tag`).
