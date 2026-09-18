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
| `'k'` | Kick/Shoot (Buzzer + Yellow) | (Handled in loop) |
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

bot = MBotBluetooth(port="COM5")  # replace with your Bluetooth port
if bot.connect():
    bot.forward()
    bot.curve_left()
    bot.stop()
    bot.disconnect()
```
