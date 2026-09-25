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

All commands are transmitted over Bluetooth Serial at **115200 baud** (standard Makeblock hardware UART rate) as single ASCII bytes:

| Byte | Action | Target in Motor Control |
|:---:|---|---|
| `'w'` | Move forward | `moveForward()` |
| `'s'` | Move backward | `moveBackward()` |
| `'a'` | In-place pivot left | `turnLeft()` |
| `'d'` | In-place pivot right | `turnRight()` |
| `'q'` | Smooth curve left | `curveLeft()` |
| `'e'` | Smooth curve right | `curveRight()` |
| `'x'` | 180° turn around | `rotate180()` |
| `'c'` | Goal celebration wiggle | `celebrate()` |
| `'k'` | Kick/Shoot (Servo on A0 + Buzzer) | `kick()` |
| `'o'` | Deploy/Open kicker servo (90°) | `setServoAngle(SERVO_KICK_ANGLE)` |
| `'p'` | Retract/Reset kicker servo (0°) | `resetServo()` |
| `' '` | Stop immediately | `stopRobot()` |
| `'+'` | Increase speed cap | `currentSpeedCap += 20` |
| `'-'` | Decrease speed cap | `currentSpeedCap -= 20` |

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
*(Note: Because this tool uses real-time keyboard tracking to implement "hold-to-move, release-to-stop", you may need to run your terminal as Administrator on Windows).*

This tool scans your ports, connects to the mBot, and lets you drive it seamlessly from your keyboard to verify the Bluetooth link and Arduino failsafes.

---

## 💻 How Computer Vision Subsystem Uses This

```python
from communication.mbot_bluetooth import MBotBluetooth

# Auto-detects the paired Makeblock mBot (e.g. COM23), or specify explicitly: MBotBluetooth(port="COM23")
bot = MBotBluetooth()  
if bot.connect():
    bot.forward()
    bot.curve_left()
    bot.stop()
    bot.disconnect()
```

---

## 📱 Mobile Phone Control (Android)

To drive the mBot independently using an Android phone, use any free Bluetooth controller app from the Google Play Store:

### Recommended 100% Free Gamepad Apps on Google Play:
1. **"Connectino: Arduino Bluetooth"** (Search `Connectino`)
   - **UI**: Modern virtual PlayStation / console gamepad with thumbsticks & ABXY buttons.
2. **"Arduino Bluetooth Control Plus"** (Search `Bluetronics`)
   - **UI**: Dedicated Gamepad mode with analog touch joystick and customizable action buttons.
3. **"Bluetooth RC Controller"** (by Andi.Co / Search `Bluetooth RC Controller`)
   - **UI**: Dedicated RC car steering and accelerator pad (works out of the box with standard RC `F/B/L/R/S` codes).

### Supported Button Commands:
The Arduino firmware accepts both custom keys and standard RC car protocol characters:

| Button / Function | Custom Keys | Standard RC Codes | Robot Action |
|---|:---:|:---:|---|
| **Forward** | `'w'` | `'F'` | Drive forward |
| **Backward** | `'s'` | `'B'` | Drive backward |
| **Turn Left** | `'a'` | `'L'` | Spin left |
| **Turn Right** | `'d'` | `'R'` | Spin right |
| **Curve Left** | `'q'` | `'G'` | Arc forward-left |
| **Curve Right** | `'e'` | `'I'` | Arc forward-right |
| **Kick / Shoot** | `'k'` | `'X'` / `'V'` *(Horn)* | Strike kicker servo on A0 |
| **Celebrate** | `'c'` | — | Victory celebration wiggle |
| **Stop / Brake** | `' '` *(Space)* | `'S'` / `'D'` | Stop motors |
| **Speed + / -** | `'+'` / `'-'` | — | Adjust speed cap |


