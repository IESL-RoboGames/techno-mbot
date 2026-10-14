"""
Interactive Laptop Calibration Tool for mBot Phone Controller
Subsystem: Phone Control & Calibration

Allows you to calibrate your mBot football robot using laptop keyboard keys:
- W / S / A / D : Live test driving (forward, reverse, turn)
- Space         : Stop immediately
- K / Y         : Test kick
- V / Z         : Test victory celebration
- T / Shift+T   : Fine-tune steering trim balance (fixes drifting)
- F / Shift+F   : Fine-tune forward speed
- R / Shift+R   : Fine-tune turn speed
- S (Shift+S)   : Save settings permanently to robot EEPROM
- ?             : View current calibration status
"""

import sys
import time
import serial
import serial.tools.list_ports

try:
    import msvcrt  # Windows instant keypress detection (no Enter key needed!)
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


def scan_ports():
    """Scans and lists available COM ports on the PC."""
    ports = serial.tools.list_ports.comports()
    results = []
    for p in ports:
        desc = p.description or ""
        hwid = p.hwid or ""
        is_mbot = any(k in (desc + hwid).lower() for k in ["makeblock", "bluetooth", "ch340", "cp210", "ftdi", "arduino"])
        results.append((p.device, desc, is_mbot))
    return results


def main():
    print("=" * 60)
    print("🤖 mBot Football - Phone Controller Calibration Tool")
    print("=" * 60)

    # 1. Scan available COM ports
    print("\n[Step 1] Scanning for mBot ports (Bluetooth / USB)...")
    ports = scan_ports()
    if not ports:
        print("❌ No COM ports found! Ensure your mBot Bluetooth is paired or USB is connected.")
        return

    print("Found ports:")
    default_port = None
    for idx, (port_name, desc, is_mbot) in enumerate(ports):
        tag = " <-- [RECOMMENDED]" if is_mbot else ""
        if is_mbot and not default_port:
            default_port = port_name
        print(f"  [{idx + 1}] {port_name}: {desc}{tag}")

    chosen_port = None
    if default_port:
        prompt = f"\nSelect port number or press Enter for [{default_port}]: "
    else:
        prompt = "\nSelect port number: "

    try:
        user_input = input(prompt).strip()
        if not user_input and default_port:
            chosen_port = default_port
        elif user_input.isdigit() and 1 <= int(user_input) <= len(ports):
            chosen_port = ports[int(user_input) - 1][0]
        elif user_input.upper().startswith("COM"):
            chosen_port = user_input.upper()
        else:
            chosen_port = ports[0][0]
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        return

    # 2. Connect
    print(f"\n[Step 2] Connecting to {chosen_port} at 115200 baud...")
    try:
        ser = serial.Serial(chosen_port, 115200, timeout=0.1)
        time.sleep(1.5)  # Wait for Arduino bootloader reset
    except Exception as exc:
        print(f"❌ Connection failed: {exc}")
        print("Tip: If Arduino IDE Serial Monitor is open, please close it first!")
        return

    print("✅ CONNECTED!")

    # Request calibration status
    ser.write(b"#?\n")

    # Background reader thread
    import threading
    running = True

    def reader():
        while running:
            try:
                line = ser.readline().decode('utf-8', errors='replace').strip()
                if line:
                    print(f"\n🤖 {line}")
            except Exception:
                break

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    time.sleep(0.5)

    print("\n" + "=" * 60)
    print("🎮 LIVE KEYBOARD CONTROLS (Press key directly):")
    print("  [w] / [s]     : Drive Forward / Backward")
    print("  [a] / [d]     : Turn Left / Right")
    print("  [Space]       : Stop motors")
    print("  [k] / [y]     : Test Kick")
    print("  [v] / [z]     : Test Goal Celebration Fanfare")
    print("\n🎛️ CALIBRATION SHORTCUTS:")
    print("  [t] / [T]     : Motor Trim -2 / +2 (Balance steering straight)")
    print("  [f] / [F]     : Forward Speed -10 / +10")
    print("  [r] / [R]     : Turn Speed -5 / +5")
    print("  [+] / [-]     : Master Speed Cap +/- 15")
    print("  [?]           : Query Current Status (#?)")
    print("  [S] (Shift+S) : SAVE Calibration to EEPROM (#SAVE)")
    print("  [!]           : RESET to Factory Defaults (#RESET)")
    print("  [q] / [Esc]   : Quit")
    print("=" * 60 + "\n")

    try:
        while True:
            if HAS_MSVCRT:
                ch = msvcrt.getch()
                # Handle special key escapes
                if ch in (b'\x00', b'\xe0'):
                    msvcrt.getch()
                    continue
                try:
                    c = ch.decode('utf-8')
                except Exception:
                    continue
            else:
                c = input("Enter command key: ").strip()[:1]

            if not c:
                continue

            # Exit
            if c in ('q', '\x1b'):  # 'q' or Esc
                ser.write(b"S")
                print("\nQuitting...")
                break

            # Live Driving
            elif c == 'w':
                print("[DRIVE] Forward (F)")
                ser.write(b"F")
            elif c == 's':
                print("[DRIVE] Backward (B)")
                ser.write(b"B")
            elif c == 'a':
                print("[DRIVE] Turn Left (L)")
                ser.write(b"L")
            elif c == 'd':
                print("[DRIVE] Turn Right (R)")
                ser.write(b"R")
            elif c == ' ':
                print("[STOP] (S)")
                ser.write(b"S")
            elif c in ('k', 'y', 'Y'):
                print("[KICK] Kick (Y)")
                ser.write(b"Y")
            elif c in ('v', 'z', 'Z'):
                print("[CELEBRATE] Victory Fanfare (Z)")
                ser.write(b"Z")

            # Calibration shortcuts
            elif c == 't':
                print("[CAL] Trim Left (-2)")
                ser.write(b"#T-\n")
            elif c == 'T':
                print("[CAL] Trim Right (+2)")
                ser.write(b"#T+\n")
            elif c == 'f':
                print("[CAL] Forward Speed (-10)")
                ser.write(b"#W-\n")
            elif c == 'F':
                print("[CAL] Forward Speed (+10)")
                ser.write(b"#W+\n")
            elif c == 'r':
                print("[CAL] Turn Speed (-5)")
                ser.write(b"#A-\n")
            elif c == 'R':
                print("[CAL] Turn Speed (+5)")
                ser.write(b"#A+\n")
            elif c == '+':
                print("[CAL] Speed Cap (+15)")
                ser.write(b"#C+\n")
            elif c == '-':
                print("[CAL] Speed Cap (-15)")
                ser.write(b"#C-\n")
            elif c == '?':
                print("[CAL] Query Status (#?)")
                ser.write(b"#?\n")
            elif c == 'S':  # Shift+S
                print("💾 [CAL] Saving configuration to EEPROM (#SAVE)...")
                ser.write(b"#SAVE\n")
            elif c == '!':
                print("🔄 [CAL] Resetting to defaults (#RESET)...")
                ser.write(b"#RESET\n")

    except KeyboardInterrupt:
        print("\nAborted by user.")
    finally:
        running = False
        try:
            ser.write(b"S")
            ser.close()
        except Exception:
            pass
        print("Disconnected cleanly.")


if __name__ == "__main__":
    main()
