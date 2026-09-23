"""
mBot Bluetooth Communication Module
Subsystem: Communication
Project: mBot Football Robot

This module handles wireless Bluetooth serial communication between
the computer (CV/Controller) and the mBot.
"""

import serial
import time
import serial.tools.list_ports
from typing import Optional


class MBotBluetooth:
    """Manages the Bluetooth serial connection to the mBot."""

    def __init__(self, port: Optional[str] = None, baudrate: int = 115200, timeout: float = 1.0):
        """
        Initialize the communication interface.
        Note: The Makeblock Bluetooth module operates at 115200 baud.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None

    @staticmethod
    def list_available_ports():
        """Scans and lists all available COM ports on the PC."""
        ports = serial.tools.list_ports.comports()
        result = []
        for p in ports:
            result.append((p.device, p.description))
        return result

    def connect(self, port: Optional[str] = None) -> bool:
        """Opens the Bluetooth serial connection."""
        target_port = port or self.port
        if not target_port:
            raise ValueError("No COM port specified for connection.")

        self.port = target_port
        try:
            print(f"[COMM] Connecting to mBot on {self.port} at {self.baudrate} baud...")
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            # Short wait for Bluetooth handshake / microcontroller reset
            time.sleep(1.5)
            print(f"[COMM] Successfully connected to {self.port}!")
            return True
        except Exception as e:
            print(f"[COMM] Connection error: {e}")
            self.ser = None
            return False

    def is_connected(self) -> bool:
        """Returns True if the serial port is currently open."""
        return self.ser is not None and self.ser.is_open

    def send_raw(self, char_cmd: str) -> bool:
        """Sends a single character command over Bluetooth."""
        if not self.is_connected():
            print("[COMM] Error: Cannot send, not connected!")
            return False

        try:
            byte_data = char_cmd.encode('ascii')
            self.ser.write(byte_data)
            self.ser.flush()
            return True
        except Exception as e:
            print(f"[COMM] Transmission error: {e}")
            return False

    def read_response(self, timeout: float = 0.5) -> str:
        """Reads any incoming response text from the mBot."""
        if not self.is_connected():
            return ""
        time.sleep(0.05)
        lines = []
        start = time.time()
        while time.time() - start < timeout:
            if self.ser.in_waiting > 0:
                try:
                    chunk = self.ser.read(self.ser.in_waiting).decode('utf-8', errors='replace')
                    lines.append(chunk)
                except Exception:
                    pass
            time.sleep(0.02)
        return "".join(lines)

    # --- High-Level Command API for CV Team ---

    def forward(self):
        """Drives robot forward."""
        return self.send_raw('w')

    def backward(self):
        """Drives robot backward."""
        return self.send_raw('s')

    def turn_left(self):
        """Pivots robot left in place."""
        return self.send_raw('a')

    def turn_right(self):
        """Pivots robot right in place."""
        return self.send_raw('d')

    def curve_left(self):
        """Arcs smoothly left (good for ball approach)."""
        return self.send_raw('q')

    def curve_right(self):
        """Arcs smoothly right (good for ball approach)."""
        return self.send_raw('e')

    def turn_around(self):
        """Executes ~180 degree pivot."""
        return self.send_raw('x')

    def celebrate(self):
        """Goal scored celebration wiggle."""
        return self.send_raw('c')

    def kick(self):
        """Triggers kicker servo strike on pin A0."""
        return self.send_raw('k')

    def stop(self):
        """Stops both motors."""
        return self.send_raw(' ')

    def speed_up(self):
        """Increases speed cap."""
        return self.send_raw('+')

    def speed_down(self):
        """Decreases speed cap."""
        return self.send_raw('-')

    def disconnect(self):
        """Safely stops robot and closes Bluetooth port."""
        if self.is_connected():
            self.stop()
            time.sleep(0.1)
            self.ser.close()
            print("[COMM] Disconnected safely.")
        self.ser = None
