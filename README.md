[![Discord](https://img.shields.io/badge/Discord-Join%20Server-7289da?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/unPZxXAtfb)

# SantaMacro - Grand Piece Online Santa Event Automation

Automated Santa tracking and combat system for Grand Piece Online using YOLOv8 computer vision.

## Core Features

- **Santa Detection**: Real-time Santa tracking using YOLOv8 model (Model.pt)
- **Computer Vision**: Advanced object detection with configurable confidence thresholds
- **Custom Attack Recording**: Record and replay your own attack combos
- **Discord Webhooks**: Get notifications when Santa is detected, attacks happen, etc.
- **Multiple Attack Modes**: Custom sequences, Megapow, or Cyborg modes
- **Live Overlay**: Real-time detection overlay with settings access

## How It Works

1. **YOLOv8 Detection**: Uses Model.pt to detect Santa in real-time screen captures
2. **Automated Tracking**: Continuously scans for Santa with configurable detection confidence
3. **Smart Combat**: Executes attack sequences when Santa is detected
4. **Notification System**: Sends Discord alerts for key events (detection, attacks, session stats)

## Quick Start

1. Ensure you have **Model.pt** in the root folder
2. Run `install.bat` to install dependencies
3. Launch with `run.bat`
4. Click the settings button in the overlay to configure detection thresholds
5. Record your attack sequence or use built-in modes
6. Press F1 to start Santa hunting

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

- **Python 3.12 or 3.13** (3.14+ not supported due to PyTorch compatibility)
- **Windows** (uses Windows-specific libraries)
- **Model.pt file** - YOLOv8 detection model (required for Santa detection)
- **GPU recommended** for faster YOLO inference

## Installation

1. Install Python 3.12/3.13 with "Add to PATH" checked
2. Download and extract SantaMacro
3. **Place Model.pt in the root folder** (same directory as run.bat)
4. Run `install.bat` to install dependencies
5. Launch with `run.bat`

## Detection Configuration

The YOLO model uses these key settings in config.json:

- **Detection threshold**: Confidence level for Santa detection (0.15-0.25 recommended)
- **Screen region**: Area to scan for Santa
- **Attack delay**: Time between detection and attack execution

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

**"Model.pt not found"**: Ensure Model.pt is in the root directory (same folder as run.bat)

**No Santa detection**:

- Verify Model.pt is a valid YOLOv8 model
- Adjust detection threshold in settings (try 0.15-0.25)
- Check if Santa is visible on screen

**Settings won't open**: Run `install.bat` to install missing packages

**Recording doesn't work**: Press F3 while the settings window is open

**Webhook failed**: Check your Discord webhook URL is correct

**Poor performance**: Consider using GPU acceleration for YOLO inference

## License

Open source project for educational purposes. Use responsibly and in accordance with game terms of service.
