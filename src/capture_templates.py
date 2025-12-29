import os
import time
import argparse
import json
import cv2
import numpy as np
from mss import mss


def main():
    parser = argparse.ArgumentParser(description="Capture ROI screenshots to build templates")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"))
    parser.add_argument("--count", type=int, default=10, help="Number of frames to capture")
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
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "captures")
    os.makedirs(out_dir, exist_ok=True)
    for i in range(args.count):
        shot = sct.grab(roi)
        frame = np.array(shot)
        bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(out_dir, f"roi_{ts}_{i:02d}.png")
        cv2.imwrite(path, bgr)
        time.sleep(0.1)
    print(f"Saved {args.count} ROI frames to {out_dir}")


if __name__ == "__main__":
    main()
