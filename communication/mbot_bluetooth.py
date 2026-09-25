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


import platform
import re


def _get_windows_bt_devices() -> dict:
    """Queries Windows Registry for paired Bluetooth MAC addresses and their friendly device names."""
    if platform.system() != "Windows":
        return {}
    try:
        import winreg
        names = {}
        path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, sub) as skey:
                        try:
                            name, _ = winreg.QueryValueEx(skey, "Name")
                            if isinstance(name, bytes):
                                name = name.decode("utf-8", errors="replace").rstrip("\x00")
                            # Sanitize non-ascii for safe printing on cp1252 consoles
                            name = name.encode("ascii", errors="replace").decode("ascii")
                            names[sub.lower()] = name
                        except Exception:
                            pass
                    i += 1
                except OSError:
                    break
        return names
    except Exception:
        return {}
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

    @classmethod
    def list_available_ports(cls):
        """
        Scans and lists all available COM ports on the PC.
        On Windows, resolves paired Bluetooth friendly device names (e.g. Makeblock, Headphones)
        and distinguishes between incoming (listen) ports and real outgoing device links.
        Returns a list of tuples: (port_device, description) with mBot candidates sorted first.
        """
        raw_ports = serial.tools.list_ports.comports()
        bt_devices = _get_windows_bt_devices()
        candidates = []

        for p in raw_ports:
            hwid = p.hwid or ""
            desc = p.description
            is_mbot = False

            # Check for Bluetooth MAC in hardware ID
            match = re.search(r'([0-9a-fA-F]{12})_', hwid)
            if match:
                mac = match.group(1).lower()
                if mac == "000000000000":
                    desc = "Bluetooth (Incoming Port - Inactive)"
                elif mac in bt_devices:
                    dev_name = bt_devices[mac]
                    if any(kw in dev_name.lower() for kw in ["makeblock", "mbot", "robot"]):
                        is_mbot = True
                        desc = f"{dev_name} (Bluetooth) [mBot Detected]"
                    else:
                        desc = f"{dev_name} (Bluetooth Device)"
                else:
                    desc = f"Bluetooth Device [{mac}]"
            elif any(kw in (desc + " " + hwid).lower() for kw in ["ch340", "ch341", "arduino", "makeblock", "mbot"]):
                is_mbot = True
                desc = f"{desc} (USB Serial) [mBot Detected]"

            candidates.append((p.device, desc, is_mbot))

        # Sort: mBot candidates first, active devices second, inactive incoming ports last
        candidates.sort(key=lambda x: (not x[2], "Incoming" in x[1], x[0]))
        return [(device, desc) for device, desc, _ in candidates]

    @classmethod
    def find_mbot_port(cls) -> Optional[str]:
        """Automatically detects and returns the first mBot COM port (Bluetooth or USB)."""
        for port, desc in cls.list_available_ports():
            if "[mBot Detected]" in desc:
                return port
        return None

    def connect(self, port: Optional[str] = None) -> bool:
        """Opens the Bluetooth serial connection."""
        target_port = port or self.port or self.find_mbot_port()
        if not target_port:
            raise ValueError("No COM port specified or automatically found for connection.")

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
            err_str = str(e).lower()
            if "semaphore timeout" in err_str:
                print("\n[COMM] ⚠️ Troubleshooting 'semaphore timeout':")
                print("  1. The selected COM port is NOT your mBot (e.g. paired headphones/earbuds/phone).")
                print("  2. Make sure the mBot is turned ON (switch on battery pack/mCore).")
                print("  3. Make sure the blue LED on the mBot Bluetooth module is flashing (ready) or solid (connected).")
                print("  4. If previously connected in mBlock or Arduino IDE, close those apps completely.\n")
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
