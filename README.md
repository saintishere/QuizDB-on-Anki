# AnkiTagProcessor

## Overview

AnkiTagProcessor is a Python application designed to streamline the creation and tagging of Anki flashcards using the Google Gemini AI API. It provides a user-friendly graphical interface built with Tkinter, facilitating several key workflows:

1.  **Exporting Notes from Anki:** Extracts notes from selected Anki decks into a Tab Separated Values (TSV) format, allowing fine-grained control over included/excluded tags and specific fields.
2.  **Processing Files to TSV:** Converts content from individual PDF and TXT files into a structured TSV format suitable for Anki import. This includes two modes:
    * **Visual Q&A (PDF):** Leverages the Gemini API's visual capabilities to extract question/answer pairs from PDF documents (like presentations). It generates images for relevant pages and links them in the TSV. Includes robust JSON parsing and incremental saving of results for resilience. Requires PyMuPDF.
    * **Text Analysis (PDF/TXT):** Utilizes the Gemini API to analyze text content extracted from PDF or TXT files to identify and extract Q&A pairs. Processes text in configurable chunks with incremental saving for resilience. PDF text extraction requires PyMuPDF.
3.  **Tagging TSV Files with Gemini AI:** Automatically categorizes and tags rows in an existing TSV file using the Gemini API based on question/answer content. Features configurable batch processing and API delays, with incremental saving of tagged results.
4.  **Workflow Automation:** Combines file processing (Visual Q&A or Text Analysis for single files) and tagging into a streamlined, two-step process within a single interface.
5.  **Bulk Process Mode (Visual PDF):** Processes multiple PDF files using the Visual Q&A approach in a batch, automatically creating images saved directly to the Anki media folder and generating a final, aggregated, tagged TSV file.

## Features

* **Graphical User Interface:** Easy-to-use interface built with Tkinter.
* **Anki Integration:** Exports notes directly from Anki via AnkiConnect. Detects Anki media folder path for streamlined image handling.
* **Gemini AI Integration:** Leverages Google Gemini models for:
    * Visual Q&A extraction from PDFs.
    * Text-based Q&A extraction from PDFs/TXTs.
    * Automated content tagging based on customizable prompts.
* **Flexible File Processing:** Handles PDF and TXT inputs for Q&A generation.
* **Configurable API Usage:** Allows selection of different Gemini models, adjustable batch sizes, and API call delays to manage usage and costs.
* **Resilience:** Incorporates incremental saving during file processing and tagging steps to minimize data loss in case of interruptions or errors.
* **Customizable Prompts:** Allows users to edit the prompts used for interacting with the Gemini API for extraction and tagging.
* **Structured Codebase:** Refactored architecture with clear separation of UI, core logic, and utilities.

## Bulk Process Mode (New Feature)

This mode, enabled via a checkbox on the "Workflow" tab, is specifically designed for batch processing **multiple PDF files** using the **Visual Q&A** method.

* **Input:** Select multiple PDF files. Non-PDF files will be skipped.
* **Processing:**
    * The application iterates through each selected PDF.
    * For each PDF, it performs the **Visual Q&A extraction** (Steps 1a, 1b, 1c of the visual workflow).
    * **Image Handling:** Images are automatically generated for each PDF page and **saved directly** into the specified Anki `collection.media` folder. Image filenames are prefixed with the sanitized PDF filename to ensure uniqueness. The "Save Images Directly" option is forced ON and disabled in the UI for this mode. A valid Anki media path *must* be provided.
    * Extracted Q&A data (as TSV rows) from each successfully processed PDF is aggregated in memory.
    * Files that fail during processing are skipped, and an attempt is made to rename the original file by adding a "UP_" prefix (e.g., `UP_failed_document.pdf`).
* **Tagging:** After processing all selected PDFs, the aggregated TSV data (containing Q&A and image links from all successful files) is tagged using the Gemini API according to the configured tagging settings (model, prompt, batch size, delay).
* **Output:** A single, final TSV file containing the aggregated and tagged data from all successfully processed PDFs is generated.
* **Limitations:** Currently, Bulk Process Mode only supports the Visual Q&A (PDF) workflow.

## Technical Aspects

* **Language:** Python 3.7+
* **GUI:** Tkinter
* **Core Libraries:**
    * `google-generativeai`: For Gemini API interaction.
    * `PyMuPDF (fitz)`: Required for all PDF processing (image generation, text extraction). Features requiring it are disabled if not installed.
* **API Key:** Requires a Google Gemini API Key.
* **Anki Integration:** Uses the AnkiConnect add-on for direct Anki interaction.
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
    │   └── ...
    │
    ├── core/                    # Core logic modules
    │   ├── anki_connect.py      # AnkiConnect interaction
    │   ├── gemini_api.py        # Gemini API calls, parsing, tagging
    │   ├── file_processor.py    # PDF/TXT handling, TSV generation
    │   └── ...
    │
    └── utils/                   # Utility functions
        ├── helpers.py           # Dialogs, sanitization, checks
        └── ...
    ```

## Prerequisites

* **Python:** Version 3.7 or later.
* **Python Libraries:** Install using pip:
    ```bash
    pip install google-generativeai PyMuPDF Pillow requests
    ```
    * `google-generativeai`: For Gemini API.
    * `PyMuPDF`: **Required** for PDF processing (Visual Q&A, PDF Text Analysis, Bulk Mode).
    * `Pillow`: Image handling (may be required by PyMuPDF or future features).
    * `requests`: (Implicit dependency, often included with other packages, but good to list).
* **Gemini API Key:** Obtain from Google AI Studio.
* **Anki & AnkiConnect:**
    * Anki application installed and running.
    * AnkiConnect Add-on installed and enabled in Anki. Required for 'Export from Anki' (Page 1) and Anki media path detection features.

## Running the Application

1.  **Set API Key:**
    * Set the `GEMINI_API_KEY` environment variable OR
    * Enter the key directly into the application's API Key field.
2.  **Run the Script:**
    * **Recommended (as a module):** Open a terminal in the directory *containing* the `AnkiTagProcessor` folder and run:
        ```bash
        python -m AnkiTagProcessor.AnkiTagProcessor_main
        ```
    * **Directly:** Navigate *into* the `AnkiTagProcessor` directory and run:
        ```bash
        python AnkiTagProcessor_main.py
        ```
        (Note: May show non-fatal relative import errors in the console using this method).

## Configuration & Usage

* **API Key:** Enter your Gemini API Key in the UI (shared across relevant tabs). Use the "Show/Hide" button to toggle visibility.
* **Model Selection:** Choose appropriate Gemini models for extraction/analysis and tagging steps. Note that Visual Q&A modes require visual-capable models.
* **Input/Output:** Use "Browse" buttons to select input files/folders and output directories.
* **Anki Media Path (Visual Q&A / Bulk Mode):**
    * For workflows involving image generation (`Visual Q&A`, `Bulk Process Mode`), you can choose to save images directly to Anki's `collection.media` folder.
    * Enable the "Save Images Directly..." checkbox (forced ON in Bulk Mode).
    * Use "Detect via AnkiConnect" or "Browse" to set the correct path. If not saving directly, images are saved to a subfolder in the TSV output directory.
* **Chunking/Delay (Text Analysis & Tagging):** Adjust "Chunk Size", "Batch Size", and "API Delay" settings to manage API calls, especially for large inputs or to avoid rate limits.
* **Prompts:** Edit the default prompts in the text boxes if needed for specific extraction or tagging requirements.
* **Bulk Mode:** Enable via the checkbox on the "Workflow" tab. Select multiple PDFs using the dedicated "Select PDFs..." button.

## Notes

* **Status Logs:** Monitor the text areas/labels on each page for progress updates and error messages.
* **Error Handling:** Critical errors usually trigger pop-up dialogs. Check logs for details.
* **Resilience & Temporary Files:** During processing (Text Analysis chunks, Visual Q&A JSON parsing, Tagging batches), the application saves intermediate results to `*_temp_results.json` or `*_temp_results.tsv` files in the relevant output directory. These can potentially be used for recovery if the application crashes. Failed files in Bulk Mode are automatically skipped and renamed.
* **PyMuPDF Dependency:** PDF-related features (Visual Q&A, Text Analysis on PDFs, Bulk Mode) **will not function** without PyMuPDF installed.
* **API Costs:** Be mindful of potential costs associated with using the Gemini API, especially with large files or batches.