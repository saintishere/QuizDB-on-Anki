# AnkiTagProcessor

## Overview

AnkiTagProcessor is a Python application designed to enhance Anki flashcards using the Gemini AI API. It provides a user-friendly graphical interface built with Tkinter to streamline the process of:

1.  **Exporting Notes from Anki:** Extracts notes from your Anki decks into a Tab Separated Values (TSV) format, allowing you to select specific decks, tags, and fields for export.
2.  **Processing Files to TSV:** Converts content from PDF and TXT files into a structured TSV format suitable for Anki import. This feature includes enhanced resilience through incremental processing and saving:
    * **Visual Q&A (PDF):** Leverages Gemini API's visual capabilities to extract question and answer pairs directly from PDF documents. It generates images for each page and links them in the TSV. Resilience is achieved by robustly parsing the API's JSON response and **incrementally saving successfully parsed Q&A pairs** to a temporary file, protecting against data loss if parsing or later steps fail.
    * **Text Analysis (PDF/TXT):** Utilizes Gemini API to analyze text content from PDF or TXT files and extract Q&A pairs. Resilience is achieved by processing the text in **configurable chunks**, calling the API for each chunk, and **incrementally saving the combined results** to a temporary file after each chunk. The final TSV contains only "Question" and "Answer" columns.
3.  **Tagging TSV Files with Gemini AI:** Automatically tags rows in a TSV file using the Gemini API in configurable batches with adjustable delays, allowing for intelligent categorization of flashcards based on their content. Incremental saving of tagged results is also implemented for resilience.
4.  **Workflow Automation:** Combines the file processing (Visual Q&A or Text Analysis) and tagging functionalities into a streamlined workflow. Users can process files, convert them to TSV, and then automatically tag the generated TSV data, all within a single interface, benefiting from the incremental saving features at each stage.

## Refactored Architecture

This version of AnkiTagProcessor has been refactored for improved organization, maintainability, and clarity.

AnkiTagProcessor/
├── AnkiTagProcessor_main.py
├── constants.py
├── prompts.py
│
├── ui/
│   ├── init.py
│   ├── page1_anki_export.py
│   ├── page2_process_file.py
│   ├── page3_tag_tsv.py
│   ├── page4_workflow.py
│
├── core/
│   ├── init.py
│   ├── anki_connect.py
│   ├── gemini_api.py
│   ├── file_processor.py
│
└── utils/
├── init.py
├── helpers.py

The codebase is structured into the following modules:

* **`AnkiTagProcessor_main.py`:** The main application entry point. Sets up the Tkinter main window, notebook interface, and initializes all UI pages and shared application state. Includes fallback import logic for direct script execution.
* **`constants.py`:** Defines global constants, settings, and default values (API keys, model lists, safety settings).
* **`prompts.py`:** Contains all default prompt strings used for interacting with the Gemini API.
* **`ui/` directory:** Contains UI code for each application page (`page1_anki_export.py`, `page2_process_file.py`, etc.).
* **`core/` directory:** Houses the core application logic:
    * `anki_connect.py`: Functions for interacting with the AnkiConnect API.
    * `gemini_api.py`: Functions for calling the Gemini API, including logic for batching (Text Analysis, Tagging), robust parsing (Visual Q&A), and incremental saving.
    * `file_processor.py`: Functions for PDF/TXT handling (image generation, text extraction, TSV generation).
    * `__init__.py`: Makes `core` a Python package.
* **`utils/` directory:** Contains utility functions:
    * `helpers.py`: General helpers (filename sanitization, dialogs, PyMuPDF check).
    * `__init__.py`: Makes `utils` a Python package.

## Usage

### Prerequisites

* **Python 3.7+:** Ensure Python 3.7 or later is installed.
* **Required Python Libraries:** Install using pip:
    ```bash
    pip install google-generativeai PyMuPDF Pillow # Pillow might be needed by PyMuPDF or future features
    ```
    * `google-generativeai`: For interacting with the Gemini API.
    * `PyMuPDF (fitz)`: Required for PDF processing (Visual Q&A image generation, PDF Text Analysis text extraction). Install with `pip install PyMuPDF`. *Note: PDF features are disabled if not installed.*
    * `tkinter (tk)`: Python's standard GUI toolkit (usually included).
* **Gemini API Key:** Obtain an API key from Google AI Studio. Set the `GEMINI_API_KEY` environment variable or enter it in the application UI.
* **AnkiConnect Add-on (Optional):** Required for Anki export (Page 1) and Anki media path detection features. Ensure AnkiConnect is installed/enabled in Anki, and Anki is running.

### Running the Application

Two ways to run:

1.  **Recommended (as a module):**
    * Open your terminal in the directory *containing* the `AnkiTagProcessor` folder (e.g., `C:\Users\Hussain\Workspace1`).
    * Run: `python -m AnkiTagProcessor.AnkiTagProcessor_main`
    * This method avoids relative import errors shown in the console.
2.  **Directly (uses fallbacks):**
    * Navigate *into* the `AnkiTagProcessor/` directory.
    * Run: `python AnkiTagProcessor_main.py`
    * You might see initial "attempted relative import" errors in the console, but the application should still run due to fallback imports.

The Anki Tag Processor window will appear with four main tabs:

* **1: Export from Anki:** Export notes from Anki to TSV.
* **2: Process File to TSV:** Convert PDF/TXT files to TSV using Gemini AI (Visual Q&A or Text Analysis modes with resilience features).
* **3: Tag TSV File:** Tag rows in an existing TSV file using Gemini AI (batch processing).
* **4: Workflow (File->TSV->Tag):** Automated workflow combining file processing and tagging with resilience features.

### Setting up API Key

* Enter your Gemini API key in the "Gemini API Key" field on Page 2, 3, or 4. The key is shared.
* Use the "Show/Hide" button to toggle visibility.

### Using the Features

Refer to in-app labels and tooltips. Key updates:

* **Resilience:** Both "Process File" (Page 2) and "Workflow" (Page 4) modes now incorporate incremental saving. If the process crashes, look for temporary files (e.g., `*_temp_results.json` or `*_temp_results.tsv`) in the output directory containing partially processed results.
* **Text Analysis (Page 2 & 4):**
    * Processes input text in chunks. Configure **"Text Chunk Size (chars)"** (default: 30000) and **"Text API Delay (sec)"** (default: 5.0) in the "Gemini Configuration" / "Workflow Configuration" section for this mode.
    * The final TSV output contains only "Question" and "Answer" columns.
* **Visual Q&A (Page 2 & 4):**
    * Uses a single API call but incrementally saves successfully parsed Q&A pairs from the response for resilience. Chunk/delay settings do *not* apply to this mode's API call.
* **Tagging (Page 3 & 4):**
    * Processes TSV rows in batches. Configure **"Tagging Batch Size"** and **"Tagging API Delay (s)"**.
    * Incrementally saves tagged results for resilience.

## Notes

* **Error Handling:** Check the "Status Log" areas for processing details and errors. Critical issues trigger dialog boxes.
* **Temporary Files:** During processing (Text Analysis, Visual Q&A parsing, Tagging), the application saves intermediate results to `.json` or `.tsv` files in the output directory (look for filenames containing `_temp_results`). These can be used for recovery if the application crashes.
* **PyMuPDF Dependency:** PDF features require PyMuPDF.
* **API Usage:** Be mindful of Gemini API costs and rate limits. Use the batch size and delay settings (for Text Analysis and Tagging) to manage API calls, especially for large files/batches.

This refactored AnkiTagProcessor provides a more modular and resilient experience for processing your documents and tagging your Anki notes.

