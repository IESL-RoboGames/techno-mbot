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
    for idx, (port_name, desc) in enumerate(ports):
        print(f"  [{idx + 1}] {port_name}: {desc}")

    # Prompt user to choose port
    try:
        selection = input("\nEnter port number (e.g. 1) or type COM name (e.g. COM5): ").strip()
        if selection.isdigit() and 1 <= int(selection) <= len(ports):
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
    print("  k       : Kick / Shoot (Buzzer Beep)")
    print("  c       : Celebrate (Rainbow LED pattern)")
    print("  [space] : Stop (LEDs Off)")
    print("  + / -   : Speed Up / Down")
    print("  exit    : Quit and disconnect")
    print("==================================================")

    try:
        while True:
            cmd = input("\nEnter command: ").strip()
            if not cmd:
                bot.stop()
                print("-> Sent STOP.")
                continue

            if cmd.lower() in ['exit', 'quit']:
                break

            char = cmd[0]
            if char in ['w', 's', 'a', 'd', 'q', 'e', 'x', 'c', 'k', ' ', '+', '-']:
                bot.send_raw(char)
                print(f"-> Sent: '{char}'")
            else:
                print(f"Unknown command '{char}'. Valid keys: w, s, a, d, q, e, x, c, k, [space], +, -")
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        bot.disconnect()
        print("Done!")


if __name__ == "__main__":
    main()
