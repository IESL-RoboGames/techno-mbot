"""
mBot Communication Testing Tool
Subsystem: Communication

This tool allows you to:
1. Scan all available Bluetooth/USB COM ports on your PC.
2. Connect to the mBot.
3. Test every command with your keyboard (w, a, s, d, q, e, x, c, space).
"""

import sys
import time
from mbot_bluetooth import MBotBluetooth


def main():
    print("==================================================")
    print("🤖 mBot Football - Communication Test Tool")
    print("   Subsystem: Communication")
    print("==================================================")

    bot = MBotBluetooth()

    # Step 1: Scan ports
    print("\n[Step 1] Scanning COM ports...")
    ports = bot.list_available_ports()

    if not ports:
        print("❌ No COM ports found! Make sure Bluetooth is paired or USB is plugged in.")
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

    # Prompt user to choose port
    try:
        prompt_str = "\nEnter port number (e.g. 1) or type COM name"
        if default_port:
            prompt_str += f" [Press Enter for {default_port} (Port {default_idx})]"
        prompt_str += ": "

        selection = input(prompt_str).strip()
        if not selection and default_port:
            chosen_port = default_port
        elif selection.isdigit() and 1 <= int(selection) <= len(ports):
            chosen_port = ports[int(selection) - 1][0]
        elif selection.upper().startswith("COM") or selection.startswith("/dev/"):
            chosen_port = selection
        elif any(p[0] == selection for p in ports):
            chosen_port = selection
        else:
            print("Invalid selection.")
            return
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return

    # Step 2: Connect
    print(f"\n[Step 2] Attempting to connect to {chosen_port}...")
    success = bot.connect(chosen_port)
    if not success:
        print("❌ Failed to connect. Check if mBlock or Arduino Serial Monitor is open (close them first)!")
        return

    # Start background listener for responses from mBot
    import threading
    def listener():
        while bot.is_connected():
            try:
                if bot.ser and bot.ser.in_waiting > 0:
                    text = bot.ser.readline().decode('utf-8', errors='replace').strip()
                    if text:
                        print(f"\n🤖 {text}\nEnter command: ", end="", flush=True)
            except Exception:
                break
            time.sleep(0.05)

    listen_thread = threading.Thread(target=listener, daemon=True)
    listen_thread.start()

    # Step 3: Interactive Command Control
    print("\n✅ CONNECTED! You are now transmitting to the mBot.")
    print("==================================================")
    print("🚗 Driving Controls (Hold key to move, release to stop):")
    print("  w / s       : Move Forward / Backward")
    print("  a / d       : Spin Left / Right in place")
    print("  q / e       : Arc Forward-Left / Forward-Right (or hold W+A / W+D)")
    print("  z / c       : Arc Backward-Left / Backward-Right (or hold S+A / S+D) [NEW]")
    print("  [space]     : Stop immediately")
    print("\n⚡ Action & Skill Controls:")
    print("  k           : Stationary Kick (Strike from a stop)")
    print("  W + k       : Running Kick (Charge forward + Strike ball) [NEW]")
    print("  j           : Direct Running Kick ('j')")
    print("  v           : Victory celebration wiggle (Rainbow LEDs)")
    print("  x           : 180° Turnaround spin")
    print("  o / p       : Servo Test (o = Deploy 90°, p = Retract 180°)")
    print("  + / -       : Master Speed Cap (+/- 15)")
    print("\n🎛️ Live Calibration Controls (Tune parameters without re-uploading):")
    print("  Ctrl + [+] + Key  (or Ctrl + Key) : Increase parameter")
    print("  Ctrl + [-] + Key  (or Alt  + Key) : Decrease parameter")
    print("    • 'w' : Forward Speed        • 's' : Backward Speed")
    print("    • 'a' : Turn Speed           • 'q' : Curve Ratio (% inner)")
    print("    • 't' : Motor Trim (Balance) • 'x' : 180 Spin Time")
    print("    • 'k' : Kick Strike Angle    • 'o' : Curve Outer Speed")
    print("  Ctrl + Enter     : Save calibration permanently to EEPROM")
    print("  Ctrl + Backspace : Reset calibration to factory defaults")
    print("  Tab / ?          : Query & display current calibration status")
    print("  Esc              : Quit and disconnect")
    print("==================================================")

    import keyboard

    CONTINUOUS_ACTIONS = {'w', 's', 'a', 'd', 'q', 'e', 'z', 'c'}
    ONE_SHOT_ACTIONS = {'k', 'x', 'v', 'o', 'p', '+', '-'}

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
        'k': ('K', 'Kick Angle'),
    }

    current_action = ' '
    held_one_shots = set()
    held_cal_keys = set()
    last_cal_time = 0.0

    try:
        while True:
            if keyboard.is_pressed('esc'):
                break

            now = time.time()

            # Modifier states
            is_ctrl = keyboard.is_pressed('ctrl') or keyboard.is_pressed('left ctrl') or keyboard.is_pressed('right ctrl')
            is_alt = keyboard.is_pressed('alt') or keyboard.is_pressed('left alt') or keyboard.is_pressed('right alt')
            is_shift = keyboard.is_pressed('shift') or keyboard.is_pressed('left shift') or keyboard.is_pressed('right shift')
            is_plus = keyboard.is_pressed('+') or keyboard.is_pressed('=')
            is_minus = keyboard.is_pressed('-')

            # -----------------------------------------------------------------
            # 1. LIVE CALIBRATION HANDLING (when Ctrl or Alt is held, or Tab/?)
            # -----------------------------------------------------------------
            if is_ctrl or is_alt:
                # Stop robot immediately if it was driving when user pressed Ctrl/Alt
                if current_action in CONTINUOUS_ACTIONS:
                    bot.send_raw(' ')
                    current_action = ' '

                # Save / Reset shortcuts
                if keyboard.is_pressed('enter'):
                    if 'save' not in held_cal_keys:
                        held_cal_keys.add('save')
                        bot.calibrate_save()
                        print("\n💾 [CAL] Saving calibration to mBot EEPROM...")
                else:
                    held_cal_keys.discard('save')

                if keyboard.is_pressed('backspace'):
                    if 'reset' not in held_cal_keys:
                        held_cal_keys.add('reset')
                        bot.calibrate_reset()
                        print("\n🔄 [CAL] Resetting mBot calibration to defaults...")
                else:
                    held_cal_keys.discard('reset')

                # Check calibratable parameter keys
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
                    print("\n📋 [CAL] Querying calibration status...")
            else:
                held_cal_keys.discard('query')

            # -----------------------------------------------------------------
            # 2. NORMAL DRIVING & ACTION HANDLING (no Ctrl / Alt pressed)
            # -----------------------------------------------------------------
            is_w = keyboard.is_pressed('w')
            is_s = keyboard.is_pressed('s')
            is_a = keyboard.is_pressed('a')
            is_d = keyboard.is_pressed('d')
            is_k = keyboard.is_pressed('k')

            # 2A. Kick Triggering (One-shot debounce: exactly 1 kick per keypress)
            # While holding W, tapping K sends 'j' (Running Kick)!
            # Pressing K alone sends 'k' (Stationary Kick)!
            if is_k:
                if 'kick' not in held_one_shots:
                    held_one_shots.add('kick')
                    if is_w:
                        bot.send_raw('j')
                        print("\n-> ⚡ RUNNING KICK! (Charging forward + Striking ball)")
                    else:
                        bot.send_raw('k')
                        print("\n-> ⚡ STATIONARY KICK!")
            else:
                held_one_shots.discard('kick')

            # Dedicated direct running kick key ('j')
            if keyboard.is_pressed('j'):
                if 'j' not in held_one_shots:
                    held_one_shots.add('j')
                    bot.send_raw('j')
                    print("\n-> ⚡ RUNNING KICK ('j')!")
            else:
                held_one_shots.discard('j')

            # Other one-shot actions (v, x, o, p, +, -)
            for other_action in ('v', 'x', 'o', 'p', '+', '-'):
                if keyboard.is_pressed(other_action):
                    if other_action not in held_one_shots:
                        held_one_shots.add(other_action)
                        bot.send_raw(other_action)
                        if other_action == 'v':
                            print("\n-> 🎉 CELEBRATION WIGGLE!")
                        elif other_action == 'x':
                            print("\n-> 🔄 180° SPIN!")
                        else:
                            print(f"\n-> Action: '{other_action}'")
                else:
                    held_one_shots.discard(other_action)

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

            # Continuous motion updates
            if new_action in CONTINUOUS_ACTIONS:
                if current_action != new_action:
                    bot.send_raw(new_action)
                    print(f"-> Driving: '{new_action}'")
                    current_action = new_action
                elif 'kick' in held_one_shots and is_w:
                    # When running kick was just fired while holding W, ensure forward driving continues
                    bot.send_raw('w')
            else:
                # Key released (new_action == ' ')
                if current_action in CONTINUOUS_ACTIONS:
                    bot.send_raw(' ')
                    print("-> Stopped (key released)")
                current_action = ' '

            time.sleep(0.04)  # Responsive 40ms polling loop

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        bot.disconnect()
        print("Done!")

if __name__ == "__main__":
    main()

