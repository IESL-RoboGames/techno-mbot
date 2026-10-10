# ✋ Gesture Control Subsystem

**Subsystem:** Two-hand webcam gesture control (Computer Vision input layer)
**Project:** mBot Robot Football (Techno Exhibition)

This folder is self-contained and does not modify anything in
`communication/` or `mbot_motor_control/` — it only *imports* the existing
`MBotBluetooth` class from `communication/mbot_bluetooth.py` to drive the
robot.

---

## 🎯 Gestures

Reads two hands from a webcam via MediaPipe HandLandmarker. Both hands are
classified independently every frame, so combos like "forward + turning
left" work naturally.

| Action | Hand | Gesture |
|---|---|---|
| Forward | Left | Open hand, **palm facing the camera** |
| Backward | Left | Open hand, **back of the hand facing the camera** |
| Stop | Left | Anything else (fist, half-open, edge-on, hand out of frame) |
| Turn left / right | Right | Open hand tilted left / right (discrete — no exact angle needed) |
| Shoot | Right | Closed fist — one-shot with cooldown |
| Celebrate | Both | **Rock-on sign** (index + pinky up, middle + ring folded) on **both** hands (~0.3 s) — one-shot with cooldown |

Notes:
- A **fist** is at least 3 of the 4 fingers curled; where the thumb sits
  doesn't matter.
- Shoot and celebrate fire on a vote over recent frames (shoot: 3 of the last
  5, celebrate: 6 of the last 9), so a single dropped or misread frame doesn't
  reset them. Each re-arms only after the gesture is released.
- Which hand is which: with **two hands** visible, the one on the left of the
  (mirrored) picture is your left/DRIVE hand and the other is your right/STEER
  hand. MediaPipe's own Left/Right label is ignored then, because it is
  unreliable on fists. With **one hand** visible, it keeps the side it was
  last seen on, falling back to MediaPipe's label. Keep your hands uncrossed.
- Hands are tracked between frames (MediaPipe VIDEO mode), which keeps fists
  from dropping out.
- Palm vs. back of hand is read from the geometry of the knuckles (sign of
  the wrist→index × wrist→pinky cross product), so it works at any hand
  rotation and any distance from the camera. The HUD shows what the left hand
  is currently read as (`L: PALM` / `L: BACK` / `L: FIST` / `L: HAND` / `L: OFF`).
  If forward/backward come out swapped on your setup, flip
  `PALM_FACING_CROSS_SIGN` at the top of `gesture_control.py`.
- Shoot works whatever the left hand is doing, so **stop + shoot** (left fist
  + right fist) kicks. The rock-on sign can never read as a fist or an open
  hand, so celebrate doesn't clash with shoot, drive or turn.
- If a *single* visible hand ends up on the wrong side for your camera, flip
  `SWAP_HANDEDNESS` at the top of `gesture_control.py`.

## 🖥️ HUD

- **Top bar** — robot link status (pulsing `ROBOT ONLINE` / `OFFLINE`) and FPS.
- **Left card (DRIVE)** — big arrow / stop icon for the current drive state,
  plus what the camera reads the left hand as (`PALM` / `BACK` / `FIST` / `HAND`).
- **Right card (STEER)** — left / straight / right indicators, a tilt gauge
  showing the dead-zone band, the right-hand read, and a kick-readiness bar
  (`RELOAD` → `READY`).
- **Command strip** (bottom) — the actual command being sent, e.g.
  `ARC FWD-LEFT [q]`, with a one-line gesture legend under it.
- **Shoot** — red screen-edge flash, a `SHOOT!` banner and shockwave rings
  (~0.8 s), visible wherever your hands are.
- **Celebrate** — confetti, fireworks, rainbow chrome and a `GOAL! CELEBRATE`
  banner (~2 s).

The layout scales with the camera resolution (designed at 640×480).

## 📂 Files

- `gesture_control.py` — webcam capture, MediaPipe hand tracking, gesture
  classification, debouncing, and the on-screen HUD. Runnable standalone
  (no robot required) for tuning gestures.
- `robot_bridge.py` — translates the gesture system's per-frame
  `(drive, turn, shoot, celebrate)` state into the single-byte serial
  protocol defined in `../communication/README.md`, via `MBotBluetooth`.
  Fails soft (detection-only mode) if `pyserial` isn't installed or no robot
  is connected.
- `PLAN.md`, `INTEGRATION_PLAN.md` — original design notes (historical; the
  gesture set and command table above supersede them).

## 🔌 Command mapping (gesture → firmware byte)

`robot_bridge.resolve_command(drive, turn)`:

| drive \ turn | center | turn_left | turn_right |
|---|---|---|---|
| **forward** | `w` | `q` (arc fwd-left) | `e` (arc fwd-right) |
| **backward** | `s` | `z` (arc back-left) | `c` (arc back-right) |
| **stop** | `' '` | `a` (pivot left) | `d` (pivot right) |

One-shots, independent of the table: shoot → `k`, celebrate → `v`.

## 🚀 Running it

```powershell
cd gestures
pip install -r requirements.txt   # mediapipe, opencv-python, pyserial
python gesture_control.py
```

- No mBot paired/connected (or `pyserial` missing) → **detection-only
  mode**: the HUD works, `ROBOT: OFFLINE` is shown, nothing is sent.
- Paired mBot found → `robot_bridge.py` auto-connects on startup (same
  auto-detection as `communication/comm_test_tool.py`) and drives it live.
  The HUD shows `ROBOT: ONLINE`.
- Speed and calibration are handled on the robot side (EEPROM-backed
  calibration, see `../communication/README.md`) — there are no speed
  controls in the gesture window. `q` quits.
- `hand_landmarker.task` (the MediaPipe model, ~8MB) is not committed —
  `gesture_control.py` downloads it automatically on first run if missing.

## ⚠️ Known limitation

The firmware's own communication failsafe (auto-stop after a silent period)
is disabled in `mbot_motor_control.ino` for the mobile-app use case.
`robot_bridge.py` compensates with a resend heartbeat and a stop-on-hands-lost
default, but a genuinely dropped Bluetooth link mid-command is still a real
risk worth the robot-control owner's attention before an unattended demo.
