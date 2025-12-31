from __future__ import annotations
import sys
import os
from typing import Optional, Tuple
import numpy as np
import cv2
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QPen, QLinearGradient, QPainterPath, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget


class ClickableWidget(QWidget):
    """Widget that can detect mouse clicks on settings button"""
    def __init__(self):
        super().__init__()
        self.overlay = None
    
    def set_overlay(self, overlay):
        self.overlay = overlay
    
    def mousePressEvent(self, event: QMouseEvent):
        if self.overlay and event.button() == Qt.LeftButton:
            x, y = event.pos().x(), event.pos().y()
            print(f"Mouse click at ({x}, {y})")  # Debug output
            
            # Check if click is on settings button
            if self.overlay.settings_button_rect:
                rect = self.overlay.settings_button_rect
                print(f"Settings button rect: {rect}")  # Debug output
                if rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]:
                    print("Settings button clicked!")  # Debug output
                    if self.overlay.settings_callback:
                        print("Calling settings callback")  # Debug output
                        self.overlay.settings_callback()
                    else:
                        print("No settings callback set!")  # Debug output
                    self.raise_()  # Keep on top
                    self.activateWindow()
                    return
            else:
                print("No settings button rect set!")  # Debug output


class OverlayQt:
    def __init__(self, title: str, x: int, y: int, w: int, h: int, click_through: bool = True, topmost: bool = True, status_bar_mode: bool = False):
        self.title = title
        self.status_bar_mode = status_bar_mode
        self.app = QApplication.instance() or QApplication(sys.argv)
        
        # Load logo
        self.logo_pixmap = None
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images", "icon.webp")
        if os.path.exists(logo_path):
            try:
                self.logo_pixmap = QPixmap(logo_path).scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception:
                pass
        
        # Current attack mode and settings callback
        self.current_attack_mode = "custom"
        self.settings_callback = None
        
        if status_bar_mode:
            # Compact status bar at top-center with settings button
            screen = self.app.primaryScreen().geometry()
            bar_width = 400  # Reduced width
            bar_height = 70   
            bar_x = (screen.width() - bar_width) // 2
            bar_y = 10
            
            self.widget = ClickableWidget()
            self.widget.set_overlay(self)
            flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
            self.widget.setWindowFlags(flags)
            self.widget.setAttribute(Qt.WA_TranslucentBackground, True)
            # Remove the ShowWithoutActivating attribute so it can receive clicks
            # self.widget.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.widget.setGeometry(bar_x, bar_y, bar_width, bar_height)
            self.widget.setWindowTitle(self.title)
            self.label = QLabel(self.widget)
            self.label.setGeometry(0, 0, bar_width, bar_height)
            self.label.setAlignment(Qt.AlignCenter)
            
            # Store button position for click detection
            self.settings_button_rect = None
            
            # Detection overlay (full screen, transparent, click-through)
            self.detection_widget = QWidget()
            det_flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
            self.detection_widget.setWindowFlags(det_flags)
            self.detection_widget.setAttribute(Qt.WA_TranslucentBackground, True)
            self.detection_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.detection_widget.setGeometry(x, y, w, h)
            self.detection_label = QLabel(self.detection_widget)
            self.detection_label.setGeometry(0, 0, w, h)
            
            self.widget.show()
            self.detection_widget.show()
        else:
            # Original full overlay
            self.label = QLabel()
            flags = Qt.FramelessWindowHint | Qt.Tool
            if topmost:
                flags |= Qt.WindowStaysOnTopHint
            self.label.setWindowFlags(flags)
            self.label.setAttribute(Qt.WA_TranslucentBackground, True)
            if click_through:
                self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.label.setGeometry(x, y, w, h)
            self.label.setWindowTitle(self.title)
            self.label.show()
            self.widget = None
            self.detection_widget = None
    
    def set_settings_callback(self, callback):
        """Set the callback function for settings button"""
        self.settings_callback = callback
    
    def raise_to_top(self):
        """Ensure overlay stays on top"""
        if self.widget:
            self.widget.raise_()
            self.widget.activateWindow()
        if self.detection_widget:
            self.detection_widget.raise_()

    def update(self, frame_bgr: np.ndarray, status_text: Optional[str] = None, det_bbox: Optional[Tuple[int, int, int, int]] = None, aim_point: Optional[Tuple[int, int]] = None, roi_offset: Tuple[int, int] = (0, 0), attack_mode: str = "custom"):
        if self.status_bar_mode and status_text:
            # Clean status bar with settings button
            bar_width = 400
            bar_height = 70
            pixmap = QPixmap(bar_width, bar_height)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            self.current_attack_mode = attack_mode
            
            # Main background
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(65, 28, 24, 240))
            painter.drawRect(QRectF(0, 0, bar_width, bar_height - 4))
            
            # Red bottom border with rounded corners
            border_radius = 15
            bottom_path = QPainterPath()
            bottom_path.moveTo(0, bar_height - 4)
            bottom_path.lineTo(0, bar_height - border_radius)
            bottom_path.arcTo(QRectF(0, bar_height - border_radius * 2, border_radius * 2, border_radius * 2), 180, -90)
            bottom_path.lineTo(bar_width - border_radius, bar_height)
            bottom_path.arcTo(QRectF(bar_width - border_radius * 2, bar_height - border_radius * 2, border_radius * 2, border_radius * 2), -90, -90)
            bottom_path.lineTo(bar_width, bar_height - 4)
            bottom_path.closeSubpath()
            
            painter.setBrush(QColor(220, 60, 60, 220))
            painter.drawPath(bottom_path)
            
            # Draw logo
            logo_x = 15
            logo_y = (bar_height - 40) // 2
            if self.logo_pixmap:
                painter.drawPixmap(logo_x, logo_y, self.logo_pixmap)
                logo_x += 48
            
            # Title
            painter.setFont(QFont("Segoe UI", 13, QFont.Bold))
            painter.setPen(QColor(255, 120, 120, 255))
            painter.drawText(QRect(logo_x, 15, 180, 25), Qt.AlignLeft | Qt.AlignVCenter, "Santa Macro")
            
            # Settings button on the right
            button_size = 50
            button_y = (bar_height - button_size) // 2 - 2
            settings_button_x = bar_width - button_size - 20
            settings_button_rect = QRectF(settings_button_x, button_y, button_size, button_size)
            self.settings_button_rect = (int(settings_button_x), int(button_y), button_size, button_size)
            
            # Draw settings button
            painter.setBrush(QColor(140, 60, 50, 220))
            painter.setPen(Qt.NoPen)
            painter.drawRect(settings_button_rect)
            
            # Settings icon (gear)
            painter.setPen(QColor(255, 255, 255, 255))
            painter.setFont(QFont("Segoe UI", 20, QFont.Bold))
            painter.drawText(settings_button_rect, Qt.AlignCenter, "⚙")
            
            # Parse status
            lines = status_text.split('\n') if status_text else []
            
            if len(lines) >= 1:
                status_line = lines[0]
                
                # Determine status
                if "PAUSED" in status_line:
                    status_color = QColor(255, 193, 7)
                    status_emoji = "❙❙"
                    status_text_display = "PAUSED"
                elif "INACTIVE" in status_line:
                    status_color = QColor(255, 82, 82)
                    status_emoji = "●"
                    status_text_display = "INACTIVE"
                elif "ACTIVE" in status_line:
                    status_color = QColor(76, 217, 100)
                    status_emoji = "●"
                    status_text_display = "ACTIVE"
                else:
                    status_color = QColor(255, 82, 82)
                    status_emoji = "●"
                    status_text_display = "INACTIVE"
                
                # Extract state detail
                state_detail = ""
                if " - " in status_line:
                    parts = status_line.split(" - ")
                    if len(parts) > 1:
                        state_detail = parts[1]
                
                # Status indicator with glow
                painter.setFont(QFont("Segoe UI", 20, QFont.Bold))
                
                # Glow effect
                painter.setPen(QPen(QColor(status_color.red(), status_color.green(), status_color.blue(), 80), 8))
                painter.drawText(QRect(logo_x + 3, 39, 28, 28), Qt.AlignCenter, status_emoji)
                
                # Main indicator
                painter.setPen(status_color)
                painter.drawText(QRect(logo_x, 36, 28, 28), Qt.AlignCenter, status_emoji)
                
                # Status text
                painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
                painter.setPen(QColor(255, 255, 255, 255))
                painter.drawText(QRect(logo_x + 35, 36, 130, 28), Qt.AlignLeft | Qt.AlignVCenter, status_text_display)
                
                # State detail
                if state_detail:
                    painter.setFont(QFont("Segoe UI", 8))
                    painter.setPen(QColor(170, 180, 200, 200))
                    painter.drawText(QRect(logo_x + 35, 48, 200, 18), Qt.AlignLeft | Qt.AlignVCenter, f"• {state_detail}")
            
            painter.end()
            self.label.setPixmap(pixmap)
            
            # Detection overlay with enhanced visuals
            if det_bbox or aim_point:
                h, w = frame_bgr.shape[:2]
                det_img = np.zeros((h, w, 4), dtype=np.uint8)
                
                if det_bbox:
                    x, y, bw, bh = det_bbox
                    ox, oy = roi_offset
                    # Detection box in pure red - less bold
                    cv2.rectangle(det_img, (x - ox, y - oy), (x - ox + bw, y - oy + bh), (0, 0, 255), 2)
                    
                    # Corner accents - smaller and less intrusive
                    corner_len = min(12, bw // 6, bh // 6)  # Much smaller corners
                    corner_color = (255, 255, 255, 200)  # Slightly transparent white
                    # Top-left
                    cv2.line(det_img, (x - ox, y - oy), (x - ox + corner_len, y - oy), corner_color, 2)
                    cv2.line(det_img, (x - ox, y - oy), (x - ox, y - oy + corner_len), corner_color, 2)
                    # Top-right
                    cv2.line(det_img, (x - ox + bw, y - oy), (x - ox + bw - corner_len, y - oy), corner_color, 2)
                    cv2.line(det_img, (x - ox + bw, y - oy), (x - ox + bw, y - oy + corner_len), corner_color, 2)
                    # Bottom-left
                    cv2.line(det_img, (x - ox, y - oy + bh), (x - ox + corner_len, y - oy + bh), corner_color, 2)
                    cv2.line(det_img, (x - ox, y - oy + bh), (x - ox, y - oy + bh - corner_len), corner_color, 2)
                    # Bottom-right
                    cv2.line(det_img, (x - ox + bw, y - oy + bh), (x - ox + bw - corner_len, y - oy + bh), corner_color, 2)
                    cv2.line(det_img, (x - ox + bw, y - oy + bh), (x - ox + bw, y - oy + bh - corner_len), corner_color, 2)
                
                if aim_point:
                    ax, ay = aim_point
                    ox, oy = roi_offset
                    # Enhanced crosshair with pure red center
                    cv2.circle(det_img, (ax - ox, ay - oy), 5, (0, 0, 255, 255), -1)  # Pure red
                    cv2.circle(det_img, (ax - ox, ay - oy), 13, (255, 255, 255, 180), 2)  # Slightly transparent ring
                    # Crosshair lines - thinner and softer
                    cv2.line(det_img, (ax - ox - 20, ay - oy), (ax - ox - 9, ay - oy), (255, 255, 255, 180), 2)
                    cv2.line(det_img, (ax - ox + 9, ay - oy), (ax - ox + 20, ay - oy), (255, 255, 255, 180), 2)
                    cv2.line(det_img, (ax - ox, ay - oy - 20), (ax - ox, ay - oy - 9), (255, 255, 255, 180), 2)
                    cv2.line(det_img, (ax - ox, ay - oy + 9), (ax - ox, ay - oy + 20), (255, 255, 255, 180), 2)
                
                qimg = QImage(det_img.data, w, h, 4 * w, QImage.Format_RGBA8888)
                self.detection_label.setPixmap(QPixmap.fromImage(qimg))
            else:
                self.detection_label.clear()
        else:
            # Original full overlay mode
            h, w = frame_bgr.shape[:2]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            self.label.setPixmap(pix)
        
        # Periodically raise to ensure always on top
        if self.widget:
            self.widget.raise_()
        if self.detection_widget:
            self.detection_widget.raise_()
        
        self.app.processEvents()

    def close(self):
        try:
            if self.widget:
                self.widget.close()
            if self.detection_widget:
                self.detection_widget.close()
            if hasattr(self, 'label') and not self.widget:
                self.label.close()
        except Exception:
            pass
