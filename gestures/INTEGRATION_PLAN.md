# Integrating gesture_control.py with the mBot — Plan

## 1. What already exists (found in `../techno-mbot`)

- **Firmware** (`mbot_motor_control/mbot_motor_control.ino`): listens on Serial @ 115200 baud, one ASCII byte per command. Commands are **level/mode commands, not one-shot** (except `kick`) — e.g. sending `'w'` puts the robot into "drive forward" and it *stays* forward until a different command arrives. There is no separate "how fast" per frame; speed is a global `currentSpeedCap` adjusted only by `+`/`-`.
- **Bluetooth bridge** (`communication/mbot_bluetooth.py`, class `MBotBluetooth`): auto-finds the paired COM port, opens pyserial at 115200, exposes `forward() / backward() / turn_left() / turn_right() / curve_left() / curve_right() / kick() / stop() / speed_up() / speed_down() / disconnect()`. This is the exact thing our `robot_func()` stub should call.
- **Byte map** (from `communication/README.md`):

  | Command | Byte | Robot behavior |
  |---|---|---|
  | Forward | `w` | both wheels forward at speed cap |
  | Backward | `s` | both wheels backward |
  | Pivot left (in place) | `a` | wheels spin opposite directions, no forward motion |
  | Pivot right (in place) | `d` | mirror of `a` |
  | Curve left | `q` | forward, left wheel slower — arcs forward-left |
  | Curve right | `e` | forward, right wheel slower — arcs forward-right |
  | Kick | `k` | one-shot servo strike, firmware already debounces with a 500ms cooldown |
  | Stop | `' '` | both motors to 0 |

- Important firmware detail: **the communication failsafe is currently disabled** (`mbot_motor_control.ino:274-281`, commented out) so the robot does *not* auto-stop if the serial link goes quiet — it was disabled for the mobile-app "hold-to-move" use case. For our system (continuous per-frame gesture state, unattended-ish), that's a real safety gap worth flagging back to the robot-control owner, or working around from our side (see §4).

## 2. The mapping problem

Our gesture system produces **independent, continuously-updated state** every frame:
```json
{"drive": "forward" | "backward" | "stop", "turn": "turn_left" | "turn_right" | "center", "shoot": true/false}
```
The firmware only understands **one mutually-exclusive mode byte at a time** (you can't send "forward" and "turn_left" as two separate simultaneous bytes — the second overwrites the first's motor state). Luckily the firmware already anticipated the "forward + turning" case with `curveLeft`/`curveRight`, so the 3×3 combinations collapse into a small lookup table:

| drive \ turn | center | turn_left | turn_right |
|---|---|---|---|
| **forward** | `w` | `q` (curve left) | `e` (curve right) |
| **backward** | `s` | `s` *(no reverse-curve byte exists — see open question)* | `s` |
| **stop** | `' '` | `a` (pivot left) | `d` (pivot right) |

`shoot=True` is independent of the table above — it's a one-shot `k` sent alongside whatever the current drive/turn byte is (the firmware's `kick()` already stops the robot itself as part of the sequence, then resumes needing a fresh command after).

## 3. Where the bridge code goes

Add a new module in **this** repo, `robot_bridge.py`, that:
1. Imports `MBotBluetooth` from `../techno-mbot/communication/mbot_bluetooth.py` (either via a relative `sys.path` insert, since the two are sibling folders, or — cleaner — copy/symlink is avoided; just add the techno-mbot path once at startup).
2. Wraps the mapping table from §2 in a function `resolve_command(drive, turn) -> single_char`.
3. Tracks **last command sent** and only calls `bot.send_raw(...)` when the resolved character actually changes frame-to-frame — the firmware treats every received byte as "start doing this," so resending the same byte 30×/sec is wasted serial traffic (harmless, but noisy) rather than wrong.
4. Sends `k` for `shoot=True` regardless of whether the drive/turn byte changed, since it's a distinct one-shot action layered on top.
5. Exposes one function, `send_to_robot(drive, turn, shoot)`, that `gesture_control.py`'s `robot_func()` calls instead of just returning the JSON payload.

This keeps `gesture_control.py` itself almost untouched: `robot_func()` currently only builds/returns the payload for display — we add one call out to `robot_bridge.send_to_robot(...)` inside it, behind a connection-established check so the vision/HUD app still runs fine with the robot powered off (useful for tuning gestures without the robot on).

## 4. Safety handling on our side (since the firmware failsafe is off)

- On startup, connect via `MBotBluetooth.find_mbot_port()` / `.connect()`; if it fails, run in **detection-only mode** (current behavior) and show a HUD banner "ROBOT: OFFLINE" instead of crashing.
- If both hands disappear from frame (nobody driving), immediately resolve to `stop()` rather than holding the last command — this is the one case our own debouncers already default to (`drive_debouncer` defaults to `"stop"`, `turn_debouncer` to `"none"`), so it falls out mostly for free; just make sure `resolve_command` maps `("stop", "center")` correctly to `' '`.
- On any serial write exception (Bluetooth drop), immediately attempt one `stop()` retry, then mark disconnected and surface it on the HUD rather than silently going quiet while the last motor command (possibly "forward") keeps running physically forever.
- Add a lightweight heartbeat: even with an unchanged command, re-send it every ~500ms. Costs nothing on the robot side (idempotent), but bounds how long a single dropped byte can leave the robot in a stale state, since the firmware would need a *fresh* correct byte to recover if one got corrupted in transit.

## 5. Implementation steps (in order)

1. Write `robot_bridge.py` with `resolve_command()` and `send_to_robot()` as described, unit-testable without hardware (pure function for the mapping table, mockable `MBotBluetooth`).
2. Wire it into `gesture_control.py::robot_func()` behind a `--robot` CLI flag (or an env var) defaulting to *off*, so you can keep developing/tuning gestures safely without the robot connected, and explicitly opt in when ready to drive it.
3. Add the "ROBOT: ONLINE/OFFLINE" indicator to the existing HUD panel (same visual language as the `L:/R:` hand-presence chips).
4. **Bench test with wheels off the ground first**: verify each of the 8 table cells fires the right byte (log the resolved char on-screen, compare against what you see the wheels/LEDs do) before trusting it to drive on the floor.
5. Floor test drive/turn only (no shoot) at a low speed cap (`bot.speed_down()` a few times first).
6. Floor test shoot in isolation, then combined with driving.
7. Tune `TURN_DEADZONE_DEG` / hold-frame counts against how the *robot* responds (not just how the HUD looks) — a gesture that looks fine on-screen might still feel twitchy once it's actually spinning wheels.

## 6. Open questions for you

- **Backward + turning**: there's no `curve_left`/`curve_right`-while-reversing byte in the current firmware. Options: (a) ignore turn while backing up (table above, simplest), (b) ask the robot-control owner to add `curveBackLeft`/`curveBackRight`, or (c) reuse in-place pivot (`a`/`d`) even while `drive=backward` is held, accepting that it'll pivot instead of reverse during that frame. Which do you want?
- **Failsafe**: do you want to raise the disabled comm-timeout in the `.ino` with whoever owns robot-control firmware, or is bridge-side heartbeasting (§4) enough for your event/demo?
- **Speed cap**: gestures don't currently drive `+`/`-`. Leave speed fixed at whatever `currentSpeedCap` firmware boots with, or wire in a gesture/keypress for it later?
