# Gesture Control Redesign — Plan

## 1. Requirement recap

Robot actions to detect (detection only, no exact angles, no transport yet):

| Action | Hand | Notes |
|---|---|---|
| Forward | Left | |
| Backward | Left | |
| Turn left | Right | discrete left/right, not a proportional angle |
| Turn right | Right | |
| Shoot | Right | one-shot trigger gesture |

Forward/backward and turning must be able to fire **at the same time** (e.g. "forward + turning left"), so left-hand and right-hand classifiers must run independently every frame and just report their own current state — no shared lockout between hands.

Right hand carries two different jobs (turn + shoot). That's fine as long as the two gestures use different, mutually-exclusive hand shapes (open hand vs. fist) — the classifier just needs to tell which shape it's looking at each frame.

## 2. Proposed gesture set

| Action | Gesture | Why this one |
|---|---|---|
| Forward | Left hand, **thumb up** (fist with thumb pointing up) | Already implemented and working in `gesture_control.py` (`classify_throttle_gesture`) for the old right-hand throttle. It's a fist shape with one clear extended feature (thumb direction) — cheap to detect, hard to confuse with an open hand or a turn gesture, no ambiguity about "how far" like a proportional angle would need. Moving it to the left hand is a straight port.
| Backward | Left hand, **thumb down** | Same gesture family as above, opposite thumb direction. |
| Turn left | Right hand, **open hand tilted left** | You already found open-hand detection is more reliable (5 extended fingers = strong, redundant signal vs. a single thumb). We don't need the angle, only the sign, so this becomes a **discrete** left/right/center classification instead of the current proportional `SteeringEstimator` — much less fussy than getting an exact degree right, and far more forgiving of hand distance/size. |
| Turn right | Right hand, **open hand tilted right** | Mirror of the above, same classifier. |
| Shoot | Right hand, **closed fist** (all fingers folded, thumb tucked or across knuckles) | Fist is a large, unambiguous shape change from the open hand used for turning, so the two never get confused. Because it's a *trigger* (one-shot), it needs edge detection (fires once on the open→fist transition) rather than a held state like the others, plus a cooldown so a lingering fist doesn't spam repeat shots. |

Neutral / no action states:
- Left hand: anything that isn't a clear thumb-up or thumb-down fist → `neutral` (already how `classify_throttle_gesture` works).
- Right hand: hand not roughly upright/open (e.g. hand not visible, ambiguous shape) → `no_turn`; open hand within a small dead-zone of vertical → `center` (no turn).

## 3. Detection approach (reusing what's proven in `gesture_control.py`)

### Left hand — forward / backward
- Reuse `classify_throttle_gesture()` and `fingers_folded()` as-is, just fed the **Left**-hand landmarks instead of Right.
- Output: `"forward" | "backward" | "neutral"`.
- Keep `GestureDebouncer` (hold N frames before a gesture "locks in") to avoid flicker.

### Right hand — turn left / turn right
- Detect "open hand": all 4 fingers extended (inverse of `fingers_folded`, i.e. `folded_count <= 1`) AND fingers reasonably spread/straight (tip-to-wrist distance clearly greater than pip-to-wrist distance, to reject a half-curled hand).
- If open: compute the same wrist→middle-finger-MCP (or palm-normal) angle used in `SteeringEstimator._raw_angle`, but **don't** map it proportionally. Instead bucket it:
  - `angle > +DEADZONE` → `turn_right`
  - `angle < -DEADZONE` → `turn_left`
  - otherwise → `center`
  - `DEADZONE` (e.g. 12–15°) replaces `STEER_MAX_ANGLE_DEG`'s proportional role — just a threshold now, no calibration baseline needed since we only care about tilt direction relative to a roughly-upright open hand, not an absolute proportional value. (Optional: keep the existing auto-calibration logic to set what "centered/vertical" means for this user's hand/camera, then bucket the delta instead of scaling it.)
- If not open (and not a fist — see below) → `no_turn`.
- Debounce with the same `GestureDebouncer` pattern (short hold, e.g. 3–5 frames, since turning should feel responsive).

### Right hand — shoot
- Reuse `fingers_folded()` (`folded_count >= 3`, or tighten to all 4 for shoot specifically to avoid overlap with "open hand" edge cases) plus require the thumb also folded across/against the palm (unlike the throttle fist, which needs thumb *extended* up/down — so "shoot fist" = thumb also folded, not pointing).
- This keeps shoot-fist and forward/backward-fist visually distinct even though both are on... wait, they're on different hands anyway (fist-thumb-up/down is left hand, fist-thumb-in is right hand), so no real collision, but keeping the thumb-tucked check makes the right-hand fist itself unambiguous from an accidental "open hand at a weird angle" reading.
- Because it's a trigger, not a state: track previous-frame shape for the right hand. Fire `shoot` exactly once on the transition into fist, then require the hand to leave the fist shape (or a cooldown timer, e.g. 500 ms) before it can fire again.

### Combining both hands per frame
- Each hand is classified independently from `results.hand_landmarks` / `results.handedness`, same as today's loop.
- Per-frame command becomes something like:
  ```json
  {"forward_backward": "forward", "turn": "turn_left", "shoot": true/false}
  ```
- No shared debouncer/state between hands — that's what already allows "forward + turn left" simultaneously in the current code (left/right are handled in independent branches of the same `for` loop), so this falls out for free.

## 4. Implementation steps

1. **Rename/repurpose existing throttle classifier** for the left hand (swap which handedness label routes to it). Rename variables (`throttle` → `drive` or similar) so the code reads correctly now that it's on the left hand.
2. **Replace `SteeringEstimator`** (proportional) with a new `TurnClassifier` (discrete): open-hand check + fist check + angle bucketing + a `GestureDebouncer` for the resulting `turn_left|turn_right|center` state.
3. **Add shoot edge-detection**: a small state machine (`WAITING` → fist detected → emit `shoot` once → `COOLDOWN` for N ms → back to `WAITING`), reusing the fist check from step 2 but with the tucked-thumb condition.
4. **Update `robot_func` payload shape** to the four independent fields above (drive, turn, shoot) instead of `throttle`/`steering`.
5. **Update on-screen HUD** to show all three states live (this is your main way to validate reliability before wiring up real hardware).
6. **Manual test pass** (see below) before touching any transport/serial code.

## 5. Test plan (detection-only, webcam)

Run through each in isolation, then in combination:
- Left thumb-up alone → forward shown, no turn, no shoot.
- Left thumb-down alone → backward shown.
- Right open hand centered → center/no turn.
- Right open hand tilted left/right → turn_left / turn_right, and check it doesn't chatter right at the dead-zone boundary (nudge slowly across the threshold).
- Right fist → shoot fires exactly once per fist entry, not repeatedly while held.
- Combinations: left thumb-up + right tilted left → forward & turn_left simultaneously. Left thumb-down + right fist → backward & a single shoot.
- Edge cases: only one hand visible, hand leaves frame mid-gesture, fast hand swaps between left/right positions (handedness label should track the physical hand via MediaPipe's own labeling, already relied on by the existing code).

## 6. Open questions for you before implementation

- Dead-zone angle for turn left/right — start at ~12° and tune by feel, or do you want it configurable via keypress like the existing `c` calibration?
- Shoot cooldown duration — 500 ms suggested, adjust to taste.
- Do you want the HUD to keep showing raw angle for turning (for tuning) even though the robot only gets left/right/center, or hide it once this is finalized?
