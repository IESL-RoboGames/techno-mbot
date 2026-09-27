"""
Two-Hand Gesture Control System for Robot Teleoperation
=========================================================
Left Hand  -> Drive     (Thumbs Up / Thumbs Down / Neutral -> forward/backward/stop)
Right Hand -> Turn      (Open hand tilted left/right -> discrete turn_left/turn_right/center)
Right Hand -> Shoot     (Closed fist, thumb tucked -> one-shot trigger with cooldown)

Detection only. Transport (Serial/Socket) is stubbed in robot_func().
"""

import cv2
import math
import json
import time
from pathlib import Path
from urllib.request import urlopen

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

try:
    from robot_bridge import RobotBridge, SPEED_MAX
except Exception as _bridge_import_error:  # e.g. pyserial not installed, or techno-mbot missing
    RobotBridge = None
    SPEED_MAX = 150
    _BRIDGE_IMPORT_ERROR = _bridge_import_error
else:
    _BRIDGE_IMPORT_ERROR = None

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
DRIVE_HOLD_FRAMES = 5          # frames a drive gesture must persist to "lock in"
TURN_HOLD_FRAMES = 4           # frames a turn gesture must persist to "lock in"
TURN_DEADZONE_DEG = 15.0       # tilt beyond this angle (from vertical) registers a turn
SHOOT_HOLD_FRAMES = 3          # frames the fist must persist before it counts as "closed"
SHOOT_COOLDOWN_SEC = 0.6       # minimum time between consecutive shots

SPEED_MIN = 0
SPEED_STEP = 20
SPEED_START = 100              # mirrors the firmware's currentSpeedCap starting value

EXTEND_RATIO = 1.15            # tip-to-wrist must exceed pip-to-wrist by this ratio to count as "extended"
THUMB_TUCK_RATIO = 0.55        # thumb tip must be this close to the index MCP (relative to palm size) to count as "tucked"

# MediaPipe's Left/Right label is computed on the raw (pre-flip) camera
# frame, mirrored on the assumption of a selfie view -- on some setups that
# still comes out swapped relative to what the person on camera is doing.
# Flip this if drive/turn end up on the wrong hand for your camera.
SWAP_HANDEDNESS = True

MODEL_PATH = Path(__file__).with_name("hand_landmarker.task")
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
HAND_CONNECTIONS = vision.HandLandmarksConnections.HAND_CONNECTIONS

# Landmark indices (MediaPipe Hands)
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

FINGER_TIPS_PIPS = [
    (INDEX_TIP, INDEX_PIP),
    (MIDDLE_TIP, MIDDLE_PIP),
    (RING_TIP, RING_PIP),
    (PINKY_TIP, PINKY_PIP),
]

# Neon HUD palette (BGR). Nothing here is grey -- "inactive" states use a
# dim/saturated version of the *same* hue instead of grey, since desaturated
# grey on a dark webcam feed reads as almost invisible.
COL_BG = (8, 6, 14)
COL_GREEN = (80, 255, 140)
COL_GREEN_DIM = (40, 110, 70)
COL_RED = (70, 60, 255)
COL_RED_DIM = (45, 40, 130)
COL_AMBER = (0, 190, 255)
COL_CYAN = (255, 230, 40)
COL_CYAN_DIM = (120, 100, 20)
COL_WHITE = (245, 245, 245)
COL_INACTIVE = (150, 90, 40)   # dim electric-blue outline, visible on dark bg
COL_MAGENTA = (255, 40, 230)
COL_MAGENTA_DIM = (120, 20, 110)


# ------------------------------------------------------------------
# robot_func: single dispatch point to hardware (stub only)
# ------------------------------------------------------------------
def robot_func(command_dict):
    """
    Receives the final command payload every frame and would forward it
    to the robot's microcontroller.

    command_dict example:
        {"drive": "forward", "turn": "turn_left", "shoot": false, "timestamp": ...}
        drive: "forward" | "backward" | "stop"
        turn:  "turn_left" | "turn_right" | "center"
        shoot: True only on the single frame a shot fires, else False
    """
    payload = json.dumps(command_dict)

    # --- Transport stub -------------------------------------------------
    # serial_conn.write((payload + "\n").encode("utf-8"))
    # socket_conn.sendall(payload.encode("utf-8"))
    # ---------------------------------------------------------------------

    return payload  # returned only so the caller can display it


# ------------------------------------------------------------------
# Shared geometry helpers (rotation-invariant: use distance from wrist
# rather than raw y-comparisons, so tilting the hand doesn't break
# finger-extended / folded checks the way a purely vertical assumption
# would).
# ------------------------------------------------------------------
def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def _hand_scale(landmarks):
    """A rotation/translation-invariant reference length for this hand,
    used to normalize thumb-tuck distance checks."""
    return _dist(landmarks[WRIST], landmarks[MIDDLE_MCP]) or 1e-6


def finger_extended(landmarks, tip_idx, pip_idx):
    wrist = landmarks[WRIST]
    return _dist(wrist, landmarks[tip_idx]) > _dist(wrist, landmarks[pip_idx]) * EXTEND_RATIO


def count_extended_fingers(landmarks):
    return sum(1 for tip, pip in FINGER_TIPS_PIPS if finger_extended(landmarks, tip, pip))


def is_open_hand(landmarks):
    """>=3 of the 4 non-thumb fingers clearly extended."""
    return count_extended_fingers(landmarks) >= 3


def is_fist(landmarks):
    """<=1 of the 4 non-thumb fingers extended AND the thumb tucked in
    against the palm (close to the index MCP), so an open hand at an
    odd angle is never mistaken for a fist."""
    if count_extended_fingers(landmarks) > 1:
        return False
    thumb_tuck_dist = _dist(landmarks[THUMB_TIP], landmarks[INDEX_MCP])
    return thumb_tuck_dist < THUMB_TUCK_RATIO * _hand_scale(landmarks)


# ------------------------------------------------------------------
# Left hand: drive gesture classification (forward / backward / stop)
# ------------------------------------------------------------------
def classify_drive_gesture(landmarks):
    """
    Returns one of: 'forward', 'backward', 'stop'
    Requires a fist (4 fingers folded) with the thumb clearly extended
    and pointing up (forward) or down (backward). Two independent checks
    must agree so the gesture survives wrist rotation:
      1. Direction check: the MCP -> TIP vector of the thumb must be
         substantially vertical (within +/-30 deg of straight up/down).
      2. Position check: the thumb TIP must be clearly above (forward) or
         below (backward) the average y of the four other finger MCPs --
         this catches a thumb that *looks* vertical in isolation but is
         actually folded across the palm rather than extended outward.
    """
    if count_extended_fingers(landmarks) > 1:
        return "stop", 0.0

    thumb_vec_x = landmarks[THUMB_TIP].x - landmarks[THUMB_MCP].x
    thumb_vec_y = landmarks[THUMB_TIP].y - landmarks[THUMB_MCP].y
    angle_deg = math.degrees(math.atan2(-thumb_vec_y, thumb_vec_x))
    # angle_deg: 90 = straight up, -90 = straight down, 0/180 = sideways

    other_mcp_y = (
        landmarks[INDEX_MCP].y
        + landmarks[MIDDLE_MCP].y
        + landmarks[RING_MCP].y
        + landmarks[PINKY_MCP].y
    ) / 4.0
    thumb_tip_y = landmarks[THUMB_TIP].y
    # Image y increases downward, so "above" means a smaller y value.
    tip_above_knuckles = thumb_tip_y < other_mcp_y
    tip_below_knuckles = thumb_tip_y > other_mcp_y

    direction_is_up = 60 <= angle_deg <= 120
    direction_is_down = -120 <= angle_deg <= -60

    if direction_is_up and tip_above_knuckles:
        return "forward", angle_deg
    elif direction_is_down and tip_below_knuckles:
        return "backward", angle_deg
    else:
        return "stop", angle_deg


# ------------------------------------------------------------------
# Right hand: discrete turn classification (turn_left / turn_right / center)
# ------------------------------------------------------------------
def classify_turn_gesture(landmarks):
    """
    Returns (state, tilt_angle_deg) where state is one of
    'turn_left', 'turn_right', 'center', 'none'.

    Only fires while the hand reads as an open palm (rotation-invariant
    finger-extension check) -- this is the shape you found MediaPipe
    detects most reliably, and it's visually unambiguous against the
    closed fist used for 'shoot'.

    We don't need a proportional angle, only the *sign* of the tilt, so
    the wrist->middle-finger-MCP vector's deviation from vertical is
    bucketed against a fixed dead-zone instead of scaled to a range.
    """
    if not is_open_hand(landmarks):
        return "none", 0.0

    wrist = landmarks[WRIST]
    palm = landmarks[MIDDLE_MCP]
    vec_x = palm.x - wrist.x
    vec_y = palm.y - wrist.y
    angle_deg = math.degrees(math.atan2(-vec_y, vec_x))  # 90 = straight up
    tilt = angle_deg - 90.0  # 0 = perfectly upright

    # Normalize into [-180, 180] in case the hand is held upside-down.
    tilt = ((tilt + 180.0) % 360.0) - 180.0

    if tilt > TURN_DEADZONE_DEG:
        return "turn_left", tilt   # palm top leans toward image-left
    elif tilt < -TURN_DEADZONE_DEG:
        return "turn_right", tilt
    else:
        return "center", tilt


# ------------------------------------------------------------------
# Debounce helper: requires a gesture to persist for N frames before
# it "locks in" as the confirmed state. Used for drive and turn.
# ------------------------------------------------------------------
class GestureDebouncer:
    def __init__(self, hold_frames, default):
        self.hold_frames = hold_frames
        self.default = default
        self.candidate = default
        self.candidate_count = 0
        self.confirmed = default

    def update(self, new_gesture):
        if new_gesture == self.candidate:
            self.candidate_count += 1
        else:
            self.candidate = new_gesture
            self.candidate_count = 1

        if self.candidate_count >= self.hold_frames:
            self.confirmed = self.candidate

        return self.confirmed


# ------------------------------------------------------------------
# Shoot trigger: edge-detects the open-hand -> fist transition (after a
# short hold, to reject a single noisy frame) and fires exactly once,
# then enforces a cooldown before it can fire again.
# ------------------------------------------------------------------
class ShootTrigger:
    def __init__(self, hold_frames=SHOOT_HOLD_FRAMES, cooldown_sec=SHOOT_COOLDOWN_SEC):
        self.hold_frames = hold_frames
        self.cooldown_sec = cooldown_sec
        self.fist_streak = 0
        self.armed = True          # False while a fist is still being held / cooling down
        self.last_shot_time = 0.0
        self.ready_ratio = 1.0     # 0..1 cooldown progress, for the HUD

    def update(self, fist_detected, now):
        cooldown_remaining = self.cooldown_sec - (now - self.last_shot_time)
        self.ready_ratio = max(0.0, min(1.0, 1.0 - cooldown_remaining / self.cooldown_sec))

        if not fist_detected:
            self.fist_streak = 0
            if cooldown_remaining <= 0:
                self.armed = True
            return False

        self.fist_streak += 1

        if (
            self.armed
            and self.fist_streak >= self.hold_frames
            and cooldown_remaining <= 0
        ):
            self.armed = False
            self.last_shot_time = now
            self.ready_ratio = 0.0
            return True

        return False


# ------------------------------------------------------------------
# Visualization helpers
# ------------------------------------------------------------------
def ensure_model():
    if not MODEL_PATH.exists():
        print("Downloading MediaPipe hand landmark model...")
        with urlopen(MODEL_URL) as response, MODEL_PATH.open("wb") as model_file:
            model_file.write(response.read())


def draw_hand_landmarks(frame, hand_landmarks, color):
    h, w, _ = frame.shape
    points = [
        (int(landmark.x * w), int(landmark.y * h))
        for landmark in hand_landmarks
    ]
    for connection in HAND_CONNECTIONS:
        cv2.line(frame, points[connection.start], points[connection.end], color, 2)
    for point in points:
        cv2.circle(frame, point, 3, color, -1)


def put_text(frame, text, org, color=COL_WHITE, scale=0.6, thickness=1, shadow=True):
    if shadow:
        cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0),
                    thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                thickness, cv2.LINE_AA)


def glow_rect(frame, x, y, w, h, color, passes=3):
    """Cheap neon glow: draw a few progressively larger, blurred, faded
    copies of a filled rect underneath the sharp one on top."""
    glow = frame.copy()
    for i in range(passes, 0, -1):
        pad = i * 5
        overlay = frame.copy()
        cv2.rectangle(overlay, (x - pad, y - pad), (x + w + pad, y + h + pad), color, -1)
        overlay = cv2.GaussianBlur(overlay, (0, 0), sigmaX=pad + 2)
        alpha = 0.16 / i
        glow = cv2.addWeighted(overlay, alpha, glow, 1 - alpha, 0)
    frame[:] = glow
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, -1)


def draw_panel(frame, x, y, w, h, alpha=0.6, accent=COL_CYAN):
    """Dark glass panel with a glowing cyan seam along the top edge and
    corner tick marks, HUD-style."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), COL_BG, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    cv2.rectangle(frame, (x, y), (x + w, y + h), accent, 1)
    cv2.line(frame, (x, y), (x + w, y), accent, 2)

    tick = 10
    for (cx, cy, dx, dy) in [
        (x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)
    ]:
        cv2.line(frame, (cx, cy), (cx + dx * tick, cy), COL_WHITE, 2)
        cv2.line(frame, (cx, cy), (cx, cy + dy * tick), COL_WHITE, 2)


def draw_state_chip(frame, x, y, w, h, label, active, bright, dim):
    """Status chip: filled + glowing when active, thin colored outline
    (never plain grey) when idle, so it always reads as visible."""
    if active:
        glow_rect(frame, x, y, w, h, bright, passes=3)
        text_color = (12, 12, 12)
    else:
        cv2.rectangle(frame, (x, y), (x + w, y + h), dim, 1)
        text_color = dim
    text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0]
    tx = x + (w - text_size[0]) // 2
    ty = y + (h + text_size[1]) // 2
    put_text(frame, label, (tx, ty), color=text_color, scale=0.55, thickness=1, shadow=not active)


def draw_turn_gauge(frame, cx, cy, radius, tilt_deg, state):
    """A small arc gauge showing the raw tilt against the dead-zone, so
    you can visually tune TURN_DEADZONE_DEG while testing."""
    cv2.ellipse(frame, (cx, cy), (radius, radius), 0, 200, 340, COL_CYAN_DIM, 2)
    cv2.ellipse(frame, (cx, cy), (radius, radius), 0,
                270 - TURN_DEADZONE_DEG, 270 + TURN_DEADZONE_DEG, COL_INACTIVE, 4)

    needle_angle = 270 - max(-90, min(90, tilt_deg))
    end_x = int(cx + radius * math.cos(math.radians(needle_angle)))
    end_y = int(cy + radius * math.sin(math.radians(needle_angle)))
    color = COL_CYAN_DIM if state == "center" else COL_CYAN
    cv2.line(frame, (cx, cy), (end_x, end_y), color, 3)
    cv2.circle(frame, (cx, cy), 4, COL_WHITE, -1)


def draw_shoot_reticle(frame, cx, cy, ready_ratio, just_fired):
    color = COL_RED if just_fired else (COL_GREEN if ready_ratio >= 1.0 else COL_AMBER)
    size = 30 if just_fired else 20
    cv2.line(frame, (cx - size, cy), (cx - size // 2, cy), color, 2)
    cv2.line(frame, (cx + size, cy), (cx + size // 2, cy), color, 2)
    cv2.line(frame, (cx, cy - size), (cx, cy - size // 2), color, 2)
    cv2.line(frame, (cx, cy + size), (cx, cy + size // 2), color, 2)
    cv2.circle(frame, (cx, cy), 4 if just_fired else 2, color, -1)
    cv2.circle(frame, (cx, cy), size + 14, COL_INACTIVE, 1)
    if ready_ratio < 1.0 and not just_fired:
        cv2.ellipse(frame, (cx, cy), (size + 10, size + 10), 0, -90,
                    -90 + int(360 * ready_ratio), COL_AMBER, 2)


def draw_scanline(frame, w, h, now):
    """A slow-moving horizontal scanline across the whole frame for a
    sci-fi HUD feel."""
    y = int((now * 90) % h)
    overlay = frame.copy()
    cv2.line(overlay, (0, y), (w, y), COL_CYAN, 1)
    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)


def draw_frame_border(frame, w, h):
    cv2.rectangle(frame, (2, 2), (w - 3, h - 3), COL_INACTIVE, 1)


def draw_speed_meter(frame, x, y, w, h, speed_cap, speed_max):
    """Minimalist speed meter: a thin segmented bar, no glow/panel."""
    ratio = max(0.0, min(1.0, speed_cap / speed_max))
    segments = 8
    gap = 3
    seg_w = (w - gap * (segments - 1)) / segments
    filled = round(ratio * segments)
    for i in range(segments):
        sx = int(x + i * (seg_w + gap))
        color = COL_CYAN if i < filled else COL_INACTIVE
        cv2.rectangle(frame, (sx, y), (int(sx + seg_w), y + h), color,
                      -1 if i < filled else 1)
    put_text(frame, f"SPD {speed_cap:3d}", (x, y - 8), color=COL_CYAN, scale=0.45, thickness=1)


def draw_robot_status(frame, x, y, connected):
    label = "ROBOT: ONLINE" if connected else "ROBOT: OFFLINE"
    color = COL_GREEN if connected else COL_RED
    put_text(frame, label, (x, y), color=color, scale=0.5, thickness=1)


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------
def main():
    ensure_model()
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam.")
        return

    drive_debouncer = GestureDebouncer(DRIVE_HOLD_FRAMES, default="stop")
    turn_debouncer = GestureDebouncer(TURN_HOLD_FRAMES, default="none")
    shoot_trigger = ShootTrigger()
    speed_cap = SPEED_START

    bridge = None
    if RobotBridge is not None:
        bridge = RobotBridge()
        if not bridge.connect():
            print("[BRIDGE] No robot connected -- running in detection-only mode.")
            bridge = None
    else:
        print(f"[BRIDGE] robot_bridge unavailable ({_BRIDGE_IMPORT_ERROR}) -- detection-only mode.")

    hand_options = vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=2,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.6,
    )

    shoot_flash_until = 0.0

    with vision.HandLandmarker.create_from_options(hand_options) as hands:
        print("Left hand: thumb-up = forward, thumb-down = backward, fist(no thumb) = stop")
        print("Right hand: open hand tilt = turn left/right, closed fist = shoot")
        print("Keys: '+' speed up, '-' speed down, 'q' quit.")

        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            # Flip horizontally so the display is mirror-like AND so that
            # MediaPipe's handedness label matches the user's actual hand
            # (MediaPipe assumes a selfie/mirrored view by default).
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                            data=rgb_frame))

            h, w, _ = frame.shape
            now = time.time()

            raw_drive = "stop"
            raw_turn = "none"
            right_hand_seen = False
            left_hand_seen = False
            fist_now = False
            turn_tilt = 0.0
            right_wrist_px = None

            if results.hand_landmarks and results.handedness:
                for hand_landmarks, handedness in zip(
                    results.hand_landmarks, results.handedness
                ):
                    label = handedness[0].category_name  # 'Left' or 'Right'
                    if SWAP_HANDEDNESS:
                        label = "Right" if label == "Left" else "Left"

                    if label == "Left":
                        left_hand_seen = True
                        raw_drive, _ = classify_drive_gesture(hand_landmarks)
                        hand_color = (
                            COL_GREEN if raw_drive == "forward" else
                            COL_RED if raw_drive == "backward" else
                            COL_INACTIVE
                        )
                        draw_hand_landmarks(frame, hand_landmarks, hand_color)

                    elif label == "Right":
                        right_hand_seen = True
                        raw_turn, turn_tilt = classify_turn_gesture(hand_landmarks)
                        fist_now = is_fist(hand_landmarks)
                        right_wrist_px = (
                            int(hand_landmarks[WRIST].x * w),
                            int(hand_landmarks[WRIST].y * h),
                        )
                        hand_color = (
                            COL_MAGENTA if fist_now else
                            COL_CYAN if raw_turn in ("turn_left", "turn_right") else
                            COL_INACTIVE
                        )
                        draw_hand_landmarks(frame, hand_landmarks, hand_color)

            drive_state = drive_debouncer.update(raw_drive if left_hand_seen else "stop")
            turn_state = turn_debouncer.update(raw_turn if right_hand_seen else "none")
            shot_fired = shoot_trigger.update(fist_now, now)
            if shot_fired:
                shoot_flash_until = now + 0.15

            # --- Build payload and dispatch every frame ---------------
            resolved_turn = turn_state if turn_state != "none" else "center"
            payload = {
                "drive": drive_state,
                "turn": resolved_turn,
                "shoot": shot_fired,
                "timestamp": now,
            }
            robot_func(payload)
            if bridge is not None:
                if bridge.connected:
                    bridge.update(drive_state, resolved_turn, shot_fired, now)
                else:
                    bridge = None  # link dropped -- fall back to detection-only

            # =====================================================
            # HUD
            # =====================================================
            draw_frame_border(frame, w, h)
            draw_scanline(frame, w, h, now)

            draw_panel(frame, 10, 10, 300, 122, accent=COL_CYAN)

            put_text(frame, "// GESTURE CONTROL", (22, 32), color=COL_CYAN, scale=0.65, thickness=2)

            # Drive chip row
            put_text(frame, "DRIVE", (22, 55), color=COL_INACTIVE, scale=0.45)
            draw_state_chip(frame, 22, 61, 80, 26, "FORWARD", drive_state == "forward", COL_GREEN, COL_GREEN_DIM)
            draw_state_chip(frame, 108, 61, 80, 26, "BACK", drive_state == "backward", COL_RED, COL_RED_DIM)
            draw_state_chip(frame, 194, 61, 100, 26, "STOP", drive_state == "stop", COL_AMBER, COL_INACTIVE)

            # Turn chip row
            put_text(frame, "TURN", (22, 101), color=COL_INACTIVE, scale=0.45)
            draw_state_chip(frame, 22, 107, 80, 26, "LEFT", turn_state == "turn_left", COL_CYAN, COL_CYAN_DIM)
            draw_state_chip(frame, 108, 107, 80, 26, "RIGHT", turn_state == "turn_right", COL_CYAN, COL_CYAN_DIM)
            draw_state_chip(frame, 194, 107, 100, 26, "CENTER", turn_state == "center", COL_AMBER, COL_INACTIVE)

            # Hand-presence indicators (top-right)
            put_text(frame, f"L:{'ON-LINE' if left_hand_seen else 'OFF'}", (w - 175, 30),
                     color=COL_GREEN if left_hand_seen else COL_INACTIVE, scale=0.55)
            put_text(frame, f"R:{'ON-LINE' if right_hand_seen else 'OFF'}", (w - 175, 55),
                     color=COL_GREEN if right_hand_seen else COL_INACTIVE, scale=0.55)

            # Turn tuning gauge, anchored near the right wrist if visible,
            # else parked in the corner.
            gauge_center = right_wrist_px if right_wrist_px else (w - 70, 90)
            draw_turn_gauge(frame, gauge_center[0], gauge_center[1] - 40, 45, turn_tilt, turn_state)

            # Shoot reticle, center screen; flashes red briefly on a hit.
            just_fired_flash = now < shoot_flash_until
            draw_shoot_reticle(frame, w // 2, h // 2, shoot_trigger.ready_ratio, just_fired_flash)
            if just_fired_flash:
                put_text(frame, "SHOOT", (w // 2 - 34, h // 2 - 34), color=COL_RED, scale=0.8, thickness=2)

            # Minimalist speed meter + robot link status, bottom-left.
            draw_robot_status(frame, 22, h - 55, bridge is not None)
            draw_speed_meter(frame, 22, h - 24, 160, 10, speed_cap, SPEED_MAX)

            cv2.imshow("Gesture Control", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key in (ord("+"), ord("=")):
                speed_cap = min(speed_cap + SPEED_STEP, SPEED_MAX)
                if bridge is not None:
                    bridge.speed_up()
            elif key == ord("-"):
                speed_cap = max(speed_cap - SPEED_STEP, SPEED_MIN)
                if bridge is not None:
                    bridge.speed_down()

    if bridge is not None:
        bridge.disconnect()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
