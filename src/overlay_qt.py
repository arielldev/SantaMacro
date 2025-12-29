from __future__ import annotations
import sys
import os
from typing import Optional, Tuple
import numpy as np
import cv2
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QPen, QLinearGradient, QPainterPath
from PySide6.QtWidgets import QApplication, QLabel, QWidget


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
        
        # Load attack mode icons
        self.megapow_pixmap = None
        megapow_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images", "megapow.webp")
        if os.path.exists(megapow_path):
            try:
                self.megapow_pixmap = QPixmap(megapow_path)
            except Exception:
                pass
        
        # Current attack mode (default: megapow)
        self.current_attack_mode = "megapow"
        
        if status_bar_mode:
            # Compact status bar at top-center with attack modes
            screen = self.app.primaryScreen().geometry()
            bar_width = 480  # Increased width for better spacing
            bar_height = 85   # Increased height for better readability
            bar_x = (screen.width() - bar_width) // 2
            bar_y = 10
            
            self.widget = QWidget()
            flags = Qt.FramelessWindowHint | Qt.Tool
            if topmost:
                flags |= Qt.WindowStaysOnTopHint
            self.widget.setWindowFlags(flags)
            self.widget.setAttribute(Qt.WA_TranslucentBackground, True)
            self.widget.setGeometry(bar_x, bar_y, bar_width, bar_height)
            self.widget.setWindowTitle(self.title)
            self.label = QLabel(self.widget)
            self.label.setGeometry(0, 0, bar_width, bar_height)
            self.label.setAlignment(Qt.AlignCenter)
            
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

    def update(self, frame_bgr: np.ndarray, status_text: Optional[str] = None, det_bbox: Optional[Tuple[int, int, int, int]] = None, aim_point: Optional[Tuple[int, int]] = None, roi_offset: Tuple[int, int] = (0, 0), attack_mode: str = "megapow"):
        if self.status_bar_mode and status_text:
            # Enhanced modern status bar with attack modes on the side
            bar_width = 480
            bar_height = 85
            pixmap = QPixmap(bar_width, bar_height)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            self.current_attack_mode = attack_mode
            
            # Main background - flat top, rounded bottom only - SOLID COLOR (no gradient)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(65, 28, 24, 240))  # Solid brownish-red
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
            
            painter.setBrush(QColor(220, 60, 60, 220))  # Bright red accent
            painter.drawPath(bottom_path)
            
            # Draw logo
            logo_x = 15
            logo_y = (bar_height - 40) // 2
            if self.logo_pixmap:
                painter.drawPixmap(logo_x, logo_y, self.logo_pixmap)
                logo_x += 48
            
            # Title - RED themed
            painter.setFont(QFont("Segoe UI", 13, QFont.Bold))
            painter.setPen(QColor(255, 120, 120, 255))  # Light red/pink
            painter.drawText(QRect(logo_x, 15, 180, 25), Qt.AlignLeft | Qt.AlignVCenter, "Santa Macro")
            
            # --- ATTACK MODE BUTTONS (SQUARE) on the right side ---
            button_size = 55  # Bigger square buttons
            button_x = bar_width - button_size - 20
            button_y = (bar_height - button_size) // 2 - 2
            
            # Draw square button for Megapow - NO BORDER when inactive
            button_rect = QRectF(button_x, button_y, button_size, button_size)
            
            # Button fill (lighter red tone)
            painter.setBrush(QColor(140, 60, 50, 220))
            painter.setPen(Qt.NoPen)  # NO border by default
            painter.drawRect(button_rect)  # Square button, no rounded corners
            
            # White border ONLY if active
            if self.current_attack_mode == "megapow":
                painter.setPen(QPen(QColor(255, 255, 255, 255), 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(button_rect)  # Square border
            
            # Draw megapow icon CENTERED in square
            if self.megapow_pixmap:
                icon_size = 38  # Icon size
                scaled_icon = self.megapow_pixmap.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_x = int(button_x + (button_size - scaled_icon.width()) // 2)
                icon_y = int(button_y + (button_size - scaled_icon.height()) // 2)
                painter.drawPixmap(icon_x, icon_y, scaled_icon)
            
            # Parse status
            lines = status_text.split('\n') if status_text else []
            
            if len(lines) >= 1:
                status_line = lines[0]
                
                # Determine status - check in specific order to avoid substring matches
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
                    # Fallback
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
                    painter.setPen(QColor(170, 180, 200, 220))
                    detail_x = logo_x + 35 + len(status_text_display) * 9
                    painter.drawText(QRect(detail_x, 39, 150, 22), Qt.AlignLeft | Qt.AlignVCenter, f"• {state_detail}")
            
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
