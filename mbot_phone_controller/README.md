# 📱 mBot Dedicated Phone Gamepad Controller & Calibration

Standalone, plug-and-play firmware specifically mapped for the popular **"BT Car Controller"** app (and standard Bluetooth RC Car apps), complete with **onboard EEPROM calibration** and a companion **laptop calibration tool**.

---

## 🏎️ Part 1: How to Drive with "BT Car Controller" App

### 1. Download & Connect:
1. Upload [mbot_phone_controller.ino](file:///c:/Users/sayur/Documents/GitHub/techno-mbot/mbot_phone_controller/mbot_phone_controller.ino) to your mBot via Arduino IDE.
2. Turn on the mBot battery power.
3. Open **BT Car Controller** (or Bluetooth RC Controller) on your phone.
4. Tap **Connect** and select your paired mBot (`Makeblock` / `mBot`).

---

### 2. Complete Phone Button Mapping:

| App Control / Button | Sent ASCII Code | Robot Behavior |
|---|:---:|---|
| **Forward Arrow** | `'F'` | Drives forward continuously (Green LEDs) |
| **Backward Arrow** | `'B'` | Drives backward continuously (Red LEDs) |
| **Left Arrow** | `'L'` | In-place spin left (Blue LED) |
| **Right Arrow** | `'R'` | In-place spin right (Blue LED) |
| **Forward-Left Diagonal** | `'G'` | Arc curve forward to the left |
| **Forward-Right Diagonal** | `'H'` | Arc curve forward to the right |
| **Back-Left Diagonal** | `'I'` | Arc curve backward to the left |
| **Back-Right Diagonal** | `'J'` | Arc curve backward to the right |
| **Button Release / Stop** | `'S'` / `'D'` | **Stops immediately** when finger leaves the screen |
| **Kick (Y / Horn / X)** | `'Y'` / `'V'` / `'X'` | **Smart Kick**: Does a **Running Kick** if moving forward, or **Stationary Kick** if stopped! (Release `'y'`, `'v'`, `'x'` safely ignored) |
| **Celebrate (Z / Lights / U)** | `'Z'` / `'W'` / `'U'` / `'C'` | **Goal Celebration Fanfare**: Plays victory melody and dances side-to-side! (Release `'z'`, `'w'`, `'u'` safely ignored) |
| **Speed Slider** | `'0'` to `'9'` | Sets robot speed from 0% to 100% full power |

> [!NOTE]  
> **Continuous Driving Fixed**: The robot will drive continuously as long as you hold down a direction button, and stops instantly when you release it. There is no timeout cutting off your drive.

---

## 🎛️ Part 2: Laptop Calibration (2 Easy Ways)

You can calibrate your mBot's speeds, straight-line steering balance (trim), and kick angle using your laptop keys. Calibrated values are saved permanently in **EEPROM** so they stay active when you switch to phone control!

### Method A: Using the Companion Python Tool
Run the script inside this folder:
```powershell
python c:\Users\sayur\Documents\GitHub\techno-mbot\mbot_phone_controller\calibrate_mbot.py
```
- Press **W / S / A / D** to test drive.
- Press **Space** to stop.
- Press **T** or **Shift+T** to adjust steering trim (balance left/right so it drives straight).
- Press **F** or **Shift+F** to increase/decrease forward speed.
- Press **Shift+S** to save to EEPROM!
- Press **?** to see current parameters.

---

### Method B: Using Arduino Serial Monitor
Open Arduino IDE Serial Monitor at **115200 baud** (with "Newline" selected):
- Send `#?` : Prints the full calibration table.
- Send `#T+` or `#T-` : Adjust steering balance trim (+ slows left / boosts right; - slows right / boosts left).
- Send `#W+` or `#W-` : Adjust forward speed.
- Send `#A+` or `#A-` : Adjust turn speed.
- Send `#K+` or `#K-` : Adjust kick strike angle.
- Send `#SAVE` : Saves all changes permanently to EEPROM!
- Send `#RESET` : Resets all settings to factory defaults.
