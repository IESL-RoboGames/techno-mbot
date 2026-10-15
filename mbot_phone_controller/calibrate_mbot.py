"""
Interactive Laptop Calibration Tool for mBot Phone Controller
Subsystem: Phone Control & Calibration

Maintains the exact mBot Phone Controller command set ('F', 'B', 'L', 'R', 'G', 'H', 'I', 'J', 'S', 'Y', 'j', 'Z')
while providing the identical, intuitive live calibration method used in comm_test_tool:
- Hold Ctrl + Key (or Ctrl + [+]) to INCREASE parameter
- Hold Alt  + Key (or Ctrl + [-]) to DECREASE parameter
- Ctrl + Enter     : Save calibration to EEPROM (#SAVE)
- Ctrl + Backspace : Reset calibration to factory defaults (#RESET)
- Tab / ?          : Query current calibration status (#?)
- Esc              : Quit and disconnect
"""

import os
import sys
import time
import threading

# Ensure communication module can be imported
comm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "communication"))
if os.path.exists(comm_dir) and comm_dir not in sys.path:
    sys.path.insert(0, comm_dir)

try:
    from mbot_bluetooth import MBotBluetooth
except ImportError:
    # Standalone fallback if communication module is missing
    import serial
    import serial.tools.list_ports

    class MBotBluetooth:  # type: ignore
        def __init__(self, port=None, baudrate=115200, timeout=1.0):
            self.port = port
            self.baudrate = baudrate
            self.timeout = timeout
            self.ser = None

        @classmethod
        def list_available_ports(cls):
            ports = serial.tools.list_ports.comports()
            candidates = []
            for p in ports:
                desc = p.description or ""
                hwid = p.hwid or ""
                is_mbot = any(k in (desc + " " + hwid).lower() for k in ["makeblock", "mbot", "bluetooth", "ch340", "cp210", "arduino"])
                marker = " [mBot Detected]" if is_mbot else ""
                candidates.append((p.device, f"{desc}{marker}"))
            candidates.sort(key=lambda x: ("[mBot Detected]" not in x[1], x[0]))
            return candidates

        def connect(self, port=None):
            self.port = port
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                time.sleep(1.5)
                return True
            except Exception as e:
                print(f"[COMM] Connection error: {e}")
                self.ser = None
                return False

        def is_connected(self):
            return self.ser is not None and self.ser.is_open

        def send_raw(self, char_cmd: str):
            if not self.is_connected():
                return False
            try:
                self.ser.write(char_cmd.encode('ascii'))
                self.ser.flush()
                return True
            except Exception:
                return False

        def send_calibration(self, cmd: str):
            clean = cmd.strip().lstrip('#')
            return self.send_raw(f"#{clean}\n")

        def calibrate_adjust(self, param_key: str, increase: bool = True):
            op = "+" if increase else "-"
            return self.send_calibration(f"{param_key.upper()}{op}")

        def calibrate_save(self):
            return self.send_calibration("SAVE")

        def calibrate_reset(self):
            return self.send_calibration("RESET")

        def calibrate_query(self):
            return self.send_calibration("?")

        def disconnect(self):
            if self.is_connected():
                self.send_raw('S')
                time.sleep(0.1)
                self.ser.close()
            self.ser = None

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False


# -----------------------------------------------------------------------------
# Command Mappings for mBot Phone Controller
# -----------------------------------------------------------------------------
# Driving keys -> Phone Controller commands sent to mbot_phone_controller.ino
PHONE_DRIVE_MAP = {
    'w': ('F', 'Forward'),
    's': ('B', 'Backward'),
    'a': ('L', 'Spin Left'),
    'd': ('R', 'Spin Right'),
    'q': ('G', 'Arc Forward-Left'),
    'e': ('H', 'Arc Forward-Right'),
    'z': ('I', 'Arc Backward-Left'),
    'c': ('J', 'Arc Backward-Right'),
}

CONTINUOUS_ACTIONS = set(PHONE_DRIVE_MAP.keys())

# Calibration Keys (Identical to comm_test_tool)
CALIBRATION_MAP = {
    'w': ('W', 'Forward Speed'),
    's': ('S', 'Backward Speed'),
    'a': ('A', 'Turn Speed'),
    'd': ('A', 'Turn Speed'),
    'q': ('Q', 'Curve Inner Ratio'),
    'e': ('Q', 'Curve Inner Ratio'),
    'o': ('O', 'Curve Outer Speed'),
    't': ('T', 'Motor Trim Balance'),
    'x': ('X', '180 Spin Time'),
    'k': ('K', 'Kick Strike Angle'),
}


def print_banner():
    print("=" * 65)
    print("🤖 mBot Football - Phone Controller Calibration & Test Tool")
    print("   Firmware: mbot_phone_controller.ino (BT Car Controller App)")
    print("   Calibration System: Unified with comm_test_tool")
    print("=" * 65)


def print_controls():
    print("\n" + "=" * 65)
    print("🚗 DRIVING CONTROLS (Hold key to move, release to stop):")
    print("  w / s       : Move Forward ('F') / Backward ('B')")
    print("  a / d       : Spin Left ('L') / Right ('R') in place")
    print("  q / e       : Arc Forward-Left ('G') / Forward-Right ('H') (or hold W+A / W+D)")
    print("  z / c       : Arc Backward-Left ('I') / Backward-Right ('J') (or hold S+A / S+D)")
    print("  [Space]     : Stop immediately ('S')")
    print("\n⚡ ACTION CONTROLS (mBot Phone Controller Protocol):")
    print("  k / y       : Kick ('Y') [Running Kick if moving forward, Stationary if stopped]")
    print("  W + k / j   : Running Kick ('j') [Charge forward + strike ball]")
    print("  v / z       : Goal Celebration Fanfare & Dance ('Z')")
    print("  + / -       : Master Speed Cap (+/- 15)")
    print("\n🎛️ LIVE CALIBRATION CONTROLS (Identical to comm_test_tool):")
    print("  Hold [Ctrl] + Key (or Ctrl + [+]) : INCREASE parameter")
    print("  Hold [Alt]  + Key (or Ctrl + [-]) : DECREASE parameter (or Ctrl+Shift+Key)")
    print("    • 'w' : Forward Speed        • 's' : Backward Speed")
    print("    • 'a' : Turn Speed           • 'q' : Curve Ratio (% inner)")
    print("    • 't' : Motor Trim (Balance) • 'o' : Curve Outer Speed")
    print("    • 'x' : 180 Spin Time        • 'k' : Kick Strike Angle")
    print("  Ctrl + Enter     : Save calibration permanently to EEPROM (#SAVE)")
    print("  Ctrl + Backspace : Reset calibration to factory defaults (#RESET)")
    print("  Tab / ?          : Query & display current calibration status (#?)")
    print("  Esc              : Quit and disconnect")
    print("=" * 65 + "\n")


def run_interactive_loop(bot: MBotBluetooth):
    current_action = ' '
    held_one_shots = set()
    held_cal_keys = set()
    last_cal_time = 0.0

    try:
        while True:
            if keyboard.is_pressed('esc'):
                break

            now = time.time()

            # Modifier key checks
            is_ctrl = keyboard.is_pressed('ctrl') or keyboard.is_pressed('left ctrl') or keyboard.is_pressed('right ctrl')
            is_alt = keyboard.is_pressed('alt') or keyboard.is_pressed('left alt') or keyboard.is_pressed('right alt')
            is_shift = keyboard.is_pressed('shift') or keyboard.is_pressed('left shift') or keyboard.is_pressed('right shift')
            is_plus = keyboard.is_pressed('+') or keyboard.is_pressed('=')
            is_minus = keyboard.is_pressed('-')

            # -----------------------------------------------------------------
            # 1. LIVE CALIBRATION HANDLING (when Ctrl or Alt is held, or Tab/?)
            # -----------------------------------------------------------------
            if is_ctrl or is_alt:
                # Safety: Stop robot immediately if moving when user enters calibration mode
                if current_action in CONTINUOUS_ACTIONS:
                    bot.send_raw('S')
                    current_action = ' '

                # Save to EEPROM: Ctrl + Enter
                if keyboard.is_pressed('enter'):
                    if 'save' not in held_cal_keys:
                        held_cal_keys.add('save')
                        bot.calibrate_save()
                        print("\n💾 [CAL] Saving calibration to mBot EEPROM (#SAVE)...")
                else:
                    held_cal_keys.discard('save')

                # Reset to Defaults: Ctrl + Backspace
                if keyboard.is_pressed('backspace'):
                    if 'reset' not in held_cal_keys:
                        held_cal_keys.add('reset')
                        bot.calibrate_reset()
                        print("\n🔄 [CAL] Resetting mBot calibration to defaults (#RESET)...")
                else:
                    held_cal_keys.discard('reset')

                # Calibratable Parameter Keys: W, S, A, D, Q, E, O, T, X, K
                for key_char, (cal_code, param_name) in CALIBRATION_MAP.items():
                    if keyboard.is_pressed(key_char):
                        if key_char not in held_cal_keys or (now - last_cal_time >= 0.25):
                            held_cal_keys.add(key_char)
                            last_cal_time = now

                            # Determine increase vs decrease
                            is_decrease = is_minus or is_alt or (is_ctrl and is_shift)
                            op_name = "Decreasing" if is_decrease else "Increasing"
                            bot.calibrate_adjust(cal_code, increase=not is_decrease)
                            print(f"\n⚙️ [CAL] {op_name} {param_name} ({cal_code}{'-' if is_decrease else '+'})...")
                    else:
                        held_cal_keys.discard(key_char)

                time.sleep(0.04)
                continue

            # Query status on Tab or '?'
            if keyboard.is_pressed('tab') or keyboard.is_pressed('?'):
                if 'query' not in held_cal_keys:
                    held_cal_keys.add('query')
                    bot.calibrate_query()
                    print("\n📋 [CAL] Querying calibration status (#?)...")
            else:
                held_cal_keys.discard('query')

            # -----------------------------------------------------------------
            # 2. NORMAL PHONE CONTROLLER DRIVING & ACTIONS (no Ctrl/Alt held)
            # -----------------------------------------------------------------
            is_w = keyboard.is_pressed('w')
            is_s = keyboard.is_pressed('s')
            is_a = keyboard.is_pressed('a')
            is_d = keyboard.is_pressed('d')
            is_k = keyboard.is_pressed('k') or keyboard.is_pressed('y')

            # 2A. Kick Triggering (Debounced single trigger)
            # While holding W, tapping K sends running kick ('j')
            # Pressing K/Y alone sends smart kick ('Y')
            if is_k:
                if 'kick' not in held_one_shots:
                    held_one_shots.add('kick')
                    if is_w:
                        bot.send_raw('j')
                        print("\n-> ⚡ RUNNING KICK ('j')! (Charging forward + Striking ball)")
                    else:
                        bot.send_raw('Y')
                        print("\n-> ⚡ SMART KICK ('Y')!")
            else:
                held_one_shots.discard('kick')

            # Direct running kick key ('j')
            if keyboard.is_pressed('j'):
                if 'j' not in held_one_shots:
                    held_one_shots.add('j')
                    bot.send_raw('j')
                    print("\n-> ⚡ RUNNING KICK ('j')!")
            else:
                held_one_shots.discard('j')

            # Celebration fanfare ('v' or 'z') -> Sends 'Z' to mbot_phone_controller.ino
            is_celebrate = keyboard.is_pressed('v') or (keyboard.is_pressed('z') and not is_s)
            if is_celebrate:
                if 'celebrate' not in held_one_shots:
                    held_one_shots.add('celebrate')
                    bot.send_raw('Z')
                    print("\n-> 🎉 GOAL CELEBRATION FANFARE ('Z')!")
            else:
                held_one_shots.discard('celebrate')

            # Master speed cap (+ / -)
            for speed_key, tag, cmd_byte in [('+', 'Speed Cap (+15)', '+'), ('=', 'Speed Cap (+15)', '+'), ('-', 'Speed Cap (-15)', '-')]:
                if keyboard.is_pressed(speed_key):
                    if speed_key not in held_one_shots:
                        held_one_shots.add(speed_key)
                        bot.send_raw(cmd_byte)
                        print(f"\n-> ⚡ {tag} ('{cmd_byte}')")
                else:
                    held_one_shots.discard(speed_key)

            # 2B. Continuous Driving Resolution
            new_action = ' '
            if is_w and is_a:
                new_action = 'q'  # Arc Forward-Left
            elif is_w and is_d:
                new_action = 'e'  # Arc Forward-Right
            elif is_s and is_a:
                new_action = 'z'  # Arc Backward-Left
            elif is_s and is_d:
                new_action = 'c'  # Arc Backward-Right
            elif is_w:
                new_action = 'w'  # Forward
            elif is_s:
                new_action = 's'  # Backward
            elif is_a:
                new_action = 'a'  # Spin Left
            elif is_d:
                new_action = 'd'  # Spin Right
            elif keyboard.is_pressed('q'):
                new_action = 'q'
            elif keyboard.is_pressed('e'):
                new_action = 'e'
            elif keyboard.is_pressed('z'):
                new_action = 'z'
            elif keyboard.is_pressed('c'):
                new_action = 'c'

            # Continuous motion updates to mbot_phone_controller
            if new_action in PHONE_DRIVE_MAP:
                if current_action != new_action:
                    cmd_char, desc = PHONE_DRIVE_MAP[new_action]
                    bot.send_raw(cmd_char)
                    print(f"-> Driving: {desc} ('{cmd_char}')")
                    current_action = new_action
                elif 'kick' in held_one_shots and is_w:
                    # When running kick was fired while holding W, resume forward drive
                    bot.send_raw('F')
            else:
                # Key released -> send phone controller Stop ('S')
                if current_action in PHONE_DRIVE_MAP:
                    bot.send_raw('S')
                    print("-> Stopped (key released) ('S')")
                current_action = ' '

            time.sleep(0.04)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        bot.send_raw('S')


def main():
    print_banner()

    bot = MBotBluetooth()

    # Step 1: Scan available ports
    print("\n[Step 1] Scanning COM ports for mBot (Bluetooth / USB)...")
    ports = bot.list_available_ports()
    if not ports:
        print("❌ No COM ports found! Ensure mBot Bluetooth is paired or USB cable is plugged in.")
        return

    print("Available Ports on your PC:")
    default_port = None
    default_idx = None
    for idx, (port_name, desc) in enumerate(ports):
        marker = ""
        if "[mBot Detected]" in desc:
            marker = " <-- [RECOMMENDED]"
            if not default_port:
                default_port = port_name
                default_idx = idx + 1
        print(f"  [{idx + 1}] {port_name}: {desc}{marker}")

    # Prompt user for port selection
    try:
        prompt_str = "\nEnter port number or type COM name"
        if default_port:
            prompt_str += f" [Press Enter for {default_port} (Port {default_idx})]"
        prompt_str += ": "

        selection = input(prompt_str).strip()
        if not selection and default_port:
            chosen_port = default_port
        elif selection.isdigit() and 1 <= int(selection) <= len(ports):
            chosen_port = ports[int(selection) - 1][0]
        elif selection.upper().startswith("COM"):
            chosen_port = selection.upper()
        else:
            chosen_port = ports[0][0]
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return

    # Step 2: Connect
    print(f"\n[Step 2] Connecting to {chosen_port} at 115200 baud...")
    success = bot.connect(chosen_port)
    if not success:
        print("❌ Connection failed. If Arduino Serial Monitor is open, please close it first!")
        return

    print("✅ CONNECTED to mBot Phone Controller!")

    # Background listener thread for incoming mBot serial text
    def listener():
        while bot.is_connected():
            try:
                if bot.ser and bot.ser.in_waiting > 0:
                    text = bot.ser.readline().decode('utf-8', errors='replace').strip()
                    if text:
                        print(f"\n🤖 {text}")
            except Exception:
                break
            time.sleep(0.04)

    listen_thread = threading.Thread(target=listener, daemon=True)
    listen_thread.start()

    # Query initial calibration table from robot
    time.sleep(0.2)
    bot.calibrate_query()
    time.sleep(0.4)

    # Step 3: Interactive Controls
    print_controls()

    if HAS_KEYBOARD:
        run_interactive_loop(bot)
    else:
        print("⚠️ Warning: 'keyboard' module not available. Please install with: pip install keyboard")

    # Cleanup on exit
    bot.disconnect()
    print("Disconnected cleanly. Done!")


if __name__ == "__main__":
    main()
