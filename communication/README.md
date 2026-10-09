# 📡 mBot Communication Subsystem

**Subsystem:** Wireless Bluetooth Communication (Computer ↔ mBot)  
**Project:** mBot Robot Football (Techno Exhibition)

---

## 🎯 Role & Responsibilities

1. **Wireless Link Management**: Establish and maintain reliable Bluetooth 4.0 wireless serial communication between the central computer (running Computer Vision) and the mBot.
2. **Protocol Bridge**: Map high-level vision decisions (`forward`, `turn_left`, `kick`, `stop`) into single-byte UART commands expected by the Robot Control team's firmware (`mbot_motor_control.ino`).
3. **Safety & Failsafe**: Ensure safe transmission and prevent runaways if the Bluetooth link drops out.
4. **CV Integration API**: Provide a clean Python interface (`MBotBluetooth`) so the Computer Vision subsystem can issue motion commands with one line of code.

---

## 📋 Communication Protocol Specification

All motion and action commands are transmitted over Bluetooth Serial at **115200 baud** (standard Makeblock hardware UART rate) as single ASCII bytes:

| Byte | Action | Target in Motor Control | Notes |
|:---:|---|---|---|
| `'w'` | Move forward | `moveForward()` | Dual green LEDs |
| `'s'` | Move backward | `moveBackward()` | Dual red LEDs |
| `'a'` | In-place pivot left | `turnLeft()` | Left blue LED |
| `'d'` | In-place pivot right | `turnRight()` | Right blue LED |
| `'q'` | Arc forward-left | `curveLeft()` | Left motor inner, right outer |
| `'e'` | Arc forward-right | `curveRight()` | Right motor inner, left outer |
| `'z'` | **Arc backward-left** *(New)* | `curveBackLeft()` | Arcs reverse to left (left inner, right outer) |
| `'c'` | **Arc backward-right** *(New)* | `curveBackRight()` | Arcs reverse to right (right inner, left outer) |
| `'x'` | 180° turnaround spin | `rotate180()` | Duration calibrated via `rotate180Ms` |
| `'v'` | Goal celebration wiggle | `celebrate()` | Moved from `'c'` to `'v'` (Victory) |
| `'k'` | Kick/Shoot (Servo on A0 + Buzzer) | `kick()` | Strike ball with calibrated angle `kickAngle` |
| `'o'` | Deploy/Open kicker servo | `setServoAngle(kickAngle)` | Helper for kicker testing |
| `'p'` | Retract/Reset kicker servo (0°) | `resetServo()` | Rest angle |
| `' '` | Stop immediately | `stopRobot()` | Both motors to 0, LEDs off |
| `'+'` | Increase speed cap | `currentSpeedCap += 15` | Global speed limit |
| `'-'` | Decrease speed cap | `currentSpeedCap -= 15` | Global speed limit |

---

## 🤝 Interface Guide for Gesture Control Team Member

> [!NOTE]  
> The gesture team member can connect backward turning into `gestures/robot_bridge.py` by simply updating `resolve_command(drive, turn)`:
> 
> ```python
> def resolve_command(drive, turn):
>     if drive == "forward":
>         if turn == "turn_left":
>             return "q"
>         if turn == "turn_right":
>             return "e"
>         return "w"
> 
>     if drive == "backward":
>         if turn == "turn_left":
>             return "z"  # <-- Backward-Left Arc (curveBackLeft)
>         if turn == "turn_right":
>             return "c"  # <-- Backward-Right Arc (curveBackRight)
>         return "s"
> 
>     # drive == "stop"
>     if turn == "turn_left":
>         return "a"
>     if turn == "turn_right":
>         return "d"
>     return " "
> ```
> No other protocol changes are required!

---

## 🎛️ Live Runtime Calibration Engine (Key & EEPROM)

You can calibrate motor speeds, steering balance (motor trim), 180° turn duration, and kick servo angles **in real time while the robot is running**, without having to re-flash Arduino code! Calibrated values are saved to the onboard **ATmega328P EEPROM** and persist across power cycles and battery replacements.

### Keyboard Shortcuts in `comm_test_tool.py`:
- **Increase Parameter**: Hold `Ctrl` + `[+]` + `[Key]` (or simply `Ctrl` + `[Key]`)
- **Decrease Parameter**: Hold `Ctrl` + `[-]` + `[Key]` (or `Alt` + `[Key]` / `Ctrl` + `Shift` + `[Key]`)
- **Save to EEPROM**: `Ctrl` + `Enter`
- **Reset Defaults**: `Ctrl` + `Backspace`
- **Query Status**: `Tab` or `?`

| Key | Parameter | Range | Step | Description |
|:---:|---|:---:|:---:|---|
| **`w`** | Forward Speed | 30 – 255 | 10 | Straight driving speed |
| **`s`** | Backward Speed | 30 – 255 | 10 | Reverse driving speed |
| **`a` / `d`** | Turn Speed | 30 – 255 | 5 | In-place pivot rotation speed |
| **`q` / `e`** | Curve Inner Ratio | 10% – 95% | 5% | Arc sharpness (inner wheel % of outer wheel) |
| **`o`** | Curve Outer Speed | 30 – 255 | 10 | Base speed while arcing |
| **`t`** | Motor Trim (Balance) | -50 to +50 | 2 | **Steering balance:** + corrects left pull, - corrects right pull |
| **`x`** | 180 Spin Time | 100 – 3000 ms | 25 ms | Exact spin duration for a true 180° turnaround |
| **`k`** | Kick Servo Angle | 20° – 180° | 5° | Servo strike extension angle |
| **`c`** | Master Speed Cap | 30 – 255 | 15 | Global speed limit cap |

### Direct Serial / Bluetooth Calibration Commands:
Commands start with `#` followed by a parameter key and `+` / `-`, or direct numeric assignment:
- `#W+` / `#W-` : Adjust forward speed
- `#T+` / `#T-` : Adjust motor trim
- `#W:180`      : Set forward speed directly to 180
- `#?`          : Print complete calibration table
- `#SAVE`       : Save current settings to EEPROM
- `#RESET`      : Restore factory default settings

---

## 🚀 Quick Start & Testing

### 1. Requirements
Install required Python libraries:
```powershell
pip install pyserial keyboard
```

> [!WARNING]  
> **Hardware Conflict:** The mCore board shares its serial pins (0 and 1) between the USB port and the Bluetooth module.
> - When uploading code via USB, you **must unplug** the Bluetooth module.
> - When driving via Bluetooth, you **must unplug** the USB cable from the PC.

### 2. Pair mBot with Windows PC
1. Turn on the mBot battery switch.
2. In Windows **Bluetooth Settings**, click **Add device** $\rightarrow$ select **Makeblock** / **mBot**.
3. Once paired, note the outgoing COM port in **Device Manager** $\rightarrow$ **Ports (COM & LPT)**.

### 3. Run the Communication Test Tool
```powershell
python communication/comm_test_tool.py
```
*(Note: Because this tool uses real-time keyboard tracking to implement "hold-to-move, release-to-stop", run your terminal as Administrator on Windows).*

This tool scans your ports, connects to the mBot, supports dual-key driving (`W+A`, `W+D`, `S+A`, `S+D`), and lets you tune calibration live with `Ctrl`+`+` / `Ctrl`+`-`.

---

## 💻 How Computer Vision Subsystem Uses This

```python
from communication.mbot_bluetooth import MBotBluetooth

# Auto-detects the paired Makeblock mBot (e.g. COM23), or specify explicitly: MBotBluetooth(port="COM23")
bot = MBotBluetooth()  
if bot.connect():
    bot.forward()
    bot.curve_left()
    bot.curve_back_left()
    bot.stop()
    bot.disconnect()
```

---

## 📱 Mobile Phone Control (Android)

To drive the mBot independently using an Android phone, use any free Bluetooth controller app from the Google Play Store:

### Recommended Gamepad Apps:
1. **"Bluetooth RC Controller"** (by Andi.Co / Search `Bluetooth RC Controller`)
   - Dedicated RC car steering and accelerator pad with standard RC `F/B/L/R/G/I/H/J/S` codes.
2. **"Connectino: Arduino Bluetooth"** (Search `Connectino`)
3. **"Arduino Bluetooth Control Plus"** (Search `Bluetronics`)

### Supported Button Commands:
The Arduino firmware accepts both custom keys and standard RC car protocol characters:

| Button / Function | Custom Keys | Standard RC Codes | Robot Action |
|---|:---:|:---:|---|
| **Forward** | `'w'` | `'F'` | Drive forward |
| **Backward** | `'s'` | `'B'` | Drive backward |
| **Turn Left** | `'a'` | `'L'` | Spin left |
| **Turn Right** | `'d'` | `'R'` | Spin right |
| **Curve Forward-Left** | `'q'` | `'G'` | Arc forward-left |
| **Curve Forward-Right** | `'e'` | `'I'` | Arc forward-right |
| **Curve Backward-Left** | `'z'` | `'H'` | Arc backward-left |
| **Curve Backward-Right** | `'c'` | `'J'` | Arc backward-right |
| **Kick / Shoot** | `'k'` | `'X'` / `'V'` *(Horn)* | Strike kicker servo on A0 |
| **Celebrate** | `'v'` | `'C'` | Victory celebration wiggle |
| **Stop / Brake** | `' '` *(Space)* | `'S'` / `'D'` | Stop motors |
| **Speed + / -** | `'+'` / `'-'` | — | Adjust speed cap |



