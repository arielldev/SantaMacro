"""
Settings GUI for SantaMacro - Simple configuration interface using PySide6
"""
import json
import os
import sys
import time
import threading
import tempfile
import shutil
import zipfile
from typing import Dict, List, Any, Optional
from pynput import mouse, keyboard as pynput_keyboard
from datetime import datetime
from action_system import ActionRecorder as FullActionRecorder

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QCheckBox,
    QGroupBox, QFormLayout, QMessageBox, QSpinBox, QDoubleSpinBox,
    QDialog, QDialogButtonBox, QProgressBar, QSystemTrayIcon, QMenu,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
    QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QKeySequence, QIcon, QPixmap, QAction
import requests


class UpdateWorker(QThread):
    """Worker thread for handling updates"""
    progress = Signal(str, str)  # message, status
    finished = Signal(bool, str)  # success, message
    
    def __init__(self):
        super().__init__()
        self.repo_url = "https://api.github.com/repos/arielldev/SantaMacro/commits/main"
        self.download_url = "https://github.com/arielldev/SantaMacro/archive/refs/heads/main.zip"
    
    def run(self):
        """Check for updates and download if available"""
        try:
            self.progress.emit("Checking for updates...", "info")
            
            # Check GitHub for latest commit
            response = requests.get(self.repo_url, timeout=10)
            if response.status_code != 200:
                self.finished.emit(False, f"GitHub API returned status {response.status_code}")
                return
            
            commit_data = response.json()
            commit_hash = commit_data['sha'][:7]
            commit_message = commit_data['commit']['message'].split('\n')[0]
            
            self.progress.emit(f"Found update: {commit_hash}", "info")
            
            # Download the update
            self.progress.emit("Downloading update...", "info")
            response = requests.get(self.download_url, timeout=60, stream=True)
            if response.status_code != 200:
                self.finished.emit(False, "Download failed")
                return
            
            # Install the update
            self._install_update(response, commit_hash, commit_message)
            
        except requests.exceptions.ConnectionError:
            self.finished.emit(False, "No internet connection")
        except requests.exceptions.Timeout:
            self.finished.emit(False, "Request timed out")
        except Exception as e:
            self.finished.emit(False, f"Update failed: {str(e)}")
    
    def _install_update(self, response, commit_hash, commit_message):
        """Install the downloaded update"""
        try:
            # Use temporary directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "update.zip")
                
                self.progress.emit("Saving update file...", "info")
                # Save the downloaded file
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                self.progress.emit("Extracting update...", "info")
                # Extract the zip file
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Find the extracted folder
                extracted_folder = None
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path) and 'santamacro' in item.lower():
                        extracted_folder = item_path
                        break
                
                if not extracted_folder:
                    self.finished.emit(False, "Extraction failed - folder not found")
                    return
                
                self.progress.emit("Installing update...", "info")
                
                # Get the project root directory
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                
                # Create backup folder
                backup_dir = os.path.join(project_root, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                os.makedirs(backup_dir, exist_ok=True)
                
                # Files and folders to preserve (user data)
                preserve_items = [
                    'config.json',
                    'Model.pt',
                    '.git',
                    '.gitignore',
                    'backup_*'
                ]
                
                # Backup current installation
                self.progress.emit("Creating backup...", "info")
                for item in os.listdir(project_root):
                    if item.startswith('backup_'):
                        continue
                    
                    src_path = os.path.join(project_root, item)
                    backup_path = os.path.join(backup_dir, item)
                    
                    try:
                        if os.path.isdir(src_path):
                            shutil.copytree(src_path, backup_path, ignore_errors=True)
                        else:
                            shutil.copy2(src_path, backup_path)
                    except Exception:
                        pass  # Continue if backup fails
                
                # Install new files
                self.progress.emit("Installing new files...", "info")
                for item in os.listdir(extracted_folder):
                    # Skip preserved items
                    if any(item.startswith(preserve) or item == preserve for preserve in preserve_items):
                        continue
                    
                    src_path = os.path.join(extracted_folder, item)
                    dst_path = os.path.join(project_root, item)
                    
                    try:
                        # Remove existing file/folder
                        if os.path.exists(dst_path):
                            if os.path.isdir(dst_path):
                                shutil.rmtree(dst_path)
                            else:
                                os.remove(dst_path)
                        
                        # Copy new file/folder
                        if os.path.isdir(src_path):
                            shutil.copytree(src_path, dst_path)
                        else:
                            shutil.copy2(src_path, dst_path)
                        
                    except Exception:
                        pass  # Continue if individual file fails
                
                self.finished.emit(True, f"Update complete! ({commit_hash})")
                
        except Exception as e:
            self.finished.emit(False, f"Installation failed: {str(e)}")


class UpdateDialog(QDialog):
    """Update progress dialog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SantaMacro Update")
        self.setFixedSize(400, 200)
        self.setModal(True)
        
        # Christmas theme
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                color: #2d2d2d;
            }
            QLabel {
                color: #2d2d2d;
            }
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                text-align: center;
                background-color: #f8f9fa;
            }
            QProgressBar::chunk {
                background-color: #dc3545;
                border-radius: 3px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("🎄 Updating SantaMacro")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #dc3545; margin: 10px;")
        layout.addWidget(title)
        
        # Status
        self.status_label = QLabel("Preparing update...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)
        
        # Close button (initially disabled)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setEnabled(False)
        layout.addWidget(self.close_btn)
    
    def update_status(self, message, status):
        """Update the status message"""
        self.status_label.setText(message)
        if status == "success":
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            self.close_btn.setEnabled(True)
        elif status == "error":
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.close_btn.setEnabled(True)


class RecordingConfirmDialog(QDialog):
    """Confirmation dialog for recording actions"""
    
    def __init__(self, parent=None, is_start=True):
        super().__init__(parent)
        self.is_start = is_start
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the dialog UI"""
        if self.is_start:
            self.setWindowTitle("Start Recording")
            title = "🔴 Start Recording"
            message = "Record your attack sequence.\nPress F3 again to stop."
        else:
            self.setWindowTitle("Recording Complete")
            title = "✅ Recording Complete"
            message = "Attack sequence recorded!\nClick 'Save' to keep it."
        
        self.setFixedSize(400, 200)
        
        # Christmas theme
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                color: #2d2d2d;
            }
            QLabel {
                color: #2d2d2d;
            }
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #a71e2a;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #dc3545; margin: 10px;")
        layout.addWidget(title_label)
        
        # Message
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setStyleSheet("margin: 10px; font-size: 12px;")
        layout.addWidget(message_label)
        
        # Buttons
        button_box = QDialogButtonBox()
        
        if self.is_start:
            ok_btn = button_box.addButton("Start Recording", QDialogButtonBox.AcceptRole)
            cancel_btn = button_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        else:
            ok_btn = button_box.addButton("Save Sequence", QDialogButtonBox.AcceptRole)
            cancel_btn = button_box.addButton("Discard", QDialogButtonBox.RejectRole)
        
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)


class SettingsGUI(QMainWindow):
    """Simple settings GUI for SantaMacro using PySide6"""
    
    def __init__(self, config_path: str, macro_instance=None):
        # Ensure we're in the main thread
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QThread
        
        app = QApplication.instance()
        if app and QThread.currentThread() != app.thread():
            raise RuntimeError("SettingsGUI must be created in the main Qt thread")
        
        super().__init__()
        self.config_path = config_path
        self.config = {}
        self.macro_instance = macro_instance  # Store reference to macro
        
        self.load_config()
        self.setup_ui()
        self.load_settings()
        self.setup_system_tray()
    
    def setup_system_tray(self):
        """Setup system tray icon for recording control"""
        try:
            # Create a more visible icon (larger red square)
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.red)
            icon = QIcon(pixmap)
            
            # Create system tray icon
            self.tray_icon = QSystemTrayIcon(icon, self)
            self.tray_icon.setToolTip("SantaMacro Settings - Right-click for options")
            
            # Create context menu
            tray_menu = QMenu()
            
            # Show/Hide settings action
            self.show_action = QAction("📱 Show Settings", self)
            self.show_action.triggered.connect(self.show_settings)
            tray_menu.addAction(self.show_action)
            
            tray_menu.addSeparator()
            
            # Exit action
            exit_action = QAction("❌ Exit", self)
            exit_action.triggered.connect(self.close)
            tray_menu.addAction(exit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            
            # Show tray icon
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray_icon.show()
                print("System tray icon created successfully - Look for RED SQUARE in tray!")
                
                # Show immediate notification about tray icon
                QTimer.singleShot(1000, lambda: self.tray_icon.showMessage(
                    "SantaMacro Ready", 
                    "Red tray icon active! Right-click for recording controls.", 
                    QSystemTrayIcon.Information, 
                    5000
                ))
            else:
                print("System tray not available")
                self.tray_icon = None
                
        except Exception as e:
            print(f"Failed to setup system tray: {e}")
            self.tray_icon = None
    
    def show_settings(self):
        """Show the settings window from tray"""
        self.show()
        self.raise_()
        self.activateWindow()
    
    def closeEvent(self, event):
        """Handle window close event"""
        super().closeEvent(event)
    
    def add_action_row(self):
        """Add a new action row to the table"""
        row = self.sequence_table.rowCount()
        self.sequence_table.insertRow(row)
        
        # Set row height to prevent overlapping
        self.sequence_table.setRowHeight(row, 35)
        
        # Row number (non-editable)
        num_item = QTableWidgetItem(str(row + 1))
        num_item.setFlags(num_item.flags() & ~Qt.ItemIsEditable)
        self.sequence_table.setItem(row, 0, num_item)
        
        # Key input (with key capture)
        key_item = QLineEdit()
        key_item.setPlaceholderText("Click and press a key...")
        key_item.setStyleSheet("padding: 6px 4px; min-height: 20px; font-size: 12px;")
        key_item.setReadOnly(True)  # Make read-only to prevent typing
        key_item.mousePressEvent = lambda event: self.start_key_capture(key_item)
        self.sequence_table.setCellWidget(row, 1, key_item)
        
        # Type dropdown (Instant or Hold)
        type_combo = QComboBox()
        type_combo.addItems(["Instant", "Hold"])
        type_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                background-color: white;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QComboBox:hover {
                border-color: #80bdff;
                background-color: #f8f9fa;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #495057;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                border: 1px solid #ced4da;
                selection-background-color: #007bff;
                selection-color: white;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 12px;
                background-color: white;
                color: #212529;
                min-height: 25px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #e9ecef;
                color: #212529;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #007bff;
                color: white;
            }
        """)
        type_combo.currentTextChanged.connect(lambda text, r=row: self.on_type_changed(r, text))
        self.sequence_table.setCellWidget(row, 2, type_combo)
        
        # Duration input (only for Hold type)
        duration_input = QDoubleSpinBox()
        duration_input.setRange(0.2, 60.0)
        duration_input.setSingleStep(0.5)
        duration_input.setValue(0.35)  # Start at 0.35s for Instant
        duration_input.setSuffix(" s")
        duration_input.setEnabled(False)  # Disabled by default (Instant selected)
        duration_input.setStyleSheet("padding: 2px;")
        duration_input.setSpecialValueText("")  # Clear special text initially
        self.sequence_table.setCellWidget(row, 3, duration_input)
        
        # Scroll to the newly added row
        self.sequence_table.scrollToBottom()
    
    def on_type_changed(self, row, type_text):
        """Handle type combo box changes"""
        duration_widget = self.sequence_table.cellWidget(row, 3)
        if duration_widget:
            if type_text == "Instant":
                # Set to 0.35s and disable
                duration_widget.setValue(0.35)
                duration_widget.setEnabled(False)
            else:
                # Enable for Hold type and prompt user to set duration
                duration_widget.setValue(1.0)  # Reset to 1 second default
                duration_widget.setEnabled(True)
                duration_widget.setFocus()  # Focus on duration field
                duration_widget.selectAll()  # Select all so user can type immediately
    
    def start_key_capture(self, line_edit):
        """Start capturing a key press"""
        line_edit.setText("Press any key...")
        line_edit.setStyleSheet("padding: 4px; background-color: #fffacd; font-weight: bold;")
        
        # Store the line_edit so we can update it in the key event
        self._capturing_key_for = line_edit
        
        # Install event filter to capture next key press
        self.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Filter events to capture key presses"""
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        
        if hasattr(self, '_capturing_key_for') and event.type() == QEvent.KeyPress:
            key_event = event
            key = key_event.key()
            
            # Map Qt key codes to readable key names
            key_name = self.qt_key_to_string(key)
            
            if key_name:
                self._capturing_key_for.setText(key_name)
                self._capturing_key_for.setStyleSheet("padding: 4px;")
                delattr(self, '_capturing_key_for')
                self.removeEventFilter(self)
                return True
        
        return super().eventFilter(obj, event)
    
    def qt_key_to_string(self, qt_key):
        """Convert Qt key code to string representation"""
        from PySide6.QtCore import Qt
        
        # Function keys
        if Qt.Key_F1 <= qt_key <= Qt.Key_F12:
            return f"f{qt_key - Qt.Key_F1 + 1}"
        
        # Number keys
        if Qt.Key_0 <= qt_key <= Qt.Key_9:
            return chr(qt_key)
        
        # Letter keys
        if Qt.Key_A <= qt_key <= Qt.Key_Z:
            return chr(qt_key).lower()
        
        # Special keys mapping
        special_keys = {
            Qt.Key_Space: "space",
            Qt.Key_Return: "enter",
            Qt.Key_Enter: "enter",
            Qt.Key_Tab: "tab",
            Qt.Key_Backspace: "backspace",
            Qt.Key_Escape: "esc",
            Qt.Key_Shift: "shift",
            Qt.Key_Control: "ctrl",
            Qt.Key_Alt: "alt",
            Qt.Key_CapsLock: "capslock",
            Qt.Key_Left: "left",
            Qt.Key_Right: "right",
            Qt.Key_Up: "up",
            Qt.Key_Down: "down",
        }
        
        return special_keys.get(qt_key, None)
    
    def update_sequence_display(self, actions):
        """Update the sequence table from loaded actions (convert from old format)"""
        self.sequence_table.setRowCount(0)  # Clear existing rows
        
        if not actions:
            return
        
        # Group actions by key press/release pairs
        i = 0
        while i < len(actions):
            timestamp, action_type, action_data = actions[i]
            
            if action_type == "key_press":
                key = action_data
                
                # Look for matching key_release
                release_time = None
                for j in range(i + 1, len(actions)):
                    if actions[j][1] == "key_release" and actions[j][2] == key:
                        release_time = actions[j][0]
                        break
                
                # Calculate duration
                if release_time is not None:
                    duration = release_time - timestamp
                    
                    # Add row
                    row = self.sequence_table.rowCount()
                    self.sequence_table.insertRow(row)
                    
                    # Set row height to prevent overlapping
                    self.sequence_table.setRowHeight(row, 35)
                    
                    # Row number
                    num_item = QTableWidgetItem(str(row + 1))
                    num_item.setFlags(num_item.flags() & ~Qt.ItemIsEditable)
                    self.sequence_table.setItem(row, 0, num_item)
                    
                    # Key
                    key_item = QLineEdit()
                    key_item.setText(str(key))
                    key_item.setStyleSheet("padding: 6px 4px; min-height: 20px; font-size: 12px;")
                    key_item.setReadOnly(True)  # Make read-only to prevent typing
                    key_item.mousePressEvent = lambda event, ki=key_item: self.start_key_capture(ki)
                    self.sequence_table.setCellWidget(row, 1, key_item)
                    
                    # Type (Instant if <= 0.4s, Hold otherwise - threshold slightly above 0.35s)
                    type_combo = QComboBox()
                    type_combo.addItems(["Instant", "Hold"])
                    is_instant = duration <= 0.4  # Use 0.4s threshold to catch 0.35s instant actions
                    type_combo.setCurrentText("Instant" if is_instant else "Hold")
                    type_combo.setStyleSheet("""
                        QComboBox {
                            padding: 4px 8px;
                            background-color: white;
                            border: 1px solid #ced4da;
                            border-radius: 4px;
                        }
                        QComboBox:hover {
                            border-color: #80bdff;
                            background-color: #f8f9fa;
                        }
                        QComboBox::drop-down {
                            border: none;
                            width: 20px;
                        }
                        QComboBox::down-arrow {
                            image: none;
                            border-left: 4px solid transparent;
                            border-right: 4px solid transparent;
                            border-top: 5px solid #495057;
                            margin-right: 5px;
                        }
                        QComboBox QAbstractItemView {
                            background-color: white;
                            border: 1px solid #ced4da;
                            selection-background-color: #007bff;
                            selection-color: white;
                            outline: none;
                        }
                        QComboBox QAbstractItemView::item {
                            padding: 6px 12px;
                            background-color: white;
                            color: #212529;
                            min-height: 25px;
                        }
                        QComboBox QAbstractItemView::item:hover {
                            background-color: #e9ecef;
                            color: #212529;
                        }
                        QComboBox QAbstractItemView::item:selected {
                            background-color: #007bff;
                            color: white;
                        }
                    """)
                    type_combo.currentTextChanged.connect(lambda text, r=row: self.on_type_changed(r, text))
                    self.sequence_table.setCellWidget(row, 2, type_combo)
                    
                    # Duration
                    duration_input = QDoubleSpinBox()
                    duration_input.setRange(0.2, 60.0)
                    duration_input.setSingleStep(0.5)
                    duration_input.setValue(max(0.2, duration))
                    duration_input.setSuffix(" s")
                    duration_input.setEnabled(not is_instant)
                    duration_input.setStyleSheet("padding: 2px;")
                    self.sequence_table.setCellWidget(row, 3, duration_input)
            
            i += 1
    
    def clear_sequence_display(self):
        """Clear the sequence display (helper for compatibility)"""
        self.sequence_table.setRowCount(0)

    
    def delete_selected_rows(self):
        """Delete selected rows from the sequence"""
        selected_rows = set(item.row() for item in self.sequence_table.selectedItems())
        
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select rows to delete by clicking on the row number(s).")
            return
        
        # Get row numbers for display
        row_numbers = sorted([r + 1 for r in selected_rows])
        
        # Create readable list of row numbers
        if len(row_numbers) == 1:
            row_text = f"row #{row_numbers[0]}"
        elif len(row_numbers) == 2:
            row_text = f"rows #{row_numbers[0]} and #{row_numbers[1]}"
        else:
            row_text = f"rows #{', #'.join(map(str, row_numbers[:-1]))} and #{row_numbers[-1]}"
        
        # Confirm deletion
        reply = QMessageBox.question(self, "Confirm Delete", 
                                    f"Are you sure you want to delete {row_text}?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Remove rows in reverse order to maintain indices
            for row in sorted(selected_rows, reverse=True):
                self.sequence_table.removeRow(row)
            
            # Renumber remaining rows
            for row in range(self.sequence_table.rowCount()):
                num_item = self.sequence_table.item(row, 0)
                if num_item:
                    num_item.setText(str(row + 1))
    
    def load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "recorded_actions": [],
            "webhooks": {
                "enabled": False,
                "discord_url": "",
                "events": {
                    "santa_detected": True,
                    "santa_lost": True,
                    "attack_started": True,
                    "attack_completed": True,
                    "macro_started": True,
                    "macro_stopped": True
                }
            },
            "attack_settings": {
                "custom_sequence_enabled": False,
                "sequence_name": "Custom Attack",
                "end_delay": 5.0
            }
        }
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("SantaMacro Settings")
        self.setGeometry(100, 100, 550, 500)  # Reduced height from 600 to 500
        
        # Modern minimal Christmas theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
                color: #2d2d2d;
            }
            QTabWidget::pane {
                border: 1px solid #e9ecef;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #f8f9fa;
                color: #6c757d;
                padding: 15px 25px;
                margin-right: 1px;
                border: none;
                font-weight: 600;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: #dc3545;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e9ecef;
                color: #495057;
            }
            QGroupBox {
                font-weight: 600;
                border: none;
                margin-top: 20px;
                padding-top: 10px;
                background-color: #ffffff;
                color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0 10px 0;
                color: #dc3545;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 13px;
                min-height: 16px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #a71e2a;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
            QLineEdit, QTextEdit {
                background-color: #f8f9fa;
                color: #2d2d2d;
                border: 1px solid #dee2e6;
                padding: 10px;
                border-radius: 4px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #dc3545;
                background-color: #ffffff;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #f8f9fa;
                color: #2d2d2d;
                border: 1px solid #dee2e6;
                padding: 10px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                min-height: 16px;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #dc3545;
                background-color: #ffffff;
            }
            /* Hide the ugly spinbox buttons */
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                width: 0px;
                border: none;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                width: 0px;
                border: none;
            }
            QCheckBox {
                color: #2d2d2d;
                font-weight: 500;
                spacing: 10px;
                padding: 5px 0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #dee2e6;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #dc3545;
                border-color: #dc3545;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDQuNUw0LjUgOEwxMSAxIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4K);
            }
            QCheckBox::indicator:hover {
                border-color: #dc3545;
                background-color: #f8f9fa;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #c82333;
                border-color: #c82333;
            }
            QLabel {
                color: #2d2d2d;
                font-weight: 500;
            }
        """)
        
        # Central widget with scroll area
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title (outside scroll area)
        title = QLabel("🎄 SantaMacro Settings")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #dc3545; margin: 15px 0 10px 0; padding: 0;")
        main_layout.addWidget(title)
        
        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Simple (default) scrolling behavior
        vbar = scroll.verticalScrollBar()
        vbar.setSingleStep(20)
        vbar.setPageStep(200)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #ffffff;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #f8f9fa;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #dc3545;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #c82333;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Content widget inside scroll
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 10, 25, 25)
        
        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Create tabs
        self.create_attack_tab()
        self.create_webhook_tab()
        self.create_update_tab()
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        save_btn = QPushButton("💾 Save Settings")
        save_btn.clicked.connect(self.save_settings)
        
        cancel_btn = QPushButton("❌ Cancel")
        cancel_btn.clicked.connect(self.close)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
        
        # Set content widget to scroll area
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
    
    def create_attack_tab(self):
        """Create the attack configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Attack sequence section
        attack_group = QGroupBox("🎯 Attack Sequence Recording")
        attack_layout = QVBoxLayout(attack_group)
        attack_layout.setSpacing(12)
        
        # Remove the enable checkbox - attack sequence is mandatory
        
        # Sequence name
        name_layout = QVBoxLayout()
        name_layout.addWidget(QLabel("Sequence Name"))
        self.sequence_name = QLineEdit()
        self.sequence_name.setPlaceholderText("Enter a name for your attack sequence...")
        name_layout.addWidget(self.sequence_name)
        attack_layout.addLayout(name_layout)
        
        # End delay setting with clean design
        delay_layout = QVBoxLayout()
        delay_layout.addWidget(QLabel("End Delay"))
        
        delay_info = QLabel("Time to wait during cooldown phase (when macro presses 3 and spams E)")
        delay_info.setStyleSheet("color: #6c757d; font-size: 12px; margin-bottom: 5px; font-weight: 400;")
        delay_layout.addWidget(delay_info)
        
        self.end_delay = QDoubleSpinBox()
        self.end_delay.setRange(0.0, 60.0)
        self.end_delay.setSingleStep(0.5)
        # Don't set default value here - let load_settings handle it
        self.end_delay.setSuffix(" seconds")
        self.end_delay.setMaximumWidth(150)
        delay_layout.addWidget(self.end_delay)
        
        attack_layout.addLayout(delay_layout)
        
        # Manual action builder instructions
        instructions_layout = QVBoxLayout()
        instructions_layout.addWidget(QLabel("⚙️ Action Builder Instructions"))
        
        instructions = QLabel("""Build your custom attack sequence by adding actions:

• Instant: Key pressed and released in 200ms (for quick taps)
• Hold: Key held down for specified duration (e.g., X for 12 seconds)

Click "Add Action" to add rows, then configure each action.
Your sequence will play during attacks, then macro presses 3 and spams E during End Delay.""")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #495057; font-size: 12px; line-height: 1.4; font-weight: 400; margin: 8px 0;")
        instructions_layout.addWidget(instructions)
        
        attack_layout.addLayout(instructions_layout)
        
        # Sequence display
        display_layout = QVBoxLayout()
        display_layout.addWidget(QLabel("📊 Recorded Sequence (Editable)"))
        
        # Create table for sequence editing
        self.sequence_table = QTableWidget()
        self.sequence_table.setColumnCount(4)
        self.sequence_table.setHorizontalHeaderLabels(["#", "Key", "Type", "Duration (s)"])
        self.sequence_table.setMaximumHeight(300)
        self.sequence_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sequence_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Use custom editors
        
        # Configure column behavior
        header = self.sequence_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # # column fixed
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Key column stretches
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Type column fixed
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Duration column fixed
        
        self.sequence_table.setColumnWidth(0, 40)   # # column
        self.sequence_table.setColumnWidth(2, 100)  # Type column
        self.sequence_table.setColumnWidth(3, 120)  # Duration column
        
        self.sequence_table.setStyleSheet("""
            QTableWidget {
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                gridline-color: #dee2e6;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #cfe2ff;
                color: #052c65;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 8px;
                border: 1px solid #dee2e6;
                font-weight: 600;
            }
        """)
        
        display_layout.addWidget(self.sequence_table)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        # Add action button
        add_action_btn = QPushButton("➕ Add Action")
        add_action_btn.setToolTip("Add a new action to your sequence")
        add_action_btn.clicked.connect(self.add_action_row)
        add_action_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        button_layout.addWidget(add_action_btn)
        
        # Delete selected row button
        delete_row_btn = QPushButton("🗑️ Delete Selected")
        delete_row_btn.setToolTip("Delete selected rows from sequence")
        delete_row_btn.clicked.connect(self.delete_selected_rows)
        delete_row_btn.setMaximumWidth(140)
        delete_row_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        button_layout.addWidget(delete_row_btn)
        
        # Clear button as simple icon
        clear_btn = QPushButton("🗑️ Clear All")
        clear_btn.setToolTip("Clear entire recorded sequence")
        clear_btn.clicked.connect(self.clear_sequence)
        clear_btn.setMaximumWidth(110)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        button_layout.addWidget(clear_btn)
        
        display_layout.addLayout(button_layout)
        
        attack_layout.addLayout(display_layout)
        
        layout.addWidget(attack_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "🎯 Attack Settings")
    
    def create_webhook_tab(self):
        """Create the webhook configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Webhook section
        webhook_group = QGroupBox("🔔 Discord Notifications")
        webhook_layout = QVBoxLayout(webhook_group)
        webhook_layout.setSpacing(12)
        
        # Enable checkbox
        self.webhooks_enabled = QCheckBox("Enable Discord Webhooks")
        webhook_layout.addWidget(self.webhooks_enabled)
        
        # Webhook URL
        url_layout = QVBoxLayout()
        url_layout.addWidget(QLabel("Webhook URL"))
        self.webhook_url = QLineEdit()
        self.webhook_url.setPlaceholderText("https://discord.com/api/webhooks/...")
        url_layout.addWidget(self.webhook_url)
        
        # Test button
        test_btn = QPushButton("🧪 Test Webhook")
        test_btn.clicked.connect(self.test_webhook)
        test_btn.setMaximumWidth(150)
        url_layout.addWidget(test_btn)
        
        webhook_layout.addLayout(url_layout)
        
        # Events
        events_layout = QVBoxLayout()
        events_layout.addWidget(QLabel("📢 Events to Send"))
        
        self.webhook_events = {}
        events = [
            ("santa_detected", "🎅 Santa Detected"),
            ("santa_lost", "❌ Santa Lost"),
            ("attack_started", "⚔️ Attack Started"),
            ("attack_completed", "✅ Attack Completed"),
            ("macro_started", "▶️ Macro Started"),
            ("macro_stopped", "⏹️ Macro Stopped")
        ]
        
        for event_key, event_name in events:
            checkbox = QCheckBox(event_name)
            self.webhook_events[event_key] = checkbox
            events_layout.addWidget(checkbox)
        
        webhook_layout.addLayout(events_layout)
        
        # Instructions
        instructions_layout = QVBoxLayout()
        instructions_layout.addWidget(QLabel("📋 Setup Instructions"))
        
        instructions = QLabel("""How to setup Discord Webhooks:

1. Go to your Discord channel settings
2. Navigate to Integrations → Webhooks  
3. Create a new webhook
4. Copy the webhook URL and paste it above
5. Select which events you want notifications for
6. Click 'Test Webhook' to verify it works

Tip: Create a dedicated channel for SantaMacro notifications!""")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #495057; font-size: 12px; line-height: 1.4; font-weight: 400; margin: 8px 0;")
        instructions_layout.addWidget(instructions)
        
        webhook_layout.addLayout(instructions_layout)
        
        layout.addWidget(webhook_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "🔔 Discord Webhooks")
    
    def create_update_tab(self):
        """Create the update tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Update section
        update_group = QGroupBox("🔄 SantaMacro Updates")
        update_layout = QVBoxLayout(update_group)
        update_layout.setSpacing(15)
        
        # Current version info
        version_layout = QVBoxLayout()
        version_layout.addWidget(QLabel("Current Version"))
        
        try:
            # Try to get current commit info
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            git_dir = os.path.join(project_root, '.git')
            if os.path.exists(git_dir):
                version_text = "Git repository (development version)"
            else:
                version_text = "Release version"
        except:
            version_text = "Unknown version"
        
        version_label = QLabel(version_text)
        version_label.setStyleSheet("color: #6c757d; font-size: 12px; margin-bottom: 10px; font-weight: 400;")
        version_layout.addWidget(version_label)
        
        update_layout.addLayout(version_layout)
        
        # Update button
        self.update_btn = QPushButton("🔄 Check for Updates")
        self.update_btn.clicked.connect(self.check_for_updates)
        self.update_btn.setMaximumWidth(200)
        update_layout.addWidget(self.update_btn)
        
        # Update info
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel("📋 Update Information"))
        
        info_text = QLabel("""This will check GitHub for the latest SantaMacro version and automatically download and install updates.

What gets updated:
• Core macro files and improvements
• Bug fixes and new features  
• UI enhancements

What gets preserved:
• Your config.json settings
• Your recorded attack sequences
• Your Model.pt file

The update process creates a backup of your current installation before applying changes.""")
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #495057; font-size: 12px; line-height: 1.4; font-weight: 400; margin: 8px 0;")
        info_layout.addWidget(info_text)
        
        update_layout.addLayout(info_layout)
        
        # Repository link
        repo_layout = QVBoxLayout()
        repo_layout.addWidget(QLabel("📂 Repository"))
        
        repo_btn = QPushButton("🔗 Open GitHub Repository")
        repo_btn.clicked.connect(self.open_repository)
        repo_btn.setMaximumWidth(200)
        repo_layout.addWidget(repo_btn)
        
        update_layout.addLayout(repo_layout)
        
        layout.addWidget(update_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "🔄 Updates")
    
    def check_for_updates(self):
        """Check for updates using worker thread"""
        try:
            # Disable button during update
            self.update_btn.setEnabled(False)
            self.update_btn.setText("🔄 Checking...")
            
            # Show update dialog
            self.update_dialog = UpdateDialog(self)
            
            # Create and start worker thread
            self.update_worker = UpdateWorker()
            self.update_worker.progress.connect(self.update_dialog.update_status)
            self.update_worker.finished.connect(self.on_update_finished)
            self.update_worker.start()
            
            # Show dialog
            self.update_dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start update: {str(e)}")
            self.update_btn.setEnabled(True)
            self.update_btn.setText("🔄 Check for Updates")
    
    def on_update_finished(self, success, message):
        """Handle update completion"""
        self.update_btn.setEnabled(True)
        self.update_btn.setText("🔄 Check for Updates")
        
        if success:
            self.update_dialog.update_status(f"✅ {message}", "success")
            # Show restart dialog
            reply = QMessageBox.question(self, "Update Complete", 
                                       f"{message}\n\nWould you like to restart SantaMacro now?",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.restart_application()
        else:
            self.update_dialog.update_status(f"❌ {message}", "error")
    
    def restart_application(self):
        """Restart the application"""
        try:
            import subprocess
            
            # Close current application
            QApplication.quit()
            
            # Determine how to restart
            if getattr(sys, 'frozen', False):
                # Running as executable
                subprocess.Popen([sys.executable])
            else:
                # Running as Python script
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                main_script = os.path.join(project_root, 'main.py')
                if os.path.exists(main_script):
                    subprocess.Popen([sys.executable, main_script])
                else:
                    # Try example.py as fallback
                    example_script = os.path.join(project_root, 'example.py')
                    if os.path.exists(example_script):
                        subprocess.Popen([sys.executable, example_script])
            
            sys.exit(0)
            
        except Exception as e:
            QMessageBox.critical(self, "Restart Failed", 
                               f"Could not restart automatically.\nPlease restart SantaMacro manually.\n\nError: {e}")
    
    def open_repository(self):
        """Open the GitHub repository in browser"""
        try:
            import webbrowser
            webbrowser.open("https://github.com/arielldev/SantaMacro")
        except Exception as e:
            QMessageBox.information(self, "Repository", 
                                  "GitHub Repository:\nhttps://github.com/arielldev/SantaMacro")
    
    def clear_sequence(self):
        """Clear the recorded sequence"""
        reply = QMessageBox.question(self, "Confirm Clear", 
                                    "Clear entire attack sequence?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.config["recorded_actions"] = []
            self.sequence_table.setRowCount(0)
            QMessageBox.information(self, "Cleared", "Sequence cleared. Click 'Add Action' to build a new sequence!")
    
    def test_webhook(self):
        """Test the Discord webhook"""
        url = self.webhook_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a webhook URL first.")
            return
        
        try:
            data = {
                "content": "🧪 **SantaMacro Test**\nWebhook is working correctly!"
            }
            response = requests.post(url, json=data, timeout=10)
            
            if response.status_code == 204:
                QMessageBox.information(self, "Success", "Webhook test successful!")
            else:
                QMessageBox.critical(self, "Error", f"Webhook test failed. Status: {response.status_code}")
        
        except ImportError:
            QMessageBox.critical(self, "Error", "Requests library not found. Install with: pip install requests")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Webhook test failed: {str(e)}")
    
    def load_settings(self):
        """Load settings into the GUI"""
        # Attack settings
        attack_settings = self.config.get("attack_settings", {})
        # Attack sequence is always enabled, no toggle needed
        self.sequence_name.setText(attack_settings.get("sequence_name", "Attack Sequence"))
        self.end_delay.setValue(attack_settings.get("end_delay", 5.0))
        
        # Display recorded actions
        if self.config.get("recorded_actions"):
            actions = self.config["recorded_actions"]
            self.update_sequence_display(actions)
        
        # Webhook settings
        webhook_settings = self.config.get("webhooks", {})
        self.webhooks_enabled.setChecked(webhook_settings.get("enabled", False))
        self.webhook_url.setText(webhook_settings.get("discord_url", ""))
        
        events = webhook_settings.get("events", {})
        for event_key, checkbox in self.webhook_events.items():
            checkbox.setChecked(events.get(event_key, True))
    
    def save_settings(self):
        """Save settings to config file"""
        # Read actions from table and convert to action format
        actions = []
        current_time = 0.0
        
        for row in range(self.sequence_table.rowCount()):
            try:
                # Get widgets
                key_widget = self.sequence_table.cellWidget(row, 1)
                type_widget = self.sequence_table.cellWidget(row, 2)
                duration_widget = self.sequence_table.cellWidget(row, 3)
                
                if not key_widget or not type_widget or not duration_widget:
                    QMessageBox.warning(self, "Invalid Data", 
                                      f"Row {row + 1} has missing data. Please complete all fields.")
                    return
                
                key = key_widget.text().strip()
                action_type = type_widget.currentText()
                duration = duration_widget.value()
                
                if not key:
                    QMessageBox.warning(self, "Invalid Data", 
                                      f"Row {row + 1} has no key specified. Please enter a key.")
                    return
                
                # Create press and release events
                if action_type == "Instant":
                    # Instant: press and release with duration from widget (default 0.35s)
                    actions.append((current_time, "key_press", key))
                    current_time += duration
                    actions.append((current_time, "key_release", key))
                    current_time += 0.05  # Add 50ms gap after each action for proper key registration
                else:
                    # Hold: press and release with specified duration
                    actions.append((current_time, "key_press", key))
                    current_time += duration
                    actions.append((current_time, "key_release", key))
                    current_time += 0.05  # Add 50ms gap after each action for proper key registration
                
            except (ValueError, AttributeError) as e:
                QMessageBox.warning(self, "Invalid Data", 
                                  f"Row {row + 1} has invalid data: {str(e)}")
                return
        
        if not actions:
            reply = QMessageBox.question(self, "Empty Sequence", 
                                        "Your attack sequence is empty. Save anyway?",
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        # Update config with GUI values
        self.config["recorded_actions"] = actions
        self.config["attack_settings"] = {
            "custom_sequence_enabled": True,  # Always enabled
            "sequence_name": self.sequence_name.text(),
            "end_delay": self.end_delay.value()
        }
        
        self.config["webhooks"] = {
            "enabled": self.webhooks_enabled.isChecked(),
            "discord_url": self.webhook_url.text().strip(),
            "events": {
                event_key: checkbox.isChecked()
                for event_key, checkbox in self.webhook_events.items()
            }
        }
        
        # Save to file
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
            
            # Reload webhook config in macro if available
            if self.macro_instance and hasattr(self.macro_instance, 'webhook_manager'):
                if self.macro_instance.webhook_manager:
                    # Reload the config from file
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        updated_config = json.load(f)
                    self.macro_instance.webhook_manager.update_config(updated_config)
                    print("✅ Webhook config reloaded in macro")
            
            QMessageBox.information(self, "Success", 
                                  f"✅ Settings saved successfully!\\n\\n{len(actions)} action events in sequence.\\nYour attack sequence is ready to use!")
            self.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"❌ Failed to save settings: {str(e)}")
    
    def show(self):
        """Show the settings window"""
        print("Settings GUI show() called")
        super().show()
        self.raise_()
        self.activateWindow()


def main():
    """Test the settings GUI"""
    app = QApplication.instance() or QApplication([])
    gui = SettingsGUI("config.json")
    gui.show()
    app.exec()


if __name__ == "__main__":
    main()
