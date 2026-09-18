# 🤖 mBot Robot Football - Motor Control Module

> Part of the **mBot Robot Football** Techno Exhibition project a 2v2 robot football game controlled by hand gestures, built on four original mBots.
>
> This module owns **movement**: turning raw commands into safe, smooth motion on a single mBot. It's built and tested standalone, before gesture or Bluetooth input exists so today, *you* are the input device, via the Serial Monitor.

---

## 📋 Overview

| | |
|---|---|
| **Board** | mCore (mBot's built in Arduino based controller) |
| **Library** | [`MeMCore`](https://github.com/Makeblock-official/Makeblock-Libraries) by Makeblock |
| **Motors** | 2× DC gear motors - `M1` (left), `M2` (right) |
| **Role in project** | Member 5 - Robot Control & Behaviour |
| **Status** | ✅ Movement primitives working · 🔜 Bluetooth input next |

This sketch answers one question: *given a command ("go forward", "turn left"...), how does the robot move reliably, at a safe speed, without jerking?* Everything upstream of that (gestures, Bluetooth packets) is a separate concern that plugs in later.

---

## ✨ Features

**Core movement**
- `moveForward()` / `moveBackward()`
- `turnLeft()` / `turnRight()` - in-place pivot
- `rotate180()` - full "turn around"
- `stopRobot()` - controlled stop

**Extras for a livelier game**
- `curveLeft()` / `curveRight()` - gentle arc turns for approaching the ball at an angle, instead of only spinning on the spot
- `celebrate()` - a quick side-to-side wiggle for a "goal scored" flourish

**Built-in safety** (per the project's safety spec)
- 🚦 **Hard speed cap** - the robot physically cannot exceed `MAX_SPEED`
- 📈 **Smooth ramping** - every speed change eases in/out instead of snapping instantly
- ⏱️ **Comm-loss failsafe** - if no command arrives for `COMM_TIMEOUT_MS`, the robot stops itself automatically. This is the same check that will later catch a dropped Bluetooth link.

---

## 🔧 Hardware Setup

1. Connect the left motor to port **M1**, the right motor to port **M2** on the mCore.
2. Power the mCore (battery or USB while testing).
3. Connect the mCore to your computer via USB for uploading and Serial Monitor access.

---

## 💻 Software Setup

1. Install the **Arduino IDE**.
2. Install the Makeblock library:
   `Sketch → Include Library → Manage Libraries → search "Makeblock" → Install`
3. Open `mbot_motor_control.ino` and select the correct board/port under **Tools**.
4. Upload.

---

## ▶️ Testing (Serial Monitor stand-in for real input)

Open **Serial Monitor**, set baud rate to **9600**, line ending to **"No line ending"**, then drive the robot with single keystrokes:

| Key | Action |
|:---:|---|
| `w` | Move forward |
| `s` | Move backward |
| `a` | Turn left (pivot) |
| `d` | Turn right (pivot) |
| `q` | Curve left |
| `e` | Curve right |
| `x` | Turn around (180°) |
| `space` | Stop |
| `c` | Celebrate wiggle |
| `+` / `-` | Increase / decrease speed cap |

**Sanity check:** if pressing `w` drives the robot *backward*, one motor's wiring is reversed relative to the code's assumption. Flip the sign on that motor inside `setMotorSpeeds()` and re-upload — no other logic needs to change.

> ⚠️ `rotate180()`'s timing (`ROTATE_180_MS`) is a starting estimate. Tune it on your actual arena floor and battery charge level to get a true 180°.

---

## 🗺️ Roadmap

- [x] Core movement functions
- [x] Speed limiting + smooth acceleration/deceleration
- [x] Comm-loss failsafe stub
- [ ] Bluetooth command listener (HC-05/HC-06) - swaps out the Serial test harness for real wireless input, reusing every function above unchanged
- [ ] Gesture driven control (via computer → wireless bridge)
- [ ] Integration with servo arm subsystem for shooting

---

## 🧩 How this fits the bigger picture

```
Player hand / phone → gesture recognition or Bluetooth → mBot → this module → motors
```

This module is intentionally input-agnostic: whatever decides *what* the robot should do (a camera, a phone app, or a human typing on a keyboard) just needs to call `moveForward()`, `turnLeft()`, `rotate180()`, etc. Swapping the input source at the top never requires touching the motor logic underneath.
