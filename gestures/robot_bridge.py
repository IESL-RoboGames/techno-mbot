"""
Robot bridge: translates the gesture system's per-frame (drive, turn, shoot)
state into the single-byte serial protocol already implemented in the
techno-mbot repo (see ../techno-mbot/communication/README.md and
mbot_motor_control/mbot_motor_control.ino). This module does not modify
anything in techno-mbot -- it only imports the existing MBotBluetooth class.

Mapping decisions:
  - forward + turn_left/right -> curve_left/curve_right ('q'/'e') so the
    robot arcs while still moving forward.
  - backward ignores turn entirely (no reverse-curve byte exists in the
    firmware) -> always plain backward ('s').
  - stop + turn_left/right -> in-place pivot ('a'/'d').
  - shoot is independent of drive/turn and always sent as its own one-shot
    'k', on top of whatever drive/turn byte is current.
"""

import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ROOTS = [
    os.path.join(_THIS_DIR, ".."),                 # this file living inside techno-mbot/gestures/
    os.path.join(_THIS_DIR, "..", "techno-mbot"),  # this file living inside the standalone gesture repo
]
for _root in _CANDIDATE_ROOTS:
    if os.path.isdir(os.path.join(_root, "communication")):
        if _root not in sys.path:
            sys.path.insert(0, _root)
        break

from communication.mbot_bluetooth import MBotBluetooth  # noqa: E402

HEARTBEAT_SEC = 0.5   # re-send the current command at least this often, even if unchanged
SPEED_MIN = 0
SPEED_MAX = 150
SPEED_STEP = 20
SPEED_START = 100


def resolve_command(drive, turn):
    """Pure mapping from gesture state to the firmware's single-byte protocol."""
    if drive == "forward":
        if turn == "turn_left":
            return "q"
        if turn == "turn_right":
            return "e"
        return "w"

    if drive == "backward":
        return "s"  # turn is ignored while backing up -- no reverse-curve byte exists

    # drive == "stop"
    if turn == "turn_left":
        return "a"
    if turn == "turn_right":
        return "d"
    return " "


class RobotBridge:
    """Owns the serial connection and applies heartbeat/failure handling on
    top of the plain MBotBluetooth API."""

    def __init__(self):
        self.bot = MBotBluetooth()
        self.connected = False
        self.speed_cap = SPEED_START
        self._last_sent_char = None
        self._last_send_time = 0.0

    def connect(self):
        try:
            self.connected = self.bot.connect()
        except Exception as exc:
            print(f"[BRIDGE] Connect failed: {exc}")
            self.connected = False
        return self.connected

    def update(self, drive, turn, shoot, now):
        """Call once per frame. Sends the resolved drive/turn byte (on
        change, or on the heartbeat interval) and a separate 'k' whenever
        shoot is True this frame."""
        if not self.connected:
            return

        char = resolve_command(drive, turn)
        should_send = (
            char != self._last_sent_char
            or (now - self._last_send_time) >= HEARTBEAT_SEC
        )
        if should_send:
            if self.bot.send_raw(char):
                self._last_sent_char = char
                self._last_send_time = now
            else:
                self._handle_failure()

        if shoot:
            if not self.bot.send_raw("k"):
                self._handle_failure()

    def _handle_failure(self):
        try:
            self.bot.send_raw(" ")
        except Exception:
            pass
        self.connected = False
        self._last_sent_char = None

    def speed_up(self):
        if not self.connected:
            return
        self.speed_cap = min(self.speed_cap + SPEED_STEP, SPEED_MAX)
        self.bot.speed_up()

    def speed_down(self):
        if not self.connected:
            return
        self.speed_cap = max(self.speed_cap - SPEED_STEP, SPEED_MIN)
        self.bot.speed_down()

    def disconnect(self):
        if self.connected:
            self.bot.disconnect()
        self.connected = False
        self._last_sent_char = None
