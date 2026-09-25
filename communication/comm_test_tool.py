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
        elif selection.upper().startswith("COM"):
            chosen_port = selection.upper()
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
    print("Controls:")
    print("  w       : Move Forward (Green LEDs)")
    print("  s       : Move Backward (Red LEDs)")
    print("  a       : Turn Left (Left Blue LED)")
    print("  d       : Turn Right (Right Blue LED)")
    print("  k       : Kick / Shoot (Servo strike on A0 + Buzzer)")
    print("  o / p   : Servo Calibration (o = Open/Deploy, p = Reset/Retract)")
    print("  c       : Celebrate (Rainbow LED pattern)")
    print("  [space] : Stop (LEDs Off)")
    print("  + / -   : Speed Up / Down")
    print("  exit    : Quit and disconnect")
    print("==================================================")

    import keyboard
    
    print("Hold 'w/s/a/d' to move. Release to stop. Press 'Esc' to exit.")
    
    current_action = ' '
    
    try:
        while True:
            if keyboard.is_pressed('esc'):
                break
                
            new_action = ' '
            if keyboard.is_pressed('w'): new_action = 'w'
            elif keyboard.is_pressed('s'): new_action = 's'
            elif keyboard.is_pressed('a'): new_action = 'a'
            elif keyboard.is_pressed('d'): new_action = 'd'
            elif keyboard.is_pressed('q'): new_action = 'q'
            elif keyboard.is_pressed('e'): new_action = 'e'
            elif keyboard.is_pressed('x'): new_action = 'x'
            elif keyboard.is_pressed('c'): new_action = 'c'
            elif keyboard.is_pressed('k'): new_action = 'k'
            elif keyboard.is_pressed('o'): new_action = 'o'
            elif keyboard.is_pressed('p'): new_action = 'p'
            elif keyboard.is_pressed('+'): new_action = '+'
            elif keyboard.is_pressed('-'): new_action = '-'
            
            if new_action != ' ':
                bot.send_raw(new_action)
                if current_action != new_action:
                    print(f"-> Started: '{new_action}'")
            else:
                if current_action != ' ':
                    bot.send_raw(' ')
                    print("-> Stopped (key released)")
                    
            current_action = new_action
            time.sleep(0.1)  # Send commands every 100ms to keep Arduino timeout fresh
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        bot.disconnect()
        print("Done!")

if __name__ == "__main__":
    main()
