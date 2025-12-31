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

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QCheckBox,
    QGroupBox, QFormLayout, QMessageBox, QSpinBox, QDoubleSpinBox,
    QDialog, QDialogButtonBox, QProgressBar, QSystemTrayIcon, QMenu
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


class ActionRecorder:
    """Records user actions for custom attack sequences"""
    
    def __init__(self):
        self.recording = False
        self.actions = []
        self.start_time = None
        self.mouse_listener = None
        self.keyboard_listener = None
    
    def start_recording(self):
        """Start recording actions"""
        self.recording = True
        self.actions = []
        self.start_time = time.time()
        
        # Start listeners
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self.keyboard_listener = pynput_keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        
        self.mouse_listener.start()
        self.keyboard_listener.start()
    
    def stop_recording(self):
        """Stop recording and return actions"""
        self.recording = False
        
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        
        if self.actions:
            elapsed = time.time() - self.start_time
            self.actions.append([elapsed, "end_marker", None])
        
        return self.actions.copy()
    
    def _on_mouse_click(self, x, y, button, pressed):
        """Handle mouse click events"""
        if not self.recording:
            return
        
        timestamp = time.time() - self.start_time
        action_type = "mouse_press" if pressed else "mouse_release"
        
        self.actions.append([timestamp, action_type, {
            "button": button.name,
            "position": [x, y]
        }])
    
    def _on_key_press(self, key):
        """Handle key press events"""
        if not self.recording:
            return
        
        timestamp = time.time() - self.start_time
        
        try:
            if hasattr(key, 'char') and key.char is not None:
                key_name = key.char
            else:
                key_name = key.name
            
            self.actions.append([timestamp, "key_press", key_name])
        except AttributeError:
            self.actions.append([timestamp, "key_press", str(key)])
    
    def _on_key_release(self, key):
        """Handle key release events"""
        if not self.recording:
            return
        
        timestamp = time.time() - self.start_time
        
        try:
            if hasattr(key, 'char') and key.char is not None:
                key_name = key.char
            else:
                key_name = key.name
            
            self.actions.append([timestamp, "key_release", key_name])
        except AttributeError:
            self.actions.append([timestamp, "key_release", str(key)])


class SettingsGUI(QMainWindow):
    """Simple settings GUI for SantaMacro using PySide6"""
    
    # Add a custom signal for F3 handling
    f3_pressed_signal = Signal()
    
    def __init__(self, config_path: str):
        # Ensure we're in the main thread
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QThread
        
        app = QApplication.instance()
        if app and QThread.currentThread() != app.thread():
            raise RuntimeError("SettingsGUI must be created in the main Qt thread")
        
        super().__init__()
        self.config_path = config_path
        self.config = {}
        self.recorder = ActionRecorder()
        self.recording_active = False
        self.f3_monitoring_ready = False  # Prevent F3 handling during startup
        
        # Connect the F3 signal to the handler
        self.f3_pressed_signal.connect(self.handle_f3_press)
        
        self.load_config()
        self.setup_ui()
        self.load_settings()
        self.setup_global_hotkeys()
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
            
            # Recording control action
            self.record_action = QAction("🔴 Start Recording", self)
            self.record_action.triggered.connect(self.toggle_recording_from_tray)
            tray_menu.addAction(self.record_action)
            
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
        if self.recording_active:
            # If recording is active, stop it first
            actions = self.recorder.stop_recording()
            self.recording_active = False
            self.update_tray_menu()
            
            # Reset window title
            self.setWindowTitle("SantaMacro Settings")
            
            # Process the recorded actions
            if actions:
                self.config["recorded_actions"] = actions
                self.update_sequence_display(actions)
                
                # Show brief success message
                if self.tray_icon:
                    self.tray_icon.showMessage("SantaMacro", "Recording saved successfully!", QSystemTrayIcon.Information, 2000)
            else:
                self.sequence_display.setPlainText("No actions recorded.")
        
        # Show the window
        self.show()
        self.raise_()
        self.activateWindow()
    
    def toggle_recording_from_tray(self):
        """Toggle recording from system tray - seamless workflow WITHOUT hiding"""
        if not self.recording_active:
            # Start recording immediately (no dialog from tray)
            self.recording_active = True
            self.recorder.start_recording()
            self.sequence_display.setPlainText("🔴 Recording in progress... Press F3 or right-click tray to stop.")
            self.update_tray_menu()
            
            # DON'T HIDE WINDOW - Keep it visible so F3 works
            self.setWindowTitle("SantaMacro Settings - 🔴 RECORDING")
            
            # Show tray notification
            if self.tray_icon:
                self.tray_icon.showMessage("SantaMacro", "Recording started! Press F3 or right-click tray to stop.", QSystemTrayIcon.Information, 3000)
        else:
            # Stop recording
            actions = self.recorder.stop_recording()
            self.recording_active = False
            self.update_tray_menu()
            
            # Reset window title
            self.setWindowTitle("SantaMacro Settings")
            
            # Process the recorded actions
            if actions:
                # Save the sequence automatically
                self.config["recorded_actions"] = actions
                self.update_sequence_display(actions)
                
                # Show brief success message
                if self.tray_icon:
                    self.tray_icon.showMessage("SantaMacro", "Recording saved successfully!", QSystemTrayIcon.Information, 2000)
            else:
                self.sequence_display.setPlainText("No actions recorded.")
    
    def update_tray_menu(self):
        """Update tray menu based on recording state"""
        if hasattr(self, 'record_action'):
            if self.recording_active:
                self.record_action.setText("⏹️ Stop Recording")
                self.show_action.setText("⏹️ Stop Recording & Show Settings")
            else:
                self.record_action.setText("🔴 Start Recording")
                self.show_action.setText("📱 Show Settings")
    
    def setup_global_hotkeys(self):
        """Setup WORKING global F3 hotkey using Qt signals"""
        try:
            # Reset the monitoring ready flag
            self.f3_monitoring_ready = False
            
            import threading
            import time
            import ctypes
            from ctypes import wintypes
            
            def check_f3_global():
                """WORKING F3 detection using Qt signals"""
                user32 = ctypes.windll.user32
                f3_was_pressed = False
                
                print("🌍 WORKING Global F3 monitoring started!")
                
                # Clear any lingering key state first
                user32.GetAsyncKeyState(0x72)  # Clear F3 state
                time.sleep(0.1)  # Brief pause to clear state
                
                # Set monitoring as ready immediately
                self.f3_monitoring_ready = True
                print("✅ F3 monitoring is now ready!")
                
                while hasattr(self, '_f3_thread_running') and self._f3_thread_running:
                    try:
                        # Check if F3 is pressed (VK_F3 = 0x72)
                        f3_is_pressed = bool(user32.GetAsyncKeyState(0x72) & 0x8000)
                        
                        # Only trigger on actual key press (transition from not pressed to pressed)
                        if f3_is_pressed and not f3_was_pressed and self.f3_monitoring_ready:
                            print("🔥 F3 DETECTED - EMITTING SIGNAL!")
                            
                            # Emit signal to trigger handler in main thread
                            try:
                                self.f3_pressed_signal.emit()
                                print("✅ Signal emitted successfully")
                            except Exception as e:
                                print(f"❌ Failed to emit signal: {e}")
                            
                            # Wait for key release to prevent multiple triggers
                            while user32.GetAsyncKeyState(0x72) & 0x8000:
                                time.sleep(0.05)
                            
                            # Brief debounce
                            time.sleep(0.2)
                        
                        f3_was_pressed = f3_is_pressed
                        time.sleep(0.05)  # Check every 50ms
                        
                    except Exception as e:
                        print(f"❌ F3 polling error: {e}")
                        time.sleep(0.1)
                
                print("🛑 Global F3 monitoring stopped")
            
            # Start the global F3 monitoring thread
            self._f3_thread_running = True
            self.f3_thread = threading.Thread(target=check_f3_global, daemon=True)
            self.f3_thread.start()
            print("✅ WORKING GLOBAL F3 hotkey setup with Qt signals!")
            
        except Exception as e:
            print(f"❌ Failed to setup global F3 hotkey: {e}")
            import traceback
            traceback.print_exc()
    
    def handle_f3_press(self):
        """Handle F3 key press - WORKING workflow with debug"""
        print("🚀 HANDLE_F3_PRESS CALLED!")
        
        # PREVENT F3 HANDLING DURING STARTUP
        if not self.f3_monitoring_ready:
            print("❌ F3 ignored - monitoring not ready yet")
            return
            
        try:
            print(f"🔥 F3 HANDLER EXECUTING! Recording active: {self.recording_active}")
            
            if not self.recording_active:
                print("📱 Starting recording workflow...")
                
                # FIRST: Make sure settings window is visible and active
                print("📱 Showing settings window...")
                self.show()
                self.raise_()
                self.activateWindow()
                self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
                
                # SECOND: Show dialog asking to start recording
                print("📱 Creating dialog...")
                dialog = RecordingConfirmDialog(self, is_start=True)
                dialog.show()
                dialog.raise_()
                dialog.activateWindow()
                
                print("📱 Executing dialog...")
                result = dialog.exec()
                print(f"Dialog result: {result}")
                
                if result == QDialog.Accepted:
                    print("✅ User confirmed - Starting recording")
                    # Start recording and MINIMIZE EVERYTHING
                    self.recording_active = True
                    self.recorder.start_recording()
                    self.sequence_display.setPlainText("🔴 Recording in progress... Press F3 again to stop.")
                    self.update_tray_menu()
                    
                    # MINIMIZE THE WINDOW SO YOU CAN RECORD
                    print("📱 Minimizing window...")
                    self.showMinimized()
                    self.hide()  # Hide from taskbar
                    
                    # Show tray notification
                    if self.tray_icon:
                        self.tray_icon.showMessage("SantaMacro", "🔴 Recording started! Press F3 again to stop.", QSystemTrayIcon.Information, 3000)
                    
                    print("✅ Recording started - Window minimized")
                else:
                    print("❌ User cancelled recording")
            else:
                # Stop recording and FORCE WINDOW TO APPEAR ON SCREEN
                print("🛑 Stopping recording...")
                actions = self.recorder.stop_recording()
                self.recording_active = False
                self.update_tray_menu()
                
                # FORCE WINDOW TO APPEAR ON SCREEN (NOT JUST TASKBAR)
                print("📱 Forcing window to appear on screen...")
                self.setWindowState(Qt.WindowNoState)  # Clear minimized state
                self.showNormal()  # Show in normal state (not minimized)
                self.raise_()  # Bring to front
                self.activateWindow()  # Give focus
                
                # Force to front of all windows
                self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
                self.show()
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
                self.show()
                
                self.setWindowTitle("SantaMacro Settings")
                
                # Process the recorded actions
                if actions:
                    # Save the sequence automatically (no dialog)
                    self.config["recorded_actions"] = actions
                    self.update_sequence_display(actions)
                    
                    # Show brief success message
                    if self.tray_icon:
                        self.tray_icon.showMessage("SantaMacro", "✅ Recording saved!", QSystemTrayIcon.Information, 2000)
                    
                    print(f"✅ Recording stopped - {len(actions)} actions saved - Window forced to screen")
                else:
                    self.sequence_display.setPlainText("No actions recorded.")
                    print("⚠️ No actions recorded - Window forced to screen")
                    
        except Exception as e:
            print(f"❌ Error handling F3: {e}")
            import traceback
            traceback.print_exc()
    
    def closeEvent(self, event):
        """Handle window close event"""
        try:
            # Stop the global F3 monitoring thread
            if hasattr(self, '_f3_thread_running'):
                self._f3_thread_running = False
                if hasattr(self, 'f3_thread'):
                    self.f3_thread.join(timeout=1.0)  # Wait up to 1 second
                    
            if hasattr(self, 'global_listener') and self.global_listener:
                self.global_listener.stop()
                self.global_listener = None
        except Exception as e:
            print(f"Error stopping keyboard listener: {e}")
        
        if self.recording_active:
            try:
                self.recorder.stop_recording()
            except Exception as e:
                print(f"Error stopping recorder: {e}")
        
        super().closeEvent(event)
    
    def start_recording_with_dialog(self):
        """Show dialog and start recording"""
        dialog = RecordingConfirmDialog(self, is_start=True)
        if dialog.exec() == QDialog.Accepted:
            self.recording_active = True
            self.recorder.start_recording()
            self.sequence_display.setPlainText("🔴 Recording in progress... Right-click tray icon to stop recording.")
            self.update_tray_menu()
            
            # Minimize to tray when recording starts
            self.showMinimized()
            self.hide()  # Hide from taskbar completely
            
            # Show tray notification
            if self.tray_icon:
                self.tray_icon.showMessage("SantaMacro", "Recording started! Right-click tray icon to stop.", QSystemTrayIcon.Information, 3000)
    
    def stop_recording_with_dialog(self):
        """Stop recording and show completion dialog"""
        actions = self.recorder.stop_recording()
        self.recording_active = False
        self.update_tray_menu()
        
        # Show the window again when recording stops
        self.show()
        self.raise_()
        self.activateWindow()
        
        if actions:
            dialog = RecordingConfirmDialog(self, is_start=False)
            if dialog.exec() == QDialog.Accepted:
                # Save the sequence
                self.config["recorded_actions"] = actions
                self.update_sequence_display(actions)
            else:
                # Discard the sequence
                self.sequence_display.setPlainText("Recording discarded.")
        else:
            self.sequence_display.setPlainText("No actions recorded.")
    
    def update_sequence_display(self, actions):
        """Update the sequence display with recorded actions"""
        display_text = "✅ Recorded Attack Sequence:\n\n"
        for i, (timestamp, action_type, action_data) in enumerate(actions):
            display_text += f"{i+1}. {timestamp:.3f}s - {action_type}"
            if action_data and action_data != "None":
                display_text += f" ({action_data})"
            display_text += "\n"
        
        self.sequence_display.setPlainText(display_text)
    
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
        self.setGeometry(100, 100, 550, 600)
        
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
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Title
        title = QLabel("🎄 SantaMacro Settings")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #dc3545; margin: 0 0 15px 0; padding: 0;")
        layout.addWidget(title)
        
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
        
        # Recording instructions
        instructions_layout = QVBoxLayout()
        instructions_layout.addWidget(QLabel("📝 Recording Instructions"))
        
        instructions = QLabel("""1. Set your End Delay above
2. Press F3 to start recording
3. Perform your attack sequence
4. Press F3 again to stop and save

Your sequence will play during attacks, then macro presses 3 and spams E during End Delay.""")
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #495057; font-size: 12px; line-height: 1.4; font-weight: 400; margin: 8px 0;")
        instructions_layout.addWidget(instructions)
        
        attack_layout.addLayout(instructions_layout)
        
        # Sequence display
        display_layout = QVBoxLayout()
        display_layout.addWidget(QLabel("📊 Recorded Sequence"))
        
        self.sequence_display = QTextEdit()
        self.sequence_display.setMaximumHeight(150)
        self.sequence_display.setPlaceholderText("Your recorded attack sequence will appear here...\n\nPress F3 while this window is open to start recording!")
        self.sequence_display.setStyleSheet("font-family: 'Consolas', 'Monaco', monospace; font-size: 11px; font-weight: 400;")
        display_layout.addWidget(self.sequence_display)
        
        # Recording button and clear button
        button_layout = QHBoxLayout()
        
        # Replace button with text instruction
        f3_instruction = QLabel("Press F3 to start recording")
        f3_instruction.setStyleSheet("""
            color: #dc3545; 
            font-weight: 600; 
            font-size: 14px; 
            padding: 10px; 
            background-color: #f8f9fa; 
            border: 1px solid #dee2e6; 
            border-radius: 4px;
        """)
        f3_instruction.setAlignment(Qt.AlignCenter)
        button_layout.addWidget(f3_instruction)
        
        # Clear button as simple icon
        clear_btn = QPushButton("🗑️")
        clear_btn.setToolTip("Clear recorded sequence")
        clear_btn.clicked.connect(self.clear_sequence)
        clear_btn.setMaximumWidth(40)
        clear_btn.setMaximumHeight(40)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #5a6268;
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

1. Go to your Discord server settings
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
    
    def toggle_recording(self):
        """Toggle recording state with button - seamless workflow WITHOUT hiding"""
        if not self.recording_active:
            # Show dialog asking to start recording
            dialog = RecordingConfirmDialog(self, is_start=True)
            if dialog.exec() == QDialog.Accepted:
                # Start recording but KEEP WINDOW VISIBLE
                self.recording_active = True
                self.recorder.start_recording()
                self.sequence_display.setPlainText("🔴 Recording in progress... Press F3 or click Stop to finish.")
                self.update_tray_menu()
                
                # DON'T MINIMIZE - Keep window visible so F3 still works
                self.setWindowTitle("SantaMacro Settings - 🔴 RECORDING")
                
                # Show tray notification
                if self.tray_icon:
                    self.tray_icon.showMessage("SantaMacro", "Recording started! Press F3 or click Stop to finish.", QSystemTrayIcon.Information, 3000)
        else:
            # Stop recording
            actions = self.recorder.stop_recording()
            self.recording_active = False
            self.update_tray_menu()
            
            # Reset window title
            self.setWindowTitle("SantaMacro Settings")
            
            # Process recorded actions
            if actions:
                # Save automatically
                self.config["recorded_actions"] = actions
                self.update_sequence_display(actions)
                
                # Show success message
                if self.tray_icon:
                    self.tray_icon.showMessage("SantaMacro", "Recording saved successfully!", QSystemTrayIcon.Information, 2000)
            else:
                self.sequence_display.setPlainText("No actions recorded.")
    
    def clear_sequence(self):
        """Clear the recorded sequence"""
        self.config["recorded_actions"] = []
        self.sequence_display.setPlainText("Sequence cleared. Press F3 to record a new sequence!")
    
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
        # Update config with GUI values
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
            
            QMessageBox.information(self, "Success", "✅ Settings saved successfully!\n\nYour attack sequence is ready to use!")
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