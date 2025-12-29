[![Discord](https://img.shields.io/badge/Discord-Join%20Server-7289da?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/unPZxXAtfb)

# 🎅 SantaMacro - Grand Piece Online Santa Event Automation

**An open-source, safe, and powerful automation tool for Grand Piece Online Santa event**

---

## 🎯 What is Santa Macro?

Santa Macro is a **fully open-source** automation tool designed for Grand Piece Online Santa event. Unlike sketchy closed-source macros that get flagged as viruses, SantaMacro is :

- ✅ **Fully open source** - Verify every line of code yourself
- ✅ **No viruses** - Clean, transparent, and safe
- ✅ **AI-powered** - Uses YOLOv8 neural network for accurate Santa detection
- ✅ **Smart tracking** - Intelligent camera control and cursor positioning
- ✅ **Community-driven** - Open for contributions and improvements

**🛡️ Concerned about safety?** All code is visible and verifiable. No hidden executables, no obfuscation, no sketchy behavior.

---

## ✨ Key Features

### 🤖 AI-Powered Detection

- **YOLOv8 Neural Network** - State-of-the-art object detection for accurate Santa tracking
- **Real-time Tracking** - Follows Santa's movement with smooth camera control
- **Grace Period System** - Maintains lock during brief detection losses (30 frames)
- **Velocity Prediction** - Leads moving targets for accurate cursor placement

### 🎮 Smart Automation

- **3-Stage Attack System** - LOAD (1s) → FIRE (5s) → COOLDOWN (5.2s)
- **Intelligent Camera Control** - Automatic left/right rotation to find Santa
- **Cursor Positioning** - Precise aiming with Roblox-compatible mouse movement
- **E Spam During Cooldown** - Automatic loot collection
- **Search & Recovery** - Automatically searches for lost targets

### 🖥️ Modern Interface

- **Clean Qt-Based UI** - Professional status bar with minimal design
- **Real-time Detection Preview** - Visual feedback of what the bot sees
- **Live Status Updates** - Track detection confidence and attack phases
- **Collapsible Windows** - Stays out of your way while active

---

## 📦 Installation

### ⚠️ Python Version Requirement

**IMPORTANT**: This application requires **Python 3.12 or 3.13**.

- ❌ **Python 3.14+ is NOT supported** due to YOLOv8/PyTorch compatibility
- ✅ **Recommended**: Python 3.13.0 (most stable)
- ✅ **Alternative**: Python 3.12.7

**Download Links:**

- [Python 3.13.0](https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe) (Recommended)
- [Python 3.12.7](https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe) (Alternative)

### 🚀 Easy Installation (Recommended)

1. **Install Python 3.12 or 3.13** (see links above)
   - ⚠️ **Check "Add Python to PATH" during installation!**
2. **Download SantaMacro**

   - Download as ZIP and extract to a folder

3. **Run the installer**

   ```bash
   Double-click install.bat
   ```

   This will:

   - Create a virtual environment
   - Install all dependencies (PyTorch, YOLOv8, PySide6, etc.)
   - Verify everything works

4. **Launch the application**
   - **Silent mode**: Double-click `run.bat` (no console, background)
   - **Dev mode**: Double-click `run_dev.bat` (with console logs)

### 🔧 Manual Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
# Run the application
python src/main.py
```

---

## 🎮 Quick Start Guide

### First Time Setup

1. **Install** - Run `install.bat` to set everything up
2. **Place Model** - Ensure `Model.pt` is in the root directory
3. **Launch Game** - Open Roblox and enter the Santa event
4. **Start Macro** - Press **F1** to begin tracking
5. **Emergency Stop** - Press **ESC** to exit immediately

### Hotkeys

- **F1** - Start/Stop tracking (toggle)
- **ESC** - Emergency stop and exit

**Note**: Hotkeys work globally without admin privileges

---

## 🎯 How It Works

### Detection System

1. **Screen Capture** - Captures a region of interest (ROI) from your screen
2. **YOLO Detection** - Neural network identifies Santa with confidence score
3. **Position Tracking** - Calculates Santa's center position and velocity
4. **Target Prediction** - Applies lead for moving targets

### Attack Sequence

```
IDLE → Detection → LOAD (1s) → FIRE (5s) → COOLDOWN (5.2s) → IDLE
         ↓                                        ↓
    Start Attack                            Spam E for Loot
```

**Attack Stages:**

- **LOAD** (1s): Mouse held down, camera adjusts
- **FIRE** (5s): Attack committed, camera frozen
- **COOLDOWN** (5.2s): Mouse released, spam E, camera frozen

---

## 🔧 Troubleshooting

### Installation Issues

**"Python not found"**

- Download Python 3.12/3.13 from links above
- Reinstall with "Add to PATH" checked

**"Python 3.14+ not supported"**

- Uninstall Python 3.14+
- Install Python 3.13 or 3.12 instead

**Package installation fails**

- Ensure you're using Python 3.12 or 3.13
- Try running `install.bat` as administrator
- Check internet connection

### Runtime Issues

**"Model.pt not found"**

- Ensure `Model.pt` is in the root SantaMacro folder
- Check `config.json` for correct path

**Santa not detected**

- Verify Model.pt is present and valid
- Adjust detection threshold in config.json (try 0.15-0.25)
- Ensure good lighting in game

**Cursor not moving in-game**

- Ensure Roblox window has focus
- Try restarting the macro
- Check if other programs are interfering

---

## 📁 Project Structure

```
SantaMacro/
├── src/
│   ├── main.py              # Application entry point
│   ├── macro.py             # Core detection and automation logic
│   ├── overlay_qt.py        # Qt-based UI overlay
│   └── __pycache__/         # Python cache
├── logs/                    # Log files directory
├── Model.pt                 # YOLOv8 trained model (REQUIRED)
├── config.json              # Configuration file
├── requirements.txt         # Python dependencies
├── install.bat              # Easy installation script
├── run.bat                  # Silent mode launcher
├── run_dev.bat              # Dev mode with console
└── README.md                # This file
```

---

## ❓ FAQ

**Q: Is this safe to use?**  
A: Yes! All code is open source and verifiable. No viruses, no hidden behavior.

**Q: Will I get banned?**  
A: Use at your own risk. This is a macro tool, not a hack.

**Q: Does it work on all games?**  
A: Designed specifically for Grand Piece Online Santa event. May work on similar games.

**Q: Can I train my own model?**  
A: Yes! Use YOLOv8 and train on Santa screenshots. Replace Model.pt.

---

## 📜 License

This project is open source. Feel free to use, modify, and distribute.

**Disclaimer**: This is for educational purposes. Use responsibly and at your own risk.

For motion-only detection, set `detection.mode` to `motion` in `config.json`.

## Config keys

- `capture.roi_fraction`: portion of the monitor to scan (top/left/width/height)
- `detection.threshold`: confidence to consider target locked
- `aiming.mouse_smooth_factor`: fraction of remaining distance per tick
- `aiming.max_click_duration_ms`: safety cap on click hold
- `loop.tick_hz`: control loop rate (20–30 recommended)
- `overlay.enabled`: toggle overlay window
- `hotkeys`: global hotkeys

## Safety

- External-only; no game memory hooks.
- `pyautogui.FAILSAFE` is enabled (move mouse to top-left corner to abort).
- Optional `safety.require_foreground` check can be extended if needed.

## Troubleshooting

- If no templates are found, macro will run but never detect.
- If overlay is black, verify ROI matches your camera framing.
- For DPI scaling issues, adjust `roi_fraction` and verify cursor clamping.
