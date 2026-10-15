# ⚽ mBot Robot Football (Techno Exhibition)

[![Arduino](https://img.shields.io/badge/Platform-Arduino%20%7C%20Makeblock%20mCore-blue.svg)](https://www.arduino.cc/)
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.10%20%7C%203.11-yellow.svg)](https://www.python.org/)
[![MediaPipe](https://img.shields.io/badge/AI-Google%20MediaPipe%20HandLandmarker-orange.svg)](https://developers.google.com/mediapipe)
[![OpenCV](https://img.shields.io/badge/CV-OpenCV%20Computer%20Vision-green.svg)](https://opencv.org/)
[![Bluetooth](https://img.shields.io/badge/Wireless-Bluetooth%204.0%20SPP-brightgreen.svg)](https://www.makeblock.com/)

A complete, high-performance robotic soccer and teleoperation system built for the **Techno Exhibition**. The system combines an agile **Makeblock mBot** (equipped with dual DC drive motors, a high-speed servo kicking mechanism, RGB lighting, and an audio buzzer) with three flexible control layers:

1. **AI Gesture Control**: Touchless teleoperation using a standard laptop webcam and Google MediaPipe hand landmark tracking with a custom Neon HUD.
2. **Laptop Keyboard Teleoperation & Live Calibration**: Real-time keyboard driving with multi-key combos and live EEPROM tuning.
3. **Smartphone Gamepad Control**: Plug-and-play Bluetooth RC Car mobile app control for matches and exhibitions.

---

## 📑 Table of Contents

- [Architecture & Data Flow](#-architecture--data-flow)
- [Tech Stack](#-tech-stack)
- [Project Subsystems](#-project-subsystems)
  - [1. Robot Motor & Servo Control (`mbot_motor_control/`)](#1-robot-motor--servo-control-mbot_motor_control)
  - [2. AI Gesture Teleoperation (`gestures/`)](#2-ai-gesture-teleoperation-gestures)
  - [3. Wireless Bluetooth Communication (`communication/`)](#3-wireless-bluetooth-communication-communication)
  - [4. Dedicated Phone Controller (`mbot_phone_controller/`)](#4-dedicated-phone-controller-mbot_phone_controller)
  - [5. Kicker Assembly & Alignment (`kicker_test/`)](#5-kicker-assembly--alignment-kicker_test)
- [Communication Protocol Specification](#-communication-protocol-specification)
  - [Motion & Action Byte Protocol](#motion--action-byte-protocol)
  - [Live EEPROM Calibration Commands](#live-eeprom-calibration-commands)
- [Hardware Setup & Wiring](#-hardware-setup--wiring)
- [Local Setup & Installation](#-local-setup--installation)
  - [Step 1: Flash Arduino Firmware](#step-1-flash-arduino-firmware)
  - [Step 2: Pair Bluetooth on Windows](#step-2-pair-bluetooth-on-windows)
  - [Step 3: Setup Python Environment](#step-3-setup-python-environment)
- [How to Run](#-how-to-run)
  - [Mode A: Running AI Gesture Control](#mode-a-running-ai-gesture-control)
  - [Mode B: Running Laptop Keyboard Driving & Live Tuner](#mode-b-running-laptop-keyboard-driving--live-tuner)
  - [Mode C: Driving with Android Smartphone](#mode-c-driving-with-android-smartphone)
  - [Mode D: Calibrating the Servo Kicker Arm](#mode-d-calibrating-the-servo-kicker-arm)
- [Troubleshooting & Gotchas](#-troubleshooting--gotchas)

---

## 🏛️ Architecture & Data Flow

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                              INPUT LAYERS                              │
 ├────────────────────────┬────────────────────────┬──────────────────────┤
 │   Webcam + MediaPipe   │    Laptop Keyboard     │  Android Smartphone  │
 │   Two-Hand CV Tracking │   comm_test_tool.py    │   BT Car Controller  │
 └───────────┬────────────┴───────────┬────────────┴───────────┬──────────┘
             │                        │                        │
             ▼                        ▼                        ▼
     robot_bridge.py          mbot_bluetooth.py       Standard RC App
             │                        │                        │
             └────────────────────────┴────────────────────────┘
                                      │
                   [Bluetooth Serial SPP @ 115200 Baud]
                                      │
                                      ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │                   MAKEBLOCK mCORE (ATmega328P)                   │
    ├──────────────────────────────────────────────────────────────────┤
    │  • Command Decoder (w, s, a, d, q, e, z, c, k, j, v, x, etc.)    │
    │  • Acceleration Ramping & Trim Compensation                      │
    │  • EEPROM Calibration Storage                                    │
    │  • Voltage Sag & Brownout Protection Logic                       │
    └──────────────┬──────────────┬──────────────┬──────────────┬──────┘
                   │              │              │              │
                   ▼              ▼              ▼              ▼
              Left Motor     Right Motor    Kicker Servo    RGB LEDs &
                 (M1)           (M2)       (Port 4 / A0)    Buzzer
```

---

## 🛠️ Tech Stack

### 1. Embedded Firmware
- **Platform**: Arduino AVR on Makeblock mCore (Microchip ATmega328P @ 16 MHz).
- **Core Libraries**:
  - `MeMCore.h`: Makeblock Hardware Abstraction Layer for DC motors (`MeDCMotor`), onboard WS2812 LEDs (`MeRGBLed`), and buzzer (`MeBuzzer`).
  - `utility/Servo.h`: Hardware timer-based PWM servo driver.
  - `EEPROM.h`: Non-volatile parameter storage across power cycles.

### 2. Computer Vision & AI Subsystem
- **Runtime**: Python 3.9 – 3.11.
- **Machine Learning**: Google MediaPipe Tasks API (`mediapipe.tasks.python.vision.HandLandmarker`).
- **Landmark Model**: `hand_landmarker.task` (Float16, 21 3D hand joints, running in `VIDEO` tracking mode).
- **Vision & Graphics**: OpenCV (`opencv-python`), NumPy.
- **HUD System**: Custom vector HUD with procedural alpha blending, dynamic gauges, screen flashes, particle explosions (confetti & fireworks).

### 3. Desktop Communications & Teleoperation
- **Serial Driver**: `pyserial` (Bluetooth Serial Port Profile / Virtual COM Port).
- **Windows Integration**: `winreg` (Windows Registry inspection for Bluetooth device discovery and MAC address parsing).
- **Real-Time Input**: `keyboard` (low-level OS keyboard hook for hold-to-drive and multi-key chord detection).

---

## 📦 Project Subsystems

### 1. Robot Motor & Servo Control (`mbot_motor_control/`)
The core firmware (`mbot_motor_control.ino`) uploaded to the mBot.
- **Motion Primitives**:
  - Linear driving: Forward (`'w'`), Backward (`'s'`).
  - In-place pivot turns: Spin Left (`'a'`), Spin Right (`'d'`).
  - Smooth dynamic arcs: Forward-Left (`'q'`), Forward-Right (`'e'`), Backward-Left (`'z'`), Backward-Right (`'c'`).
  - Tactical turnaround: 180° spin (`'x'`) calibrated to exact milliseconds.
- **Smooth Speed Ramping**: Both motors smoothly ramp speeds in discrete steps (`RAMP_STEP = 15`, `RAMP_DELAY = 20ms`), preventing sudden battery voltage drops and wheel slippage.
- **Motor Trim Compensation**: Real-time steering balance adjustment (`motorTrim`) to correct mechanical differences between left and right DC motors.
- **Persistent EEPROM Storage**: Motor speeds, arc ratios, steering trim, 180° spin duration, and kick angle are stored in onboard EEPROM (using magic marker `0x4D42`).
- **Smart Kicking Engine**:
  - **Stationary Kick (`'k'`)**: Stops wheels, flashes yellow, swings servo 90° forward, snaps back to rest.
  - **Running Kick (`'j'`)**: Charges wheels forward into the ball *while* striking with the servo. LEDs are shut down during strike to eliminate power sag and prevent microcontroller brownouts.
- **Victory Celebration (`'v'`)**: 6-step musical victory fanfare (C5, E5, G5, C6) synchronized with side-to-side wiggle turns and multi-color RGB cycling.

### 2. AI Gesture Teleoperation (`gestures/`)
A touchless computer vision control system allowing anyone to pilot the robot using hand gestures in front of a laptop webcam.
- **Two-Hand Control Paradigm**:
  - **Left Hand (Drive)**:
    - Open palm facing camera $\rightarrow$ **Forward** (`'w'`)
    - Back of hand facing camera $\rightarrow$ **Backward** (`'s'`)
    - Fist / Hand out of frame $\rightarrow$ **Stop** (`' '`)
    - *Geometry Math*: Palm orientation is determined using the 2D cross product sign of $(\vec{v}_{\text{wrist}\to\text{index}} \times \vec{v}_{\text{wrist}\to\text{pinky}})$, ensuring detection works regardless of tilt or distance.
  - **Right Hand (Steer & Shoot)**:
    - Open hand tilted left/right ($\pm 15^\circ$ deadzone) $\rightarrow$ **Turn Left** / **Turn Right** (`'a'` / `'d'`).
    - Closed fist $\rightarrow$ **Shoot** (triggers stationary kick `'k'` or running kick `'j'`).
  - **Both Hands (Celebrate)**:
    - Rock-on sign ($\text{Index} + \text{Pinky}$ extended, middle + ring curled) on **both** hands $\rightarrow$ **Goal Victory Fanfare** (`'v'`).
- **Combo Resolution**: Driving forward while tilting right seamlessly sends the forward-right arc command (`'e'`).
- **Sci-Fi Neon HUD**: Scalable HUD displaying live link status, FPS, drive/steer indicators, tilt deadzone bar, kick reload gauge, and celebration animations.
- **Fail-Safe Bridge (`robot_bridge.py`)**: Sends 0.5s heartbeats, handles auto-reconnect, and immediately sends stop (`' '`) if hands leave the frame or the link drops.

### 3. Wireless Bluetooth Communication (`communication/`)
- **`mbot_bluetooth.py`**: A robust Python abstraction for Makeblock Bluetooth communication:
  - Scans Windows Registry (`BTHPORT`) to distinguish true Makeblock mBot outgoing serial ports from unassigned or incoming listening ports.
  - Provides a simple Python API (`bot.forward()`, `bot.kick()`, `bot.curve_left()`, `bot.stop()`).
  - Sends `#` calibration packets and manages serial connection timeouts.
- **`comm_test_tool.py`**: An administrative desktop control terminal:
  - Supports hold-to-drive keyboard teleoperation (`W`, `A`, `S`, `D`, `Q`, `E`, `Z`, `C`).
  - Multi-key chord detection (`W + K` = Running Kick, `W + A` = Curve Left).
  - Live parameter adjustment: `Ctrl` + `[+]` / `[-]` + Parameter Key to tune speeds, trim, and angles live.
  - `Ctrl + Enter` to commit calibration permanently to EEPROM.
- **`comm_usb_led_test/`**: Minimal test sketch to verify serial packets and onboard RGB LEDs without running DC motors.

### 4. Dedicated Phone Controller (`mbot_phone_controller/`)
- **Firmware (`mbot_phone_controller.ino`)**: Mapped to standard Android Bluetooth RC Gamepad apps (e.g. *BT Car Controller* by Andi.Co, *Connectino*, *Bluetronics*).
- **Features**:
  - Maps virtual buttons: `'F'`, `'B'`, `'L'`, `'R'`, `'G'`, `'H'`, `'I'`, `'J'`, `'S'`, `'D'`, `'Y'`, `'Z'`, `'0'`-`'9'`.
  - Continuous drive mode (does not time out while button is held).
  - Smart kicking (running kick when moving forward, stationary kick when stopped).
- **Desktop Companion (`calibrate_mbot.py`)**: Standalone Python tuning tool to calibrate EEPROM settings for phone driving mode.

### 5. Kicker Assembly & Alignment (`kicker_test/`)
- **Calibration Sketch (`kicker_test.ino`)**:
  - Enforces strict hardware safety boundaries ($[90^\circ, 180^\circ]$).
  - Locks the servo shaft at $180^\circ$ (Safe Rest) on boot so builders can physically attach the 3D printed kicker arm in the tucked-away position and screw in the horn safely.
  - Interactive test commands (`'k'` to kick, `'o'` to hold at $90^\circ$ strike position to verify ball contact height, `'p'` to retract).

---

## 📡 Communication Protocol Specification

All wireless serial communication runs at **115200 baud** (8 data bits, no parity, 1 stop bit).

### Motion & Action Byte Protocol

| ASCII Byte | Standard RC Code | Robot Action | Hardware Execution | LED Visual Indicator |
|:---:|:---:|---|---|---|
| `'w'` | `'F'` | Forward | Both motors forward at `forwardSpeed` | Dual Green |
| `'s'` | `'B'` | Backward | Both motors reverse at `backwardSpeed` | Dual Red |
| `'a'` | `'L'` | Spin Left | Left reverse, Right forward at `turnSpeed` | Left Blue, Right Off |
| `'d'` | `'R'` | Spin Right | Left forward, Right reverse at `turnSpeed` | Right Blue, Left Off |
| `'q'` | `'G'` | Forward-Left Arc | Inner wheel slower, Outer wheel faster | Cyan Left |
| `'e'` | `'H'` / `'I'` | Forward-Right Arc | Inner wheel slower, Outer wheel faster | Cyan Right |
| `'z'` | `'I'` / `'H'` | Backward-Left Arc | Reverse arc to the left | Dim Red-Magenta Left |
| `'c'` | `'J'` | Backward-Right Arc | Reverse arc to the right | Dim Red-Magenta Right |
| `' '` | `'S'` / `'D'` | Immediate Stop | Both motors 0, active ramp down | All LEDs Off |
| `'k'` | `'X'` / `'V'` | Stationary Kick | Robot stops $\rightarrow$ Servo strikes $90^\circ$ $\rightarrow$ retracts | Yellow Flash + Chirp |
| `'j'` | — | **Running Kick** | **Wheels charge forward** $\rightarrow$ Servo strikes | **LEDs OFF (Anti-brownout)** |
| `'v'` | `'Z'` / `'C'` | Victory Celebration | Side-to-side wiggle + 6-step buzzer melody | Rainbow Cycling |
| `'x'` | — | 180° Turnaround | Fast in-place spin for `rotate180Ms` | Dual Amber |
| `'+'` | — | Increase Speed Cap | Global speed ceiling $+15$ | High Pitch Beep |
| `'-'` | — | Decrease Speed Cap | Global speed ceiling $-15$ | Low Pitch Beep |

### Live EEPROM Calibration Commands

Send these commands from a serial terminal or Python script:

| Command | Action | Description |
|---|---|---|
| `#?` | Query Status | Prints full calibration table and EEPROM state |
| `#W+` / `#W-` | Adjust Forward Speed | Increments / decrements forward speed by 10 |
| `#S+` / `#S-` | Adjust Backward Speed | Increments / decrements backward speed by 10 |
| `#A+` / `#A-` | Adjust Turn Speed | Increments / decrements pivot speed by 5 |
| `#T+` / `#T-` | Adjust Steering Trim | Corrects pull (+ corrects left pull, - corrects right pull) |
| `#Q+` / `#Q-` | Adjust Arc Curve Ratio | Tightens or widens arc turns (10% to 95%) |
| `#K+` / `#K-` | Adjust Kick Angle | Fine-tunes servo front strike angle ($90^\circ \text{--} 180^\circ$) |
| `#X+` / `#X-` | Adjust 180° Spin Time | Increases/decreases turnaround duration in ms |
| `#SAVE` | Save to EEPROM | Permanently writes configuration to ATmega328P EEPROM |
| `#RESET` | Reset to Defaults | Restores original factory settings |

---

## 🔌 Hardware Setup & Wiring

| Component | mCore Port / Pin | Details |
|---|---|---|
| **Left DC Motor** | **Port M1** | Drive wheel (Left) |
| **Right DC Motor** | **Port M2** | Drive wheel (Right) |
| **Kicker Servo** | **Port 4 (Digital Pin 9 / A0)** | High-speed ball striking mechanism |
| **Bluetooth Module** | **Onboard Header** | Makeblock Bluetooth 4.0 Module (UART TX/RX) |
| **RGB LEDs** | **Onboard (Pin 13)** | 2x WS2812 Smart LEDs |
| **Buzzer** | **Onboard (Pin 8)** | Piezo audio buzzer |
| **Power Supply** | **Battery Jack** | 3.7V LiPo or 4x AA Battery Pack |

> [!CAUTION]
> **CRITICAL HARDWARE CONFLICT**:
> The ATmega328P shares its hardware UART pins (Pin 0 RX / Pin 1 TX) between the USB port and the Bluetooth module.
> - **When uploading code via USB**: You **MUST UNPLUG** the Bluetooth module from the mCore board. Otherwise, flashing will fail with `avrdude: stk500_getsync()`.
> - **When driving via Bluetooth**: You **MUST UNPLUG** the USB cable from the PC.

---

## 🚀 Local Setup & Installation

### Prerequisites
1. **Operating System**: Windows 10 / 11 (recommended for native Bluetooth registry discovery and keyboard hooks).
2. **Python**: Python 3.9, 3.10, or 3.11 installed and added to `PATH`.
3. **Arduino IDE**: Version 1.8.x or 2.x installed.
4. **Makeblock Library**: Install `Makeblock` library in Arduino IDE (**Sketch** $\rightarrow$ **Include Library** $\rightarrow$ **Manage Libraries** $\rightarrow$ Search for `MakeBlockDrive` or `Makeblock`).

---

### Step 1: Flash Arduino Firmware

1. **Unplug the Bluetooth module** from the mBot.
2. Connect the mBot to your PC using the USB cable.
3. Open `mbot_motor_control/mbot_motor_control.ino` (or `mbot_phone_controller/mbot_phone_controller.ino` if using only a smartphone) in Arduino IDE.
4. Select board and port:
   - **Board**: `Arduino Uno`
   - **Port**: Select the COM port corresponding to the USB cable (e.g. `COM3`).
5. Click **Upload**. Wait for `Done uploading`.
6. **Disconnect the USB cable** and **plug the Bluetooth module back into the mBot**.

---

### Step 2: Pair Bluetooth on Windows

1. Turn on the mBot battery power switch. The blue LED on the Bluetooth module will blink.
2. On your Windows PC, go to **Settings** $\rightarrow$ **Bluetooth & devices** $\rightarrow$ **Add device**.
3. Select **Bluetooth**, find **Makeblock** or **mBot**, and click to pair (default PIN is `0000` if prompted).
4. Once paired, Windows creates outgoing and incoming virtual COM ports.

---

### Step 3: Setup Python Environment

Open PowerShell or Command Prompt in the repository root:

```powershell
# Create a virtual environment (optional but recommended)
python -m venv venv
.\venv\Scripts\activate

# Install all required dependencies
pip install pyserial keyboard opencv-python mediapipe numpy
```

---

## 🎮 How to Run

### Mode A: Running AI Gesture Control
Control the robot hands-free via your laptop webcam:

```powershell
python gestures/gesture_control.py
```

- The script auto-downloads `hand_landmarker.task` (~8MB) on first run if missing.
- It automatically searches for your paired mBot and connects.
- **Controls**:
  - **Left Hand**: Show Palm $\rightarrow$ Move Forward | Show Back of Hand $\rightarrow$ Reverse | Fist / Away $\rightarrow$ Stop.
  - **Right Hand**: Tilt Hand $\rightarrow$ Steer Left/Right | Closed Fist $\rightarrow$ Kick.
  - **Both Hands**: Double Rock-on Sign $\rightarrow$ Goal Celebration.
  - Press `q` in the camera window to quit.

---

### Mode B: Running Laptop Keyboard Driving & Live Tuner
Drive the robot using precision keyboard controls:

> [!IMPORTANT]
> Run your terminal as **Administrator** on Windows so the `keyboard` module can capture system-wide keystrokes.

```powershell
python communication/comm_test_tool.py
```

1. Select your mBot COM port from the auto-detected list (press `Enter` for recommended port).
2. Drive using **Hold-to-Move**:
   - `W` / `S`: Forward / Reverse
   - `A` / `D`: Spin Left / Right
   - `Q` / `E`: Curve Forward-Left / Forward-Right
   - `Z` / `C`: Curve Backward-Left / Backward-Right
   - `K`: Stationary Kick
   - `W + K`: Running Kick
   - `V`: Victory celebration
3. **Tune Calibration Live**:
   - `Ctrl + Key`: Increase parameter (`w`: forward speed, `t`: motor trim, `k`: kick angle, etc.)
   - `Alt + Key`: Decrease parameter
   - `Ctrl + Enter`: Save permanently to EEPROM!
   - `Esc`: Disconnect cleanly.

---

### Mode C: Driving with Android Smartphone

1. Upload `mbot_phone_controller/mbot_phone_controller.ino` to the mBot.
2. Install **Bluetooth RC Controller** (or **BT Car Controller**) from Google Play Store on your Android phone.
3. Pair phone with mBot over Bluetooth.
4. Open the app, tap **Settings** $\rightarrow$ **Connect**, and select the mBot.
5. Use on-screen joystick arrows to drive, button `X` or `Horn` to kick, and button `Lights` or `Z` to celebrate!

---

### Mode D: Calibrating the Servo Kicker Arm

When assembling the 3D-printed kicker arm for the first time:

1. Remove the arm/horn from the servo gear shaft.
2. Upload `kicker_test/kicker_test.ino` to the mBot.
3. On startup, the servo rotates to $180^\circ$ (Safe Rest) and locks in place.
4. While the servo is powered and locked, press the kicker arm onto the shaft in its **fully retracted position** and tighten the center screw.
5. Send `'k'` in the Serial Monitor (115200 baud) to test a $90^\circ$ strike.

---

## ⚠️ Troubleshooting & Gotchas

| Issue | Root Cause | Solution |
|---|---|---|
| Arduino IDE fails to upload (`stk500_getsync()`) | Bluetooth module is occupying UART Pin 0/1 | **Unplug the Bluetooth module** from the board before uploading via USB. |
| Python script says `PermissionError` when pressing keys | `keyboard` library requires root/admin hooks | Right-click PowerShell/Terminal and select **Run as Administrator**. |
| Robot pulls slightly to the left or right while driving straight | Inherent DC motor RPM variance | Adjust motor trim: In `comm_test_tool.py`, press `Ctrl + T` to correct left pull, or `Alt + T` to correct right pull. Then press `Ctrl + Enter` to save to EEPROM. |
| Robot resets / reboots when kicking while driving | Battery voltage sag caused by simultaneous DC motor + Servo peak current draw | Use fully charged batteries. The firmware automatically cuts off RGB LEDs during running kicks to prevent brownouts. |
| Forward and backward gestures are reversed on webcam | Camera mirroring or coordinate inversion | Open `gestures/gesture_control.py` and flip `PALM_FACING_CROSS_SIGN = 1` at line 63. |
| Single hand appears on the wrong side of the HUD | Camera horizontal flip / selfie view mismatch | Open `gestures/gesture_control.py` and toggle `SWAP_HANDEDNESS = False` at line 72. |

---

## 👥 Team & Acknowledgments

Developed for the **Techno Exhibition - mBot Robot Football Showcase**.  
Designed with modular subsystems to enable seamless collaboration across Hardware/CAD, Embedded Firmware, Wireless Communication, and Computer Vision teams.
