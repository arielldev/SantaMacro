import time
import json
import os
import math
import logging
import threading
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Optional, Tuple, List

import numpy as np
import cv2
from mss import mss
import pyautogui
import pydirectinput
from pynput import keyboard
import platform
import ctypes
from ctypes import wintypes
from overlay_qt import OverlayQt
import glob

VK_LEFT = 0x25
VK_RIGHT = 0x27

KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP = 0x0002


class MacroState:
    IDLE = "idle"
    LEARNING = "learning"
    DETECTING = "detecting"
    CLICKING = "clicking"
    LOST = "lost"
    PAUSED = "paused"
    SHUTDOWN = "shutdown"
    CAMERA_TRACKING = "camera_tracking"


@dataclass
class DetectionResult:
    bbox: Optional[Tuple[int, int, int, int]]
    confidence: float
    color_score: float = 0.0
    
    
@dataclass
class SantaProfile:
    """Learned characteristics of Santa during learning phase"""
    size_min: int = 0
    size_max: int = 9999
    avg_speed: float = 0.0
    color_signature: Optional[np.ndarray] = None
    movement_history: List[Tuple[float, Tuple[int, int]]] = None
    
    def __post_init__(self):
        if self.movement_history is None:
            self.movement_history = []


class SantaMacro:
    def __init__(self, config_path: str):
        self.config_path = config_path  # Store config path for settings GUI
        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        self.logger = self._setup_logger(self.cfg["logging"])
        self.state = MacroState.IDLE
        self.last_state = self.state

        self.sct = mss()
        self.monitor_index = self.cfg["capture"]["monitor_index"]
        self.monitor = self.sct.monitors[self.monitor_index]
        self.roi = self._compute_roi()
        self.grayscale = self.cfg["capture"].get("grayscale", True)

        self.templates: List[np.ndarray] = []
        self.template_names: List[str] = []
        self._load_templates(self.cfg["detection"]["templates"], self.grayscale)

        self.det_mode: str = self.cfg["detection"].get("mode", "template").lower()
        self.method = getattr(cv2, self.cfg["detection"].get("method", "TM_CCOEFF_NORMED"))
        self.scales: List[float] = self.cfg["detection"].get("scales", [0.9, 1.0, 1.1])
        self.threshold: float = float(self.cfg["detection"].get("threshold", 0.20))
        self.ema_alpha: float = float(self.cfg["detection"].get("ema_alpha", 0.25))
        
        self._last_detection_frame = -1000
        self._detection_grace_frames = 20  # Increased from 8 to 20 for long custom attack sequences
        self._predicted_position = None
        self._position_history = []
        self._max_position_history = 5
        self._consecutive_detections = 0
        self._required_detections_to_start = 3
        
        self._static_santa_position = None
        self._static_santa_start_time = None
        self._static_santa_timeout = 15.0
        self._static_position_threshold = 100
        self._doing_recovery_search = False
        self._recovery_search_start = None
        self._recovery_search_duration = 1.5
        
        # Search alternation
        self._search_direction_start = None
        self._search_direction_duration = 3.0  # Switch directions every 3 seconds
        
        self.attack_committed = False
        
        # Attack phase tracking
        self.attack_phase = "idle"
        self.attack_phase_start: Optional[float] = None
        
        # Initialize custom attack manager
        try:
            from action_system import CustomAttackManager
            self.custom_attack_manager = CustomAttackManager(self.config_path)
        except Exception as e:
            self.logger.error(f"Failed to initialize custom attack manager: {e}")
            self.custom_attack_manager = None
        
        # Initialize webhook manager
        try:
            from webhook_manager import WebhookManager
            self.webhook_manager = WebhookManager(self.cfg)
            self.logger.info("Webhook manager initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize webhook manager: {e}")
            self.webhook_manager = None
        
        self._x_key_down = False
        self._smoothed_cursor_pos = None
        self._cursor_smooth_alpha = 0.4
        self.motion_cfg = self.cfg["detection"].get("motion", {})

        self.learning_duration: float = float(self.cfg.get("smart_tracking", {}).get("learning_duration_seconds", 10.0))
        self.lock_on_enabled: bool = bool(self.cfg.get("smart_tracking", {}).get("enabled", True))
        self.min_santa_size: int = int(self.cfg.get("smart_tracking", {}).get("min_santa_size_px", 25))
        self.max_santa_size: int = int(self.cfg.get("smart_tracking", {}).get("max_santa_size_px", 300))
        self.size_tolerance: float = float(self.cfg.get("smart_tracking", {}).get("size_tolerance", 0.5))
        self.position_jump_threshold: int = int(self.cfg.get("smart_tracking", {}).get("max_position_jump_px", 150))
        self.color_similarity_threshold: float = float(self.cfg.get("smart_tracking", {}).get("color_similarity_threshold", 0.6))
        
        self.camera_control_enabled: bool = bool(self.cfg.get("camera_control", {}).get("enabled", True))
        self.camera_left_edge_threshold: int = int(self.cfg.get("camera_control", {}).get("left_edge_threshold_px", 100))
        self.camera_drag_speed: float = float(self.cfg.get("camera_control", {}).get("drag_speed", 0.3))
        self.camera_center_deadzone: int = int(self.cfg.get("camera_control", {}).get("center_deadzone_px", 50))

        self.mouse_smooth: float = float(self.cfg["aiming"].get("mouse_smooth_factor", 0.35))
        self.max_click_duration_ms: int = int(self.cfg["aiming"].get("max_click_duration_ms", 4000))
        self.reentry_delay_ms: int = int(self.cfg["aiming"].get("reentry_delay_ms", 250))
        self.cooldown_ms: int = int(self.cfg["aiming"].get("cooldown_after_loss_ms", 500))
        self.clamp_to_screen: bool = bool(self.cfg["aiming"].get("clamp_to_screen", True))

        self.tick_hz: int = int(self.cfg["loop"].get("tick_hz", 25))
        self.idle_backoff_ms: int = int(self.cfg["loop"].get("idle_backoff_ms", 25))
        self.tick_interval: float = 1.0 / max(self.tick_hz, 1)

        self.overlay_enabled = bool(self.cfg["overlay"].get("enabled", True))
        self.overlay_title = self.cfg["overlay"].get("window_title", "SantaMacro Overlay")
        self.overlay_engine = self.cfg["overlay"].get("engine", "opencv").lower()
        self.overlay_click_through = bool(self.cfg["overlay"].get("click_through", True))
        self.overlay_topmost = bool(self.cfg["overlay"].get("topmost", True))
        self.overlay_draw_frame = bool(self.cfg["overlay"].get("draw_frame", False))
        self.overlay_status_bar_mode = bool(self.cfg["overlay"].get("status_bar_mode", False))
        self.show_fps = bool(self.cfg["overlay"].get("show_fps", True))
        self.save_low_conf_frames = bool(self.cfg["overlay"].get("save_low_conf_frames", False))
        self.dump_dir = self.cfg["overlay"].get("dump_dir", "logs/dumps")
        os.makedirs(self.dump_dir, exist_ok=True)
        self.low_conf_dump_threshold = float(self.cfg["overlay"].get("low_conf_dump_threshold", 0.55))
        self.mouse_smooth: float = float(self.cfg.get("aiming", {}).get("mouse_smooth_factor", 0.35))
        self.max_mouse_speed_px: int = int(self.cfg.get("aiming", {}).get("max_mouse_speed_px", 1200))
        self.clicks_enabled = bool(self.cfg["clicks"].get("enabled", False))
        self.click_load_ms = int(self.cfg.get("clicks", {}).get("load_ms", 1000))
        self.click_shoot_ms = int(self.cfg.get("clicks", {}).get("shoot_ms", 5000))
        self.click_cooldown_ms = int(self.cfg.get("clicks", {}).get("cooldown_ms", 6000))
        self.click_min_move_speed = float(self.cfg.get("clicks", {}).get("min_movement_px_per_sec", 3))
        self.click_skip_movement_validation = self.cfg.get("clicks", {}).get("skip_movement_validation", False)
        self.click_always_spam = self.cfg.get("clicks", {}).get("always_click_during_shoot", False)
        self.shoot_accept_conf = float(self.cfg.get("clicks", {}).get("shoot_accept_conf", 0.10))
        self.prefer_color_during_shoot = bool(self.cfg.get("clicks", {}).get("prefer_color_during_shoot", True))
        self.shoot_ignore_radius_px = int(self.cfg.get("clicks", {}).get("shoot_ignore_radius_px", 180))
        self.require_foreground = bool(self.cfg["safety"].get("require_foreground", False))

        self.learning_enabled = bool(self.cfg.get("learning", {}).get("enabled", False))
        self.learning_auto_adjust = bool(self.cfg.get("learning", {}).get("auto_adjust_threshold", True))
        self.learning_log = bool(self.cfg.get("learning", {}).get("log_detections", True))
        self.learning_save_samples = bool(self.cfg.get("learning", {}).get("save_samples", True))
        self.learning_sample_dir = self.cfg.get("learning", {}).get("sample_dir", "logs/learning")
        if self.learning_enabled:
            os.makedirs(self.learning_sample_dir, exist_ok=True)
        self._learning_detections = []

        self._learning_start_ts: Optional[float] = None
        self._santa_profile: SantaProfile = SantaProfile()
        self._learning_samples: List[Tuple[float, Tuple[int, int, int, int], np.ndarray]] = []
        self._learning_first_bbox: Optional[Tuple[int, int, int, int]] = None
        self._learning_stable_count: int = 0
        self._learning_lost_count: int = 0
        self._learning_continuous_start: Optional[float] = None
        self._learning_last_sample_ts: Optional[float] = None
        self._postlock_consecutive_valid: int = 0
        self._postlock_required_valid: int = 5
        self._locked_santa: bool = False
        self._last_santa_center: Optional[Tuple[int, int]] = None
        self._santa_velocity: Tuple[float, float] = (0.0, 0.0)
        self._predicted_position: Optional[Tuple[int, int]] = None
        self._rejected_detections_count: int = 0
        self._camera_drag_active: bool = False
        self._camera_drag_start_ts: Optional[float] = None
        self._right_mouse_down: bool = False
        self._debug_log_counter: int = 0
        
        self._detection_movement_history: List[Tuple[int, int]] = []
        self._max_movement_history: int = 10  # Increased to track more frames
        self._min_movement_pixels: int = 15  # Reasonable movement threshold - Santa moves, trees don't
        self._has_attacked_successfully: bool = False
        self._camera_has_tracked: bool = False  # Track if we've followed Santa with camera
        self._static_rejection_count: int = 0  # Track consecutive static object rejections
        self._last_rejected_position: Optional[int] = None  # X position of last rejected static object

        self._keyboard_listener = None
        self._running = False
        self._paused = False
        self._zoom_performed = False
        self._mouse_down = False
        self._click_started_ts: Optional[float] = None
        
        # Hotkey debouncing to prevent phantom keypresses
        self._last_hotkey_time = {}
        self._hotkey_debounce_ms = 500  # Minimum 500ms between same hotkey presses
        
        # Periodic cleanup to prevent stuck keys
        self._last_cleanup_frame = 0
        self._cleanup_interval = 100  # Force cleanup every 100 frames
        
        # Periodic cleanup to prevent stuck keys
        self._last_cleanup_frame = 0
        self._cleanup_interval = 100  # Force cleanup every 100 frames

        self._ema_conf: Optional[float] = None
        self._ema_center: Optional[Tuple[float, float]] = None
        
        self._velocity: Tuple[float, float] = (0.0, 0.0)
        self._last_position: Optional[Tuple[float, float]] = None
        self._last_position_ts: Optional[float] = None
        self._stable_detections: int = 0
        self._required_stable_frames: int = 1
        self._last_valid_bbox: Optional[Tuple[int, int, int, int]] = None
        self._prediction_weight: float = 0.4
        self._last_detection_ts: Optional[float] = None
        self._low_conf_start_ts: Optional[float] = None

        self._last_loss_ts: Optional[float] = None
        self._last_reentry_ts: Optional[float] = None
        self._movement_history: List[Tuple[float, Tuple[int, int]]] = []
        self._click_cycle_phase: str = "cooldown"
        self._click_cycle_start_ts: Optional[float] = None
        self._locked_aim_point: Optional[Tuple[int, int]] = None
        self._shoot_ref_bbox: Optional[Tuple[int, int, int, int]] = None
        
        self._locked_on_santa: bool = False
        self._lock_start_ts: Optional[float] = None
        self._lock_timeout_seconds: float = 30.0
        self._santa_bbox_history: List[Tuple[int, int, int, int]] = []
        self._max_bbox_history: int = 5
        self._stuck_detection_threshold: int = 10
        self._stuck_counter: int = 0
        self._last_movement_ts: Optional[float] = None
        self._movement_timeout_seconds: float = 2.0
        
        self._last_e_press_ts: Optional[float] = None
        self._e_spam_interval: float = 0.1
        
        self._santa_confirm_start_ts: Optional[float] = None
        self._santa_confirm_duration: float = 1.5

        self._shoot_tracker = None
        self._shoot_track_failures: int = 0
        self._shoot_pending_candidate: Optional[Tuple[int, int, int, int]] = None
        self._shoot_pending_count: int = 0
        self.shoot_roi_radius_px: int = int(self.cfg.get("shoot", {}).get("roi_radius_px", 220))
        self.shoot_accept_consecutive: int = int(self.cfg.get("shoot", {}).get("accept_consecutive", 2))
        self.shoot_color_red_weight: float = float(self.cfg.get("shoot", {}).get("red_weight", 0.12))
        self.shoot_fallback_ms: int = int(self.cfg.get("shoot", {}).get("fallback_ms", 450))
        self.shoot_tracker_fail_reset: int = int(self.cfg.get("shoot", {}).get("tracker_fail_reset", 3))
        self.shoot_blend_detection: bool = bool(self.cfg.get("shoot", {}).get("blend_detection", True))
        self.shoot_det_max_jump_px: int = int(self.cfg.get("shoot", {}).get("det_max_jump_px", 120))
        self.shoot_det_min_iou: float = float(self.cfg.get("shoot", {}).get("det_min_iou", 0.18))
        self.shoot_det_max_area_frac: float = float(self.cfg.get("shoot", {}).get("det_max_area_frac", 0.25))
        self.shoot_det_max_center_dist_px: int = int(self.cfg.get("shoot", {}).get("det_max_center_dist_px", 220))
        self.shoot_blend_iou_min: float = float(self.cfg.get("shoot", {}).get("blend_iou_min", 0.30))
        self._shoot_tmpl: Optional[np.ndarray] = None
        self._shoot_tmpl_size: Optional[Tuple[int, int]] = None
        self._shoot_track_box: Optional[Tuple[int, int, int, int]] = None
        self.shoot_tmpl_min_score: float = float(self.cfg.get("shoot", {}).get("tmpl_min_score", 0.45))
        self._shoot_last_det_center: Optional[Tuple[int, int]] = None
        self._shoot_last_det_ts: Optional[float] = None

        self._fps = 0.0
        self._last_frame_ts = time.time()
        self._prev_frame_gray: Optional[np.ndarray] = None
        self._overlay_initialized = False
        self._qt_overlay: Optional[OverlayQt] = None
        self._last_overlay_update_ts = 0.0

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0

        self.logger.info("SantaMacro initialized. Templates loaded: %d", len(self.templates))
        self.ignore_top_fraction = float(self.cfg.get("capture", {}).get("ignore_top_fraction", 0.0))
        self.tracking_stickiness_ms: int = int(self.cfg.get("aiming", {}).get("tracking_stickiness_ms", 600))
        self.ignore_zones: List[dict] = self.cfg.get("capture", {}).get("ignore_zones", [])
        self.logger.debug("Config: det_mode=%s method=%s scales=%s threshold=%.2f ema_alpha=%.2f", self.det_mode, self.method, self.scales, self.threshold, self.ema_alpha)
        self.logger.debug("ROI: left=%d top=%d width=%d height=%d ignore_top_fraction=%.2f", self.roi["left"], self.roi["top"], self.roi["width"], self.roi["height"], self.ignore_top_fraction)
        self.logger.debug("Click cycle: load=%dms shoot=%dms cooldown=%dms always_spam=%s skip_move_val=%s", self.click_load_ms, self.click_shoot_ms, self.click_cooldown_ms, self.click_always_spam, self.click_skip_movement_validation)
        self.logger.debug("Shoot phase: accept_conf=%.2f prefer_color=%s ignore_radius=%dpx", self.shoot_accept_conf, self.prefer_color_during_shoot, self.shoot_ignore_radius_px)
        self.logger.debug("Shoot tracker: roi_radius=%dpx accept_consecutive=%d red_weight=%.2f", self.shoot_roi_radius_px, self.shoot_accept_consecutive, self.shoot_color_red_weight)
        self.logger.debug("Shoot template: min_score=%.2f", self.shoot_tmpl_min_score)
        self.logger.debug("Aiming: mouse_smooth=%.2f max_mouse_speed=%dpx stickiness_ms=%d clamp=%s", self.mouse_smooth, self.max_mouse_speed_px, self.tracking_stickiness_ms, self.clamp_to_screen)
        
        self.minimal_santa_mode_enabled = True
        self.smooth_mouse_pos = None
        self.smooth_factor = 0.22
        self.camera_keys_pressed = set()
        
        self.is_holding_arrow = False
        self.current_arrow_key = None
        self.arrow_lock = threading.Lock()
        self.keys_lock = threading.Lock()
        
        self.search_state = "idle"
        self.last_santa_side = "left"
        
        self.last_kill_time = 0
        self.e_spam_duration = 3.0
        
        self.yolo_model = None
        self.yolo_model_path = self.cfg.get("detection", {}).get("yolo_model_path", None)
        self.santa_class_name = "Santa"
        if self.yolo_model_path:
            if not os.path.isabs(self.yolo_model_path):
                config_dir = os.path.dirname(os.path.abspath(config_path))
                self.yolo_model_path = os.path.join(config_dir, self.yolo_model_path)
            
            if os.path.exists(self.yolo_model_path):
                try:
                    from ultralytics import YOLO
                    self.yolo_model = YOLO(self.yolo_model_path)
                    self.logger.info(f"[YOLO MODEL] Loaded from {self.yolo_model_path}")
                except Exception as e:
                    self.logger.error(f"[YOLO MODEL] Failed to load: {e}")
            else:
                self.logger.warning(f"[YOLO MODEL] File not found: {self.yolo_model_path}")
        else:
            self.logger.warning("[YOLO MODEL] No model path configured")
        
        self.logger.info("[MINIMAL MODE] Santa Lock-on Mode ENABLED")



    def _setup_logger(self, log_cfg: dict) -> logging.Logger:
        logger = logging.getLogger("SantaMacro")
        level = getattr(logging, log_cfg.get("level", "INFO"))
        logger.setLevel(level)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        return logger



    def _perform_initial_zoom(self):
        """Zoom out to max, then zoom in to a fixed level on startup."""
        self.logger.info("[ZOOM] Performing initial zoom setup...")
        
        self.logger.info("[ZOOM] Zooming out to maximum...")
        for _ in range(20):
            pyautogui.scroll(-100)
            time.sleep(0.05)
        
        time.sleep(0.3)
        
        zoom_in_amount = self.cfg.get("camera_control", {}).get("initial_zoom_in", 5)
        self.logger.info(f"[ZOOM] Zooming in by {zoom_in_amount} steps...")
        for _ in range(zoom_in_amount):
            pyautogui.scroll(100)
            time.sleep(0.05)
        
        time.sleep(0.3)
        self.logger.info("[ZOOM] Initial zoom setup complete!")

    def _is_roblox_focused(self) -> bool:
        """Check if Roblox window is currently focused."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            return "Roblox" in title or "roblox" in title.lower()
        except:
            return True
    
    def _force_focus_roblox(self) -> bool:
        """Forcefully focus Roblox window - critical for input to work"""
        try:
            # Find Roblox window
            hwnd = ctypes.windll.user32.FindWindowW(None, "Roblox")
            if hwnd:
                # Restore if minimized
                SW_RESTORE = 9
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                
                # Force foreground
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                
                # Extra push - sometimes needed
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetActiveWindow(hwnd)
                
                return True
            return False
        except Exception as e:
            self.logger.warning(f"[FOCUS] Failed to focus Roblox: {e}")
            return False

    def _compute_roi(self) -> dict:
        left = self.monitor["left"]
        top = self.monitor["top"]
        width = self.monitor["width"]
        height = self.monitor["height"]
        frac = self.cfg["capture"]["roi_fraction"]
        roi = {
            "left": int(left + frac["left"] * width),
            "top": int(top + frac["top"] * height),
            "width": int(frac["width"] * width),
            "height": int(frac["height"] * height),
        }
        return roi
    
    def _native_key_release(self, vk_code: int):
        """Force release a key using Windows SendInput API (most reliable)"""
        try:
            # Define INPUT structure
            PUL = ctypes.POINTER(ctypes.c_ulong)
            
            class KeyBdInput(ctypes.Structure):
                _fields_ = [("wVk", ctypes.c_ushort),
                           ("wScan", ctypes.c_ushort),
                           ("dwFlags", ctypes.c_ulong),
                           ("time", ctypes.c_ulong),
                           ("dwExtraInfo", PUL)]
            
            class HardwareInput(ctypes.Structure):
                _fields_ = [("uMsg", ctypes.c_ulong),
                           ("wParamL", ctypes.c_short),
                           ("wParamH", ctypes.c_ushort)]
            
            class MouseInput(ctypes.Structure):
                _fields_ = [("dx", ctypes.c_long),
                           ("dy", ctypes.c_long),
                           ("mouseData", ctypes.c_ulong),
                           ("dwFlags", ctypes.c_ulong),
                           ("time", ctypes.c_ulong),
                           ("dwExtraInfo", PUL)]
            
            class Input_I(ctypes.Union):
                _fields_ = [("ki", KeyBdInput),
                           ("mi", MouseInput),
                           ("hi", HardwareInput)]
            
            class Input(ctypes.Structure):
                _fields_ = [("type", ctypes.c_ulong),
                           ("ii", Input_I)]
            
            # Create keyup event
            extra = ctypes.c_ulong(0)
            ii_ = Input_I()
            ii_.ki = KeyBdInput(vk_code, 0, 0x0002, 0, ctypes.pointer(extra))  # 0x0002 = KEYEVENTF_KEYUP
            x = Input(ctypes.c_ulong(1), ii_)
            
            # Send the input
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
            time.sleep(0.01)
        except Exception as e:
            self.logger.warning(f"[NATIVE INPUT ERROR] Failed to release VK {vk_code}: {e}")
    
    def _force_release_all_arrows(self):
        """Force release all arrow keys using native Windows API (most reliable)"""
        try:
            # Release LEFT and RIGHT arrows using Windows SendInput
            self._native_key_release(0x25)  # VK_LEFT
            self._native_key_release(0x27)  # VK_RIGHT
            
            # Also try pydirectinput as backup
            for key in ['left', 'right']:
                try:
                    pydirectinput.keyUp(key)
                except:
                    pass
            
            # Clear our tracking state
            with self.arrow_lock:
                self.current_arrow_key = None
                self.is_holding_arrow = False
            with self.keys_lock:
                self.camera_keys_pressed.clear()
            
            time.sleep(0.02)
        except Exception as e:
            self.logger.warning(f"[CLEANUP ERROR] {e}")
    
    def _safe_key_press(self, key: str, action: str = "down"):
        """Safely press/release a key with cleanup and delays to prevent stuck keys"""
        try:
            if action == "down":
                pydirectinput.keyDown(key)
                time.sleep(0.01)  # Small delay after keyDown
            elif action == "up":
                pydirectinput.keyUp(key)
                time.sleep(0.01)  # Small delay after keyUp
        except Exception as e:
            self.logger.warning(f"[INPUT ERROR] Failed to {action} key '{key}': {e}")

    def _load_templates(self, paths: List[str], grayscale: bool):
        loaded = 0
        exts = {".png", ".jpg", ".jpeg", ".bmp"}
        for p in paths:
            candidates: List[str] = []
            if any(ch in p for ch in ["*", "?"]):
                candidates = sorted(glob.glob(p))
            elif os.path.isdir(p):
                for name in os.listdir(p):
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp) and os.path.splitext(fp)[1].lower() in exts:
                        candidates.append(fp)
                candidates.sort()
            elif os.path.exists(p):
                candidates = [p]
            else:
                self.logger.warning("Template path not found: %s", p)
                continue

            for fp in candidates:
                img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR)
                if img is None:
                    self.logger.warning("Failed to load template: %s", fp)
                    continue
                self.templates.append(img)
                self.template_names.append(os.path.basename(fp))
                loaded += 1

        if loaded == 0:
            self.logger.warning("No templates loaded. Detection will be disabled until templates are provided.")
        else:
            self.logger.info("Loaded %d templates: %s", loaded, ", ".join(self.template_names[:6]) + ("..." if loaded > 6 else ""))

    def _ignored_top_pixels(self) -> int:
        """Return the number of pixels from the top of the ROI to ignore."""
        frac = max(0.0, float(getattr(self, "ignore_top_fraction", 0.0)))
        return int(frac * self.roi["height"]) if frac > 0.0 else 0

    def _grab_frame(self, mask_cursor: bool = True) -> np.ndarray:
        shot = self.sct.grab(self.roi)
        frame = np.array(shot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        if getattr(self, "ignore_top_fraction", 0.0) > 0.0:
            mask_h = int(frame.shape[0] * self.ignore_top_fraction)
            if mask_h > 0:
                frame[:mask_h, :] = 0
        if mask_cursor:
            try:
                if self._click_cycle_phase == "shoot" and self._mouse_down and self.shoot_ignore_radius_px > 0:
                    cur = pyautogui.position()
                    cx = cur.x - self.roi["left"]
                    cy = cur.y - self.roi["top"]
                    if 0 <= cx < frame.shape[1] and 0 <= cy < frame.shape[0]:
                        cv2.circle(frame, (int(cx), int(cy)), int(self.shoot_ignore_radius_px), (0, 0, 0), -1)
                        self.logger.debug("Shoot mask circle applied at ROI(%d,%d) radius=%d", int(cx), int(cy), int(self.shoot_ignore_radius_px))
            except Exception:
                pass
        ignore_middle = self.cfg.get("capture", {}).get("ignore_middle_zone", {})
        if ignore_middle.get("enabled", False):
            left_f = ignore_middle.get("left_frac", 0.35)
            right_f = ignore_middle.get("right_frac", 0.65)
            top_f = ignore_middle.get("top_frac", 0.0)
            height_f = ignore_middle.get("height_frac", 0.35)
            h, w = frame.shape[:2]
            x0 = int(w * left_f)
            x1 = int(w * right_f)
            y0 = int(h * top_f)
            y1 = int(h * (top_f + height_f))
            if x0 < x1 and y0 < y1:
                frame[y0:y1, x0:x1] = 0
        if isinstance(self.ignore_zones, list) and self.ignore_zones:
            h, w = frame.shape[:2]
            for z in self.ignore_zones:
                lf = float(z.get("left_frac", 0.0))
                tf = float(z.get("top_frac", 0.0))
                wf = float(z.get("width_frac", 0.0))
                hf = float(z.get("height_frac", 0.0))
                x0 = max(0, int(w * lf))
                y0 = max(0, int(h * tf))
                x1 = min(w, int(x0 + w * wf))
                y1 = min(h, int(y0 + h * hf))
                if x1 > x0 and y1 > y0:
                    frame[y0:y1, x0:x1] = 0
        return frame

    def _match_templates(self, frame: np.ndarray) -> Optional[DetectionResult]:
        if not self.templates:
            return DetectionResult(bbox=None, confidence=0.0)
        best_conf = -1.0
        best_bbox = None
        frame_for_match = frame
        for ti, tmpl in enumerate(self.templates):
            for s in self.scales:
                h, w = tmpl.shape[:2]
                scaled_w = max(1, int(w * s))
                scaled_h = max(1, int(h * s))
                tmpl_scaled = cv2.resize(tmpl, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
                if frame_for_match.shape[0] < scaled_h or frame_for_match.shape[1] < scaled_w:
                    continue
                res = cv2.matchTemplate(frame_for_match, tmpl_scaled, self.method)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                if self.method in (cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED):
                    conf = 1.0 - float(min_val)
                    loc = min_loc
                else:
                    conf = float(max_val)
                    loc = max_loc
                if conf > best_conf:
                    x, y = loc
                    bbox = (x, y, scaled_w, scaled_h)
                    best_conf = conf
                    best_bbox = bbox
        if best_bbox is None:
            return DetectionResult(bbox=None, confidence=0.0)
        abs_bbox = (
            self.roi["left"] + best_bbox[0],
            self.roi["top"] + best_bbox[1],
            best_bbox[2],
            best_bbox[3],
        )
        return DetectionResult(bbox=abs_bbox, confidence=best_conf)

    def _detect_motion_color(self, frame_bgr: np.ndarray) -> Optional[DetectionResult]:
        """Detect Santa's red sleigh using color segmentation"""
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

        lower_red1 = np.array([0, 80, 80])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 80, 80])
        upper_red2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < 30:
            return None

        x, y, w, h = cv2.boundingRect(largest)
        
        if w < 20 or h < 20:
            self.logger.debug("Rejecting tiny color detection: %dx%d (min 20x20)", w, h)
            return None
        
        if y < self._ignored_top_pixels():
            return None
        abs_bbox = (
            self.roi["left"] + x,
            self.roi["top"] + y,
            w,
            h,
        )

        conf = min(0.95, 0.7 + (area / 5000.0))
        return DetectionResult(bbox=abs_bbox, confidence=conf)

    def _detect_shoot_red(self, frame_bgr: np.ndarray, ref_center: Tuple[int, int]) -> Optional[DetectionResult]:
        cx, cy = ref_center
        rx = max(0, cx - self.roi["left"] - self.shoot_roi_radius_px)
        ry = max(0, cy - self.roi["top"] - self.shoot_roi_radius_px)
        rw = min(self.roi["width"], (cx - self.roi["left"] + self.shoot_roi_radius_px)) - rx
        rh = min(self.roi["height"], (cy - self.roi["top"] + self.shoot_roi_radius_px)) - ry
        if rw <= 10 or rh <= 10:
            return None
        search = frame_bgr[int(ry):int(ry+rh), int(rx):int(rx+rw)]
        hsv = cv2.cvtColor(search, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 80, 80], dtype=np.uint8)
        upper1 = np.array([10, 255, 255], dtype=np.uint8)
        lower2 = np.array([160, 80, 80], dtype=np.uint8)
        upper2 = np.array([179, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return None
        largest = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < 25:
            return None
        x, y, w, h = cv2.boundingRect(largest)
        
        if w < 20 or h < 20:
            self.logger.debug("_detect_shoot_red: Rejecting tiny detection: %dx%d (min 20x20)", w, h)
            return None
        
        gx = self.roi["left"] + rx + x
        gy = self.roi["top"] + ry + y
        conf = min(0.95, 0.6 + area / 4000.0)
        return DetectionResult(bbox=(gx, gy, w, h), confidence=conf)

    def _detect_motion(self, frame_gray: np.ndarray) -> DetectionResult:
        if self._prev_frame_gray is None:
            self._prev_frame_gray = frame_gray.copy()
            return DetectionResult(bbox=None, confidence=0.0)
        blur_k = int(self.motion_cfg.get("blur_kernel", 9))
        if blur_k % 2 == 0:
            blur_k += 1
        thr = int(self.motion_cfg.get("diff_threshold", 25))
        morph_k = int(self.motion_cfg.get("morph_kernel", 5))
        min_area = int(self.motion_cfg.get("min_area", 800))

        diff = cv2.absdiff(frame_gray, self._prev_frame_gray)
        diff = cv2.GaussianBlur(diff, (blur_k, blur_k), 0)

        _, mask_aggressive = cv2.threshold(diff, max(10, thr - 10), 255, cv2.THRESH_BINARY)
        _, mask_normal = cv2.threshold(diff, thr, 255, cv2.THRESH_BINARY)

        mask = cv2.bitwise_or(mask_aggressive, mask_normal)

        if morph_k > 1:
            kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_k, morph_k))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self._prev_frame_gray = frame_gray.copy()

        self.logger.debug("Motion detection: blur_k=%d thr=%d morph_k=%d min_area=%d contours=%d", blur_k, thr, morph_k, min_area, len(contours))
        if not contours:
            return DetectionResult(bbox=None, confidence=0.0)

        ignored_top = self._ignored_top_pixels()
        def _y_of(c):
            return cv2.boundingRect(c)[1]
        valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area and _y_of(c) >= ignored_top]

        if not valid_contours:
            small_contours = [c for c in contours if cv2.contourArea(c) >= min_area * 0.25 and _y_of(c) >= ignored_top]
            if small_contours:
                largest = max(small_contours, key=cv2.contourArea)
                area = cv2.contourArea(largest)
                self.logger.debug("Motion detection: using SMALL contour area=%.1f", area)
            else:
                return DetectionResult(bbox=None, confidence=0.0)
        else:
            largest = max(valid_contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            self.logger.debug("Motion detection: using VALID contour area=%.1f", area)

        if area < min_area * 0.20:
            if self._last_valid_bbox is None:
                self.logger.debug("Motion detection: area below minimum and no last bbox")
                return DetectionResult(bbox=None, confidence=0.0)
            area = min_area * 0.15
            self.logger.debug("Motion detection: relaxed area due to tracking -> %.1f", area)

        x, y, w, h = cv2.boundingRect(largest)
        
        if w < 20 or h < 20:
            self.logger.debug("_detect_motion: Rejecting tiny detection: %dx%d (min 20x20)", w, h)
            return DetectionResult(bbox=None, confidence=0.0)
        
        if y < ignored_top:
            self.logger.debug("Motion detection: skipped in top band y=%d < %d", y, ignored_top)
            return DetectionResult(bbox=None, confidence=0.0)

        abs_bbox = (
            self.roi["left"] + x,
            self.roi["top"] + y,
            w,
            h,
        )
        roi_area = self.roi["width"] * self.roi["height"]

        size_factor = min(1.0, float(area) / max(1.0, roi_area * 0.08))
        base_conf = min(0.95, size_factor * 0.9 + 0.08)
        if self._last_valid_bbox is not None:
            base_conf = min(0.95, base_conf + 0.05)
        conf = base_conf
        self.logger.debug("Motion detection: bbox=%s conf=%.2f size_factor=%.3f", abs_bbox, conf, size_factor)

        return DetectionResult(bbox=abs_bbox, confidence=conf)

    def _ema(self, prev: Optional[float], val: float, alpha: float) -> float:
        return val if prev is None else (alpha * val + (1 - alpha) * prev)

    def _ema_pt(self, prev: Optional[Tuple[float, float]], pt: Tuple[float, float], alpha: float) -> Tuple[float, float]:
        if prev is None:
            return pt
        return (alpha * pt[0] + (1 - alpha) * prev[0], alpha * pt[1] + (1 - alpha) * prev[1])
    
    def _start_learning_phase(self):
        """Initialize learning phase to understand Santa's characteristics"""
        self._learning_start_ts = time.time()
        self._learning_samples = []
        self._santa_profile = SantaProfile()
        self._locked_santa = False
        self._learning_stable_count = 0
        self._learning_first_bbox = None
        self._learning_lost_count = 0
        self._learning_continuous_start = None
        self._learning_last_sample_ts = None
        self.state = MacroState.LEARNING
        self.logger.info("=" * 60)
        self.logger.info("🎓 LEARNING PHASE STARTED")
        self.logger.info("Will track Santa for %.1fs to learn characteristics", self.learning_duration)
        self.logger.info("Looking for CONSISTENT detections (rejecting random noise)")
        self.logger.info("=" * 60)
    
    def _process_learning_sample(self, bbox: Tuple[int, int, int, int], frame_bgr: np.ndarray, confidence: float):
        """Collect and analyze detection during learning phase - ONLY from stable consistent source"""
        now = time.time()
        x, y, w, h = bbox
        size = max(w, h)
        center = (x + w // 2, y + h // 2)
        
        if self._learning_first_bbox is None:
            self._learning_first_bbox = bbox
            self._last_santa_center = center
            self._learning_continuous_start = now
            self._learning_last_sample_ts = now
            self.logger.info("📍 FIRST DETECTION: size=%dx%d at (%d,%d) conf=%.2f", 
                           w, h, x, y, confidence)
            return
        
        first_x, first_y, first_w, first_h = self._learning_first_bbox
        first_size = max(first_w, first_h)
        first_center = (first_x + first_w // 2, first_y + first_h // 2)
        
        size_ratio = size / first_size if first_size > 0 else 999
        if size_ratio < 0.5 or size_ratio > 2.0:
            self.logger.info("⚠️ LEARNING: Ignoring detection - size %dx%d too different from first %dx%d (ratio=%.2f)",
                           w, h, first_w, first_h, size_ratio)
            self._learning_lost_count += 1
            self._learning_continuous_start = None
            self.logger.info("⏱️ LEARNING: Resetting continuous timer due to size mismatch.")
            return
        
        if self._last_santa_center:
            dx = center[0] - self._last_santa_center[0]
            dy = center[1] - self._last_santa_center[1]
            jump_dist = math.sqrt(dx*dx + dy*dy)
            max_reasonable_jump = 200
            
            if jump_dist > max_reasonable_jump:
                self.logger.info("⚠️ LEARNING: Ignoring detection - jumped %dpx from last position (max %d)",
                               int(jump_dist), max_reasonable_jump)
                self._learning_lost_count += 1
                self._learning_continuous_start = None
                self.logger.info("⏱️ LEARNING: Resetting continuous timer due to jump.")
                return
        
        self._learning_samples.append((now, bbox, frame_bgr.copy()))
        self._learning_stable_count += 1
        self._learning_lost_count = 0
        self._last_santa_center = center
        if self._learning_continuous_start is None:
            self._learning_continuous_start = now
            self.logger.info("⏱️ LEARNING: Continuous timer started.")
        self._learning_last_sample_ts = now
        
        if len(self._learning_samples) == 1:
            self._santa_profile.size_min = size
            self._santa_profile.size_max = size
        else:
            self._santa_profile.size_min = min(self._santa_profile.size_min, size)
            self._santa_profile.size_max = max(self._santa_profile.size_max, size)
        
        self._santa_profile.movement_history.append((now, center))
        
        if len(self._santa_profile.movement_history) >= 2:
            total_dist = 0.0
            total_time = 0.0
            for i in range(1, len(self._santa_profile.movement_history)):
                t0, p0 = self._santa_profile.movement_history[i-1]
                t1, p1 = self._santa_profile.movement_history[i]
                dt = t1 - t0
                if dt > 0:
                    dx = p1[0] - p0[0]
                    dy = p1[1] - p0[1]
                    dist = math.sqrt(dx*dx + dy*dy)
                    total_dist += dist
                    total_time += dt
            
            if total_time > 0:
                self._santa_profile.avg_speed = total_dist / total_time
        

        roi_y2 = min(frame_bgr.shape[0], roi_y + h)
        
        if roi_x2 > roi_x and roi_y2 > roi_y:
            santa_region = frame_bgr[roi_y:roi_y2, roi_x:roi_x2]
            hsv_region = cv2.cvtColor(santa_region, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv_region], [0], None, [180], [0, 180])
            hist = cv2.normalize(hist, hist).flatten()
            self._santa_profile.color_signature = hist
        
        elapsed = now - self._learning_start_ts
        continuous = 0.0
        if self._learning_continuous_start:
            continuous = now - self._learning_continuous_start
        if len(self._learning_samples) % 25 == 0:
            self.logger.info("📊 LEARNING: %.1fs/%.1fs | Stable: %d samples | Continuous: %.1fs | Size: %d-%d px | Speed: %.1f px/s | Pos: (%d,%d)", 
                           elapsed, self.learning_duration, len(self._learning_samples), continuous,
                           self._santa_profile.size_min, self._santa_profile.size_max,
                           self._santa_profile.avg_speed, center[0], center[1])
    
    def _finalize_learning(self):
        """Complete learning phase and lock onto Santa"""
        min_required_samples = 50
        min_continuous = 3.0
        now = time.time()
        continuous = 0.0
        if self._learning_continuous_start:
            continuous = now - self._learning_continuous_start
        if len(self._learning_samples) < min_required_samples or continuous < min_continuous:
            self.logger.warning("⚠️ LEARNING FAILED: Only %d stable samples (need %d) or %.1fs continuous (need %.1fs)", 
                              len(self._learning_samples), min_required_samples, continuous, min_continuous)
            self.logger.warning("Resetting to search for more consistent target")
            self._learning_start_ts = None
            self._learning_first_bbox = None
            self._learning_continuous_start = None
            self._locked_santa = False
            self.state = MacroState.DETECTING
            return
        if self._santa_profile.avg_speed < 10 or self._santa_profile.avg_speed > 500:
            self.logger.warning("⚠️ LEARNING FAILED: Unrealistic speed %.1f px/s (expected 10-500)", 
                              self._santa_profile.avg_speed)
            self.logger.warning("Resetting to search for moving target")
            self._learning_start_ts = None
            self._learning_first_bbox = None
            self._learning_continuous_start = None
            self._locked_santa = False
            self.state = MacroState.DETECTING
            return
        
        self._locked_santa = True
        self.state = MacroState.DETECTING
        
        size_range = self._santa_profile.size_max - self._santa_profile.size_min
        tolerance = int(size_range * self.size_tolerance)
        self._santa_profile.size_min = max(self.min_santa_size, self._santa_profile.size_min - tolerance)
        self._santa_profile.size_max = min(self.max_santa_size, self._santa_profile.size_max + tolerance)
        
        self.logger.info("=" * 60)
        self.logger.info("🔒 LOCK-ON ENGAGED!")
        self.logger.info("Size range: %d-%d px (learned from %d stable samples)",
                        self._santa_profile.size_min, self._santa_profile.size_max,
                        len(self._learning_samples))
        self.logger.info("Movement speed: %.1f px/s (avg from tracking)", 
                        self._santa_profile.avg_speed)
        self.logger.info("Now filtering ALL detections against this profile")
        self.logger.info("=" * 60)
    
    def _validate_detection(self, bbox: Tuple[int, int, int, int], frame_bgr: np.ndarray) -> Tuple[bool, str]:
        """
        Validate if detection matches learned Santa profile.
        Returns: (is_valid, rejection_reason)
        """
        if not self._locked_santa:
            return (True, "")
        
        x, y, w, h = bbox
        size = max(w, h)
        center = (x + w // 2, y + h // 2)
        
        if size < self._santa_profile.size_min or size > self._santa_profile.size_max:
            return (False, f"SIZE={size}px not in [{self._santa_profile.size_min}-{self._santa_profile.size_max}]")
        
        if self._last_santa_center:
            dx = center[0] - self._last_santa_center[0]
            dy = center[1] - self._last_santa_center[1]
            jump_dist = math.sqrt(dx*dx + dy*dy)
            
            expected_max_jump = self._santa_profile.avg_speed * self.tick_interval * 3.0
            max_allowed_jump = max(self.position_jump_threshold, expected_max_jump)
            
            if jump_dist > max_allowed_jump:
                return (False, f"JUMP={int(jump_dist)}px > max={int(max_allowed_jump)}px from ({self._last_santa_center[0]},{self._last_santa_center[1]}) to ({center[0]},{center[1]})")
        
        if self._santa_profile.color_signature is not None:
            roi_x = max(0, x - self.roi["left"])
            roi_y = max(0, y - self.roi["top"])
            roi_x2 = min(frame_bgr.shape[1], roi_x + w)
            roi_y2 = min(frame_bgr.shape[0], roi_y + h)
            
            if roi_x2 > roi_x and roi_y2 > roi_y:
                det_region = frame_bgr[roi_y:roi_y2, roi_x:roi_x2]
                hsv_region = cv2.cvtColor(det_region, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv_region], [0], None, [180], [0, 180])
                hist = cv2.normalize(hist, hist).flatten()
                
                similarity = cv2.compareHist(self._santa_profile.color_signature, hist, cv2.HISTCMP_CORREL)
                
                if similarity < self.color_similarity_threshold:
                    return (False, f"color similarity {similarity:.2f} < {self.color_similarity_threshold}")
        
        return (True, "")
    
    def _update_santa_tracking(self, bbox: Tuple[int, int, int, int]):
        x, y, w, h = bbox
        center = (x + w // 2, y + h // 2)
        now = time.time()
        
        if self._debug_log_counter % 25 == 0:
            self.logger.info("TRACKING UPDATE: pos=(%d,%d) size=%dx%d", 
                           center[0], center[1], w, h)
        
        if self._last_santa_center and self._last_position_ts:
            dt = now - self._last_position_ts
            if dt > 0:
                dx = center[0] - self._last_santa_center[0]
                dy = center[1] - self._last_santa_center[1]
                vx = dx / dt
                vy = dy / dt
                self._santa_velocity = (
                    0.7 * self._santa_velocity[0] + 0.3 * vx,
                    0.7 * self._santa_velocity[1] + 0.3 * vy
                )
        
        self._last_santa_center = center
        self._last_position_ts = now
        
        pred_x = center[0] + self._santa_velocity[0] * self.tick_interval
        pred_y = center[1] + self._santa_velocity[1] * self.tick_interval
        self._predicted_position = (int(pred_x), int(pred_y))

        if self._locked_santa:
            self._postlock_consecutive_valid += 1
            if self._postlock_consecutive_valid == self._postlock_required_valid:
                self.logger.info("✅ Post-lock: %d consecutive valid detections. Shooting enabled.", self._postlock_required_valid)
        def _reset_postlock_valid(self):
            self._postlock_consecutive_valid = 0
    
    def _check_camera_control_needed(self, bbox: Optional[Tuple[int, int, int, int]]) -> bool:
        """Check if Santa is going off-screen to the left and camera needs to follow"""
        if not self.camera_control_enabled or not self._locked_santa:
            return False
        
        if bbox:
            x, y, w, h = bbox
            distance_from_left = x - self.monitor["left"]
            
            if distance_from_left < self.camera_left_edge_threshold:
                return True
        
        elif self._predicted_position:
            pred_x, pred_y = self._predicted_position
            if pred_x < self.monitor["left"] + self.camera_left_edge_threshold:
                return True
        
        return False
    
    def _perform_camera_drag(self, target_x: int):
        """Drag camera left to follow Santa using right-mouse drag"""
        screen_center_x = self.monitor["left"] + self.monitor["width"] // 2
        offset_x = target_x - screen_center_x
        
        if abs(offset_x) < self.camera_center_deadzone:
            return
        
        drag_distance = int(offset_x * self.camera_drag_speed)
        
        if not self._right_mouse_down:
            pyautogui.mouseDown(button='right')
            self._right_mouse_down = True
            self._camera_drag_start_ts = time.time()
            if self._debug_log_counter % 25 == 0:
                self.logger.info("🎥 CAMERA DRAG: Started | Target offset: %dpx", offset_x)
        
        cur = pyautogui.position()
        new_x = cur.x + drag_distance
        new_y = cur.y
        
        new_x = max(self.monitor["left"], min(self.monitor["left"] + self.monitor["width"] - 1, new_x))
        
        pyautogui.moveTo(new_x, new_y, duration=0)
        
        self._debug_log_counter += 1
    
    def _stop_camera_drag(self):
        """Stop camera dragging"""
        if self._right_mouse_down:
            pyautogui.mouseUp(button='right')
            self._right_mouse_down = False
            
            if self._camera_drag_start_ts:
                duration = time.time() - self._camera_drag_start_ts
                self.logger.info("🎥 CAMERA DRAG: Stopped | Duration: %.1fs", duration)
                self._camera_drag_start_ts = None


    def _aim_point(self, bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        x, y, w, h = bbox
        cx = x + w // 4  # Aim between left edge and center (1/4 width from left)
        cy = y + h // 2
        if self.clamp_to_screen:
            screen_right = self.monitor["left"] + self.monitor["width"]
            screen_bottom = self.monitor["top"] + self.monitor["height"]
            cx = max(self.monitor["left"], min(screen_right - 1, cx))
            cy = max(self.monitor["top"], min(screen_bottom - 1, cy))
        return (cx, cy)

    def _update_fps(self):
        now = time.time()
        dt = now - self._last_frame_ts
        self._last_frame_ts = now
        if dt > 0:
            self._fps = 1.0 / dt

    def _push_movement(self, pt: Tuple[int, int]):
        now = time.time()
        self._movement_history.append((now, pt))
        cutoff = now - 2.0
        while self._movement_history and self._movement_history[0][0] < cutoff:
            self._movement_history.pop(0)

    def _is_moving_naturally(self) -> bool:
        if len(self._movement_history) < 2:
            return False
        total_dist = 0.0
        total_time = 0.0
        for i in range(1, len(self._movement_history)):
            t0, p0 = self._movement_history[i - 1]
            t1, p1 = self._movement_history[i]
            dt = t1 - t0
            if dt <= 0:
                continue
            dx = p1[0] - p0[0]
            dy = p1[1] - p0[1]
            total_dist += math.hypot(dx, dy)
            total_time += dt
        if total_time <= 0:
            return False
        speed = total_dist / total_time
        is_moving = speed >= self.click_min_move_speed
        if not is_moving:
            self.logger.debug("Movement speed %.2f px/s < threshold %.2f", speed, self.click_min_move_speed)
        return is_moving

    def _move_mouse_towards(self, target: Tuple[int, int]):
        cur = pyautogui.position()
        
        now = time.time()
        if self._click_cycle_phase != "shoot" and self._last_position and self._last_position_ts:
            dt = now - self._last_position_ts
            if dt > 0 and dt < 0.5:
                vx = (target[0] - self._last_position[0]) / dt
                vy = (target[1] - self._last_position[1]) / dt
                self._velocity = (
                    0.6 * self._velocity[0] + 0.4 * vx,
                    0.6 * self._velocity[1] + 0.4 * vy
                )
                pred_x = target[0] + self._velocity[0] * self.tick_interval * self._prediction_weight
                pred_y = target[1] + self._velocity[1] * self.tick_interval * self._prediction_weight
                target = (int(pred_x), int(pred_y))
        
        self._last_position = target
        self._last_position_ts = now
        
        dx = target[0] - cur.x
        dy = target[1] - cur.y
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance > 100:
            smooth = self.mouse_smooth * 0.6
        elif distance > 50:
            smooth = self.mouse_smooth
        else:
            smooth = self.mouse_smooth * 1.5

        if self._click_cycle_phase == "shoot":
            if distance > 120:
                smooth *= 0.6
            elif distance > 60:
                smooth *= 0.8
        
        step_x = int(dx * smooth)
        step_y = int(dy * smooth)

        if distance > 80:
            if step_x == 0 and dx != 0:
                step_x = 2 if dx > 0 else -2
            if step_y == 0 and dy != 0:
                step_y = 2 if dy > 0 else -2
        
        if step_x == 0 and dx != 0:
            step_x = 1 if dx > 0 else -1
        if step_y == 0 and dy != 0:
            step_y = 1 if dy > 0 else -1
        
        new_x = cur.x + step_x
        new_y = cur.y + step_y
        
        try:
            import ctypes
            from ctypes import wintypes
            
            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ('dx', wintypes.LONG),
                    ('dy', wintypes.LONG),
                    ('mouseData', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD),
                    ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))
                ]
            
            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [('mi', MOUSEINPUT)]
                _anonymous_ = ('u',)
                _fields_ = [
                    ('type', wintypes.DWORD),
                    ('u', _INPUT)
                ]
            
            INPUT_MOUSE = 0
            MOUSEEVENTF_MOVE = 0x0001
            MOUSEEVENTF_ABSOLUTE = 0x8000
            
            screen_width = ctypes.windll.user32.GetSystemMetrics(0)
            screen_height = ctypes.windll.user32.GetSystemMetrics(1)
            
            abs_x = int((new_x * 65536) / screen_width)
            abs_y = int((new_y * 65536) / screen_height)
            
            extra = ctypes.c_ulong(0)
            ii = INPUT()
            ii.type = INPUT_MOUSE
            ii.mi = MOUSEINPUT(
                dx=abs_x,
                dy=abs_y,
                mouseData=0,
                dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                time=0,
                dwExtraInfo=ctypes.pointer(extra)
            )
            
            ctypes.windll.user32.SendInput(1, ctypes.byref(ii), ctypes.sizeof(ii))
            self.logger.debug(f"Mouse moved via SendInput to ({new_x}, {new_y})")
        except Exception as e:
            self.logger.warning(f"SendInput failed: {e}, falling back to pyautogui")
            pyautogui.moveTo(new_x, new_y, duration=0)

    def _send_mouse_click(self, down: bool = True):
        """Send mouse click using Python pyautogui"""
        try:
            if down:
                pyautogui.mouseDown()
                self.logger.info("[PYAUTOGUI] Mouse DOWN")
            else:
                pyautogui.mouseUp()
                self.logger.info("[PYAUTOGUI] Mouse UP")
        except Exception as e:
            self.logger.error(f"pyautogui click failed: {e}")
    
    def _send_x_key(self, down: bool = True):
        """Send X key press/release using pydirectinput"""
        try:
            if down:
                pydirectinput.keyDown('x')
                self.logger.info("[PYDIRECTINPUT] X key DOWN")
            else:
                pydirectinput.keyUp('x')
                self.logger.info("[PYDIRECTINPUT] X key UP")
        except Exception as e:
            self.logger.error(f"X key input failed: {e}")
    
    def _send_attack_input(self, down: bool = True):
        """Send attack input using custom attack system"""
        if not self.custom_attack_manager:
            self.logger.error("[ATTACK] No custom attack manager available!")
            return
        
        if not self.custom_attack_manager.has_custom_sequence():
            self.logger.warning("[ATTACK] No custom sequence recorded! Please record one in settings.")
            return
        
        if down and not self.custom_attack_manager.player.playing:
            # Start custom attack sequence
            self.custom_attack_manager.play_custom_attack(loop=True)
            self.logger.info("[CUSTOM ATTACK] Started custom attack sequence")
        elif not down and self.custom_attack_manager.player.playing:
            # Stop custom attack sequence
            self.custom_attack_manager.stop_attack()
            self.logger.info("[CUSTOM ATTACK] Stopped custom attack sequence")
    
    def _get_load_duration(self) -> float:
        """Get load phase duration for custom attacks"""
        return float(self.cfg.get("clicks", {}).get("load_ms", 1000)) / 1000.0
    
    def _get_fire_duration(self) -> float:
        """Get fire phase duration for custom attacks"""
        return float(self.cfg.get("clicks", {}).get("shoot_ms", 5000)) / 1000.0
    
    def _get_cooldown_duration(self) -> float:
        """Get cooldown phase duration for custom attacks"""
        return float(self.cfg.get("clicks", {}).get("cooldown_ms", 6000)) / 1000.0
    
    def toggle_attack_mode(self):
        """Toggle custom attack mode on/off"""
        if self.custom_attack_manager:
            current_enabled = self.custom_attack_manager.is_custom_enabled()
            # This would need to be implemented to toggle the setting
            self.logger.info(f"[ATTACK MODE] Custom attacks: {'Enabled' if current_enabled else 'Disabled'}")
        else:
            self.logger.info("[ATTACK MODE] Custom attack manager not available")
    
    def _on_attack_mode_button_click(self, mode: str):
        """Handle attack mode button clicks (legacy)"""
        print("_on_attack_mode_button_click called!")  # Debug output
        self.open_settings()
    
    def _on_settings_button_click(self):
        """Handle settings button click - opens settings GUI"""
        print("_on_settings_button_click called!")  # Debug output
        self.open_settings()
    
    def open_settings(self):
        """Open the settings GUI"""
        print("open_settings called!")  # Debug output
        try:
            # Import here to avoid circular imports
            from PySide6.QtCore import QTimer
            
            # Use QTimer to run in main thread
            def create_settings():
                from settings_gui import SettingsGUI
                print(f"Opening settings with config path: {self.config_path}")  # Debug output
                
                # Store reference to prevent garbage collection
                if not hasattr(self, '_settings_window'):
                    self._settings_window = None
                
                # Close existing window if open
                if self._settings_window is not None:
                    self._settings_window.close()
                
                # Create and store new settings window
                self._settings_window = SettingsGUI(self.config_path, macro_instance=self)
                self._settings_window.show()
                print("Settings window created and shown")
            
            # Schedule to run in main thread
            QTimer.singleShot(0, create_settings)
            
        except Exception as e:
            self.logger.error(f"Failed to open settings: {e}")
            import traceback
            traceback.print_exc()

    def _click_down(self):
        if not self._mouse_down:
            self._send_mouse_click(down=True)
            self._mouse_down = True
            self._click_started_ts = time.time()
            self.logger.info("mouseDown")

    def _create_tracker(self):
        import cv2
        tracker = None
        try:
            if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
                tracker = cv2.legacy.TrackerCSRT_create()
            elif hasattr(cv2, "TrackerCSRT_create"):
                tracker = cv2.TrackerCSRT_create()
        except Exception:
            tracker = None
        if tracker is None:
            try:
                if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerKCF_create"):
                    tracker = cv2.legacy.TrackerKCF_create()
                elif hasattr(cv2, "TrackerKCF_create"):
                    tracker = cv2.TrackerKCF_create()
            except Exception:
                tracker = None
        if tracker is None:
            try:
                if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerMOSSE_create"):
                    tracker = cv2.legacy.TrackerMOSSE_create()
            except Exception:
                tracker = None
        return tracker

    def _init_shoot_tracker(self, frame_bgr: np.ndarray, bbox_global: Tuple[int, int, int, int]):
        x, y, w, h = bbox_global
        rx = max(0, x - self.roi["left"]) 
        ry = max(0, y - self.roi["top"]) 
        rw = max(1, min(w, self.roi["width"] - rx))
        rh = max(1, min(h, self.roi["height"] - ry))
        local_bbox = (int(rx), int(ry), int(rw), int(rh))
        self._shoot_tracker = self._create_tracker()
        if self._shoot_tracker is not None:
            try:
                ok = self._shoot_tracker.init(frame_bgr, local_bbox)
                self._shoot_track_failures = 0
                self.logger.debug("Shoot tracker initialized at %s (local)", local_bbox)
                return ok
            except Exception as e:
                self.logger.debug("Shoot tracker init failed: %s", e)
        else:
            self.logger.debug("Shoot tracker unavailable")
        return False

    def _update_shoot_tracker(self, frame_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        if self._shoot_tracker is None:
            return None
        try:
            ok, box = self._shoot_tracker.update(frame_bgr)
        except Exception as e:
            self.logger.debug("Shoot tracker update error: %s", e)
            ok, box = False, None
        if not ok or box is None:
            self._shoot_track_failures += 1
            return None
        lx, ly, lw, lh = [int(v) for v in box]
        gx = lx + self.roi["left"]
        gy = ly + self.roi["top"]
        self._shoot_track_failures = 0
        return (gx, gy, lw, lh)

    def _init_shoot_template(self, frame_bgr: np.ndarray, bbox_global: Tuple[int, int, int, int]) -> bool:
        x, y, w, h = bbox_global
        rx = max(0, x - self.roi["left"]) 
        ry = max(0, y - self.roi["top"]) 
        rw = max(1, min(w, self.roi["width"] - rx))
        rh = max(1, min(h, self.roi["height"] - ry))
        crop = frame_bgr[int(ry):int(ry+rh), int(rx):int(rx+rw)]
        if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
            self._shoot_tmpl = None
            self._shoot_tmpl_size = None
            return False
        self._shoot_tmpl = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        self._shoot_tmpl_size = (int(rw), int(rh))
        self._shoot_track_box = bbox_global
        self.logger.debug("Shoot template initialized size=%s", self._shoot_tmpl_size)
        return True

    def _update_shoot_template(self, frame_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        if self._shoot_tmpl is None or self._shoot_tmpl_size is None:
            return None
        tw, th = self._shoot_tmpl_size
        ref = self._shoot_track_box or self._shoot_ref_bbox
        if ref is None:
            return None
        cx, cy = self._aim_point(ref)
        rx = max(0, cx - self.roi["left"] - self.shoot_roi_radius_px)
        ry = max(0, cy - self.roi["top"] - self.shoot_roi_radius_px)
        rw = min(self.roi["width"], (cx - self.roi["left"] + self.shoot_roi_radius_px)) - rx
        rh = min(self.roi["height"], (cy - self.roi["top"] + self.shoot_roi_radius_px)) - ry
        if rw <= tw or rh <= th:
            rx, ry = 0, 0
            rw, rh = self.roi["width"], self.roi["height"]
        search = frame_bgr[int(ry):int(ry+rh), int(rx):int(rx+rw)]
        if search.size == 0:
            return None
        search_gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
        try:
            res = cv2.matchTemplate(search_gray, self._shoot_tmpl, cv2.TM_CCOEFF_NORMED)
        except Exception as e:
            self.logger.debug("matchTemplate error: %s", e)
            return None
        minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(res)
        if maxVal < self.shoot_tmpl_min_score:
            self.logger.debug("Shoot tmpl score low: %.2f < %.2f", maxVal, self.shoot_tmpl_min_score)
            return None
        top_left = (int(maxLoc[0] + rx), int(maxLoc[1] + ry))
        new_box = (top_left[0] + self.roi["left"], top_left[1] + self.roi["top"], tw, th)
        self._shoot_track_box = new_box
        self.logger.debug("Shoot tmpl update: score=%.2f box=%s", maxVal, new_box)
        return new_box

    def _check_santa_left_screen(self, bbox: Tuple[int, int, int, int]) -> bool:
        """Check if Santa left the screen from top, left, or right edges."""
        x, y, w, h = bbox
        screen_left = self.roi["left"]
        screen_top = self.roi["top"]
        screen_right = self.roi["left"] + self.roi["width"]
        screen_bottom = self.roi["top"] + self.roi["height"]
        
        cx = x + w // 2
        cy = y + h // 2
        
        if cx < screen_left + 50:
            self.logger.info("Santa left screen from LEFT edge (cx=%d < %d)", cx, screen_left + 50)
            return True
        
        if cx > screen_right - 50:
            self.logger.info("Santa left screen from RIGHT edge (cx=%d > %d)", cx, screen_right - 50)
            return True
        
        if cy < screen_top + 50:
            self.logger.info("Santa left screen from TOP edge (cy=%d < %d)", cy, screen_top + 50)
            return True
        
        return False
    
    def _red_ratio(self, frame_bgr: np.ndarray, bbox_global: Tuple[int, int, int, int]) -> float:
        x, y, w, h = bbox_global
        rx = max(0, x - self.roi["left"]) 
        ry = max(0, y - self.roi["top"]) 
        rw = max(1, min(w, self.roi["width"] - rx))
        rh = max(1, min(h, self.roi["height"] - ry))
        crop = frame_bgr[int(ry):int(ry+rh), int(rx):int(rx+rw)]
        if crop.size == 0:
            return 0.0
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 100, 70], dtype=np.uint8)
        upper1 = np.array([10, 255, 255], dtype=np.uint8)
        lower2 = np.array([160, 100, 70], dtype=np.uint8)
        upper2 = np.array([179, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
        red = np.count_nonzero(mask)
        total = crop.shape[0] * crop.shape[1]
        return float(red) / float(max(1, total))

    def _initiate_lock_on(self, bbox: Tuple[int, int, int, int]) -> bool:
        """Start lock-on tracking of Santa. Returns True if lock-on initiated."""
        x, y, w, h = bbox
        
        if w < 30 or h < 30:
            self.logger.debug("LOCK-ON REJECTED: Too small (w=%d, h=%d < 30px)", w, h)
            return False
        
        roi_area = self.roi["width"] * self.roi["height"]
        if (w * h) > roi_area * 0.25:
            self.logger.debug("LOCK-ON REJECTED: Too large (area=%d > 25%% ROI)", w * h)
            return False
        
        aspect = w / max(h, 1)
        if aspect < 0.3 or aspect > 3.5:
            self.logger.debug("LOCK-ON REJECTED: Bad aspect ratio %.2f", aspect)
            return False
        
        self._locked_on_santa = True
        self._lock_start_ts = time.time()
        self._last_movement_ts = time.time()
        self._santa_bbox_history = [bbox]
        self._stuck_counter = 0
        self.logger.info("LOCK-ON INITIATED: Santa detected at bbox=%s (w=%d, h=%d)", bbox, w, h)
        return True
    
    def _update_lock_on(self, bbox: Tuple[int, int, int, int]):
        """Update lock-on tracking with new Santa position."""
        now = time.time()
        
        if self._santa_bbox_history:
            last_bbox = self._santa_bbox_history[-1]
            last_cx, last_cy = last_bbox[0] + last_bbox[2] // 2, last_bbox[1] + last_bbox[3] // 2
            curr_cx, curr_cy = bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2
            distance = math.hypot(curr_cx - last_cx, curr_cy - last_cy)
            
            if distance < 10:
                self._stuck_counter += 1
                
                if self._last_movement_ts:
                    time_still = now - self._last_movement_ts
                    if time_still > self._movement_timeout_seconds:
                        self.logger.warning("NO MOVEMENT for %.1fs - Santa is ALWAYS moving! Releasing lock.", time_still)
                        self._release_lock_on(f"Static object detected (no movement for {time_still:.1f}s)")
                        return
                
                if self._stuck_counter >= self._stuck_detection_threshold:
                    self.logger.warning("STUCK DETECTION: Bbox hasn't moved in %d frames (dist=%.1f)", 
                                      self._stuck_counter, distance)
                    self._release_lock_on(f"Stuck on static object ({self._stuck_counter} frames)")
                    return
            else:
                self._stuck_counter = 0
                self._last_movement_ts = now
                self.logger.debug("Movement detected: %.1f pixels", distance)
        else:
            self._last_movement_ts = now
        
        self._santa_bbox_history.append(bbox)
        if len(self._santa_bbox_history) > self._max_bbox_history:
            self._santa_bbox_history.pop(0)
    
    def _release_lock_on(self, reason: str):
        """Release lock-on and reset tracking."""
        if self._locked_on_santa:
            self.logger.info("LOCK-ON RELEASED: %s", reason)
        self._locked_on_santa = False
        self._lock_start_ts = None
        self._last_movement_ts = None
        self._santa_bbox_history = []
        self._stuck_counter = 0
        self._shoot_tracker = None
        self._shoot_tmpl = None
        self._shoot_ref_bbox = None
        self._last_valid_bbox = None
    
    def _is_valid_track_box(self, frame_bgr: np.ndarray, bbox_global: Tuple[int, int, int, int]) -> bool:
        w, h = bbox_global[2], bbox_global[3]
        if w < 28 or h < 28:
            return False
        roi_area = self.roi["width"] * self.roi["height"]
        if (w * h) > roi_area * self.shoot_det_max_area_frac:
            return False
        if self.prefer_color_during_shoot:
            rr = self._red_ratio(frame_bgr, bbox_global)
            if rr < self.shoot_color_red_weight * 0.6:
                return False
        return True

    def _click_up(self):
        if self._mouse_down:
            self._send_mouse_click(down=False)
            self._mouse_down = False
            self._click_started_ts = None
            self.logger.info("mouseUp")

    def _should_release_click(self) -> bool:
        if not self._mouse_down:
            return False
        if self._click_started_ts and (time.time() - self._click_started_ts) * 1000.0 > self.max_click_duration_ms:
            return True
        return False

    def _draw_overlay(self, frame_bgr: np.ndarray, det: DetectionResult, aim: Optional[Tuple[int, int]], attack_mode: str = "custom"):
        now = time.time()
        if now - self._last_overlay_update_ts < self.tick_interval * 0.9:
            return
        self._last_overlay_update_ts = now

        try:
            if self.overlay_engine == "qt":
                if not self._qt_overlay:
                    self._qt_overlay = OverlayQt(
                        self.overlay_title,
                        self.roi["left"], self.roi["top"], self.roi["width"], self.roi["height"],
                        click_through=self.overlay_click_through,
                        topmost=self.overlay_topmost,
                        status_bar_mode=self.overlay_status_bar_mode,
                    )
                    # Set up callback for settings button clicks
                    self._qt_overlay.set_settings_callback(self._on_settings_button_click)
            else:
                self._ensure_overlay_window(frame_bgr.shape[1], frame_bgr.shape[0])

            if self.overlay_draw_frame:
                img = frame_bgr.copy()
            else:
                img = np.zeros((self.roi["height"], self.roi["width"], 3), dtype=np.uint8)
            
            status_text = None
            if self.overlay_status_bar_mode:
                if self._paused:
                    state_display = "PAUSED"
                elif self._running:
                    state_display = f"ACTIVE - {self.state.upper()}"
                else:
                    state_display = "INACTIVE"
                
                status_text = f"{state_display}\nFPS: {self._fps:.1f} | Conf: {det.confidence:.2f}"
            
            if not self.overlay_status_bar_mode:
                if det.bbox is not None:
                    x, y, w, h = det.bbox
                    cv2.rectangle(img, (x - self.roi["left"], y - self.roi["top"]), (x - self.roi["left"] + w, y - self.roi["top"] + h), (0, 255, 0), 3)
                if aim is not None:
                    ax = aim[0] - self.roi["left"]
                    ay = aim[1] - self.roi["top"]
                    cv2.circle(img, (ax, ay), 6, (0, 0, 255), -1)
                    cv2.circle(img, (ax, ay), 8, (255, 255, 255), 2)
                info = f"state={self.state} conf={det.confidence:.2f} fps={self._fps:.1f}"
                cv2.putText(img, info, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(img, info, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
            
            if self.overlay_engine == "qt":
                if self.overlay_status_bar_mode:
                    self._qt_overlay.update(
                        img,
                        status_text=status_text,
                        det_bbox=det.bbox,
                        aim_point=aim,
                        roi_offset=(self.roi["left"], self.roi["top"]),
                        attack_mode=attack_mode
                    )
                else:
                    self._qt_overlay.update(img)
            else:
                cv2.imshow(self.overlay_title, img)
                cv2.waitKey(1)
        except Exception as e:
            self.logger.error("Overlay draw error: %s", e)
        except Exception as e:
            self.logger.error("Overlay draw error: %s", e)

    def _ensure_overlay_window(self, width: int, height: int):
        if self._overlay_initialized:
            return
        try:
            cv2.namedWindow(self.overlay_title, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.overlay_title, width, height)
            cv2.moveWindow(self.overlay_title, self.roi["left"], self.roi["top"])
            if platform.system() == "Windows":
                try:
                    user32 = ctypes.windll.user32
                    gdi32 = ctypes.windll.gdi32
                    kernel32 = ctypes.windll.kernel32
                    FindWindowW = user32.FindWindowW
                    SetWindowLongW = user32.SetWindowLongW
                    GetWindowLongW = user32.GetWindowLongW
                    SetLayeredWindowAttributes = user32.SetLayeredWindowAttributes
                    SetWindowPos = user32.SetWindowPos

                    hwnd = FindWindowW(None, self.overlay_title)
                    if hwnd:
                        GWL_EXSTYLE = -20
                        GWL_STYLE = -16
                        WS_EX_LAYERED = 0x00080000
                        WS_EX_TRANSPARENT = 0x00000020
                        WS_EX_TOPMOST = 0x00000008
                        LWA_ALPHA = 0x00000002
                        SWP_NOMOVE = 0x0002
                        SWP_NOSIZE = 0x0001
                        SWP_NOACTIVATE = 0x0010
                        HWND_TOPMOST = -1

                        ex = GetWindowLongW(hwnd, GWL_EXSTYLE)
                        SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST)
                        SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
                        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

                        WS_CAPTION = 0x00C00000
                        WS_THICKFRAME = 0x00040000
                        WS_MINIMIZE = 0x20000000
                        WS_MAXIMIZE = 0x01000000
                        WS_SYSMENU = 0x00080000
                        style = GetWindowLongW(hwnd, GWL_STYLE)
                        style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZE | WS_MAXIMIZE | WS_SYSMENU)
                        SetWindowLongW(hwnd, GWL_STYLE, style)
                        SetWindowPos(hwnd, HWND_TOPMOST, self.roi["left"], self.roi["top"], width, height, SWP_NOACTIVATE)
                except Exception as e:
                    self.logger.warning("Overlay window style tweak failed: %s", e)
        finally:
            self._overlay_initialized = True

    def _destroy_overlay_window(self):
        if self.overlay_engine == "qt":
            if self._qt_overlay:
                try:
                    self._qt_overlay.close()
                except Exception:
                    pass
                self._qt_overlay = None
        else:
            if self._overlay_initialized:
                try:
                    cv2.destroyWindow(self.overlay_title)
                except Exception:
                    pass
                self._overlay_initialized = False

    def _save_dump_if_needed(self, frame_bgr: np.ndarray, det: DetectionResult):
        if not self.save_low_conf_frames:
            return
        if det.confidence < self.low_conf_dump_threshold:
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.dump_dir, f"lowconf_{ts}_{det.confidence:.2f}.png")
            cv2.imwrite(path, frame_bgr)

    def _on_key(self, key):
        try:
            name = key.name if hasattr(key, 'name') else None
        except Exception:
            name = None
        if name is None:
            try:
                name = key.char
            except Exception:
                name = str(key)
        hk = self.cfg["hotkeys"]
        if isinstance(name, str):
            # Debounce hotkey presses to prevent phantom triggers
            current_time = time.time() * 1000  # Convert to milliseconds
            key_lower = name.lower()
            last_time = self._last_hotkey_time.get(key_lower, 0)
            
            if current_time - last_time < self._hotkey_debounce_ms:
                self.logger.debug(f"[HOTKEY] Ignoring duplicate key press: {key_lower} (debounce)")
                return
            
            self._last_hotkey_time[key_lower] = current_time
            
            if name.lower() == hk.get("toggle", "f1").lower():
                self.logger.info(f"[HOTKEY] Toggle key '{name}' pressed at frame {self._debug_log_counter}")
                if self._running:
                    self._running = False
                    self._paused = False
                    self.state = MacroState.IDLE
                    
                    # Stop custom attack sequence if running
                    if self.custom_attack_manager and self.custom_attack_manager.player.playing:
                        self.custom_attack_manager.stop_attack()
                        self.logger.info("[STOP] Stopped custom attack sequence")
                    
                    if self._mouse_down:
                        self._click_up()
                    if self._x_key_down:
                        pydirectinput.keyUp('x')
                        self._x_key_down = False
                    try:
                        with self.arrow_lock:
                            if self.current_arrow_key:
                                pydirectinput.keyUp(self.current_arrow_key)
                                self.logger.info(f"[STOP] Released {self.current_arrow_key}")
                            pydirectinput.keyUp('left')
                            pydirectinput.keyUp('right')
                            with self.keys_lock:
                                self.camera_keys_pressed.clear()
                            self.is_holding_arrow = False
                            self.current_arrow_key = None
                    except Exception as e:
                        self.logger.warning(f"Error releasing keys on stop: {e}")
                    self.search_state = "idle"
                    self.attack_phase = "idle"
                    self.attack_committed = False
                    self._consecutive_detections = 0
                    self._last_detection_frame = -1000
                    self._last_santa_center = None
                    self._position_history.clear()
                    self._detection_movement_history.clear()
                    self.logger.info("Hotkey TOGGLE -> STOPPED (running=False)")
                    # Webhook: Macro stopped
                    if self.webhook_manager:
                        self.webhook_manager.macro_stopped()
                else:
                    if not self._zoom_performed:
                        self._perform_initial_zoom()
                        self._zoom_performed = True
                    self._running = True
                    self._paused = False
                    self.state = MacroState.DETECTING
                    self.logger.info("Hotkey TOGGLE -> STARTED (running=True)")
                    # Webhook: Macro started
                    if self.webhook_manager:
                        self.webhook_manager.macro_started()
            elif name.lower() == hk.get("start", "").lower() and hk.get("start"):
                if not self._running:
                    if not self._zoom_performed:
                        self._perform_initial_zoom()
                        self._zoom_performed = True
                    self._running = True
                    self._paused = False
                    self.state = MacroState.DETECTING
                    self.logger.info("Hotkey START -> running=True")
            elif name.lower() == hk.get("stop", "").lower() and hk.get("stop"):
                if self._running:
                    self._running = False
                    self._paused = False
                    self.state = MacroState.IDLE
                    
                    # Stop custom attack sequence if running
                    if self.custom_attack_manager and self.custom_attack_manager.player.playing:
                        self.custom_attack_manager.stop_attack()
                        self.logger.info("[STOP] Stopped custom attack sequence")
                    
                    if self._mouse_down:
                        self._click_up()
                    if self._x_key_down:
                        pydirectinput.keyUp('x')
                        self._x_key_down = False
                    try:
                        with self.arrow_lock:
                            if self.current_arrow_key:
                                pydirectinput.keyUp(self.current_arrow_key)
                                self.logger.info(f"[STOP] Released {self.current_arrow_key}")
                            pydirectinput.keyUp('left')
                            pydirectinput.keyUp('right')
                            with self.keys_lock:
                                self.camera_keys_pressed.clear()
                            self.is_holding_arrow = False
                            self.current_arrow_key = None
                    except Exception as e:
                        self.logger.warning(f"Error releasing keys on stop: {e}")
                    self.logger.info("Hotkey STOP -> running=False")
            elif name.lower() == hk["shutdown"].lower():
                self.state = MacroState.SHUTDOWN
                self.logger.info("Hotkey shutdown")

    def start_hotkeys(self):
        self._keyboard_listener = keyboard.Listener(on_press=self._on_key)
        self._keyboard_listener.start()

    def stop_hotkeys(self):
        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

    def run(self):
        self.start_hotkeys()
        toggle_key = self.cfg["hotkeys"].get("toggle", self.cfg["hotkeys"].get("start", "F1"))
        self.logger.info("Macro loop started. Press %s to START/STOP (toggle).", toggle_key.upper())
        try:
            while self.state != MacroState.SHUTDOWN:
                start_ts = time.time()
                
                # Periodic cleanup to prevent stuck keys every 100 frames
                if self._debug_log_counter - self._last_cleanup_frame >= self._cleanup_interval:
                    self._force_release_all_arrows()
                    self._last_cleanup_frame = self._debug_log_counter
                    self.logger.info(f"[CLEANUP] Frame {self._debug_log_counter}: Native arrow release")
                
                frame_bgr = self._grab_frame(mask_cursor=not (self._click_cycle_phase == "shoot"))
                frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

                if not self._running:
                    self.state = MacroState.IDLE
                    det = DetectionResult(bbox=None, confidence=0.0)
                    if self.overlay_enabled:
                        self._update_fps()
                        self._draw_overlay(frame_bgr, det, None, attack_mode="custom")
                    time.sleep(self.idle_backoff_ms / 1000.0)
                    continue

                if self._paused:
                    self.state = MacroState.PAUSED
                    det = DetectionResult(bbox=None, confidence=0.0)
                    if self._mouse_down:
                        self._click_up()
                    if self.overlay_enabled:
                        self._update_fps()
                        self._draw_overlay(frame_bgr, det, None, attack_mode="custom")
                    time.sleep(self.tick_interval)
                    continue
                

                if self.minimal_santa_mode_enabled:
                    if self._debug_log_counter == 0:
                        self.logger.info("[MINIMAL MODE] Active - running YOLO detection loop")
                    
                    if self._debug_log_counter % 10 == 0 and self.search_state != "idle":
                        self.logger.info(f"[FRAME {self._debug_log_counter}] search_state={self.search_state}, attack_phase={self.attack_phase}")
                    
                    if self.search_state == "searching_left":
                        # SIMPLIFIED: Just hold LEFT continuously like GPO Santa
                        if not self.is_holding_arrow or self.current_arrow_key != 'left':
                            with self.arrow_lock:
                                # Release any other arrow first
                                if self.current_arrow_key and self.current_arrow_key != 'left':
                                    pydirectinput.keyUp(self.current_arrow_key)
                                pydirectinput.keyDown('left')
                                with self.keys_lock:
                                    self.camera_keys_pressed.clear()
                                    self.camera_keys_pressed.add('left')
                                self.is_holding_arrow = True
                                self.current_arrow_key = 'left'
                                self.logger.info("[SEARCH] Holding LEFT arrow")
                        
                        # Log status every 30 frames
                        if self._debug_log_counter % 30 == 0:
                            self.logger.info(f"[SEARCH] LEFT held (frame {self._debug_log_counter})")
                        time.sleep(0.01)
                    
                    best_santa = None
                    
                    if self.yolo_model:
                        try:
                            results = self.yolo_model(frame_bgr, verbose=False)
                            
                            if not self._running:
                                self.logger.info("[STOP] Detected stop signal after YOLO detection")
                                continue
                            
                            for result in results:
                                boxes = result.boxes
                                if self._debug_log_counter % 25 == 0 and len(boxes) > 0:
                                    self.logger.info(f"[YOLO RAW] Found {len(boxes)} detections")
                                
                                for box in boxes:
                                    class_id = int(box.cls[0])
                                    class_name = result.names[class_id]
                                    confidence = float(box.conf[0])
                                    
                                    if self._debug_log_counter % 25 == 0:
                                        self.logger.info(f"[YOLO RAW] class={class_name}, conf={confidence:.4f}")
                                    
                                    if class_name.lower() == self.santa_class_name.lower() and confidence >= self.threshold:
                                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                                        candidate_cx = int((x1 + x2) / 2)
                                        candidate_cy = int((y1 + y2) / 2)
                                        candidate_w = int(x2 - x1)
                                        candidate_h = int(y2 - y1)
                                        
                                        min_santa_width = 40
                                        min_santa_height = 25
                                        max_santa_height = 200  # Prevent detecting tall trees
                                        
                                        # Reject if too small
                                        if candidate_w < min_santa_width or candidate_h < min_santa_height:
                                            if self._debug_log_counter % 10 == 0:
                                                self.logger.info(f"[YOLO REJECT] Too small: {candidate_w}x{candidate_h} (min {min_santa_width}x{min_santa_height}) conf={confidence:.2f}")
                                            continue
                                        
                                        # Reject if too tall (likely a tree or decoration)
                                        if candidate_h > max_santa_height:
                                            if self._debug_log_counter % 10 == 0:
                                                self.logger.info(f"[YOLO REJECT] Too tall: {candidate_h}px (max {max_santa_height}px) - likely tree/decoration, conf={confidence:.2f}")
                                            continue
                                        
                                        # Aspect ratio check: Santa should be roughly square or wider than tall
                                        # Trees are much taller than wide (aspect ratio > 3.0)
                                        # Only apply strict check during idle phase, be lenient during tracking/combat
                                        aspect_ratio = candidate_h / candidate_w
                                        max_aspect_ratio = 3.0 if self.attack_phase != "idle" else 2.5  # More lenient during combat
                                        if aspect_ratio > max_aspect_ratio:
                                            if self._debug_log_counter % 10 == 0:
                                                self.logger.info(f"[YOLO REJECT] Too tall/narrow (aspect {aspect_ratio:.2f} > {max_aspect_ratio}) - likely tree, conf={confidence:.2f}")
                                            continue
                                        
                                        is_valid_candidate = True
                                        frames_since_search = self._debug_log_counter - getattr(self, '_search_exit_frame', -999)
                                        skip_validation = frames_since_search < 3
                                        
                                        # Skip position jump validation if camera is actively moving - camera movement causes legitimate large position changes
                                        camera_is_moving = self.current_arrow_key is not None and self.is_holding_arrow
                                        
                                        # Skip position jump validation during attack phases or when camera is moving
                                        if self._last_santa_center is not None and self.search_state == "idle" and not skip_validation and self.attack_phase == "idle" and not camera_is_moving:
                                            prev_cx, prev_cy = self._last_santa_center
                                            jump_distance = abs(candidate_cx - prev_cx)
                                            max_reasonable_jump = 250
                                            
                                            if jump_distance > max_reasonable_jump:
                                                is_valid_candidate = False
                                                if self._debug_log_counter % 10 == 0:
                                                    self.logger.info(f"[YOLO REJECT] Position jump too large: X={candidate_cx} (prev={prev_cx}, jump={jump_distance}px > {max_reasonable_jump}px) conf={confidence:.2f}")
                                        
                                        if is_valid_candidate and self.attack_phase == "idle":
                                            self._detection_movement_history.append((candidate_cx, candidate_cy))
                                            if len(self._detection_movement_history) > self._max_movement_history:
                                                self._detection_movement_history.pop(0)
                                            
                                            # Only check movement after collecting enough frames (reduced to 5 for faster response)
                                            if len(self._detection_movement_history) >= 5:
                                                x_positions = [pos[0] for pos in self._detection_movement_history]
                                                y_positions = [pos[1] for pos in self._detection_movement_history]
                                                x_range = max(x_positions) - min(x_positions)
                                                y_range = max(y_positions) - min(y_positions)
                                                total_movement = max(x_range, y_range)
                                                
                                                if total_movement < self._min_movement_pixels:
                                                    is_valid_candidate = False
                                                    self.logger.info(f"[YOLO REJECT] Static object detected (moved only {total_movement}px over 5 frames) - likely tree/decoration at X={candidate_cx}")
                                                    self._consecutive_detections = 0
                                                    self._detection_movement_history.clear()
                                        
                                        if is_valid_candidate:
                                            if best_santa is None or confidence > best_santa['confidence']:
                                                best_santa = {
                                                    'box': (int(x1), int(y1), int(x2), int(y2)),
                                                    'confidence': confidence
                                                }
                                                if self._debug_log_counter % 10 == 0:
                                                    self.logger.info(f"[YOLO ACCEPT] Santa {candidate_w}x{candidate_h}, aspect={aspect_ratio:.2f}, conf={confidence:.2f}, phase={self.attack_phase}")
                        except Exception as e:
                            if self._debug_log_counter % 50 == 0:
                                self.logger.error(f"[YOLO ERROR] {e}")
                    else:
                        if self._debug_log_counter % 100 == 0:
                            self.logger.warning("[YOLO MODEL] Not loaded - cannot detect Santa")
                    
                    if self._debug_log_counter % 25 == 0:
                        if best_santa:
                            self.logger.info(f"[DEBUG] YOLO detected Santa: {best_santa}")
                        else:
                            self.logger.info("[DEBUG] YOLO detection returned None")
                    
                    if not self._running:
                        self.logger.info("[STOP] Stopping before processing Santa detection")
                        if self._mouse_down:
                            self._send_mouse_click(down=False)
                            self._mouse_down = False
                        with self.arrow_lock:
                            if self.current_arrow_key:
                                pydirectinput.keyUp(self.current_arrow_key)
                                with self.keys_lock:
                                    self.camera_keys_pressed.discard(self.current_arrow_key)
                                self.current_arrow_key = None
                                self.is_holding_arrow = False
                        continue
                    
                    current_time = time.time()
                    
                    if self.attack_phase == "cooldown" and best_santa:
                        if self.attack_phase_start is None:
                            self.attack_phase_start = current_time
                        phase_elapsed = current_time - self.attack_phase_start
                        if phase_elapsed >= self._get_cooldown_duration():
                            # CRITICAL: Before restarting attack, validate Santa's position
                            # If Santa is too far out of bounds, abort and search instead of looping forever
                            x1, y1, x2, y2 = best_santa['box']
                            w = x2 - x1
                            santa_cx = x1 + w // 2
                            
                            # Check if Santa is within reasonable bounds for continuing attack
                            # Use 20-80% range (vs 25-75% safe zone for starting attacks)
                            # This gives some margin but prevents attacking way out of bounds targets
                            abort_zone_left = int(self.roi["width"] * 0.20)
                            abort_zone_right = int(self.roi["width"] * 0.80)
                            
                            if santa_cx < abort_zone_left or santa_cx > abort_zone_right:
                                # Santa is way out of bounds - this might be a tree or Santa escaped
                                # Abort the attack loop and search for proper target
                                self.logger.info(f"[COOLDOWN END] Santa at X={santa_cx} outside acceptable range ({abort_zone_left}-{abort_zone_right}) - ABORTING attack loop")
                                
                                # Press '1' after E spam sequence ends (even when aborting)
                                pydirectinput.press('1')
                                self.logger.info("[COOLDOWN] Pressed '1' after E spam sequence (aborting)")
                                
                                self.attack_phase = "idle"
                                self._consecutive_detections = 0
                                self._detection_movement_history.clear()
                                self._has_attacked_successfully = True  # Preserve attack state
                                
                                with self.arrow_lock:
                                    if self.current_arrow_key is not None:
                                        pydirectinput.keyUp(self.current_arrow_key)
                                        with self.keys_lock:
                                            self.camera_keys_pressed.discard(self.current_arrow_key)
                                        self.current_arrow_key = None
                                        self.is_holding_arrow = False
                                
                                # Force search to reposition camera
                                self.search_state = "searching_left"
                                self.logger.info("[COOLDOWN END] Forcing search to find better target position")
                            else:
                                # Santa is in acceptable position, continue attack cycle
                                with self.arrow_lock:
                                    if self.current_arrow_key is not None:
                                        pydirectinput.keyUp(self.current_arrow_key)
                                        with self.keys_lock:
                                            self.camera_keys_pressed.discard(self.current_arrow_key)
                                        self.current_arrow_key = None
                                        self.is_holding_arrow = False
                                
                                # Press '1' after E spam sequence ends
                                pydirectinput.press('1')
                                self.logger.info("[COOLDOWN] Pressed '1' after E spam sequence")
                                
                                # Reset consecutive detections for the next attack cycle
                                self._consecutive_detections = 0
                                self.attack_phase = "load"
                                self.attack_phase_start = current_time
                                self.attack_committed = False  # Reset for new attack cycle
                                self.logger.info(f"[MEGAPOW] Cooldown complete (Santa at X={santa_cx}) -> Stage 1: LOAD started (1.0s)")
                                
                                # Start custom attack for the new cycle
                                if self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled():
                                    if not self.custom_attack_manager.player.playing:
                                        self._send_attack_input(down=True)
                                        self.attack_committed = True  # Mark that attack has been started
                                        self.logger.info(f"[ATTACK INPUT] CUSTOM SEQUENCE RESTARTED (COOLDOWN->LOAD)")
                    
                    if best_santa:
                        x1, y1, x2, y2 = best_santa['box']
                        w = x2 - x1
                        h = y2 - y1
                        santa_cx = x1 + w // 4  # Aim between left edge and center (1/4 width from left)
                        santa_cy = y1 + h // 2
                        
                        self._position_history.append((santa_cx, santa_cy))
                        if len(self._position_history) > self._max_position_history:
                            self._position_history.pop(0)
                        
                        if len(self._position_history) >= 2:
                            dx = self._position_history[-1][0] - self._position_history[0][0]
                            dy = self._position_history[-1][1] - self._position_history[0][1]
                            frames = len(self._position_history)
                            vx = dx / frames
                            vy = dy / frames
                            self._predicted_position = (int(santa_cx + vx * 2), int(santa_cy + vy * 2))
                        
                        if self._debug_log_counter % 10 == 0:
                            self.logger.info(f"[SANTA DETECTED] Position: ({santa_cx}, {santa_cy}), size: {w}x{h}, conf: {best_santa['confidence']:.2f}")
                            # Webhook: Santa detected (rate-limited in webhook manager)
                            if self.webhook_manager and self._consecutive_detections == 1:
                                self.webhook_manager.santa_detected(best_santa['confidence'], (santa_cx, santa_cy, w, h))
                        
                        target_x_roi = santa_cx
                        target_y_roi = santa_cy
                        
                        if self._debug_log_counter % 10 == 0:
                            self.logger.info(f"[AIM] Left-quarter of Santa (between left edge and center)")
                        
                        target_x = target_x_roi + self.roi["left"]
                        target_y = target_y_roi + self.roi["top"]
                        
                        if target_y < 10:
                            target_y = 10
                        
                        ctypes.windll.user32.SetCursorPos(target_x, target_y)
                        ctypes.windll.user32.mouse_event(0x0001, 0, 1, 0, 0)
                        
                        self._last_santa_center = (santa_cx, santa_cy)
                        
                        ctypes.windll.user32.SetCursorPos(target_x, target_y)
                        ctypes.windll.user32.mouse_event(0x0001, 0, 1, 0, 0)
                        
                        if self._debug_log_counter % 10 == 0:
                            self.logger.info(f"[CURSOR MOVED] ROI: ({target_x_roi}, {target_y_roi}) -> Screen: ({target_x}, {target_y})")
                        
                        roi_center_x = self.roi["width"] // 2
                        optimal_position = int(self.roi["width"] * 0.60)
                        offset_x = santa_cx - optimal_position
                        move_threshold = self.roi["width"] * 0.30
                        
                        if self.search_state != "idle":
                            with self.arrow_lock:
                                if self.current_arrow_key is not None:
                                    pydirectinput.keyUp(self.current_arrow_key)
                                    with self.keys_lock:
                                        self.camera_keys_pressed.discard(self.current_arrow_key)
                                    self.current_arrow_key = None
                                    self.is_holding_arrow = False
                            self.logger.info(f"[SEARCH] Santa found! Stopping search, switching to tracking")
                            self.search_state = "idle"
                            self._search_exit_frame = self._debug_log_counter
                            
                            # CRITICAL: Clear movement history after search stops
                            # During camera pan, static trees appear to "move" - need fresh data with camera frozen
                            self._detection_movement_history.clear()
                            self._consecutive_detections = 0
                            self.logger.info(f"[MOVEMENT RESET] Cleared history - validating fresh movement with camera stopped")
                        
                        # If Santa detected immediately on startup (within first 3 frames), abort search
                        if self._debug_log_counter <= 3 and self.search_state == "idle":
                            self.logger.info(f"[STARTUP] Santa detected immediately (frame {self._debug_log_counter}) - skipping search phase")
                        
                        if santa_cx < roi_center_x:
                            self.last_santa_side = "left"
                        else:
                            self.last_santa_side = "right"
                        
                        if self._debug_log_counter % 5 == 0:
                            phase_status = f"[{self.attack_phase.upper()}]" if self.attack_phase != "idle" else "[IDLE]"
                            self.logger.info(f"[CAMERA DEBUG] {phase_status} Santa ROI X={santa_cx}, Optimal={optimal_position}, Offset={offset_x:.0f}, Threshold={move_threshold:.0f}")
                        
                        
                        # Camera repositioning during attack (inspired by GPO Santa.py)
                        # CRITICAL: For long custom attacks, aggressively track Santa to prevent loss
                        # Must keep Santa in view even during 20+ second attack sequences
                        if self.attack_phase in ["load", "fire"]:
                            # Check if Santa is in the danger zone (too far left or right)
                            # Use wider thresholds (10-90%) for more aggressive tracking during attacks
                            reposition_threshold_left = int(self.roi["width"] * 0.10)  # Left 10% - very aggressive
                            reposition_threshold_right = int(self.roi["width"] * 0.90)  # Right 90% - very aggressive
                            
                            with self.arrow_lock:
                                if santa_cx < reposition_threshold_left:
                                    # Santa too far left - move camera LEFT to recenter
                                    if self.current_arrow_key != 'left':
                                        if self.current_arrow_key:
                                            pydirectinput.keyUp(self.current_arrow_key)
                                            with self.keys_lock:
                                                self.camera_keys_pressed.discard(self.current_arrow_key)
                                        pydirectinput.keyDown('left')
                                        with self.keys_lock:
                                            self.camera_keys_pressed.add('left')
                                        self.current_arrow_key = 'left'
                                        self.is_holding_arrow = True
                                        self._camera_has_tracked = True  # Confirmed we're tracking Santa
                                        if self._debug_log_counter % 5 == 0:  # More frequent logging
                                            self.logger.info(f"[{self.attack_phase.upper()} TRACK] Santa at X={santa_cx} too far LEFT - repositioning camera")
                                elif santa_cx > reposition_threshold_right:
                                    # Santa too far right - move camera RIGHT to recenter
                                    if self.current_arrow_key != 'right':
                                        if self.current_arrow_key:
                                            pydirectinput.keyUp(self.current_arrow_key)
                                            with self.keys_lock:
                                                self.camera_keys_pressed.discard(self.current_arrow_key)
                                        pydirectinput.keyDown('right')
                                        with self.keys_lock:
                                            self.camera_keys_pressed.add('right')
                                        self.current_arrow_key = 'right'
                                        self.is_holding_arrow = True
                                        self._camera_has_tracked = True  # Confirmed we're tracking Santa
                                        if self._debug_log_counter % 5 == 0:  # More frequent logging
                                            self.logger.info(f"[{self.attack_phase.upper()} TRACK] Santa at X={santa_cx} too far RIGHT - repositioning camera")
                                else:
                                    # Santa is centered enough - release arrow keys
                                    if self.current_arrow_key is not None:
                                        key_to_release = self.current_arrow_key
                                        pydirectinput.keyUp(key_to_release)
                                        with self.keys_lock:
                                            self.camera_keys_pressed.discard(key_to_release)
                                        self.current_arrow_key = None
                                        self.is_holding_arrow = False
                        
                        elif self.attack_phase == "cooldown":
                            # During cooldown, TRACK Santa with camera to keep them on screen
                            # Determine which direction Santa is moving
                            move_threshold = self.roi["width"] * 0.20  # More aggressive tracking during cooldown
                            optimal_center = self.roi["width"] // 2
                            offset_x = santa_cx - optimal_center
                            
                            should_move_left = offset_x < -move_threshold
                            should_move_right = offset_x > move_threshold
                            
                            with self.arrow_lock:
                                if should_move_left:
                                    if self.current_arrow_key != 'left':
                                        if self.current_arrow_key:
                                            pydirectinput.keyUp(self.current_arrow_key)
                                            with self.keys_lock:
                                                self.camera_keys_pressed.discard(self.current_arrow_key)
                                        pydirectinput.keyDown('left')
                                        with self.keys_lock:
                                            self.camera_keys_pressed.add('left')
                                        self.current_arrow_key = 'left'
                                        self.is_holding_arrow = True
                                        self._camera_has_tracked = True  # Confirmed we're tracking Santa
                                        if self._debug_log_counter % 10 == 0:
                                            self.logger.info(f"[COOLDOWN] Following Santa LEFT (offset={offset_x:.0f})")
                                elif should_move_right:
                                    if self.current_arrow_key != 'right':
                                        if self.current_arrow_key:
                                            pydirectinput.keyUp(self.current_arrow_key)
                                            with self.keys_lock:
                                                self.camera_keys_pressed.discard(self.current_arrow_key)
                                        pydirectinput.keyDown('right')
                                        with self.keys_lock:
                                            self.camera_keys_pressed.add('right')
                                        self.current_arrow_key = 'right'
                                        self.is_holding_arrow = True
                                        self._camera_has_tracked = True  # Confirmed we're tracking Santa
                                        if self._debug_log_counter % 10 == 0:
                                            self.logger.info(f"[COOLDOWN] Following Santa RIGHT (offset={offset_x:.0f})")
                                else:
                                    # Santa is centered enough, stop moving
                                    if self.current_arrow_key:
                                        pydirectinput.keyUp(self.current_arrow_key)
                                        with self.keys_lock:
                                            self.camera_keys_pressed.discard(self.current_arrow_key)
                                        self.current_arrow_key = None
                                        self.is_holding_arrow = False
                        
                        self._last_detection_frame = self._debug_log_counter
                        self._consecutive_detections += 1
                        current_time = time.time()
                        
                        # Log detection state every 25 frames
                        if self._debug_log_counter % 25 == 0:
                            self.logger.info(f"[DETECTION STATE] consecutive={self._consecutive_detections}, attack_phase={self.attack_phase}, has_attacked={self._has_attacked_successfully}")
                        
                        can_start_attack = False
                        # Simple: If YOLO consistently detects Santa, attack
                        required_detections = 3
                        
                        if self.attack_phase == "idle" and self._consecutive_detections >= required_detections:
                            # YOLO detected Santa consistently - that's enough validation
                            can_start_attack = True
                            if self._has_attacked_successfully:
                                self.logger.info(f"[ATTACK] Santa detected {self._consecutive_detections} times, restarting attack")
                            else:
                                self.logger.info(f"[ATTACK] Santa detected {self._consecutive_detections} times, starting first attack")
                        
                        if can_start_attack:
                            safe_zone_left = int(self.roi["width"] * 0.25)
                            safe_zone_right = int(self.roi["width"] * 0.75)
                            
                            if santa_cx < safe_zone_left:
                                self.logger.info(f"[ATTACK BLOCKED] Santa at X={santa_cx} LEFT of safe zone (< {safe_zone_left}) - moving camera LEFT")
                                can_start_attack = False
                                with self.arrow_lock:
                                    if self.current_arrow_key != "left":
                                        if self.current_arrow_key is not None:
                                            pydirectinput.keyUp(self.current_arrow_key)
                                            with self.keys_lock:
                                                self.camera_keys_pressed.discard(self.current_arrow_key)
                                        pydirectinput.keyDown("left")
                                        with self.keys_lock:
                                            self.camera_keys_pressed.add("left")
                                        self.current_arrow_key = "left"
                                        self.is_holding_arrow = True
                                        self._camera_has_tracked = True  # Mark that we've tracked Santa
                            elif santa_cx > safe_zone_right:
                                self.logger.info(f"[ATTACK BLOCKED] Santa at X={santa_cx} RIGHT of safe zone (> {safe_zone_right}) - moving camera RIGHT")
                                can_start_attack = False
                                with self.arrow_lock:
                                    if self.current_arrow_key != "right":
                                        if self.current_arrow_key is not None:
                                            pydirectinput.keyUp(self.current_arrow_key)
                                            with self.keys_lock:
                                                self.camera_keys_pressed.discard(self.current_arrow_key)
                                        pydirectinput.keyDown("right")
                                        with self.keys_lock:
                                            self.camera_keys_pressed.add("right")
                                        self.current_arrow_key = "right"
                                        self.is_holding_arrow = True
                                        self._camera_has_tracked = True  # Mark that we've tracked Santa
                        
                        if can_start_attack:
                            # CRITICAL: Restore Roblox focus before attack
                            # Mouse clicks and long operations can steal focus, breaking all inputs
                            if not self._is_roblox_focused():
                                self.logger.info("[FOCUS] Restoring Roblox focus before attack...")
                                self._force_focus_roblox()
                                time.sleep(0.05)  # Brief delay for focus to take effect
                            
                            self.logger.info(f"[ATTACK START] Santa detected {self._consecutive_detections} times, starting attack now")
                            
                            # Webhook: Attack started
                            if self.webhook_manager:
                                attack_mode = "custom" if (self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled()) else "standard"
                                self.webhook_manager.attack_started(attack_mode)
                            
                            # CRITICAL: Force-release all arrow keys using native Windows API
                            self._force_release_all_arrows()
                            self.logger.info(f"[CAMERA] Force-released all arrows - freezing for attack")
                            
                            self.attack_phase = "load"
                            self.attack_phase_start = current_time
                            self.attack_committed = False  # Reset for this attack cycle
                            self.logger.info(f"[MEGAPOW] Stage 1: LOAD started (1.0s) - Santa detected!")
                            
                            # Start custom attack immediately when entering LOAD phase
                            if self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled():
                                if not self.custom_attack_manager.player.playing:
                                    self._send_attack_input(down=True)
                                    self.attack_committed = True  # Mark that attack has been started
                                    self.logger.info(f"[ATTACK INPUT] CUSTOM SEQUENCE STARTED (LOAD)")
                        elif self.attack_phase == "cooldown":
                            if self.attack_phase_start is None:
                                self.attack_phase_start = current_time
                            phase_elapsed = current_time - self.attack_phase_start
                            
                            pydirectinput.press('e')
                            if self._debug_log_counter % 10 == 0:
                                self.logger.info(f"[COOLDOWN] Spamming E during cooldown ({phase_elapsed:.1f}s/{self._get_cooldown_duration()}s)")
                        
                        if self.attack_phase == "load":
                            if self.attack_phase_start is None:
                                self.attack_phase_start = current_time
                            phase_elapsed = current_time - self.attack_phase_start
                            
                            # For custom attacks, DON'T spam - already started when entering load phase
                            # Only traditional attacks spam input
                            if not (self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled()):
                                # Traditional attack - spam input
                                if not self._mouse_down and not self._x_key_down:
                                    self._send_attack_input(down=True)
                                    input_type = "TRADITIONAL"
                                    self.logger.info(f"[ATTACK INPUT] {input_type} DOWN (LOAD)")
                            
                            if phase_elapsed >= self._get_load_duration():
                                self.attack_phase = "fire"
                                self.attack_phase_start = current_time
                                # Note: don't reset attack_committed - custom attack is already running
                                self._has_attacked_successfully = True
                                self.logger.info("[MEGAPOW] Stage 1 complete -> Stage 2: FIRE started (5.0s)")
                            elif self._debug_log_counter % 25 == 0:
                                mode_name = "CUSTOM"
                                self.logger.info(f"[{mode_name}] Stage 1: LOAD ({phase_elapsed:.1f}s/{self._get_load_duration()}s)")
                        
                        elif self.attack_phase == "fire":
                            if self.attack_phase_start is None:
                                self.attack_phase_start = current_time
                            phase_elapsed = current_time - self.attack_phase_start
                            
                            # For custom attacks, don't spam input - let custom sequence handle it
                            if self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled():
                                # Custom attack is already running, don't interfere
                                pass
                            else:
                                # Traditional attack - spam input
                                if not self._mouse_down and not self._x_key_down:
                                    self._send_attack_input(down=True)
                                    input_type = "CUSTOM SEQUENCE"
                                    self.logger.info(f"[ATTACK INPUT] {input_type} DOWN (FIRE)")
                            
                            if phase_elapsed >= self._get_fire_duration():
                                # Stop custom attack or traditional attack
                                if self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled():
                                    if self.custom_attack_manager.player.playing:
                                        self.custom_attack_manager.stop_attack()
                                        self.logger.info("[CUSTOM ATTACK] Fire phase complete - stopped custom sequence")
                                else:
                                    if self._mouse_down or self._x_key_down:
                                        self._send_attack_input(down=False)
                                        input_type = "CUSTOM SEQUENCE"
                                        self.logger.info(f"[ATTACK INPUT] {input_type} UP (FIRE COMPLETE)")
                                
                                # Press '1' before starting E spam sequence
                                pydirectinput.press('1')
                                self.logger.info("[COOLDOWN] Pressed '1' before E spam sequence")
                                
                                self.attack_phase = "cooldown"
                                self.attack_phase_start = current_time
                                self.logger.info("[MEGAPOW] Stage 2 complete -> Stage 3: COOLDOWN started (5.2s)")
                                
                                # Webhook: Attack completed
                                if self.webhook_manager:
                                    attack_mode = "custom" if (self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled()) else "standard"
                                    duration = current_time - self.attack_phase_start if self.attack_phase_start else 0
                                    self.webhook_manager.attack_completed(attack_mode, duration)
                            elif self._debug_log_counter % 25 == 0:
                                mode_name = "CUSTOM"
                                self.logger.info(f"[{mode_name}] Stage 2: FIRE ({phase_elapsed:.1f}s/{self._get_fire_duration()}s)")
                        
                        if self.overlay_enabled:
                            self._update_fps()
                            overlay_x = x1 + self.roi["left"]
                            overlay_y = y1 + self.roi["top"]
                            overlay_bbox = (overlay_x, overlay_y, w, h)
                            det = DetectionResult(bbox=overlay_bbox, confidence=best_santa['confidence'])
                            self._draw_overlay(frame_bgr, det, (target_x, target_y), attack_mode="custom")
                    else:
                        if not self._running:
                            self.logger.info("[STOP] Stopping in no-detection branch")
                            if self._mouse_down or self._x_key_down:
                                self._send_attack_input(down=False)
                            with self.arrow_lock:
                                if self.current_arrow_key:
                                    pydirectinput.keyUp(self.current_arrow_key)
                                    with self.keys_lock:
                                        self.camera_keys_pressed.discard(self.current_arrow_key)
                                    self.current_arrow_key = None
                                    self.is_holding_arrow = False
                            continue
                        
                        if self._last_detection_frame >= 0:
                            frames_since_detection = self._debug_log_counter - self._last_detection_frame
                        else:
                            frames_since_detection = 9999
                        
                        if frames_since_detection <= self._detection_grace_frames and self._last_detection_frame >= 0:
                            # For custom attacks, don't spam input during grace - sequence is already running
                            # Only spam for traditional attacks
                            if self.attack_phase in ["load", "fire"]:
                                if not (self.custom_attack_manager and self.custom_attack_manager.is_custom_enabled()):
                                    # Traditional attack - keep spamming
                                    if not self._mouse_down and not self._x_key_down:
                                        self._send_attack_input(down=True)
                                        input_type = "TRADITIONAL"
                                        self.logger.info(f"[ATTACK INPUT] {input_type} DOWN (GRACE PERIOD)")
                                # For custom attacks, do nothing - sequence is already playing
                            
                            current_time = time.time()
                            if self.attack_phase_start is None:
                                self.attack_phase_start = current_time
                            phase_elapsed = current_time - self.attack_phase_start
                            
                            if self.attack_phase == "fire" and phase_elapsed >= self._get_fire_duration():
                                if self._mouse_down or self._x_key_down:
                                    self._send_attack_input(down=False)
                                    input_type = "CUSTOM SEQUENCE"
                                    self.logger.info(f"[ATTACK INPUT] {input_type} UP (GRACE FIRE COMPLETE)")
                                
                                # Press '1' before starting E spam sequence
                                pydirectinput.press('1')
                                self.logger.info("[COOLDOWN] Pressed '1' before E spam sequence")
                                
                                self.attack_phase = "cooldown"
                                self.attack_phase_start = current_time
                                mode_name = "CUSTOM"
                                self.logger.info(f"[{mode_name}] Stage 2 complete (grace) -> Stage 3: COOLDOWN")
                            elif self.attack_phase == "cooldown":
                                pydirectinput.press('e')
                                if self._debug_log_counter % 10 == 0:
                                    self.logger.info(f"[COOLDOWN] Spamming E during grace period cooldown")
                            
                            # Extended prediction window during attacks (especially for long custom sequences)
                            prediction_window = 30 if self.attack_phase in ["load", "fire"] else 15
                            if self._predicted_position and frames_since_detection < prediction_window:
                                pred_x_roi, pred_y_roi = self._predicted_position
                                pred_x = pred_x_roi + self.roi["left"]
                                pred_y = pred_y_roi + self.roi["top"]
                                pred_x = max(self.monitor["left"], min(pred_x, self.monitor["left"] + self.monitor["width"]))
                                pred_y = max(self.monitor["top"], min(pred_y, self.monitor["top"] + self.monitor["height"]))
                                ctypes.windll.user32.SetCursorPos(pred_x, pred_y)
                                ctypes.windll.user32.mouse_event(0x0001, 0, 1, 0, 0)
                                if self._debug_log_counter % 25 == 0:
                                    self.logger.info(f"[GRACE] Tracking predicted position ({frames_since_detection}/{self._detection_grace_frames})")
                            elif self._debug_log_counter % 25 == 0:
                                self.logger.info(f"[GRACE] Keeping lock ({frames_since_detection}/{self._detection_grace_frames} frames)")
                        else:
                            self._consecutive_detections = 0
                            if self._last_santa_center is not None:
                                self._last_santa_center = None
                                self.logger.info("[POSITION RESET] Grace expired, clearing old position data")
                            self._detection_movement_history.clear()
                            if self._debug_log_counter % 50 == 0:
                                self.logger.info("[SEARCHING] Looking for Santa...")
                            
                            # Don't abort attack if we're in FIRE or LOAD phase - keep going!
                            # Santa might reappear, and we need to complete the cycle regardless
                            if self.attack_phase in ["load", "fire"]:
                                # Check if fire duration is complete
                                if self.attack_phase == "fire":
                                    phase_elapsed = time.time() - self.attack_phase_start
                                    if phase_elapsed >= self._get_fire_duration():
                                        # Fire complete, go to cooldown
                                        if self._mouse_down or self._x_key_down:
                                            self._send_attack_input(down=False)
                                            input_type = "CUSTOM SEQUENCE"
                                            self.logger.info(f"[FIRE COMPLETE] {input_type} UP (no visual)")
                                        
                                        # Press '1' before starting E spam sequence
                                        pydirectinput.press('1')
                                        self.logger.info("[COOLDOWN] Pressed '1' before E spam sequence")
                                        
                                        self.attack_phase = "cooldown"
                                        self.attack_phase_start = time.time()
                                        self.attack_committed = True
                                        self._has_attacked_successfully = True
                                        mode_name = "CUSTOM"
                                        self.logger.info(f"[{mode_name}] Fire complete (lost visual) -> Starting COOLDOWN")
                                    else:
                                        # Keep firing even without visual
                                        if not self._mouse_down and not self._x_key_down:
                                            self._send_attack_input(down=True)
                                # Continue with attack, don't search
                                continue
                            
                            # Legacy mouse_down handling (should not reach here)
                            if self._mouse_down and self.attack_phase != "cooldown":
                                self._send_mouse_click(down=False)
                                self._mouse_down = False
                                pydirectinput.press('1')
                                self.attack_phase = "cooldown"
                                self.attack_phase_start = time.time()
                                self.attack_committed = True
                                self._has_attacked_successfully = True
                                self.logger.info("[COOLDOWN] Starting cooldown cycle after losing Santa")
                                
                                self.last_kill_time = time.time()
                                self.logger.info("[LOOT] Starting E spam sequence...")
                            
                            time_since_kill = time.time() - self.last_kill_time
                            if time_since_kill < self.e_spam_duration:
                                pydirectinput.press('e')
                                if self._debug_log_counter % 10 == 0:
                                    self.logger.info(f"[LOOT] Spamming E ({time_since_kill:.1f}s/{self.e_spam_duration}s)")
                            
                            if self.search_state == "idle":
                                # CRITICAL: Force-release ALL arrows before starting search
                                self._force_release_all_arrows()
                                self.logger.info("[SEARCH] Force-released all arrows before search")
                                
                                # DO NOT search during any attack phase - must complete attack cycle first
                                if self.attack_phase in ["load", "fire", "cooldown"]:
                                    self.logger.info(f"[SEARCH] Cannot search - {self.attack_phase} in progress, waiting...")
                                    continue  # Skip search, stay waiting for attack to complete
                                
                                self._last_santa_center = None
                                self._detection_movement_history.clear()
                                
                                # CRITICAL: Restore Roblox focus before search
                                # Camera movement requires focus to work
                                if not self._is_roblox_focused():
                                    self.logger.info("[FOCUS] Restoring Roblox focus for search...")
                                    self._force_focus_roblox()
                                    time.sleep(0.05)  # Brief delay for focus to take effect
                                
                                # Always search left when Santa is lost
                                self.search_state = "searching_left"
                                self.logger.info(f"[SEARCH] Santa lost, searching left...")
                                
                                # CRITICAL: Force-release all arrows before starting search
                                self._force_release_all_arrows()
                                self.logger.info(f"[SEARCH] Force-released all arrows - ready for clean search")
                            
                            self._predicted_position = None
                            self._position_history.clear()
                            self._smoothed_cursor_pos = None
                        
                        if self.overlay_enabled:
                            self._update_fps()
                            det = DetectionResult(bbox=None, confidence=0.0)
                            self._draw_overlay(frame_bgr, det, None, attack_mode="custom")
                    
                    self._debug_log_counter += 1
                    time.sleep(self.tick_interval)
                    continue

                det = DetectionResult(bbox=None, confidence=0.0)
                
                if self.lock_on_enabled and not self._locked_santa and self._learning_start_ts is None:
                    if self.det_mode == "motion":
                        color_det = self._detect_motion_color(frame_bgr)
                        if color_det and color_det.bbox:
                            x, y, w, h = color_det.bbox
                            if w >= self.min_santa_size and h >= self.min_santa_size:
                                self._start_learning_phase()
                                det = color_det
                            else:
                                if self._debug_log_counter % 50 == 0:
                                    self.logger.debug("Skipping small detection during search: %dx%d", w, h)
                    else:
                        det = self._match_templates(frame_gray) if self.det_mode == "template" else self._detect_motion(frame_gray)
                        if det.bbox:
                            self._start_learning_phase()
                
                elif self.state == MacroState.LEARNING:
                    elapsed = time.time() - self._learning_start_ts
                    
                    if elapsed < self.learning_duration:
                        if self.det_mode == "motion":
                            color_det = self._detect_motion_color(frame_bgr)
                            if color_det and color_det.bbox:
                                det = color_det
                                self._process_learning_sample(det.bbox, frame_bgr, det.confidence)
                            else:
                                if self._debug_log_counter % 25 == 0:
                                    self.logger.debug("Learning: temporary detection loss")
                        else:
                            det = self._match_templates(frame_gray) if self.det_mode == "template" else self._detect_motion(frame_gray)
                            if det.bbox:
                                self._process_learning_sample(det.bbox, frame_bgr, det.confidence)
                    else:
                        self._finalize_learning()
                
                elif self._locked_santa:
                    self.state = MacroState.DETECTING
                    
                    if self.det_mode == "motion":
                        color_det = self._detect_motion_color(frame_bgr)
                        if color_det and color_det.bbox:
                            is_valid, rejection_reason = self._validate_detection(color_det.bbox, frame_bgr)
                            
                            if is_valid:
                                det = color_det
                                self._update_santa_tracking(det.bbox)
                                self._rejected_detections_count = 0
                                if self._debug_log_counter % 25 == 0:
                                    x, y, w, h = det.bbox
                                    self.logger.debug("✓ Validated: %dx%d at (%d,%d) conf=%.2f (consecutive: %d)", 
                                                     w, h, x, y, det.confidence, self._postlock_consecutive_valid)
                            else:
                                self._rejected_detections_count += 1
                                self._reset_postlock_valid()
                                if self._rejected_detections_count <= 10 or self._rejected_detections_count % 5 == 0:
                                    x, y, w, h = color_det.bbox
                                    self.logger.info("✗ REJECT #%d: %dx%d at (%d,%d) - %s", 
                                                   self._rejected_detections_count, w, h, x, y, rejection_reason)
                                
                                if self._predicted_position and self._rejected_detections_count < 15:
                                    if self._last_santa_center:
                                        avg_size = (self._santa_profile.size_min + self._santa_profile.size_max) // 2
                                        pred_x = self._predicted_position[0] - avg_size // 2
                                        pred_y = self._predicted_position[1] - avg_size // 2
                                        det = DetectionResult(
                                            bbox=(pred_x, pred_y, avg_size, avg_size),
                                            confidence=0.5
                                        )
                                        if self._debug_log_counter % 25 == 0:
                                            self.logger.debug("Using prediction: %s", det.bbox)
                        else:
                            if self._predicted_position and self._rejected_detections_count < 20:
                                avg_size = (self._santa_profile.size_min + self._santa_profile.size_max) // 2
                                pred_x = self._predicted_position[0] - avg_size // 2
                                pred_y = self._predicted_position[1] - avg_size // 2
                                det = DetectionResult(
                                    bbox=(pred_x, pred_y, avg_size, avg_size),
                                    confidence=0.4
                                )
                                
                                if self._check_camera_control_needed(det.bbox):
                                    self.state = MacroState.CAMERA_TRACKING
                                    self._perform_camera_drag(pred_x)
                                    
                                if self._debug_log_counter % 25 == 0:
                                    self.logger.debug("No detection, using prediction: %s", det.bbox)
                            else:
                                if self._rejected_detections_count >= 50:
                                    self.logger.warning("⚠️ Lost Santa - resetting lock (rejected %d times)", 
                                                       self._rejected_detections_count)
                                    self._locked_santa = False
                                    self._learning_start_ts = None
                                    self._rejected_detections_count = 0
                                    self._stop_camera_drag()
                                elif self._debug_log_counter % 50 == 0:
                                    self.logger.debug("Searching for Santa... (rejected %d)", 
                                                     self._rejected_detections_count)
                    else:
                        det_raw = self._match_templates(frame_gray) if self.det_mode == "template" else self._detect_motion(frame_gray)
                        if det_raw.bbox:
                            is_valid, rejection_reason = self._validate_detection(det_raw.bbox, frame_bgr)
                            if is_valid:
                                det = det_raw
                                self._update_santa_tracking(det.bbox)
                                self._rejected_detections_count = 0
                            else:
                                self._rejected_detections_count += 1
                                if self._debug_log_counter % 10 == 0:
                                    self.logger.info("✗ Rejected: %s", rejection_reason)
                    
                    if det.bbox and self._camera_drag_active:
                        x, y, w, h = det.bbox
                        distance_from_left = x - self.monitor["left"]
                        if distance_from_left > self.camera_left_edge_threshold + 100:
                            self._stop_camera_drag()
                            self.state = MacroState.DETECTING
                
                else:
                    self.state = MacroState.DETECTING
                    
                    if self.det_mode == "motion":
                        color_det = self._detect_motion_color(frame_bgr)
                        if color_det:
                            det = color_det
                        else:
                            det = self._detect_motion(frame_gray)
                    elif self.det_mode == "template":
                        det = self._match_templates(frame_gray)
                    else:
                        det_t = self._match_templates(frame_gray)
                        if det_t.bbox and det_t.confidence >= self.threshold:
                            det = det_t
                        else:
                            det = self._detect_motion(frame_gray)
                
                self._debug_log_counter += 1
                
                if self._locked_on_santa and self._lock_start_ts:
                    lock_duration = time.time() - self._lock_start_ts
                    if lock_duration > self._lock_timeout_seconds:
                        self._release_lock_on(f"Timeout after {lock_duration:.1f}s")
                
                det = DetectionResult(bbox=None, confidence=0.0)
                
                if self._locked_on_santa:
                    self.state = MacroState.DETECTING
                    self.logger.debug("LOCKED ON SANTA - Using tracker only")
                    
                    track_box = None
                    if self._shoot_tracker is not None:
                        track_box = self._update_shoot_tracker(frame_bgr)
                    if track_box is None and self._shoot_tmpl is not None:
                        track_box = self._update_shoot_template(frame_bgr)
                    
                    if track_box is not None:
                        if self._is_valid_track_box(frame_bgr, track_box):
                            if self._check_santa_left_screen(track_box):
                                self._release_lock_on("Santa left screen")
                                det = DetectionResult(bbox=None, confidence=0.0)
                            else:
                                det = DetectionResult(bbox=track_box, confidence=0.95)
                                self._update_lock_on(track_box)
                                self.logger.debug("LOCKED TRACKING: bbox=%s", track_box)
                        else:
                            self.logger.warning("Tracker gave invalid box, attempting recovery")
                            wide_color_det = self._detect_motion_color(frame_bgr)
                            if wide_color_det and wide_color_det.bbox:
                                ww, wh = wide_color_det.bbox[2], wide_color_det.bbox[3]
                                if ww >= 30 and wh >= 30:
                                    det = wide_color_det
                                    self._update_lock_on(wide_color_det.bbox)
                                    self._init_shoot_tracker(frame_bgr, wide_color_det.bbox)
                                    self._init_shoot_template(frame_bgr, wide_color_det.bbox)
                                    self.logger.info("Recovered lock with WIDE color search (w=%d, h=%d)", ww, wh)
                                else:
                                    if self._click_cycle_phase in ("load", "shoot"):
                                        self.logger.warning("Wide search found small object %dx%d - continuing with grace period", ww, wh)
                                        det = DetectionResult(bbox=None, confidence=0.0)
                                    else:
                                        self._release_lock_on(f"Lost Santa (wide search too small {ww}x{wh})")
                            else:
                                if self._click_cycle_phase in ("load", "shoot"):
                                    self.logger.warning("Tracker failed - wide search failed - continuing with grace period during %s phase", self._click_cycle_phase)
                                    det = DetectionResult(bbox=None, confidence=0.0)
                                else:
                                    self._release_lock_on("Lost Santa (tracker failed, wide search failed)")
                else:
                    self.state = MacroState.DETECTING
                    self.logger.debug("SEARCHING for Santa")
                    
                    if self.det_mode == "template":
                        try:
                            det = self._match_templates(frame_gray)
                        except Exception as e:
                            self.logger.error("Template matching error: %s", e)
                            det = DetectionResult(bbox=None, confidence=0.0)
                    elif self.det_mode == "motion":
                        try:
                            color_det = self._detect_motion_color(frame_bgr)
                            if color_det is not None:
                                self.logger.info("Found red sleigh color detection, using it (conf=%.2f)", color_det.confidence)
                                det = color_det
                            else:
                                det = self._detect_motion(frame_gray)
                                
                                if det.bbox is not None:
                                    _, _, w, h = det.bbox
                                    det_area = w * h
                                    max_santa_area = self.roi["width"] * self.roi["height"] * 0.15
                                    if det_area > max_santa_area:
                                        self.logger.info("Rejecting large motion blob (area=%.0f > max=%.0f)", det_area, max_santa_area)
                                        det = DetectionResult(bbox=None, confidence=0.0)
                        except Exception as e:
                            self.logger.error("Motion detection error: %s", e)
                            det = DetectionResult(bbox=None, confidence=0.0)
                    else:
                        try:
                            det_t = self._match_templates(frame_gray if len(frame_gray.shape) == 2 else frame_bgr)
                            if det_t.bbox is not None and det_t.confidence >= self.threshold:
                                det = det_t
                            else:
                                det = self._detect_motion(frame_gray if len(frame_gray.shape) == 2 else cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY))
                        except Exception as e:
                            self.logger.error("Hybrid detection error: %s", e)
                            det = DetectionResult(bbox=None, confidence=0.0)
                    
                    if det.bbox is not None and det.confidence > 0.5:
                        if not self._locked_on_santa:
                            if self._initiate_lock_on(det.bbox):
                                self._init_shoot_tracker(frame_bgr, det.bbox)
                                self._init_shoot_template(frame_bgr, det.bbox)
                                self._shoot_ref_bbox = det.bbox
                                self.logger.info("Santa detected and locked on!")
                            else:
                                self.logger.debug("Lock-on validation failed, continuing with normal tracking")
                
                self._ema_conf = self._ema(self._ema_conf, det.confidence, self.ema_alpha)
                
                if self.learning_enabled and det.bbox is not None:
                    self._learning_detections.append({
                        "ts": time.time(),
                        "conf": det.confidence,
                        "bbox": det.bbox,
                        "threshold": self.threshold
                    })
                    
                    if self.learning_save_samples and det.confidence > 0.5:
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        path = os.path.join(self.learning_sample_dir, f"detect_{ts}_{det.confidence:.2f}.png")
                        cv2.imwrite(path, frame_bgr)
                    
                    if self.learning_auto_adjust and len(self._learning_detections) > 50:
                        recent = [d["conf"] for d in self._learning_detections[-50:]]
                        avg_conf = sum(recent) / len(recent)
                        if avg_conf > self.threshold + 0.1:
                            self.threshold = min(0.85, self.threshold + 0.02)
                            self.logger.info("Learning: threshold increased to %.2f", self.threshold)
                        elif avg_conf < self.threshold - 0.15:
                            self.threshold = max(0.45, self.threshold - 0.02)
                            self.logger.info("Learning: threshold decreased to %.2f", self.threshold)
                        self._learning_detections = self._learning_detections[-50:]
                
                aim = None
                
                self.logger.info("FRAME: phase=%s locked=%s det.bbox=%s conf=%.2f", 
                                self._click_cycle_phase, self._locked_on_santa, det.bbox, det.confidence)
                
                if det.bbox is not None:
                    center = self._aim_point(det.bbox)
                    self._ema_center = self._ema_pt(self._ema_center, center, self.ema_alpha)
                    aim = (int(self._ema_center[0]), int(self._ema_center[1]))
                    self._last_valid_bbox = det.bbox
                    self._last_detection_ts = time.time()
                    
                    if self._click_cycle_phase == "load" and self._click_cycle_start_ts is None:
                        screen_center_x = self.monitor["left"] + self.monitor["width"] // 2
                        screen_center_y = self.monitor["top"] + self.monitor["height"] // 2
                        
                        deadzone_w = int(self.monitor["width"] * 0.3)
                        deadzone_h = int(self.monitor["height"] * 0.3)
                        
                        dist_from_center_x = abs(aim[0] - screen_center_x)
                        dist_from_center_y = abs(aim[1] - screen_center_y)
                        
                        if dist_from_center_x < deadzone_w // 2 and dist_from_center_y < deadzone_h // 2:
                            self.logger.warning("REJECTING START: Target in center deadzone (%.1f, %.1f from center) - likely particles!", 
                                              dist_from_center_x, dist_from_center_y)
                            det = DetectionResult(bbox=None, confidence=0.0)
                            aim = None
                            self._santa_confirm_start_ts = None
                    
                    if aim and self._locked_on_santa:
                        self.logger.info("LOCKED AIM: bbox=%s -> aim=%s", det.bbox, aim)
                    elif aim:
                        self.logger.info("AIM: bbox=%s -> aim=%s", det.bbox, aim)
                
                elif self._click_cycle_phase == "shoot" and self._last_valid_bbox is not None:
                    last_center = self._aim_point(self._last_valid_bbox)
                    
                    if len(self._santa_bbox_history) >= 2:
                        prev_bbox = self._santa_bbox_history[-2]
                        curr_bbox = self._santa_bbox_history[-1]
                        prev_center = self._aim_point(prev_bbox)
                        curr_center = self._aim_point(curr_bbox)
                        
                        vx = (curr_center[0] - prev_center[0]) * 2.0
                        vy = (curr_center[1] - prev_center[1]) * 2.0
                        
                        pred_x = curr_center[0] + vx
                        pred_y = curr_center[1] + vy
                        aim = (int(pred_x), int(pred_y))
                        self.logger.debug("SHOOT w/ PREDICTION: center=%s velocity=(%.1f,%.1f) pred=%s", 
                                        curr_center, vx, vy, aim)
                    else:
                        aim = last_center
                        self.logger.debug("SHOOT: aim=%s", aim)
                
                else:
                    self.logger.info("NO AIM: det.bbox=%s locked=%s phase=%s", det.bbox, self._locked_on_santa, self._click_cycle_phase)

                if aim and det.bbox is not None:
                    cur = pyautogui.position()
                    self.logger.info("AIM: det_bbox=%s calculated_aim=%s cursor_before=%s", det.bbox, aim, (cur.x, cur.y))
                    self._move_mouse_towards(aim)
                    cur_after = pyautogui.position()
                    self.logger.info("AIM: cursor_after=%s", (cur_after.x, cur_after.y))
                    self._push_movement(aim)

                    if self.clicks_enabled:
                        moving_ok = self._is_moving_naturally()
                        
                        if self.click_skip_movement_validation:
                            moving_ok = True
                            self.logger.debug("Movement validation SKIPPED (debug mode)")

                        if self._click_cycle_start_ts is None and det.bbox is not None:
                            if self._santa_confirm_start_ts is None:
                                self._santa_confirm_start_ts = time.time()
                                self.logger.info("SANTA DETECTION: Starting confirmation timer")
                            
                            confirm_elapsed = time.time() - self._santa_confirm_start_ts
                            if confirm_elapsed >= self._santa_confirm_duration:
                                self._click_cycle_start_ts = time.time()
                                self._click_cycle_phase = "load"
                                self.logger.info("CLICK CYCLE START: phase=load after %.1fs confirmation, bbox=%s", confirm_elapsed, det.bbox)
                            else:
                                self.logger.debug("Confirming Santa: %.1f/%.1fs", confirm_elapsed, self._santa_confirm_duration)
                        elif det.bbox is None:
                            if self._santa_confirm_start_ts is not None:
                                self.logger.debug("Lost Santa during confirmation - resetting")
                                self._santa_confirm_start_ts = None

                        phase_elapsed = 0.0
                        if self._click_cycle_start_ts is not None:
                            phase_elapsed = (time.time() - self._click_cycle_start_ts) * 1000.0

                        if self._click_cycle_phase == "cooldown" and self._click_cycle_start_ts is not None and phase_elapsed >= self.click_cooldown_ms:
                            self._click_cycle_phase = "cooldown"
                            self._click_cycle_start_ts = None
                            self.logger.info("PHASE: cooldown complete - resetting to detect new Santa")
                        elif self._click_cycle_phase == "load" and phase_elapsed >= self.click_load_ms:
                            if self._last_valid_bbox is not None:
                                self._click_cycle_phase = "shoot"
                                self._click_cycle_start_ts = time.time()
                                phase_elapsed = 0
                                self._low_conf_start_ts = None
                                if self._locked_on_santa:
                                    self.logger.info("PHASE: load->shoot (LOCKED ON)")
                                else:
                                    self.logger.info("PHASE: load->shoot (TRACKING)")
                            else:
                                self.logger.debug("Staying in LOAD phase - no valid target yet")
                        elif self._click_cycle_phase == "shoot" and phase_elapsed >= self.click_shoot_ms:
                            if self._mouse_down:
                                self._click_up()
                            self._click_cycle_phase = "cooldown"
                            self._click_cycle_start_ts = time.time()
                            phase_elapsed = 0
                            self._locked_aim_point = None
                            self._last_e_press_ts = None
                            self.logger.info("PHASE: shoot->cooldown (STAYING LOCKED for next cycle)")

                        cycles_active = 0.0
                        if self._click_cycle_start_ts is not None:
                            cycles_active = time.time() - self._click_cycle_start_ts
                        
                        if self.click_always_spam and self._click_cycle_phase == "shoot":
                            allow_click = True
                            self.logger.debug("Click gating: spam_mode=True -> allow_click=True")
                        else:
                            allow_click = moving_ok or (cycles_active < 0.5)
                            self.logger.debug("Click gating: moving_ok=%s cycles_active=%.2fs -> allow_click=%s", moving_ok, cycles_active, allow_click)
                        
                        if self._click_cycle_phase in ("load", "shoot") and allow_click:
                            if not self._mouse_down:
                                self._click_down()
                                self.logger.info("CLICK DOWN: phase=%s (spam_mode=%s)", self._click_cycle_phase, self.click_always_spam and self._click_cycle_phase == "shoot")
                        else:
                            if self._mouse_down:
                                self._click_up()
                                self.logger.debug("CLICK UP: phase=%s", self._click_cycle_phase)

                    self.state = MacroState.CLICKING if self.clicks_enabled else MacroState.DETECTING
                
                elif det.bbox is None and self.clicks_enabled:
                    if self._last_detection_ts is None:
                        self._last_detection_ts = time.time()
                    
                    time_since_detection = time.time() - self._last_detection_ts
                    grace_period = 1.0
                    
                    if self._click_cycle_phase in ("load", "shoot") and time_since_detection < grace_period:
                        if self._last_valid_bbox is not None:
                            aim = self._aim_point(self._last_valid_bbox)
                            self._move_mouse_towards(aim)
                        self.logger.debug("Detection lost temporarily (%.1fs) - continuing in grace period", time_since_detection)
                    elif time_since_detection >= grace_period:
                        if self._mouse_down:
                            self._click_up()
                            self.logger.info("Detection lost for %.1fs - releasing mouse button", time_since_detection)
                        
                        if self._click_cycle_start_ts is not None:
                            self._click_cycle_start_ts = None
                            self._click_cycle_phase = "cooldown"
                            self._santa_confirm_start_ts = None
                            self.logger.info("Detection lost - RESETTING cycle, waiting for Santa")
                    
                    self.state = MacroState.DETECTING

                if self.clicks_enabled and self._click_cycle_phase == "cooldown" and self._click_cycle_start_ts is not None:
                    now = time.time()
                    phase_elapsed = (now - self._click_cycle_start_ts) * 1000.0
                    if self._last_e_press_ts is None or (now - self._last_e_press_ts) >= self._e_spam_interval:
                        kbd = keyboard.Controller()
                        kbd.press('e')
                        kbd.release('e')
                        self._last_e_press_ts = now
                        self.logger.info("COOLDOWN: Pressed E key (%.1fs into cooldown)", phase_elapsed / 1000.0)

                self._update_fps()
                if self.overlay_enabled:
                    self._draw_overlay(frame_bgr, det, aim, attack_mode="custom")
                self._save_dump_if_needed(frame_bgr, det)

                elapsed = time.time() - start_ts
                remain = max(0.0, self.tick_interval - elapsed)
                time.sleep(remain)
        finally:
            if self._mouse_down:
                self._click_up()
            try:
                with self.arrow_lock:
                    pydirectinput.keyUp('left')
                    pydirectinput.keyUp('right')
                    with self.keys_lock:
                        self.camera_keys_pressed.clear()
                    self.is_holding_arrow = False
                    self.current_arrow_key = None
                self.logger.info("[CLEANUP] Released all arrow keys")
            except Exception as e:
                self.logger.warning(f"Error releasing keys on exit: {e}")
            self.stop_hotkeys()
            # Only destroy overlay on shutdown, not on pause
            if self.state == MacroState.SHUTDOWN:
                try:
                    self._destroy_overlay_window()
                except Exception:
                    pass
            self.logger.info("Macro loop exited.")
