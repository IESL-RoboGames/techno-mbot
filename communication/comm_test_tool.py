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

    # Step 3: Interactive Command Control
    print("\n✅ CONNECTED! You are now transmitting wirelessly to the mBot.")
    print("==================================================")
    print("Controls (matches Robot Control team's code):")
    print("  w       : Move Forward")
    print("  s       : Move Backward")
    print("  a       : Turn Left (pivot)")
    print("  d       : Turn Right (pivot)")
    print("  q       : Curve Left")
    print("  e       : Curve Right")
    print("  x       : Turn Around (180°)")
    print("  c       : Celebrate (wiggle)")
    print("  [space] : Stop Robot")
    print("  + / -   : Increase / Decrease speed cap")
    print("  exit    : Quit and disconnect")
    print("==================================================")

    try:
        while True:
            cmd = input("\nEnter command: ").strip()
            if not cmd:
                # If user just hits enter, send stop for safety
                bot.stop()
                print("-> Stopped.")
                continue

            if cmd.lower() in ['exit', 'quit']:
                break

            char = cmd[0]
            if char in ['w', 's', 'a', 'd', 'q', 'e', 'x', 'c', ' ', '+', '-']:
                bot.send_raw(char)
                print(f"-> Sent command: '{char}'")
            else:
                print(f"Unknown command '{char}'. Valid keys: w, s, a, d, q, e, x, c, [space], +, -")
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        bot.disconnect()
        print("Done!")


if __name__ == "__main__":
    main()
