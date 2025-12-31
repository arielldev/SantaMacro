# SantaMacro - Grand Piece Online Santa Event Bot

A simple automation tool for the Grand Piece Online Santa event. Records custom attack sequences and sends Discord notifications.

## Features

- **Custom Attack Recording**: Record your own attack combos with mouse and keyboard
- **Discord Webhooks**: Get notifications when Santa is found, attacks happen, etc.
- **Easy Setup**: Settings GUI accessible from the overlay
- **Multiple Attack Modes**: Custom sequences, Megapow, or Cyborg modes

## Quick Start

1. Run `install.bat` to install dependencies
2. Launch with `run.bat`
3. Click the settings button in the overlay to configure
4. Record your attack sequence
5. Press F1 to start hunting

## Controls

- **F1** - Start/Stop the macro
- **ESC** - Exit
- **Settings Button** - Click in overlay to open configuration

## Recording Attacks

1. Click settings button in overlay
2. Go to "Attack Settings" tab
3. Press F3 to start recording
4. Perform your attack sequence
5. Press F3 again to stop and save

## Discord Webhooks

1. Create a webhook in your Discord server
2. Copy the webhook URL
3. Paste it in Settings → Discord Webhooks
4. Choose which events to get notifications for

## Requirements

- Python 3.12 or 3.13 (3.14+ not supported)
- Windows (uses Windows-specific libraries)
- Model.pt file (YOLOv8 detection model)

## Installation

1. Install Python 3.12/3.13 with "Add to PATH" checked
2. Download and extract SantaMacro
3. Run `install.bat`
4. Launch with `run.bat`

## File Structure

```
SantaMacro/
├── src/                    # Source code
├── config.json            # Settings (auto-generated)
├── Model.pt              # Detection model (required)
├── install.bat           # Setup script
└── run.bat              # Launcher
```

## Troubleshooting

**Settings won't open**: Run `install.bat` to install missing packages

**No detection**: Make sure Model.pt is in the root folder

**Recording doesn't work**: Press F3 while the settings window is open

**Webhook failed**: Check your Discord webhook URL is correct

## License

Opevailable webhook events:\*\*

- Santa Detected/Lost
- Attack Started/Completed
- Macro Started/Stopped (with session stats)

---

## 🎮 Controls

### Hotkeys

- **F1** - Start/Stop tracking (toggle)
- **ESC** - Emergency stop and exit
- **⚙️ Settings Button** - Click in overlay to open settings

### Attack Modes

- **Custom Mode**: Uses your recorded attack sequence (when enabled)
- **Megapow Mode**: Traditional high-damage attack (5s duration)
- **Cyborg Mode**: Traditional sustained attack (15s duration)

---

## 📦 Installation

### ⚠️ Requirements

**Python Version**: 3.12 or 3.13 (3.14+ not supported due to PyTorch compatibility)

**Dependencies:**

```bash
pip install PySide6 numpy opencv-python mss pyautogui pydirectinput pynput requests ultralytics
```

### 🚀 Easy Installation

1. **Install Python 3.12/3.13** with "Add to PATH" checked
2. **Download SantaMacro** and extract to folder
3. **Run installer**: `install.bat`
4. **Launch**: `run.bat` or `run_dev.bat`

---

## 📁 File Structure

```
SantaMacro/
├── src/
│   ├── main.py              # Application entry point
│   ├── macro.py             # Core detection and automation logic
│   ├── overlay_qt.py        # Qt-based UI overlay with settings button
│   ├── settings_gui.py      # Settings configuration GUI
│   ├── webhook_manager.py   # Discord webhook system
│   └── action_system.py     # Custom attack recording/playback
├── config.json             # Configuration (auto-updated with new settings)
├── Model.pt               # YOLOv8 model (required)
├── install.bat            # Easy installation script
├── run.bat               # Silent mode launcher
└── run_dev.bat           # Dev mode with console
```

---

## 🔧 Troubleshooting

### New Features Issues

**"No custom attack sequence found"**

- Record a sequence in Settings → Attack Settings first
- Ensure "Enable Custom Attack Sequence" is checked

**"Webhook test failed"**

- Verify Discord webhook URL is correct
- Check internet connection and install `requests`: `pip install requests`

**"Settings GUI won't open"**

- Ensure all packages installed: run `install.bat`
- Try running from command line to see error messages

### Legacy Issues

**"Model.pt not found"**

- Ensure Model.pt is in root directory
- Download from original source if missing

**Detection not working**

- Original detection system still used
- Adjust threshold in config.json (0.15-0.25)
- Verify Model.pt is valid YOLOv8 model

---

## 🔄 Migration from Previous Versions

Your existing setup will work with minimal changes:

✅ **Automatic**: `config.json` is auto-updated with new settings  
✅ **Compatible**: Original attack modes (megapow/cyborg) still work  
✅ **Optional**: New features are opt-in via settings  
✅ **Improved**: Settings button added to overlay for easy access

**To use new features:**

1. Run `run.bat` or `run_dev.bat`
2. Click ⚙️ settings button in overlay
3. Configure custom attacks and/or webhooks
4. Save and restart macro

---

## ✨ What's Different

### Added

- ✅ Custom attack recording system
- ✅ Discord webhook notifications
- ✅ Settings GUI accessible from overlay
- ✅ Simple tkinter-based interface

### Improved

- 🔄 Easy access to settings via overlay button
- 🔄 Streamlined user experience
- 🔄 Better integration with existing workflow

---

## 📜 License & Disclaimer

Open source project for educational purposes. Use responsibly and in accordance with game terms of service.

**Safety**: All code is transparent and verifiable. No viruses, no hidden behavior.
