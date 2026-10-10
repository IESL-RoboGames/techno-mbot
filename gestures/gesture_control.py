"""
Two-Hand Gesture Control System for Robot Teleoperation
=========================================================
Left Hand  -> Drive     (Open palm facing camera = forward, back of hand facing camera = backward,
                         anything else = stop)
Right Hand -> Turn      (Open hand tilted left/right -> discrete turn_left/turn_right/center)
Right Hand -> Shoot     (Closed fist, thumb tucked -> one-shot trigger with cooldown)
Both Hands -> Celebrate (Two closed fists held together -> one-shot trigger with cooldown)

Commands go to the robot through robot_bridge.py when a robot is connected;
otherwise this runs detection-only.
"""

import cv2
import math
import json
import random
import time
from collections import deque

import numpy as np
from pathlib import Path
from urllib.request import urlopen

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

try:
    from robot_bridge import RobotBridge
except Exception as _bridge_import_error:  # e.g. pyserial not installed, or techno-mbot missing
    RobotBridge = None
    _BRIDGE_IMPORT_ERROR = _bridge_import_error
else:
    _BRIDGE_IMPORT_ERROR = None

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
DRIVE_HOLD_FRAMES = 5          # frames a drive gesture must persist to "lock in"
TURN_HOLD_FRAMES = 4           # frames a turn gesture must persist to "lock in"
TURN_DEADZONE_DEG = 15.0       # tilt beyond this angle (from vertical) registers a turn
# One-shot gestures fire on a vote over the last `WINDOW` frames rather than
# a consecutive streak, so a single dropped/misread frame doesn't reset them.
SHOOT_WINDOW, SHOOT_NEED, SHOOT_RELEASE = 5, 3, 1
SHOOT_COOLDOWN_SEC = 0.6       # minimum time between consecutive shots
CELEBRATE_WINDOW, CELEBRATE_NEED, CELEBRATE_RELEASE = 9, 6, 2
CELEBRATE_COOLDOWN_SEC = 2.5   # minimum time between celebrations (the wiggle itself takes ~0.7s)
LEFT_FIST_SUPPRESS_FRAMES = 6  # shoot is blocked if the left hand was a fist in any of these recent frames

CURL_TIP_TO_MCP_RATIO = 0.55   # fingertip this close to its own knuckle (relative to palm size) = curled
HAND_STICKY_DIST = 0.15        # one visible hand within this fraction of frame width of a side's last wrist keeps that side
HAND_MEMORY_SEC = 0.5          # forget a side's last wrist position after this long unseen

SHOOT_FX_SEC = 0.8             # how long the on-screen shoot effect lasts
CELEBRATE_FX_SEC = 2.2         # how long the celebrate banner lasts (confetti keeps falling a bit longer)
FIREWORK_SEC = 0.9             # lifetime of each firework burst
CONFETTI_COUNT = 120

# Palm vs back-of-hand is read from the sign of the 2D cross product of
# (wrist->index MCP) x (wrist->pinky MCP) in the mirrored display. For the
# drive (left) hand with the palm facing the camera that sign is negative.
# Flip this to +1 if forward/backward come out swapped on your setup.
PALM_FACING_CROSS_SIGN = -1
ORIENTATION_MIN_SIN = 0.25     # |sin| of the index/pinky spread below this = hand edge-on, orientation unknown

EXTEND_RATIO = 1.15           # tip-to-wrist must exceed pip-to-wrist by this ratio to count as "extended"

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
        {"drive": "forward", "turn": "turn_left", "shoot": false, "celebrate": false, "timestamp": ...}
        drive:     "forward" | "backward" | "stop"
        turn:      "turn_left" | "turn_right" | "center"
        shoot:     True only on the single frame a shot fires, else False
        celebrate: True only on the single frame a celebration fires, else False
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
    used to normalize distance checks."""
    return _dist(landmarks[WRIST], landmarks[MIDDLE_MCP]) or 1e-6


def finger_extended(landmarks, tip_idx, pip_idx):
    wrist = landmarks[WRIST]
    return _dist(wrist, landmarks[tip_idx]) > _dist(wrist, landmarks[pip_idx]) * EXTEND_RATIO


def count_extended_fingers(landmarks):
    return sum(1 for tip, pip in FINGER_TIPS_PIPS if finger_extended(landmarks, tip, pip))


def is_open_hand(landmarks):
    """>=3 of the 4 non-thumb fingers clearly extended."""
    return count_extended_fingers(landmarks) >= 3


FINGER_TIPS_PIPS_MCPS = [
    (INDEX_TIP, INDEX_PIP, INDEX_MCP),
    (MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP),
    (RING_TIP, RING_PIP, RING_MCP),
    (PINKY_TIP, PINKY_PIP, PINKY_MCP),
]


def finger_curled(landmarks, tip_idx, pip_idx, mcp_idx):
    """Tip folded back closer to the wrist than its middle joint, OR tip
    right next to its own knuckle. The second test catches fists pointed
    at the camera, where foreshortening squashes wrist distances."""
    wrist, tip = landmarks[WRIST], landmarks[tip_idx]
    if _dist(wrist, tip) < _dist(wrist, landmarks[pip_idx]):
        return True
    return _dist(tip, landmarks[mcp_idx]) < CURL_TIP_TO_MCP_RATIO * _hand_scale(landmarks)


def is_fist(landmarks):
    """>=3 of the 4 non-thumb fingers curled (the thumb can be anywhere),
    and never more than one finger extended -- so a fist and an open hand
    can never both be true for the same hand."""
    if count_extended_fingers(landmarks) > 1:
        return False
    curled = sum(1 for tip, pip, mcp in FINGER_TIPS_PIPS_MCPS if finger_curled(landmarks, tip, pip, mcp))
    return curled >= 3


# ------------------------------------------------------------------
# Left hand: drive gesture classification (forward / backward / stop)
# ------------------------------------------------------------------
def palm_orientation(landmarks):
    """
    Which side of the hand faces the camera: 'palm', 'back', or None when
    the hand is edge-on / ambiguous.

    Uses the sign of the cross product of (wrist->index MCP) x
    (wrist->pinky MCP). Turning the hand over flips that sign, and the
    sign is unaffected by rotating the hand in the image plane, so it
    works at any wrist angle. Normalized by the vector lengths so it's
    independent of hand size / distance from the camera.
    """
    wrist = landmarks[WRIST]
    ix = landmarks[INDEX_MCP].x - wrist.x
    iy = landmarks[INDEX_MCP].y - wrist.y
    px = landmarks[PINKY_MCP].x - wrist.x
    py = landmarks[PINKY_MCP].y - wrist.y

    norm = math.hypot(ix, iy) * math.hypot(px, py)
    if norm == 0:
        return None

    sin_spread = (ix * py - iy * px) / norm
    if abs(sin_spread) < ORIENTATION_MIN_SIN:
        return None

    return "palm" if sin_spread * PALM_FACING_CROSS_SIGN > 0 else "back"


def classify_drive_gesture(landmarks):
    """
    Returns (state, orientation) where state is one of
    'forward', 'backward', 'stop'.

    Only an open hand counts: palm facing the camera -> 'forward', back of
    the hand facing the camera -> 'backward'. A fist, a half-open hand, or
    an edge-on hand all read as 'stop', so the robot only moves on a
    deliberate, unambiguous gesture.
    """
    if not is_open_hand(landmarks):
        return "stop", None

    orientation = palm_orientation(landmarks)
    if orientation == "palm":
        return "forward", orientation
    if orientation == "back":
        return "backward", orientation
    return "stop", orientation


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
# One-shot trigger (used for shoot and celebrate): fires once when the
# condition is seen in at least `need` of the last `window` frames, so a
# dropped or misread frame doesn't reset it. It re-arms only after the
# condition has mostly released (<= `release` of the window) -- hysteresis,
# so a held gesture can't fire twice -- and a cooldown must also elapse.
# ------------------------------------------------------------------
class OneShotTrigger:
    def __init__(self, window, need, release, cooldown_sec):
        self.need = need
        self.release = release
        self.cooldown_sec = cooldown_sec
        self.history = deque(maxlen=window)
        self.armed = True
        self.last_fire_time = -1e9
        self.ready_ratio = 1.0     # 0..1 cooldown progress, for the HUD

    def update(self, condition_active, now):
        self.history.append(bool(condition_active))
        count = sum(self.history)
        cooldown_remaining = self.cooldown_sec - (now - self.last_fire_time)
        self.ready_ratio = max(0.0, min(1.0, 1.0 - cooldown_remaining / self.cooldown_sec))

        if count <= self.release:
            self.armed = True

        if self.armed and count >= self.need and cooldown_remaining <= 0:
            self.armed = False
            self.last_fire_time = now
            self.ready_ratio = 0.0
            return True
        return False


# ------------------------------------------------------------------
# Hand assignment: decides which detected hand is the user's left (DRIVE)
# and which is the right (STEER). MediaPipe's Left/Right label is weakest
# on fists -- two fists often get the *same* label -- so with two hands
# visible we go purely by position in the mirrored display, and with one
# hand we prefer continuity with where each side was last seen.
# ------------------------------------------------------------------
class HandAssigner:
    def __init__(self):
        self.last_wrist = {"Left": None, "Right": None}   # (x, y, time) in normalized coords

    def assign(self, hand_landmarks_list, handedness_list, now):
        sides = {"Left": None, "Right": None}
        hands = list(zip(hand_landmarks_list or [], handedness_list or []))

        if len(hands) >= 2:
            ordered = sorted(hands[:2], key=lambda hl: hl[0][WRIST].x)
            sides["Left"], sides["Right"] = ordered[0][0], ordered[1][0]
        elif len(hands) == 1:
            landmarks, handedness = hands[0]
            sides[self._side_for_single(landmarks, handedness, now)] = landmarks

        for side, landmarks in sides.items():
            if landmarks is not None:
                self.last_wrist[side] = (landmarks[WRIST].x, landmarks[WRIST].y, now)
            elif self.last_wrist[side] and now - self.last_wrist[side][2] > HAND_MEMORY_SEC:
                self.last_wrist[side] = None
        return sides

    def _side_for_single(self, landmarks, handedness, now):
        wx, wy = landmarks[WRIST].x, landmarks[WRIST].y
        best_side, best_dist = None, HAND_STICKY_DIST
        for side, last in self.last_wrist.items():
            if last is None or now - last[2] > HAND_MEMORY_SEC:
                continue
            d = math.hypot(wx - last[0], wy - last[1])
            if d < best_dist:
                best_side, best_dist = side, d
        if best_side:
            return best_side
        label = handedness[0].category_name
        if SWAP_HANDEDNESS:
            label = "Right" if label == "Left" else "Left"
        return label


# ------------------------------------------------------------------
# Visualization
# ------------------------------------------------------------------
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_BOLD = cv2.FONT_HERSHEY_DUPLEX
PANEL_ALPHA = 0.62

COMMAND_LABELS = {
    ("forward", "center"): ("FORWARD", "w"),
    ("forward", "turn_left"): ("ARC FWD-LEFT", "q"),
    ("forward", "turn_right"): ("ARC FWD-RIGHT", "e"),
    ("backward", "center"): ("BACKWARD", "s"),
    ("backward", "turn_left"): ("ARC BACK-LEFT", "z"),
    ("backward", "turn_right"): ("ARC BACK-RIGHT", "c"),
    ("stop", "center"): ("STOP", "space"),
    ("stop", "turn_left"): ("PIVOT LEFT", "a"),
    ("stop", "turn_right"): ("PIVOT RIGHT", "d"),
}

CONFETTI_COLORS = [COL_GREEN, COL_RED, COL_AMBER, COL_CYAN, COL_MAGENTA, COL_WHITE]
FIREWORK_COLORS = [COL_AMBER, COL_CYAN, COL_MAGENTA, COL_GREEN]

_ARROW = [(0, -1), (0.85, 0.05), (0.35, 0.05), (0.35, 0.9), (-0.35, 0.9), (-0.35, 0.05), (-0.85, 0.05)]
_TRIANGLE = [(0, -1), (0.9, 0.7), (-0.9, 0.7)]
_ROTATE = {
    "up": lambda x, y: (x, y),
    "down": lambda x, y: (x, -y),
    "left": lambda x, y: (y, x),
    "right": lambda x, y: (-y, x),
}


def ensure_model():
    if not MODEL_PATH.exists():
        print("Downloading MediaPipe hand landmark model...")
        with urlopen(MODEL_URL) as response, MODEL_PATH.open("wb") as model_file:
            model_file.write(response.read())


def hud_scale(w):
    """Layout is designed at 640px wide and scaled proportionally."""
    return w / 640.0


def put_text(frame, text, org, color=COL_WHITE, scale=0.6, thickness=1, shadow=True, font=FONT):
    x, y = int(org[0]), int(org[1])
    if shadow:
        # Same thickness, offset copies: a thicker shadow would drift right,
        # because Hershey glyph advance grows with stroke thickness.
        d = max(1, thickness)
        for dx, dy in ((d, d), (-d, -d), (d, -d), (-d, d)):
            cv2.putText(frame, text, (x + dx, y + dy), font, scale, (0, 0, 0), thickness, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def text_width(text, scale, thickness=1, font=FONT):
    return cv2.getTextSize(text, font, scale, thickness)[0][0]


def put_text_centered(frame, text, cx, baseline_y, color, scale, thickness=1, font=FONT, shadow=True):
    x = cx - text_width(text, scale, thickness, font) / 2
    put_text(frame, text, (x, baseline_y), color, scale, thickness, shadow, font)


def scale_color(color, k):
    return tuple(int(c * k) for c in color)


def hue_color(phase):
    hsv = np.uint8([[[int(phase * 180) % 180, 230, 255]]])
    return tuple(int(c) for c in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])


def glow_rect(frame, x, y, w, h, color, spread=10):
    """Neon glow: one blurred halo added around a filled rect. Works on a
    downscaled region of interest only, so it stays cheap per frame."""
    fh, fw = frame.shape[:2]
    reach = spread * 2
    x0, y0 = max(0, x - reach), max(0, y - reach)
    x1, y1 = min(fw, x + w + reach), min(fh, y + h + reach)
    if x1 <= x0 or y1 <= y0:
        return
    roi = frame[y0:y1, x0:x1]
    small = cv2.resize(np.zeros_like(roi), None, fx=0.25, fy=0.25)
    q = lambda v: int(v * 0.25)
    cv2.rectangle(small, (q(x - x0), q(y - y0)), (q(x + w - x0), q(y + h - y0)), color, -1)
    small = cv2.GaussianBlur(small, (0, 0), sigmaX=max(1.0, spread * 0.25))
    halo = cv2.resize(small, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_LINEAR)
    cv2.addWeighted(roi, 1.0, halo, 0.8, 0, roi)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, -1)


def draw_pill(frame, cx, cy, w, h, color, thickness=1, fill=None):
    r = h // 2
    x0, x1, cy = int(cx - w / 2 + r), int(cx + w / 2 - r), int(cy)
    if fill is not None:
        cv2.rectangle(frame, (x0, cy - r), (x1, cy + r), fill, -1)
        cv2.circle(frame, (x0, cy), r, fill, -1, cv2.LINE_AA)
        cv2.circle(frame, (x1, cy), r, fill, -1, cv2.LINE_AA)
    cv2.line(frame, (x0, cy - r), (x1, cy - r), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x0, cy + r), (x1, cy + r), color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (x0, cy), (r, r), 0, 90, 270, color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (x1, cy), (r, r), 0, -90, 90, color, thickness, cv2.LINE_AA)


def draw_corner_brackets(frame, x0, y0, x1, y1, length, color, thickness):
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        cv2.line(frame, (cx, cy), (cx + dx * length, cy), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * length), color, thickness, cv2.LINE_AA)


def draw_icon(frame, shape, cx, cy, size, direction, color, filled):
    rot = _ROTATE[direction]
    pts = np.array([[cx + rot(x, y)[0] * size, cy + rot(x, y)[1] * size] for x, y in shape], np.int32)
    if filled:
        cv2.fillPoly(frame, [pts], color, cv2.LINE_AA)
    else:
        cv2.polylines(frame, [pts], True, color, max(1, int(size / 9)), cv2.LINE_AA)


def draw_hand_landmarks(frame, hand_landmarks, color, tag, s):
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand_landmarks]
    line_w = max(1, int(round(1.5 * s)))
    for connection in HAND_CONNECTIONS:
        cv2.line(frame, pts[connection.start], pts[connection.end], color, line_w, cv2.LINE_AA)
    r = max(2, int(round(2.5 * s)))
    for p in pts:
        cv2.circle(frame, p, r + 1, color, -1, cv2.LINE_AA)
        cv2.circle(frame, p, max(1, r - 1), COL_WHITE, -1, cv2.LINE_AA)
    wx, wy = pts[WRIST]
    put_text_centered(frame, tag, wx, wy + 20 * s, color, 0.42 * s, max(1, int(round(s))), FONT_BOLD)


def draw_turn_gauge(frame, cx, cy, radius, tilt_deg, state, s):
    """Arc gauge of the raw tilt against the dead-zone band."""
    th = max(1, int(round(2 * s)))
    cv2.ellipse(frame, (cx, cy), (radius, radius), 0, 200, 340, COL_CYAN_DIM, th, cv2.LINE_AA)
    band = COL_AMBER if state == "center" else COL_INACTIVE
    cv2.ellipse(frame, (cx, cy), (radius, radius), 0,
                270 - TURN_DEADZONE_DEG, 270 + TURN_DEADZONE_DEG, band, th * 2, cv2.LINE_AA)

    needle_angle = 270 - max(-70, min(70, tilt_deg))
    end_x = int(cx + radius * math.cos(math.radians(needle_angle)))
    end_y = int(cy + radius * math.sin(math.radians(needle_angle)))
    color = (COL_CYAN if state in ("turn_left", "turn_right")
             else COL_AMBER if state == "center" else COL_INACTIVE)
    cv2.line(frame, (cx, cy), (end_x, end_y), color, th + 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), max(2, int(round(3 * s))), COL_WHITE, -1, cv2.LINE_AA)


def draw_reticle(frame, cx, cy, s, ready_ratio, firing):
    color = COL_RED if firing else (COL_GREEN if ready_ratio >= 1.0 else COL_AMBER)
    size, gap = int(12 * s), int(5 * s)
    th = max(1, int(round(1.5 * s)))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(frame, (cx + dx * gap, cy + dy * gap), (cx + dx * size, cy + dy * size), color, th, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), max(1, int(1.5 * s)), color, -1, cv2.LINE_AA)
    if ready_ratio < 1.0 and not firing:
        r = size + int(5 * s)
        cv2.ellipse(frame, (cx, cy), (r, r), 0, -90, -90 + int(360 * ready_ratio), COL_AMBER, th, cv2.LINE_AA)


# ------------------------------------------------------------------
# Effects: shoot flash and celebration (confetti + fireworks + banner)
# ------------------------------------------------------------------
class HudFx:
    def __init__(self):
        self.shoot_at = None
        self.celebrate_at = None
        self.confetti = []     # [x, y, vx, vy, angle, spin, size, color]
        self.bursts = []       # (start_time, x, y, color)
        self._last_now = None

    def trigger_shoot(self, now):
        self.shoot_at = now

    def trigger_celebrate(self, now, w, h):
        s = hud_scale(w)
        self.celebrate_at = now
        for _ in range(CONFETTI_COUNT):
            self.confetti.append([
                random.uniform(0, w), random.uniform(-0.35 * h, -5),
                random.uniform(-70, 70) * s, random.uniform(40, 170) * s,
                random.uniform(0, math.pi), random.uniform(-8, 8),
                random.uniform(4, 8) * s, random.choice(CONFETTI_COLORS),
            ])
        self.bursts = [
            (now + delay, random.uniform(0.25, 0.75) * w, random.uniform(0.25, 0.55) * h,
             random.choice(FIREWORK_COLORS))
            for delay in (0.0, 0.35, 0.7)
        ]

    def shoot_t(self, now):
        if self.shoot_at is None:
            return None
        t = (now - self.shoot_at) / SHOOT_FX_SEC
        return t if 0 <= t < 1 else None

    def celebrate_t(self, now):
        if self.celebrate_at is None:
            return None
        t = (now - self.celebrate_at) / CELEBRATE_FX_SEC
        return t if 0 <= t < 1 else None

    def draw(self, frame, now):
        h, w = frame.shape[:2]
        s = hud_scale(w)
        dt = 0.0 if self._last_now is None else min(0.1, max(0.0, now - self._last_now))
        self._last_now = now

        shoot_t = self.shoot_t(now)
        if shoot_t is not None:
            self._draw_shoot_flash(frame, shoot_t, w, h, s)
        self._draw_fireworks(frame, now, s)
        self._update_and_draw_confetti(frame, dt, h, s)
        if shoot_t is not None and shoot_t < 0.85:
            self._draw_shoot_banner(frame, shoot_t, w, s)
        celebrate_t = self.celebrate_t(now)
        if celebrate_t is not None:
            self._draw_celebrate_banner(frame, celebrate_t, now, w, h, s)

    def _draw_shoot_flash(self, frame, t, w, h, s):
        # Thick red screen-edge flash, visible wherever the hands are.
        alpha = 0.75 * (1 - t) ** 1.4
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w - 1, h - 1), COL_RED, int(22 * s))
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        if t < 0.45:
            cv2.rectangle(frame, (1, 1), (w - 2, h - 2), COL_RED, max(2, int(3 * s)))

        # Shockwave rings expanding from the reticle.
        cx, cy = w // 2, h // 2
        for k in range(3):
            tk = (t - k * 0.12) / 0.6
            if 0 < tk < 1:
                r = int((14 + 150 * (1 - (1 - tk) ** 2)) * s)
                color = COL_RED if k % 2 == 0 else COL_AMBER
                cv2.circle(frame, (cx, cy), r, color, max(1, int(4 * s * (1 - tk))), cv2.LINE_AA)

    def _draw_shoot_banner(self, frame, t, w, s):
        pop = 1.0 + 0.35 * max(0.0, 1 - t / 0.15)
        scale = 1.15 * s * pop
        thickness = max(2, int(round(2 * s * pop)))
        text = "SHOOT!"
        (tw, th), _ = cv2.getTextSize(text, FONT_BOLD, scale, thickness)
        pad = int(14 * s)
        cy = int(76 * s)
        x0, y0 = w // 2 - tw // 2 - pad, cy - th // 2 - pad
        glow_rect(frame, x0, y0, tw + 2 * pad, th + 2 * pad, COL_RED, spread=int(14 * s))
        put_text(frame, text, (w // 2 - tw // 2, cy + th // 2), COL_WHITE, scale, thickness, True, FONT_BOLD)

    def _draw_fireworks(self, frame, now, s):
        for start, bx, by, color in self.bursts:
            tk = (now - start) / FIREWORK_SEC
            if not 0 <= tk < 1:
                continue
            r = 80 * s * (1 - (1 - tk) ** 3)
            fade = 1 - tk
            spark = scale_color(color, 0.35 + 0.65 * fade)
            droop = 25 * s * tk * tk
            for i in range(16):
                ang = i * math.tau / 16
                ca, sa = math.cos(ang), math.sin(ang)
                p0 = (int(bx + ca * r * 0.55), int(by + sa * r * 0.55 + droop))
                p1 = (int(bx + ca * r), int(by + sa * r + droop))
                cv2.line(frame, p0, p1, spark, max(1, int(round(2 * s))), cv2.LINE_AA)
                cv2.circle(frame, p1, max(1, int(round((2.5 * fade + 1) * s))),
                           COL_WHITE if tk < 0.3 else spark, -1, cv2.LINE_AA)
            if tk < 0.15:
                cv2.circle(frame, (int(bx), int(by)), int(10 * s * (1 - tk / 0.15)) + 1, COL_WHITE, -1, cv2.LINE_AA)
        self.bursts = [b for b in self.bursts if now - b[0] < FIREWORK_SEC]

    def _update_and_draw_confetti(self, frame, dt, h, s):
        gravity, terminal = 260 * s, 220 * s
        alive = []
        for p in self.confetti:
            x, y, vx, vy, ang, spin, size, color = p
            vy = min(vy + gravity * dt, terminal)
            vx *= (1 - 0.6 * dt)
            x += vx * dt + math.sin(ang * 2) * 20 * s * dt
            y += vy * dt
            ang += spin * dt
            if y > h + 20:
                continue
            p[0], p[1], p[2], p[3], p[4] = x, y, vx, vy, ang
            alive.append(p)
            if y < -10:
                continue
            half_w = size * (0.35 + 0.65 * abs(math.cos(ang))) / 2
            half_h = size * 0.3
            ca, sa = math.cos(ang), math.sin(ang)
            pts = np.array([[x + dx * ca - dy * sa, y + dx * sa + dy * ca]
                            for dx, dy in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h))],
                           np.int32)
            cv2.fillPoly(frame, [pts], color, cv2.LINE_AA)
        self.confetti = alive

    def _draw_celebrate_banner(self, frame, t, now, w, h, s):
        color = hue_color((now * 0.9) % 1.0)
        bounce = 1 + 0.08 * math.sin(t * math.tau * 3)
        grow = 0.6 + 0.4 * min(1.0, t / 0.08)
        scale = 1.05 * s * bounce * grow
        thickness = max(2, int(round(2 * s)))
        text = "GOAL!  CELEBRATE"
        (tw, th), _ = cv2.getTextSize(text, FONT_BOLD, scale, thickness)
        pad = int(16 * s)
        cy = int(h * 0.66)
        x0, y0 = w // 2 - tw // 2 - pad, cy - th // 2 - pad
        x1, y1 = x0 + tw + 2 * pad, y0 + th + 2 * pad
        cv2.rectangle(frame, (x0, y0), (x1, y1), COL_BG, -1)
        cv2.rectangle(frame, (x0, y0), (x1, y1), color, max(2, int(2 * s)), cv2.LINE_AA)
        e = int(6 * s)
        draw_corner_brackets(frame, x0 - e, y0 - e, x1 + e, y1 + e, int(14 * s), COL_WHITE, max(1, int(2 * s)))
        put_text(frame, text, (w // 2 - tw // 2, cy + th // 2), color, scale, thickness, True, FONT_BOLD)


# ------------------------------------------------------------------
# HUD
# ------------------------------------------------------------------
def render_hud(frame, st, fx, now):
    """Draws the whole HUD for one frame. `st` holds the current gesture
    state (see main()); `fx` owns the shoot/celebrate effects."""
    h, w = frame.shape[:2]
    s = hud_scale(w)

    def S(v):
        return int(round(v * s))

    tk = max(1, S(1))
    celebrating = fx.celebrate_t(now) is not None
    shoot_t = fx.shoot_t(now)
    accent = hue_color((now * 0.7) % 1.0) if celebrating else COL_CYAN
    pulse_th = max(1, S(2 + (2 * abs(math.sin(now * 8)) if celebrating else 0)))

    bar_h = S(30)
    lc = (S(10), bar_h + S(10), S(150), S(118))          # left card: x, y, w, h
    rc = (w - S(160), bar_h + S(10), S(150), S(150))     # right card
    strip_w, strip_h, strip_cy = S(250), S(26), h - S(44)
    legend_h = S(22)

    # --- translucent backgrounds, batched into a single blend ---------
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), COL_BG, -1)
    for x, y, cw, ch in (lc, rc):
        cv2.rectangle(overlay, (x, y), (x + cw, y + ch), COL_BG, -1)
    draw_pill(overlay, w // 2, strip_cy, strip_w, strip_h, COL_BG, fill=COL_BG)
    cv2.rectangle(overlay, (0, h - legend_h), (w, h), COL_BG, -1)
    scan_y = int((now * 70) % h)
    cv2.line(overlay, (0, scan_y), (w, scan_y), COL_CYAN, 1)
    cv2.addWeighted(overlay, PANEL_ALPHA, frame, 1 - PANEL_ALPHA, 0, frame)

    # --- frame chrome ---------------------------------------------------
    draw_corner_brackets(frame, 3, 3, w - 4, h - 4, S(28), accent, pulse_th)

    # --- top bar --------------------------------------------------------
    cv2.line(frame, (0, bar_h), (w, bar_h), accent, pulse_th, cv2.LINE_AA)
    put_text(frame, "MBOT // GESTURE LINK", (S(12), S(20)), accent, 0.48 * s, tk, font=FONT_BOLD)

    online = st["robot_online"]
    status_col = COL_GREEN if online else COL_RED
    pill_w, pill_cx, pill_cy = S(165), w // 2 + S(20), bar_h // 2
    draw_pill(frame, pill_cx, pill_cy, pill_w, S(20), status_col, tk)
    pulse = 0.5 + 0.5 * math.sin(now * 5)
    dot_x = pill_cx - pill_w // 2 + S(14)
    cv2.circle(frame, (dot_x, pill_cy), S(4) + int(S(3) * pulse), scale_color(status_col, 0.45), tk, cv2.LINE_AA)
    cv2.circle(frame, (dot_x, pill_cy), S(4), status_col, -1, cv2.LINE_AA)
    put_text(frame, "ROBOT ONLINE" if online else "ROBOT OFFLINE", (dot_x + S(12), pill_cy + S(5)),
             status_col, 0.42 * s, tk, font=FONT_BOLD)

    fps_text = f"{st['fps']:.0f} FPS"
    put_text(frame, fps_text, (w - S(12) - text_width(fps_text, 0.45 * s, tk), S(20)), COL_CYAN, 0.45 * s, tk)

    # --- left card: DRIVE ----------------------------------------------
    x, y, cw, ch = lc
    left_seen, drive = st["left_seen"], st["drive"]
    drive_col = {"forward": COL_GREEN, "backward": COL_RED}.get(drive, COL_AMBER)
    edge = drive_col if left_seen else COL_INACTIVE
    cv2.rectangle(frame, (x, y), (x + cw, y + ch), scale_color(edge, 0.6), 1, cv2.LINE_AA)
    draw_corner_brackets(frame, x, y, x + cw, y + ch, S(10), accent if celebrating else edge, max(1, S(2)))
    put_text(frame, "LEFT  |  DRIVE", (x + S(10), y + S(17)), COL_CYAN, 0.4 * s, tk, font=FONT_BOLD)
    cv2.line(frame, (x + S(8), y + S(24)), (x + cw - S(8), y + S(24)), COL_CYAN_DIM, 1, cv2.LINE_AA)
    icx, icy = x + cw // 2, y + S(56)
    if not left_seen:
        put_text_centered(frame, "NO HAND", icx, y + S(66), COL_AMBER, 0.6 * s, tk, FONT_BOLD)
        put_text_centered(frame, "show your left hand", icx, y + S(90), COL_CYAN, 0.38 * s, tk)
    else:
        if drive == "forward":
            draw_icon(frame, _ARROW, icx, icy, S(22), "up", drive_col, True)
        elif drive == "backward":
            draw_icon(frame, _ARROW, icx, icy, S(22), "down", drive_col, True)
        else:
            half = S(13)
            cv2.rectangle(frame, (icx - half, icy - half), (icx + half, icy + half), drive_col, -1, cv2.LINE_AA)
        word = {"forward": "FORWARD", "backward": "BACKWARD"}.get(drive, "STOP")
        put_text_centered(frame, word, icx, y + S(97), drive_col, 0.6 * s, tk, FONT_BOLD)
        put_text_centered(frame, f"read: {st['left_read']}", icx, y + S(112), COL_CYAN, 0.38 * s, tk)

    # --- right card: STEER + KICK -----------------------------------------
    x, y, cw, ch = rc
    right_seen, turn = st["right_seen"], st["turn"]
    edge = COL_CYAN if right_seen else COL_INACTIVE
    cv2.rectangle(frame, (x, y), (x + cw, y + ch), scale_color(edge, 0.6), 1, cv2.LINE_AA)
    draw_corner_brackets(frame, x, y, x + cw, y + ch, S(10), accent if celebrating else edge, max(1, S(2)))
    put_text(frame, "RIGHT  |  STEER", (x + S(10), y + S(17)), COL_CYAN, 0.4 * s, tk, font=FONT_BOLD)
    cv2.line(frame, (x + S(8), y + S(24)), (x + cw - S(8), y + S(24)), COL_CYAN_DIM, 1, cv2.LINE_AA)
    ccx = x + cw // 2
    for dx, direction, key in ((-40, "left", "turn_left"), (0, "up", "center"), (40, "right", "turn_right")):
        active = right_seen and turn == key
        col = (COL_AMBER if key == "center" else COL_CYAN) if active else COL_INACTIVE
        draw_icon(frame, _TRIANGLE, ccx + S(dx), y + S(44), S(11), direction, col, active)
    draw_turn_gauge(frame, ccx, y + S(100), S(30), st["tilt"], turn if right_seen else "none", s)
    if right_seen:
        put_text_centered(frame, f"read: {st['right_read']}", ccx, y + S(118), COL_CYAN, 0.38 * s, tk)
    else:
        put_text_centered(frame, "NO HAND", ccx, y + S(118), COL_AMBER, 0.42 * s, tk, FONT_BOLD)

    bx0, bx1, by0, by1 = x + S(46), x + cw - S(10), y + S(128), y + S(141)
    put_text(frame, "KICK", (x + S(10), by1 - S(1)), COL_CYAN, 0.4 * s, tk, font=FONT_BOLD)
    ready = st["kick_ready"]
    if shoot_t is not None and shoot_t < 0.6:
        fill, label, frac = (COL_RED if int(now * 16) % 2 == 0 else COL_WHITE), "KICK!", 1.0
    elif ready >= 1.0:
        fill, label, frac = COL_GREEN, "READY", 1.0
    else:
        fill, label, frac = COL_AMBER, "RELOAD", ready
    cv2.rectangle(frame, (bx0, by0), (bx1, by1), scale_color(fill, 0.6), 1)
    cv2.rectangle(frame, (bx0, by0), (bx0 + int((bx1 - bx0) * frac), by1), fill, -1)
    if frac >= 1.0:
        put_text_centered(frame, label, (bx0 + bx1) // 2, by1 - S(3), (12, 12, 12), 0.36 * s, tk, FONT_BOLD, shadow=False)
    else:
        put_text_centered(frame, label, (bx0 + bx1) // 2, by1 - S(3), COL_WHITE, 0.36 * s, tk, FONT_BOLD)

    # --- reticle -------------------------------------------------------
    draw_reticle(frame, w // 2, h // 2, s, ready, shoot_t is not None and shoot_t < 0.5)

    # --- command strip: what is actually being sent ---------------------
    label, key = COMMAND_LABELS[(drive, st["turn_resolved"])]
    if drive in ("forward", "backward"):
        cmd_col = drive_col
    elif st["turn_resolved"] != "center":
        cmd_col = COL_CYAN
    else:
        cmd_col = COL_AMBER
    draw_pill(frame, w // 2, strip_cy, strip_w, strip_h, cmd_col, max(1, S(1.5)))
    put_text_centered(frame, f"{label}   [{key}]", w // 2, strip_cy + S(6), cmd_col, 0.52 * s, tk, FONT_BOLD)

    # --- legend ----------------------------------------------------------
    legend = "LEFT: palm=FWD  back=REV   |   RIGHT: tilt=TURN  fist=KICK   |   2 FISTS = CELEBRATE"
    put_text_centered(frame, legend, w // 2, h - S(8), scale_color(COL_CYAN, 0.9), 0.36 * s, tk)

    # --- effects on top of everything -----------------------------------
    fx.draw(frame, now)


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
    shoot_trigger = OneShotTrigger(SHOOT_WINDOW, SHOOT_NEED, SHOOT_RELEASE, SHOOT_COOLDOWN_SEC)
    celebrate_trigger = OneShotTrigger(CELEBRATE_WINDOW, CELEBRATE_NEED, CELEBRATE_RELEASE, CELEBRATE_COOLDOWN_SEC)
    left_fist_recent = deque(maxlen=LEFT_FIST_SUPPRESS_FRAMES)
    hand_assigner = HandAssigner()
    fx = HudFx()

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
        # VIDEO mode tracks hands between frames instead of re-detecting from
        # scratch, which keeps fists (low detection confidence) from dropping out.
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    fps = 0.0
    last_frame_time = None
    last_timestamp_ms = -1

    with vision.HandLandmarker.create_from_options(hand_options) as hands:
        print("Left hand:  open palm facing camera = forward, back of hand facing camera = backward")
        print("Right hand: open hand tilt = turn left/right, closed fist = shoot")
        print("Both hands: two closed fists = celebrate")
        print("Press 'q' to quit.")

        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            # Flip horizontally so the display is mirror-like AND so that
            # MediaPipe's handedness label matches the user's actual hand
            # (MediaPipe assumes a selfie/mirrored view by default).
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            timestamp_ms = max(int(time.monotonic() * 1000), last_timestamp_ms + 1)  # must strictly increase
            last_timestamp_ms = timestamp_ms
            results = hands.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame), timestamp_ms)

            h, w, _ = frame.shape
            s = hud_scale(w)
            now = time.time()
            if last_frame_time is not None and now > last_frame_time:
                inst = 1.0 / (now - last_frame_time)
                fps = inst if fps == 0 else 0.9 * fps + 0.1 * inst
            last_frame_time = now

            raw_drive = "stop"
            raw_turn = "none"
            right_hand_seen = False
            left_hand_seen = False
            fist_now = False
            left_fist_now = False
            left_orientation = None
            turn_tilt = 0.0

            sides = hand_assigner.assign(results.hand_landmarks, results.handedness, now)

            left_landmarks = sides["Left"]
            if left_landmarks is not None:
                left_hand_seen = True
                raw_drive, left_orientation = classify_drive_gesture(left_landmarks)
                left_fist_now = is_fist(left_landmarks)
                hand_color = (
                    COL_MAGENTA if left_fist_now else
                    COL_GREEN if raw_drive == "forward" else
                    COL_RED if raw_drive == "backward" else
                    COL_INACTIVE
                )
                draw_hand_landmarks(frame, left_landmarks, hand_color, "DRIVE", s)

            right_landmarks = sides["Right"]
            if right_landmarks is not None:
                right_hand_seen = True
                raw_turn, turn_tilt = classify_turn_gesture(right_landmarks)
                fist_now = is_fist(right_landmarks)
                hand_color = (
                    COL_MAGENTA if fist_now else
                    COL_CYAN if raw_turn in ("turn_left", "turn_right") else
                    COL_INACTIVE
                )
                draw_hand_landmarks(frame, right_landmarks, hand_color, "STEER", s)

            drive_state = drive_debouncer.update(raw_drive if left_hand_seen else "stop")
            turn_state = turn_debouncer.update(raw_turn if right_hand_seen else "none")
            # Two fists = celebrate. A right fist only counts as "shoot" if the
            # left hand hasn't been a fist in the last few frames -- otherwise
            # raising both fists (or a flickering left fist) would kick the
            # ball before the celebrate vote completes.
            left_fist_recent.append(left_fist_now)
            both_fists = left_fist_now and fist_now
            shot_fired = shoot_trigger.update(fist_now and not any(left_fist_recent), now)
            celebrate_fired = celebrate_trigger.update(both_fists, now)
            if shot_fired:
                fx.trigger_shoot(now)
            if celebrate_fired:
                fx.trigger_celebrate(now, w, h)

            # --- Build payload and dispatch every frame ---------------
            resolved_turn = turn_state if turn_state != "none" else "center"
            payload = {
                "drive": drive_state,
                "turn": resolved_turn,
                "shoot": shot_fired,
                "celebrate": celebrate_fired,
                "timestamp": now,
            }
            robot_func(payload)
            if bridge is not None:
                if bridge.connected:
                    bridge.update(drive_state, resolved_turn, shot_fired, celebrate_fired, now)
                else:
                    bridge = None  # link dropped -- fall back to detection-only

            # --- HUD --------------------------------------------------
            if left_fist_now:
                left_read = "FIST"
            elif left_orientation == "palm":
                left_read = "PALM"
            elif left_orientation == "back":
                left_read = "BACK"
            else:
                left_read = "HAND"
            if fist_now:
                right_read = "FIST"
            elif raw_turn != "none":
                right_read = "OPEN"
            else:
                right_read = "HAND"

            render_hud(frame, {
                "robot_online": bridge is not None,
                "fps": fps,
                "left_seen": left_hand_seen,
                "right_seen": right_hand_seen,
                "left_read": left_read,
                "right_read": right_read,
                "drive": drive_state,
                "turn": turn_state,
                "turn_resolved": resolved_turn,
                "tilt": turn_tilt,
                "kick_ready": shoot_trigger.ready_ratio,
            }, fx, now)

            cv2.imshow("Gesture Control", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    if bridge is not None:
        bridge.disconnect()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
