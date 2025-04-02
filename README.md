# AnkiTagProcessor

## Overview

AnkiTagProcessor is a Python application designed to enhance Anki flashcards using the Gemini AI API. It provides a user-friendly graphical interface built with Tkinter to streamline the process of:

1.  **Exporting Notes from Anki:**  Extracts notes from your Anki decks into a Tab Separated Values (TSV) format, allowing you to select specific decks, tags, and fields for export.
2.  **Processing Files to TSV:** Converts content from PDF and TXT files into a structured TSV format suitable for Anki import. This feature includes:
    *   **Visual Q&A (PDF):**  Leverages Gemini API's visual capabilities to extract question and answer pairs directly from PDF documents, especially useful for visually-rich quiz materials. It can generate images for each page of the PDF and link them in the TSV for visual context in Anki cards.
    *   **Text Analysis (PDF/TXT):**  Utilizes Gemini API to analyze text content from PDF or TXT files and extract relevant information, formatting the output into a TSV.
3.  **Tagging TSV Files with Gemini AI:**  Automatically tags rows in a TSV file using the Gemini API, allowing for batch tagging of flashcards based on their content. Users can customize prompts and models for intelligent tag generation.
4.  **Workflow Automation:** Combines the above functionalities into a streamlined workflow, allowing users to process files, convert them to TSV, and then automatically tag the generated TSV data, all within a single interface.

## Refactored Architecture

This version of AnkiTagProcessor has been refactored for improved organization, maintainability, and clarity.

AnkiTagProcessor/
├── AnkiTagProcessor_main.py
├── constants.py
├── prompts.py
│
├── ui/
│   ├── __init__.py
│   ├── page1_anki_export.py
│   ├── page2_process_file.py
│   ├── page3_tag_tsv.py
│   ├── page4_workflow.py
│
├── core/
│   ├── __init__.py
│   ├── anki_connect.py
│   ├── gemini_api.py
│   ├── file_processor.py
│
└── utils/
    ├── __init__.py
    ├── helpers.py

The codebase is structured into the following modules:

*   **`AnkiTagProcessor_main.py`:**  The main application entry point. Sets up the Tkinter main window, notebook interface, and initializes all UI pages and shared application state.
*   **`constants.py`:**  Defines global constants, settings, and default values used throughout the application, such as API keys (with placeholder defaults), Gemini model lists, and safety settings.
*   **`prompts.py`:**  Contains all the prompt strings used for interacting with the Gemini API. This modularization allows for easy customization and modification of prompts.
*   **`ui/` directory:**  Contains all UI-related code, with each page of the application (Export from Anki, Process File, Tag TSV File, Workflow) implemented as a separate Python file (e.g., `page1_anki_export.py`, `page2_process_file.py`, etc.).  The `__init__.py` file makes `ui` a Python package.
*   **`core/` directory:**  Houses the core logic of the application, separated into modules based on functionality:
    *   `anki_connect.py`:  Functions for interacting with the AnkiConnect API to export data from Anki, detect media paths, etc.
    *   `gemini_api.py`:  Functions for calling the Gemini API for visual extraction, text analysis, and batch tagging. Includes API configuration and response parsing.
    *   `file_processor.py`:  Functions for handling PDF and TXT files, including image generation from PDFs (using PyMuPDF), text extraction, and TSV file generation.
    *   `__init__.py`:  Makes `core` a Python package.
*   **`utils/` directory:**  Contains utility and helper functions used across the application:
    *   `helpers.py`:  General helper functions like filename sanitization, error dialogs, and PyMuPDF checking.
    *   `__init__.py`: Makes `utils` a Python package.

## Usage

### Prerequisites

*   **Python 3.7+:** Ensure you have Python 3.7 or a later version installed on your system.
*   **Required Python Libraries:** Install necessary libraries using pip:
    ```bash
    pip install google-generativeai PyMuPDF tk
    ```
    *   `google-generativeai`:  For interacting with the Gemini API.
    *   `PyMuPDF (fitz)`: For PDF processing (image generation and text extraction). Install with `pip install PyMuPDF`.  *Note: Visual Q&A and PDF Text Analysis features are disabled if PyMuPDF is not installed.*
    *   `tkinter (tk)`:  Python's standard GUI toolkit, usually included with Python installations.
*   **Gemini API Key:** You will need an API key from Google AI Studio to use the Gemini API features.  Set the `GEMINI_API_KEY` environment variable or enter it directly in the application UI.
*   **AnkiConnect Add-on (Optional):** For Anki export and media path detection features, ensure the AnkiConnect add-on is installed and enabled in your Anki application, and Anki is running when using these features.

### Running the Application

1.  Navigate to the `AnkiTagProcessor/` directory in your terminal.
2.  Run the main application script:
    ```bash
    python AnkiTagProcessor_main.py
    ```
3.  The Anki Tag Processor window will appear, providing access to the four main tabs:
    *   **1: Export from Anki:** Export notes from Anki to TSV.
    *   **2: Process File to TSV:** Convert PDF or TXT files to TSV using Gemini AI. Choose between Visual Q&A and Text Analysis modes.
    *   **3: Tag TSV File:**  Tag rows in an existing TSV file using Gemini AI for batch tagging.
    *   **4: Workflow (File->TSV->Tag):**  Automated workflow to process files to TSV and then tag them in sequence.

### Setting up API Key

*   Enter your Gemini API key in the "Gemini API Key" field in Page 2, Page 3, or Page 4. The API key is shared across all pages.
*   Use the "Show/Hide" button to toggle the visibility of the API key for security.

### Using the Features

Each tab provides a specific function with its own set of configurations and options. Refer to the in-app labels and tooltips for guidance on using each feature.  Key workflows include:

*   **Visual Q&A Workflow (Page 2 & 4):**  Process PDF quizzes visually, generating images and extracting Q&A pairs into a TSV for Anki with image links.
*   **Text Analysis Workflow (Page 2 & 4):** Analyze text content from PDFs or TXT files to extract information and create TSV files for Anki.
*   **TSV Tagging (Page 3 & 4):**  Tag existing TSV files to categorize your flashcards automatically using Gemini AI.
*   **Anki Export (Page 1):** Export specific notes from your Anki collection to TSV for further processing or backup.

## Notes

*   **Error Handling:** The application includes error handling and logging. Check the "Status Log" areas in each page for details on processing steps and any errors encountered. Error dialogs will also appear for critical issues.
*   **PyMuPDF Dependency:**  PDF-related features (image generation, PDF text extraction) require the PyMuPDF library. Ensure it is installed for full functionality.
*   **API Usage:** Be mindful of Gemini API usage and rate limits, especially when processing large files or batches. The "Tag TSV File" and "Workflow" pages include options to control batch sizes and API delays to help manage API calls.

This refactored AnkiTagProcessor provides a more modular and maintainable codebase, making it easier to extend and improve its features in the future.
