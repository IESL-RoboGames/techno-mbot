# ✋ Gesture Control Subsystem

**Subsystem:** Two-hand webcam gesture control (Computer Vision input layer)
**Project:** mBot Robot Football (Techno Exhibition)

This folder is self-contained and does not modify anything in
`communication/` or `mbot_motor_control/` — it only *imports* the existing
`MBotBluetooth` class from `communication/mbot_bluetooth.py` to actually
drive the robot.

---

## 🎯 Role & Responsibilities

Reads two hands from a webcam via MediaPipe HandLandmarker and turns them
into robot commands:

| Action | Hand | Gesture |
|---|---|---|
| Forward | Left | Thumb up (fist, thumb pointing up) |
| Backward | Left | Thumb down (fist, thumb pointing down) |
| Turn left / right | Right | Open hand tilted left / right (discrete, no exact angle needed) |
| Shoot | Right | Closed fist (thumb tucked in) — one-shot trigger with cooldown |

Both hands are read independently every frame, so combos like
"forward + turning left" work naturally.

## 📂 Files

- `gesture_control.py` — webcam capture, MediaPipe hand tracking, gesture
  classification, debouncing, and the on-screen HUD. Runnable standalone
  (no robot required) for tuning gestures.
- `robot_bridge.py` — translates the gesture system's per-frame
  `(drive, turn, shoot)` state into the single-byte serial protocol already
  defined in `../communication/README.md`, and drives it through
  `MBotBluetooth`. Fails soft (detection-only mode) if `pyserial` isn't
  installed or no robot is connected, so this always runs even off the robot.
- `PLAN.md` — original gesture-set design notes (why these specific gestures
  were chosen for reliability).
- `INTEGRATION_PLAN.md` — the plan for wiring gesture output into the
  existing mBot Bluetooth/firmware protocol, including the drive×turn
  command mapping table and open safety considerations.

## 🔌 Command mapping (gesture → firmware byte)

Reuses the byte protocol from `../communication/README.md` as-is — no new
protocol was added. `robot_bridge.resolve_command(drive, turn)`:

| drive \ turn | center | turn_left | turn_right |
|---|---|---|---|
| **forward** | `w` | `q` (curve left) | `e` (curve right) |
| **backward** | `s` | `s` *(turn ignored while backing up — no reverse-curve byte exists)* | `s` |
| **stop** | `' '` | `a` (pivot left) | `d` (pivot right) |

`shoot=True` is independent and always sends a one-shot `k` on top of
whatever drive/turn byte is current (the firmware itself debounces kicks).

## 🚀 Running it

```powershell
cd gestures
pip install -r requirements.txt   # mediapipe, opencv-python, pyserial (see below)
python gesture_control.py
```

- If no mBot is paired/connected (or `pyserial` isn't installed), it runs in
  **detection-only mode** — the HUD still works, `ROBOT: OFFLINE` is shown,
  and no serial writes happen.
- If a paired mBot is found, `robot_bridge.py` auto-connects on startup
  (same auto-detection as `communication/comm_test_tool.py`) and drives it
  live.
- `hand_landmarker.task` (the MediaPipe model, ~8MB) is not committed here —
  `gesture_control.py` downloads it automatically on first run if missing.
- Keys: `+` / `-` adjust the robot's speed cap (mirrors the firmware's
  `currentSpeedCap`, shown as a minimalist bar meter on the HUD), `q` quits.

### Dependencies

`mediapipe`, `opencv-python` (for `gesture_control.py`), and `pyserial`
(only needed for live robot control — already a dependency of
`communication/`, see its README).

## ⚠️ Known limitation carried over from the integration plan

The firmware's own communication failsafe (auto-stop after a silent
period) is currently disabled in `mbot_motor_control.ino` for the
mobile-app control use case. `robot_bridge.py` compensates from this side
with a resend heartbeat and a stop-on-hands-lost default, but a genuinely
dropped Bluetooth link mid-command is still a real risk worth the
robot-control owner's attention before an unattended demo.
