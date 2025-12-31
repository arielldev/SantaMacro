"""
Custom Action System for SantaMacro
Handles recording and playback of user-defined attack sequences
"""
import time
import json
import threading
from typing import List, Tuple, Any, Optional, Dict
from pynput import keyboard
import pyautogui
import pydirectinput
import ctypes
from ctypes import wintypes
import ctypes.wintypes

# Windows mouse hook constants
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208

# Hook procedure type
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class ActionRecorder:
    """Records user input actions for custom attack sequences"""
    
    def __init__(self):
        self.recording = False
        self.actions: List[Tuple[float, str, Any]] = []
        self.start_time: Optional[float] = None
        
        # Input listeners
        self.keyboard_listener: Optional[keyboard.Listener] = None
        
        # Mouse polling
        self.mouse_thread = None
        self.mouse_thread_running = False
        self.last_mouse_state = {"left": False, "right": False, "middle": False}
    
    def _poll_mouse_state(self):
        """Poll mouse button states using Windows API"""
        import ctypes
        
        print("🖱️ Mouse polling thread started")
        
        while self.mouse_thread_running and self.recording:
            try:
                # Check mouse button states using Windows API
                left_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
                right_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000)
                middle_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x04) & 0x8000)
                
                current_state = {"left": left_pressed, "right": right_pressed, "middle": middle_pressed}
                
                # Check for state changes
                for button, pressed in current_state.items():
                    if pressed != self.last_mouse_state[button]:
                        print(f"🖱️ MOUSE STATE CHANGE: {button} {'pressed' if pressed else 'released'}")
                        self._record_mouse_event(button, pressed)
                        self.last_mouse_state[button] = pressed
                
                time.sleep(0.01)  # Poll every 10ms
                
            except Exception as e:
                print(f"❌ Mouse polling error: {e}")
                break
        
        print("🖱️ Mouse polling thread stopped")
    
    def _record_mouse_event(self, button: str, pressed: bool):
        """Record a mouse event"""
        print(f"🖱️ WINDOWS HOOK: {button} {'pressed' if pressed else 'released'}")
        
        if not self.recording:
            return
        
        timestamp = self._get_timestamp()
        action_type = "key_press" if pressed else "key_release"
        
        print(f"✅ Recording mouse event: {action_type} {button} at {timestamp:.3f}s")
        self.actions.append((timestamp, action_type, button))
    
    def start_recording(self):
        """Start recording user actions"""
        if self.recording:
            return
        
        self.recording = True
        self.actions = []
        self.start_time = time.time()
        
        print("🔴 Recording started! Perform your attack sequence...")
        print("🖱️ Mouse polling will capture clicks")
        print("⌨️ Keyboard listener will capture keys (except F3)")
        
        try:
            # Reset mouse state
            self.last_mouse_state = {"left": False, "right": False, "middle": False}
            
            # Start mouse polling thread
            self.mouse_thread_running = True
            self.mouse_thread = threading.Thread(target=self._poll_mouse_state, daemon=True)
            self.mouse_thread.start()
            print("✅ Mouse polling thread started!")
            
            # Start keyboard listener
            self.keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
                suppress=False
            )
            
            self.keyboard_listener.start()
            print("✅ Keyboard listener started!")
            
        except Exception as e:
            print(f"❌ Error starting recording: {e}")
            import traceback
            traceback.print_exc()
            self.recording = False
    
    def stop_recording(self) -> List[Tuple[float, str, Any]]:
        """Stop recording and return the recorded actions"""
        if not self.recording:
            return []
        
        self.recording = False
        
        # Stop mouse polling
        self.mouse_thread_running = False
        if self.mouse_thread and self.mouse_thread.is_alive():
            self.mouse_thread.join(timeout=1.0)
            print("✅ Mouse polling thread stopped")
        
        # Stop keyboard listener
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
            print("✅ Keyboard listener stopped")
        
        # Add end marker
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.actions.append((elapsed, "end_marker", None))
        
        print(f"⏹️ Recording stopped! Captured {len(self.actions)} actions.")
        return self.actions.copy()
    
    def _get_timestamp(self) -> float:
        """Get current timestamp relative to recording start"""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time
    
    def _on_key_press(self, key):
        """Handle key press events"""
        if not self.recording:
            return
        
        timestamp = self._get_timestamp()
        
        try:
            # Handle special keys
            if hasattr(key, 'char') and key.char is not None:
                key_name = key.char
            else:
                key_name = key.name
            
            # Skip F3 key since it's used for recording control
            if key_name.lower() == 'f3':
                print("🚫 Skipping F3 key from recording")
                return
            
            print(f"⌨️ Recording key press: {key_name} at {timestamp:.3f}s")
            self.actions.append((timestamp, "key_press", key_name))
            
        except AttributeError:
            # Handle special keys that don't have char attribute
            key_str = str(key)
            if 'f3' not in key_str.lower():
                print(f"⌨️ Recording special key press: {key_str} at {timestamp:.3f}s")
                self.actions.append((timestamp, "key_press", key_str))
    
    def _on_key_release(self, key):
        """Handle key release events"""
        if not self.recording:
            return
        
        timestamp = self._get_timestamp()
        
        try:
            if hasattr(key, 'char') and key.char is not None:
                key_name = key.char
            else:
                key_name = key.name
            
            # Skip F3 key since it's used for recording control
            if key_name.lower() == 'f3':
                return
            
            print(f"⌨️ Recording key release: {key_name} at {timestamp:.3f}s")
            self.actions.append((timestamp, "key_release", key_name))
            
        except AttributeError:
            key_str = str(key)
            if 'f3' not in key_str.lower():
                print(f"⌨️ Recording special key release: {key_str} at {timestamp:.3f}s")
                self.actions.append((timestamp, "key_release", key_str))


class ActionPlayer:
    """Plays back recorded action sequences with end delay cooldown"""
    
    def __init__(self):
        self.playing = False
        self.current_thread: Optional[threading.Thread] = None
        self.stop_requested = False
        self.in_end_delay = False
    
    def play_sequence(self, actions: List[Tuple[float, str, Any]], 
                     loop: bool = False, end_delay: float = 5.0):
        """Play back a sequence of actions with end delay cooldown"""
        if self.playing:
            print("⚠️ Already playing a sequence!")
            return
        
        if not actions:
            print("⚠️ No actions to play!")
            return
        
        self.stop_requested = False
        self.current_thread = threading.Thread(
            target=self._play_sequence_thread,
            args=(actions, loop, end_delay)
        )
        self.current_thread.daemon = True
        self.current_thread.start()
    
    def stop_playback(self):
        """Stop the current playback"""
        self.stop_requested = True
        if self.current_thread and self.current_thread.is_alive():
            self.current_thread.join(timeout=1.0)
        self.playing = False
        self.in_end_delay = False
    
    def _play_sequence_thread(self, actions: List[Tuple[float, str, Any]], 
                            loop: bool, end_delay: float):
        """Thread function for playing back actions with end delay"""
        self.playing = True
        
        try:
            while True:
                print("▶️ Playing attack sequence...")
                
                # Play the recorded sequence
                last_timestamp = 0.0
                for timestamp, action_type, action_data in actions:
                    if self.stop_requested:
                        break
                    
                    # Calculate delay
                    delay = timestamp - last_timestamp
                    if delay > 0:
                        time.sleep(delay)
                    
                    # Execute action
                    self._execute_action(action_type, action_data)
                    last_timestamp = timestamp
                
                if self.stop_requested or not loop:
                    break
                
                # End delay phase - press 3 and spam E
                print(f"⏳ End delay phase ({end_delay}s) - pressing 3 and spamming E...")
                self.in_end_delay = True
                
                # Press 3 key
                self._press_key("3", True)
                time.sleep(0.1)
                self._press_key("3", False)
                time.sleep(0.2)
                
                # Spam E for the duration of end delay
                end_delay_start = time.time()
                while time.time() - end_delay_start < end_delay:
                    if self.stop_requested:
                        break
                    
                    # Press E
                    self._press_key("e", True)
                    time.sleep(0.05)
                    self._press_key("e", False)
                    time.sleep(0.15)  # E every 0.2 seconds
                
                # Press 3 again to end cooldown phase
                if not self.stop_requested:
                    self._press_key("3", True)
                    time.sleep(0.1)
                    self._press_key("3", False)
                    time.sleep(0.5)  # Brief pause before next sequence
                
                self.in_end_delay = False
                
                if not loop or self.stop_requested:
                    break
                
                print("🔄 Starting next attack cycle...")
        
        except Exception as e:
            print(f"❌ Error during playback: {e}")
        
        finally:
            self.playing = False
            self.in_end_delay = False
            print("⏹️ Attack sequence finished.")
    
    def _execute_action(self, action_type: str, action_data: Any):
        """Execute a single action"""
        try:
            if action_type == "key_press":
                key = action_data
                self._press_key(key, True)
            
            elif action_type == "key_release":
                key = action_data
                self._press_key(key, False)
            
            elif action_type == "end_marker":
                pass  # End of sequence marker
            
        except Exception as e:
            print(f"❌ Error executing action {action_type}: {e}")
    
    def _press_key(self, key: str, press: bool):
        """Press or release a key or mouse button"""
        try:
            # Handle mouse buttons
            if key in ['left', 'right', 'middle']:
                if press:
                    pyautogui.mouseDown(button=key)
                else:
                    pyautogui.mouseUp(button=key)
                return
            
            # Handle keyboard keys
            key_mapping = {
                'space': 'space',
                'enter': 'enter',
                'shift': 'shift',
                'ctrl': 'ctrl',
                'alt': 'alt',
                'tab': 'tab',
                'esc': 'esc',
                'up': 'up',
                'down': 'down',
                'left': 'left',
                'right': 'right'
            }
            
            mapped_key = key_mapping.get(key.lower(), key)
            
            if press:
                pydirectinput.keyDown(mapped_key)
            else:
                pydirectinput.keyUp(mapped_key)
                
        except Exception as e:
            print(f"❌ Error with key/button {key}: {e}")


class CustomAttackManager:
    """Manages custom attack sequences"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = {}
        self.recorder = ActionRecorder()
        self.player = ActionPlayer()
        
        self.load_config()
    
    def load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {}
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def start_recording(self):
        """Start recording a new attack sequence"""
        self.recorder.start_recording()
    
    def stop_recording(self, sequence_name: str = "Custom Attack"):
        """Stop recording and save the sequence"""
        actions = self.recorder.stop_recording()
        
        if actions:
            self.config["recorded_actions"] = actions
            self.config["attack_settings"] = self.config.get("attack_settings", {})
            self.config["attack_settings"]["sequence_name"] = sequence_name
            self.save_config()
            
            print(f"✅ Sequence '{sequence_name}' saved with {len(actions)} actions.")
            return True
        
        return False
    
    def play_custom_attack(self, loop: bool = False):
        """Play the saved custom attack sequence with end delay"""
        actions = self.config.get("recorded_actions", [])
        
        if not actions:
            print("⚠️ No custom attack sequence found!")
            return False
        
        attack_settings = self.config.get("attack_settings", {})
        sequence_name = attack_settings.get("sequence_name", "Custom Attack")
        end_delay = attack_settings.get("end_delay", 5.0)
        
        print(f"▶️ Playing '{sequence_name}' sequence with {end_delay}s end delay...")
        self.player.play_sequence(actions, loop, end_delay)
        return True
    
    def stop_attack(self):
        """Stop the current attack playback"""
        self.player.stop_playback()
    
    def is_custom_enabled(self) -> bool:
        """Check if custom attack mode is enabled"""
        attack_settings = self.config.get("attack_settings", {})
        enabled = attack_settings.get("custom_sequence_enabled", False)
        
        print(f"🔍 is_custom_enabled check:")
        print(f"   - attack_settings: {attack_settings}")
        print(f"   - custom_sequence_enabled: {enabled}")
        print(f"   - has_sequence: {self.has_custom_sequence()}")
        
        return enabled
    
    def has_custom_sequence(self) -> bool:
        """Check if a custom sequence exists"""
        return bool(self.config.get("recorded_actions"))
    
    def get_sequence_info(self) -> Dict[str, Any]:
        """Get information about the current sequence"""
        actions = self.config.get("recorded_actions", [])
        attack_settings = self.config.get("attack_settings", {})
        
        if not actions:
            return {"exists": False}
        
        # Calculate sequence duration
        duration = 0.0
        if actions:
            last_action = actions[-1]
            if last_action[1] == "end_marker":
                duration = last_action[0]
        
        return {
            "exists": True,
            "name": attack_settings.get("sequence_name", "Custom Attack"),
            "action_count": len(actions),
            "duration": duration,
            "loop_enabled": attack_settings.get("loop_sequence", True),
            "delay": attack_settings.get("sequence_delay", 0.1)
        }
    
    def clear_sequence(self):
        """Clear the current custom sequence"""
        self.config["recorded_actions"] = []
        self.save_config()
        print("🗑️ Custom sequence cleared.")


# Example usage and testing
if __name__ == "__main__":
    import sys
    
    # Test the custom attack system
    manager = CustomAttackManager("test_config.json")
    
    print("Custom Attack System Test")
    print("Commands:")
    print("  r - Start recording")
    print("  s - Stop recording")
    print("  p - Play sequence")
    print("  l - Play sequence (looped)")
    print("  x - Stop playback")
    print("  i - Show sequence info")
    print("  c - Clear sequence")
    print("  q - Quit")
    
    while True:
        try:
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == 'r':
                manager.start_recording()
            elif cmd == 's':
                manager.stop_recording("Test Sequence")
            elif cmd == 'p':
                manager.play_custom_attack(loop=False)
            elif cmd == 'l':
                manager.play_custom_attack(loop=True)
            elif cmd == 'x':
                manager.stop_attack()
            elif cmd == 'i':
                info = manager.get_sequence_info()
                print(f"Sequence info: {info}")
            elif cmd == 'c':
                manager.clear_sequence()
            elif cmd == 'q':
                manager.stop_attack()
                break
            else:
                print("Unknown command!")
                
        except KeyboardInterrupt:
            manager.stop_attack()
            break
    
    print("Test complete!")