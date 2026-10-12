"""
Robot bridge: translates the gesture system's per-frame
(drive, turn, shoot, celebrate) state into the single-byte serial protocol
defined in ../communication/README.md and implemented by
mbot_motor_control/mbot_motor_control.ino. This module does not modify
anything else in the repo -- it only imports the existing MBotBluetooth class.

Mapping:
  - forward  + turn_left/right -> forward arcs  ('q' / 'e')
  - backward + turn_left/right -> backward arcs ('z' / 'c')
  - stop     + turn_left/right -> in-place pivot ('a' / 'd')
  - shoot     -> one-shot 'k' on top of the current drive/turn byte
  - celebrate -> one-shot 'v' (replaces that frame's drive/turn byte;
                 the firmware stops the robot when the wiggle finishes)
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_ROOTS = [
    os.path.join(_THIS_DIR, ".."),                 # this file living inside techno-mbot/gestures/
    os.path.join(_THIS_DIR, "..", "techno-mbot"),  # standalone dev copy next to the techno-mbot repo
]
for _root in _CANDIDATE_ROOTS:
    if os.path.isdir(os.path.join(_root, "communication")):
        if _root not in sys.path:
            sys.path.insert(0, _root)
        break

from communication.mbot_bluetooth import MBotBluetooth  # noqa: E402

HEARTBEAT_SEC = 0.5   # re-send the current command at least this often, even if unchanged


def resolve_command(drive, turn):
    """Pure mapping from gesture state to the firmware's single-byte protocol."""
    if drive == "forward":
        if turn == "turn_left":
            return "q"
        if turn == "turn_right":
            return "e"
        return "w"

    if drive == "backward":
        if turn == "turn_left":
            return "z"  # backward-left arc
        if turn == "turn_right":
            return "c"  # backward-right arc
        return "s"

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
        self._last_sent_char = None
        self._last_send_time = 0.0

    def connect(self):
        try:
            self.connected = self.bot.connect()
        except Exception as exc:
            print(f"[BRIDGE] Connect failed: {exc}")
            self.connected = False
        return self.connected

    def update(self, drive, turn, shoot, celebrate, now):
        """Call once per frame. Sends the resolved drive/turn byte (on
        change, or on the heartbeat interval), plus a separate one-shot
        'k' / 'v' on the frame a shot / celebration fires."""
        if not self.connected:
            return

        if celebrate:
            if not self.bot.send_raw("v"):
                self._handle_failure()
            self._last_sent_char = None  # robot is stopped after the wiggle; force a fresh send
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
                return

        if shoot:
            kick_cmd = "j" if drive == "forward" else "k"
            if not self.bot.send_raw(kick_cmd):
                self._handle_failure()
            self._last_sent_char = None  # kick ends; force a fresh send

    def _handle_failure(self):
        try:
            self.bot.send_raw(" ")
        except Exception:
            pass
        self.connected = False
        self._last_sent_char = None

    def disconnect(self):
        if self.connected:
            self.bot.disconnect()
        self.connected = False
        self._last_sent_char = None
