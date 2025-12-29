import os
import time
import argparse
import json
import cv2
import numpy as np
from mss import mss
from pynput import keyboard


def main():
    parser = argparse.ArgumentParser(description="Interactive template capture tool - Press SPACE to capture, ESC to exit")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"))
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    
    sct = mss()
    monitor = sct.monitors[cfg["capture"]["monitor_index"]]
    frac = cfg["capture"]["roi_fraction"]
    roi = {
        "left": int(monitor["left"] + frac["left"] * monitor["width"]),
        "top": int(monitor["top"] + frac["top"] * monitor["height"]),
        "width": int(frac["width"] * monitor["width"]),
        "height": int(frac["height"] * monitor["height"]),
    }
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    os.makedirs(out_dir, exist_ok=True)
    
    print("=" * 60)
    print("🎯 SANTA TEMPLATE CAPTURE TOOL")
    print("=" * 60)
    print("Instructions:")
    print("  1. Position Santa/sleigh in the capture region")
    print("  2. Press SPACE to capture a template")
    print("  3. Press ESC to exit")
    print()
    print(f"📁 Templates will be saved to: {out_dir}")
    print(f"🎯 Capture region: {roi['width']}x{roi['height']} at ({roi['left']}, {roi['top']})")
    print()
    print("Ready! Press SPACE when Santa appears...")
    print("=" * 60)
    
    capture_count = 0
    selecting_roi = False
    selection_start = None
    selection_end = None
    current_frame = None
    
    def on_press(key):
        nonlocal capture_count, selecting_roi, selection_start, current_frame
        try:
            if key == keyboard.Key.space:
                # Capture full ROI
                shot = sct.grab(roi)
                frame = np.array(shot)
                bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                ts = time.strftime("%Y%m%d_%H%M%S")
                count_str = f"{capture_count+1:03d}"
                path = os.path.join(out_dir, f"santa_{ts}_{count_str}.png")
                cv2.imwrite(path, bgr)
                capture_count += 1
                print(f"✅ Captured template #{capture_count}: {os.path.basename(path)}")
                
            elif key == keyboard.Key.esc:
                print(f"\\n🎉 Capture complete! Saved {capture_count} templates to {out_dir}")
                return False
        except AttributeError:
            pass
    
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    
    # Show live preview
    cv2.namedWindow("Santa Capture Preview", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Santa Capture Preview", 800, 600)
    
    try:
        while listener.is_alive():
            shot = sct.grab(roi)
            frame = np.array(shot)
            bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            current_frame = bgr.copy()
            
            # Add overlay text
            overlay = bgr.copy()
            cv2.putText(overlay, "Press SPACE to capture | ESC to exit", (20, 40), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(overlay, f"Templates captured: {capture_count}", (20, 80), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            # Draw crosshair at center
            h, w = overlay.shape[:2]
            cx, cy = w // 2, h // 2
            cv2.line(overlay, (cx - 30, cy), (cx + 30, cy), (0, 255, 255), 2)
            cv2.line(overlay, (cx, cy - 30), (cx, cy + 30), (0, 255, 255), 2)
            cv2.circle(overlay, (cx, cy), 5, (0, 0, 255), -1)
            
            cv2.imshow("Santa Capture Preview", overlay)
            
            if cv2.waitKey(100) & 0xFF == 27:  # ESC
                break
            
            time.sleep(0.05)
    finally:
        cv2.destroyAllWindows()
        listener.stop()


if __name__ == "__main__":
    main()
