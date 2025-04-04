# ui/page1_anki_export.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
import os
import traceback

# Import necessary components from other modules using relative paths
try:
    from ..core.anki_connect import invoke_anki_connect, ProcessingError as AnkiProcessingError
    from ..utils.helpers import show_error_dialog # Use helper for consistency if desired
except ImportError:
    # Fallback for direct execution or different structure
    print("Error: Relative imports failed in page1_anki_export.py. Using direct imports.")
    from ..core.anki_connect import invoke_anki_connect, ProcessingError as AnkiProcessingError
    from ..utils.helpers import show_error_dialog


class AnkiExportPage(ttk.Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app_instance # Reference to the main application

        # --- Page 1 Variables (Local State) ---
        self.p1_selected_deck = tk.StringVar()
        # These lists store the actual tag/field names, not Listbox items
        self.p1_include_tags = []
        self.p1_exclude_tags = []
        self.p1_selected_fields = []
        self.p1_available_fields = [] # Fields for the currently selected deck's note type

        # --- Build UI ---
        self._build_ui()

        # Populate initial data if available from app instance
        self.update_anki_data(self.app.anki_decks, self.app.anki_tags, self.app.anki_note_types)
        print("Initialized AnkiExportPage")

    def _build_ui(self):
        """Creates the UI elements for Page 1."""
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        middle_frame = ttk.Frame(self)
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="Select Deck:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.p1_deck_combo = ttk.Combobox(top_frame, textvariable=self.p1_selected_deck, state="readonly", values=self.app.anki_decks) # Use app data for initial values
        self.p1_deck_combo.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        top_frame.grid_columnconfigure(1, weight=1)
        self.p1_deck_combo.bind("<<ComboboxSelected>>", self._on_deck_selected)

        # --- Tags Frame ---
        tag_frame = ttk.LabelFrame(middle_frame, text="Tags")
        tag_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5), pady=5)
        # Available Tags
        available_tag_frame = ttk.Frame(tag_frame)
        available_tag_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(available_tag_frame, text="Available Tags:").pack(anchor=tk.W)
        self.p1_available_tags_listbox = tk.Listbox(available_tag_frame, selectmode=tk.EXTENDED)
        self.p1_available_tags_listbox.pack(fill=tk.BOTH, expand=True)
        tags_scrollbar = ttk.Scrollbar(available_tag_frame, orient=tk.VERTICAL, command=self.p1_available_tags_listbox.yview)
        tags_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.p1_available_tags_listbox.config(yscrollcommand=tags_scrollbar.set)
        # Tag Buttons
        tag_button_frame = ttk.Frame(tag_frame)
        tag_button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        ttk.Button(tag_button_frame, text="Include >", command=self._include_selected_tags).pack(pady=5, fill=tk.X)
        ttk.Button(tag_button_frame, text="< Remove", command=self._remove_included_tags).pack(pady=5, fill=tk.X)
        ttk.Button(tag_button_frame, text="Exclude >", command=self._exclude_selected_tags).pack(pady=5, fill=tk.X)
        ttk.Button(tag_button_frame, text="< Remove", command=self._remove_excluded_tags).pack(pady=5, fill=tk.X)
        ttk.Button(tag_button_frame, text="Untagged", command=self._select_untagged).pack(pady=5, fill=tk.X)
        # Selected Tags
        selected_tag_frame = ttk.Frame(tag_frame)
        selected_tag_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(selected_tag_frame, text="Include Tags:").pack(anchor=tk.W)
        self.p1_included_tags_listbox = tk.Listbox(selected_tag_frame, height=6)
        self.p1_included_tags_listbox.pack(fill=tk.BOTH, expand=True)
        ttk.Label(selected_tag_frame, text="Exclude Tags:").pack(anchor=tk.W)
        self.p1_excluded_tags_listbox = tk.Listbox(selected_tag_frame, height=6)
        self.p1_excluded_tags_listbox.pack(fill=tk.BOTH, expand=True)

        # --- Fields Frame ---
        fields_frame = ttk.LabelFrame(middle_frame, text="Fields")
        fields_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        # Available Fields
        available_fields_frame = ttk.Frame(fields_frame)
        available_fields_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(available_fields_frame, text="Available Fields:").pack(anchor=tk.W)
        self.p1_available_fields_listbox = tk.Listbox(available_fields_frame, selectmode=tk.EXTENDED)
        self.p1_available_fields_listbox.pack(fill=tk.BOTH, expand=True)
        # Field Buttons
        field_button_frame = ttk.Frame(fields_frame)
        field_button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        ttk.Button(field_button_frame, text="Add >", command=self._add_selected_fields).pack(pady=5, fill=tk.X)
        ttk.Button(field_button_frame, text="< Remove", command=self._remove_selected_fields).pack(pady=5, fill=tk.X)
        ttk.Button(field_button_frame, text="Move Up", command=self._move_field_up).pack(pady=5, fill=tk.X)
        ttk.Button(field_button_frame, text="Move Down", command=self._move_field_down).pack(pady=5, fill=tk.X)
        # Selected Fields
        selected_fields_frame = ttk.Frame(fields_frame)
        selected_fields_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(selected_fields_frame, text="Selected Fields:").pack(anchor=tk.W)
        self.p1_selected_fields_listbox = tk.Listbox(selected_fields_frame)
        self.p1_selected_fields_listbox.pack(fill=tk.BOTH, expand=True)

        # --- Export Button ---
        ttk.Button(bottom_frame, text="Export to TSV", command=self._export_to_tsv).pack(side=tk.RIGHT, padx=5, pady=5)

    def update_anki_data(self, decks, tags, note_types):
        """Updates the UI with the latest data loaded from Anki."""
        # Update deck dropdown
        if hasattr(self, 'p1_deck_combo'):
            self.p1_deck_combo["values"] = decks
            if decks and not self.p1_selected_deck.get():
                self.p1_selected_deck.set(decks[0]) # Select first deck if none selected
                self._on_deck_selected(None) # Trigger field update

        # Update available tags listbox
        if hasattr(self, 'p1_available_tags_listbox'):
            self.p1_available_tags_listbox.delete(0, tk.END)
            for tag in sorted(tags):
                self.p1_available_tags_listbox.insert(tk.END, tag)

        # Clear fields if deck changed or data reloaded
        if hasattr(self, 'p1_available_fields_listbox'): self.p1_available_fields_listbox.delete(0, tk.END)
        if hasattr(self, 'p1_selected_fields_listbox'): self.p1_selected_fields_listbox.delete(0, tk.END)
        self.p1_available_fields = []
        self.p1_selected_fields = []

        # Trigger update for the currently selected deck's fields
        self._on_deck_selected(None)


    def _on_deck_selected(self, event):
        """Handles deck selection change."""
        deck = self.p1_selected_deck.get()
        if not deck: return

        # Clear previous field lists
        self.p1_available_fields_listbox.delete(0, tk.END)
        self.p1_selected_fields_listbox.delete(0, tk.END)
        self.p1_available_fields = []
        self.p1_selected_fields = []

        query = f'deck:"{deck}"'
        try:
            # Use imported invoke_anki_connect
            note_ids = invoke_anki_connect("findNotes", {"query": query})
            if not note_ids:
                # Don't show messagebox here, just clear fields
                print(f"Info: No notes found in deck '{deck}'.")
                return

            # Get info for the first note to find the model
            notes_info = invoke_anki_connect("notesInfo", {"notes": [note_ids[0]]})
            if not notes_info or not isinstance(notes_info, list) or not notes_info[0]:
                 messagebox.showerror("Error", "Could not retrieve note information.", parent=self)
                 return

            first_note_info = notes_info[0]
            model_name = first_note_info.get("modelName")

            # Use the note_types data stored in the app instance
            if not model_name or model_name not in self.app.anki_note_types:
                 messagebox.showerror("Error", f"Could not determine note type or fields for deck '{deck}'. Model: '{model_name}'", parent=self)
                 return

            fields = self.app.anki_note_types[model_name]
            self.p1_available_fields = sorted(fields)
            for field in self.p1_available_fields:
                self.p1_available_fields_listbox.insert(tk.END, field)

        except AnkiProcessingError as e:
            messagebox.showerror("AnkiConnect Error", f"Failed to get fields for deck '{deck}':\n{e}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error getting fields for deck '{deck}':\n{e}", parent=self)

    def _include_selected_tags(self):
        selected_indices = self.p1_available_tags_listbox.curselection()
        current_included = set(self.p1_included_tags_listbox.get(0, tk.END))
        for i in selected_indices:
            tag = self.p1_available_tags_listbox.get(i)
            if tag not in current_included:
                self.p1_included_tags_listbox.insert(tk.END, tag)
        # Update the internal list directly from the listbox content
        self.p1_include_tags = list(self.p1_included_tags_listbox.get(0, tk.END))

    def _exclude_selected_tags(self):
        selected_indices = self.p1_available_tags_listbox.curselection()
        current_excluded = set(self.p1_excluded_tags_listbox.get(0, tk.END))
        for i in selected_indices:
            tag = self.p1_available_tags_listbox.get(i)
            if tag not in current_excluded:
                self.p1_excluded_tags_listbox.insert(tk.END, tag)
        self.p1_exclude_tags = list(self.p1_excluded_tags_listbox.get(0, tk.END))

    def _remove_included_tags(self):
        selected_indices = self.p1_included_tags_listbox.curselection()
        for i in reversed(selected_indices):
            self.p1_included_tags_listbox.delete(i)
        self.p1_include_tags = list(self.p1_included_tags_listbox.get(0, tk.END))

    def _remove_excluded_tags(self):
        selected_indices = self.p1_excluded_tags_listbox.curselection()
        for i in reversed(selected_indices):
            self.p1_excluded_tags_listbox.delete(i)
        self.p1_exclude_tags = list(self.p1_excluded_tags_listbox.get(0, tk.END))

    def _select_untagged(self):
        self.p1_included_tags_listbox.delete(0, tk.END)
        self.p1_excluded_tags_listbox.delete(0, tk.END)
        untagged_marker = "untagged" # Use a consistent marker
        self.p1_included_tags_listbox.insert(tk.END, untagged_marker)
        self.p1_include_tags = [untagged_marker]
        self.p1_exclude_tags = []

    def _add_selected_fields(self):
        selected_indices = self.p1_available_fields_listbox.curselection()
        current_selected = set(self.p1_selected_fields_listbox.get(0, tk.END))
        for i in selected_indices:
            field = self.p1_available_fields_listbox.get(i)
            if field not in current_selected:
                self.p1_selected_fields_listbox.insert(tk.END, field)
        self.p1_selected_fields = list(self.p1_selected_fields_listbox.get(0, tk.END))

    def _remove_selected_fields(self):
        selected_indices = self.p1_selected_fields_listbox.curselection()
        for i in reversed(selected_indices):
            self.p1_selected_fields_listbox.delete(i)
        self.p1_selected_fields = list(self.p1_selected_fields_listbox.get(0, tk.END))

    def _move_field(self, direction):
        """Internal helper to move selected field up or down."""
        selected_indices = self.p1_selected_fields_listbox.curselection()
        if not selected_indices: return
        index = selected_indices[0] # Move only one at a time

        if direction == "up" and index > 0:
            new_index = index - 1
        elif direction == "down" and index < self.p1_selected_fields_listbox.size() - 1:
            new_index = index + 1
        else:
            return # Cannot move further

        field = self.p1_selected_fields_listbox.get(index)
        self.p1_selected_fields_listbox.delete(index)
        self.p1_selected_fields_listbox.insert(new_index, field)
        # Keep the moved item selected and active
        self.p1_selected_fields_listbox.selection_set(new_index)
        self.p1_selected_fields_listbox.activate(new_index)
        # Update the internal list state
        self.p1_selected_fields = list(self.p1_selected_fields_listbox.get(0, tk.END))

    def _move_field_up(self):
        self._move_field("up")

    def _move_field_down(self):
        self._move_field("down")

    def _export_to_tsv(self):
        deck = self.p1_selected_deck.get()
        if not deck:
            messagebox.showerror("Error", "Please select a deck.", parent=self)
            return

        # Get fields directly from the listbox at the time of export
        self.p1_selected_fields = list(self.p1_selected_fields_listbox.get(0, tk.END))
        if not self.p1_selected_fields:
            messagebox.showerror("Error", "Please select at least one field.", parent=self)
            return

        # Get tags directly from listboxes
        self.p1_include_tags = list(self.p1_included_tags_listbox.get(0, tk.END))
        self.p1_exclude_tags = list(self.p1_excluded_tags_listbox.get(0, tk.END))

        # Build AnkiConnect query
        query = f'deck:"{deck}"'
        include_tag_parts = []
        exclude_tag_parts = []
        is_untagged_query = False

        if "untagged" in self.p1_include_tags:
            include_tag_parts.append("tag:none")
            is_untagged_query = True
            # Include other tags as OR conditions if present
            temp_include_tags = [t for t in self.p1_include_tags if t != "untagged"]
            for tag in temp_include_tags:
                include_tag_parts.append(f'tag:"{tag}"')
        else:
            for tag in self.p1_include_tags:
                include_tag_parts.append(f'tag:"{tag}"')

        for tag in self.p1_exclude_tags:
            exclude_tag_parts.append(f'-tag:"{tag}"')

        if include_tag_parts:
            # If only 'untagged' is included, just add 'tag:none'
            if len(include_tag_parts) == 1 and is_untagged_query:
                query += f" {include_tag_parts[0]}"
            else: # Otherwise, use OR for included tags
                query += " (" + " OR ".join(include_tag_parts) + ")"

        if exclude_tag_parts:
            query += " " + " ".join(exclude_tag_parts)

        print(f"Anki Query: {query}")

        try:
            note_ids = invoke_anki_connect("findNotes", {"query": query})
            if not note_ids:
                messagebox.showinfo("Info", "No notes found matching criteria.", parent=self)
                return

            notes_info = invoke_anki_connect("notesInfo", {"notes": note_ids})
            if not notes_info:
                messagebox.showerror("Error", "Failed to retrieve note info.", parent=self)
                return

            file_path = filedialog.asksaveasfilename(
                parent=self,
                title="Save Exported Notes As TSV",
                defaultextension=".txt",
                filetypes=[("Text files (TSV)", "*.txt"), ("TSV files", "*.tsv"), ("All files", "*.*")]
            )
            if not file_path:
                return # User cancelled save dialog

            exported_count = 0
            with open(file_path, "w", encoding="utf-8", newline='') as f: # Added newline=''
                f.write("\t".join(self.p1_selected_fields) + "\n") # Write header
                for note in notes_info:
                    row = []
                    valid_note = True
                    if "fields" not in note:
                        print(f"Warning: Skipping note ID {note.get('noteId', 'N/A')} - no 'fields'.")
                        valid_note = False
                        continue # Skip this note

                    for field_name in self.p1_selected_fields:
                        field_data = note["fields"].get(field_name)
                        if field_data and "value" in field_data:
                            content = field_data["value"]
                            # Basic HTML stripping and newline/tab replacement
                            content = re.sub('<[^<]+?>', '', content)
                            content = content.replace("\n", " ").replace("\r", " ").replace("\t", " ")
                            row.append(content.strip())
                        else:
                            # Log missing field but still add an empty cell
                            print(f"Warning: Field '{field_name}' missing or invalid in note ID {note.get('noteId', 'N/A')}. Appending empty string.")
                            row.append("")

                    if valid_note:
                        f.write("\t".join(row) + "\n")
                        exported_count += 1

            messagebox.showinfo("Success", f"Exported {exported_count} notes to\n{file_path}", parent=self)

            # Ask to switch to Page 3 (Tagging)
            if self.app.switch_to_page: # Check if method exists on app
                 if messagebox.askyesno("Proceed?", f"Exported {exported_count} notes.\nSwitch to 'Tag TSV File' page and load this file?", parent=self):
                     # Use self.after to ensure switch happens on main thread
                     self.after(0, self.app.switch_to_page, 2, file_path) # Page 3 is index 2

        except AnkiProcessingError as e:
            messagebox.showerror("Export Error", f"AnkiConnect error during export:\n{e}\nQuery: {query}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export notes: {e}\nQuery: {query}\n\n{traceback.format_exc()}", parent=self)
