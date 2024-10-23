import sys
import os
import re
import traceback
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QFileDialog,
    QLabel,
    QTextEdit,
    QProgressBar,
    QCheckBox,
    QVBoxLayout,
    QHBoxLayout,
)
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal


class WorkerThread(QThread):
    progress_updated = pyqtSignal(int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, folder_path, i18n_data, include_message, include_characters_dialogue, include_strings_schedules, include_events):
        super().__init__()
        self.folder_path = folder_path
        self.i18n_data = i18n_data
        self.npc_names = {}
        self.include_message = include_message
        self.include_characters_dialogue = include_characters_dialogue
        self.include_strings_schedules = include_strings_schedules
        self.include_events = include_events

    def run(self):
        # Recursive file system traversal
        text_files = []
        for root, _, filenames in os.walk(self.folder_path):
            for filename in filenames:
                if filename.endswith(".json"):
                    text_files.append(os.path.join(root, filename))

        total_files = len(text_files)
        processed_files = 0

        # Dictionary to store (i18n_key, npc_name) pairs
        self.npc_names = {}

        for file_path in text_files:
            self.log_message.emit(f"Processing file: {file_path}")
            self.processTextFile(file_path)
            processed_files += 1
            progress = int((processed_files / total_files) * 100)
            self.progress_updated.emit(progress)

        self.log_message.emit(f"Dictionary npc_names: {self.npc_names}")
        self.finished.emit(
            {"i18n_data": self.i18n_data, "npc_names": self.npc_names}
        )

    def processTextFile(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text_data = f.read()

            # Find all i18n keys and NPC names in the file
            self.find_i18n_keys_and_npc_names(text_data)

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            error_message = f"Error in file {file_path}:\n"
            error_message += f"{exc_type.__name__}: {exc_value}\n"
            error_message += "".join(
                traceback.format_tb(exc_traceback, limit=10)
            )
            self.log_message.emit(error_message)

    def find_i18n_keys_and_npc_names(self, text_data):
        # Поиск speak, dialogue, textAboveHead, dialogueWarpOut (только если включена галочка "Events")
        if self.include_events:
            # Find speak (case-insensitive)
            matches_speak = re.findall(
                r'[Ss]peak\s+([a-zA-Z0-9_.-]+)\s+\\"\s*{{i18n:([a-zA-Z0-9_.-]+)}}\s*\\?"',
                text_data,
            )
            for npc_name, i18n_key in matches_speak:
                self.npc_names[i18n_key] = npc_name

            # Find dialogue NpcName
            matches_dialogue = re.findall(
                r'[Dd]ialogue\s+([a-zA-Z0-9_.-]+)\s+\\"\s*{{i18n:([a-zA-Z0-9_.-]+)}}\s*\\?"',
                text_data,
            )
            for npc_name, i18n_key in matches_dialogue:
                self.npc_names[i18n_key] = npc_name

            # Find textAboveHead (case-insensitive)
            matches_text_above_head = re.findall(
                r'[Tt]ext[Aa]bove[Hh]ead\s+([a-zA-Z0-9_.-]+)\s+\\"\s*{{i18n:([a-zA-Z0-9_.-]+)}}\s*\\?"',
                text_data,
            )
            for npc_name, i18n_key in matches_text_above_head:
                self.npc_names[i18n_key] = npc_name

            # Find dialogueWarpOut
            matches_dialogue_warp_out = re.findall(
                r'[Dd]ialogue[Ww]arp[Oo]ut\s+([a-zA-Z0-9_.-]+)\s+\\"\s*{{i18n:([a-zA-Z0-9_.-]+)}}\s*\\?"',
                text_data,
            )
            for npc_name, i18n_key in matches_dialogue_warp_out:
                self.npc_names[i18n_key] = npc_name

        # Find message (only if checkbox is checked)
        if self.include_message:
            matches_message = re.findall(
                r'[Mm]essage\s+\\"\s*{{i18n:([a-zA-Z0-9_.-]+)}}\s*\\?"',
                text_data,
            )
            for i18n_key in matches_message:
                self.npc_names[i18n_key] = "message"

        # Check if we need to process Characters/Dialogue/ (case-insensitive)
        if self.include_characters_dialogue:
            npc_name = None  # Initialize the NPC name
            inside_entries = False  # Flag to track if we are inside an "Entries" block
            brace_level = 0  # Variable to track the level of curly brace nesting
            target_found = False  # Flag to track if "Target" has been found for the current block
            combined_line = ""  # Variable to store combined lines for a single Entries block

            for line in text_data.splitlines():
                # Check for NPC name in the Target line (case-insensitive), excluding rainy
                target_match = re.search(r'"Target": "[Cc]haracters/[Dd]ialogue/([a-zA-Z0-9_.-]+)",', line)
                if target_match and "rainy" not in line:
                    npc_name = target_match.group(1)
                    inside_entries = False  # Reset the entries flag for a new NPC
                    target_found = True  # Set the target_found flag
                    combined_line = ""  # Reset combined_line

                # Check if we are inside the Entries block
                if npc_name:
                    # Combine lines for a single Entries block
                    combined_line += line.strip()  # Add the current line to combined_line

                    # Check for the start of the Entries block
                    if ('"Entries":' in combined_line or '"entries":' in combined_line) and target_found:
                        brace_level = combined_line.count('{') - combined_line.count('}')  # Initialize brace level
                        if brace_level > 0:
                            inside_entries = True
                            target_found = False
                        continue

                    if inside_entries:
                        # Update the brace level
                        brace_level += line.count('{') - line.count('}')

                        # Check for the end of the Entries block
                        if brace_level == 0:
                            # Find all i18n keys in the combined line
                            i18n_key_matches = re.findall(r'{{i18n:([a-zA-Z0-9_.-]+)}}', combined_line)
                            for i18n_key in i18n_key_matches:
                                self.npc_names[i18n_key] = npc_name  # Associate the i18n key with the NPC name

                            inside_entries = False
                            npc_name = None
                            combined_line = ""  # Reset combined_line

        # Check if we need to process Strings/schedules/ (case-insensitive)
        if self.include_strings_schedules:
            npc_name = None  # Initialize the NPC name
            inside_entries = False  # Flag to track if we are inside an "Entries" block
            brace_level = 0  # Variable to track the level of curly brace nesting
            target_found = False  # Flag to track if "Target" has been found for the current block
            combined_line = ""  # Variable to store combined lines for a single Entries block

            for line in text_data.splitlines():
                # Check for NPC name in the Target line (case-insensitive)
                target_match = re.search(r'"Target": "[Ss]trings/[Ss]chedules/([a-zA-Z0-9_.-]+)",', line)
                if target_match:
                    npc_name = target_match.group(1)
                    inside_entries = False  # Reset the entries flag for a new NPC
                    target_found = True  # Set the target_found flag
                    combined_line = ""  # Reset combined_line

                # Check if we are inside the Entries block
                if npc_name:
                    # Combine lines for a single Entries block
                    combined_line += line.strip()  # Add the current line to combined_line

                    # Check for the start of the Entries block
                    if ('"Entries":' in combined_line or '"entries":' in combined_line) and target_found:
                        brace_level = combined_line.count('{') - combined_line.count('}')  # Initialize brace level
                        if brace_level > 0:
                            inside_entries = True
                            target_found = False
                        continue

                    if inside_entries:
                        # Update the brace level
                        brace_level += line.count('{') - line.count('}')

                        # Check for the end of the Entries block
                        if brace_level == 0:
                            # Find all i18n keys in the combined line
                            i18n_key_matches = re.findall(r'{{i18n:([a-zA-Z0-9_.-]+)}}', combined_line)
                            for i18n_key in i18n_key_matches:
                                self.npc_names[i18n_key] = npc_name  # Associate the i18n key with the NPC name

                            inside_entries = False
                            npc_name = None
                            combined_line = ""  # Reset combined_line


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("SV i18n Comment Namer by Alex(GoD)")
        self.setGeometry(100, 100, 800, 600)

        # Dark Theme
        self.setDarkTheme()

        # Main layout
        main_layout = QVBoxLayout()

        # Top layout for button and folder path
        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)

        # Folder selection button
        self.btn_select_folder = QPushButton("Select Folder", self)
        self.btn_select_folder.clicked.connect(self.selectFolder)
        self.btn_select_folder.setStyleSheet(
            "background-color: #4CAF50; color: white;"
        )
        top_layout.addWidget(self.btn_select_folder)

        # Label to display the selected folder path
        self.lbl_folder_path = QLabel("", self)
        top_layout.addWidget(self.lbl_folder_path)

        # Text field to display logs
        self.txt_logs = QTextEdit(self)
        self.txt_logs.setReadOnly(True)
        main_layout.addWidget(self.txt_logs)

        # Bottom layout for checkboxes and progress bar
        bottom_layout = QHBoxLayout()
        main_layout.addLayout(bottom_layout)

        # Checkbox "Include message"
        self.checkbox_include_message = QCheckBox("Include message", self)
        self.checkbox_include_message.setChecked(False)
        bottom_layout.addWidget(self.checkbox_include_message)

        # Checkbox "Don't add comments to lines with existing comments"
        self.checkbox_skip_commented_lines = QCheckBox(
            "Don't add comments to lines with existing comments", self
        )
        self.checkbox_skip_commented_lines.setChecked(False)
        bottom_layout.addWidget(self.checkbox_skip_commented_lines)

        # Checkbox "Include Characters/Dialogue/"
        self.checkbox_include_characters_dialogue = QCheckBox("Include Characters/Dialogue/", self)
        self.checkbox_include_characters_dialogue.setChecked(False)
        bottom_layout.addWidget(self.checkbox_include_characters_dialogue)

        # Checkbox "Include Strings/schedules/"
        self.checkbox_include_strings_schedules = QCheckBox("Include Strings/schedules/", self)
        self.checkbox_include_strings_schedules.setChecked(False)
        bottom_layout.addWidget(self.checkbox_include_strings_schedules)

        # Checkbox "Include Events"
        self.checkbox_include_events = QCheckBox("Include Events", self)
        self.checkbox_include_events.setChecked(False)  # Выключена по умолчанию
        bottom_layout.addWidget(self.checkbox_include_events)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        bottom_layout.addWidget(self.progress_bar)

        self.setLayout(main_layout)
        self.worker_thread = None

        # Corrected signals
        self.worker_thread_progress_updated = pyqtSignal(int)
        self.worker_thread_log_message = pyqtSignal(str)
        self.worker_thread_finished = pyqtSignal(dict)

        self.show()

    def setDarkTheme(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        QApplication.setPalette(palette)

    def selectFolder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Folder"
        )
        if folder_path:
            self.lbl_folder_path.setText(folder_path)
            self.processFolder(folder_path)

    def processFolder(self, folder_path):
        i18n_path = os.path.join(folder_path, "i18n", "default.json")
        if not os.path.exists(i18n_path):
            self.log("File i18n/default.json not found!")
            return

        try:
            # Open default.json as a text file
            with open(i18n_path, "r", encoding="utf-8") as f:
                i18n_data = f.readlines()
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            error_message = f"Error in file {i18n_path}:\n"
            error_message += f"{exc_type.__name__}: {exc_value}\n"
            error_message += "".join(
                traceback.format_tb(exc_traceback, limit=10)
            )
            self.log(error_message)
            return

        # Create and start the processing thread
        self.worker_thread = WorkerThread(
            folder_path,
            i18n_data,
            self.checkbox_include_message.isChecked(),
            self.checkbox_include_characters_dialogue.isChecked(),
            self.checkbox_include_strings_schedules.isChecked(),
            self.checkbox_include_events.isChecked(),  # Pass the checkbox value
        )
        self.worker_thread.progress_updated.connect(
            self.updateProgressBar
        )
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.finished.connect(self.onProcessingFinished)
        self.worker_thread.start()

    def updateProgressBar(self, progress):
        self.progress_bar.setValue(progress)

    def onProcessingFinished(self, result):
        i18n_data = result["i18n_data"]
        npc_names = result["npc_names"]
        i18n_path = os.path.join(
            self.lbl_folder_path.text(), "i18n", "default.json"
        )

        self.log(f"Received dictionary npc_names: {npc_names}")

        # Save the modified default.json to a new file default_with_comments.json
        default_with_comments_path = os.path.join(
            self.lbl_folder_path.text(),
            "i18n",
            "default_with_comments.json",
        )
        with open(default_with_comments_path, "w", encoding="utf-8") as f:
            # Write lines from i18n_data to the file and add comments
            for line in i18n_data:
                comment = ""  # Initialize the comment variable

                # Check if we need to skip the line with a comment
                if self.checkbox_skip_commented_lines.isChecked() and "//" in line:
                    f.write(line)
                    continue  # Move to the next line

                # Check if the line contains an i18n key
                for i18n_key, npc_name in npc_names.items():
                    if i18n_key in line:
                        comment = f" //{npc_name}"  # Save the comment
                        break  # Exit the loop if a comment is found

                # Write the line and comment together
                f.write(line.rstrip("\n") + comment + "\n")

        self.log("File i18n/default_with_comments.json updated!")
        self.worker_thread = None


    def log(self, message):
        self.txt_logs.append(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())
