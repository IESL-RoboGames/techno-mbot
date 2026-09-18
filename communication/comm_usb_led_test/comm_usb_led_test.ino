#include <MeMCore.h>

// Onboard RGB LEDs (Port 0 on mCore, 2 LEDs: 1=Left, 2=Right)
MeRGBLed rgbLeds(0, 2);

// Onboard Buzzer
MeBuzzer buzzer;

// Failsafe timer (same as project spec)
unsigned long lastCommandTime = 0;
const unsigned long COMM_TIMEOUT_MS = 1500;

void setup() {
  Serial.begin(9600);
  
  // Initialize RGB LEDs
  rgbLeds.setpin(13); // mCore onboard RGB pin
  setLeds(0, 0, 0);   // All off

  // Startup beep
  buzzer.tone(1000, 150);
  delay(150);
  buzzer.noTone();

  Serial.println("======================================");
  Serial.println("mBot Communication USB/LED Test Ready!");
  Serial.println("Commands: w=Green, s=Red, a=Left Blue, d=Right Blue, space=Off, c=Rainbow");
  Serial.println("======================================");

  lastCommandTime = millis();
}

void setLeds(uint8_t red, uint8_t green, uint8_t blue) {
  rgbLeds.setColor(1, red, green, blue); // Left LED
  rgbLeds.setColor(2, red, green, blue); // Right LED
  rgbLeds.show();
}

void handleCommand(char c) {
  lastCommandTime = millis();
  
  switch (c) {
    case 'w':
      // Forward: Both LEDs Bright GREEN
      setLeds(0, 150, 0);
      Serial.println("[mBot] 'w' -> FORWARD (Green LEDs)");
      break;

    case 's':
      // Backward: Both LEDs Bright RED
      setLeds(150, 0, 0);
      Serial.println("[mBot] 's' -> BACKWARD (Red LEDs)");
      break;

    case 'a':
      // Turn Left: Left LED BLUE, Right OFF
      rgbLeds.setColor(1, 0, 0, 150);
      rgbLeds.setColor(2, 0, 0, 0);
      rgbLeds.show();
      Serial.println("[mBot] 'a' -> TURN LEFT (Left Blue LED)");
      break;

    case 'd':
      // Turn Right: Right LED BLUE, Left OFF
      rgbLeds.setColor(1, 0, 0, 0);
      rgbLeds.setColor(2, 0, 0, 150);
      rgbLeds.show();
      Serial.println("[mBot] 'd' -> TURN RIGHT (Right Blue LED)");
      break;

    case 'q':
      // Curve Left: Cyan on left
      rgbLeds.setColor(1, 0, 150, 150);
      rgbLeds.setColor(2, 0, 50, 50);
      rgbLeds.show();
      Serial.println("[mBot] 'q' -> CURVE LEFT");
      break;

    case 'e':
      // Curve Right: Cyan on right
      rgbLeds.setColor(1, 0, 50, 50);
      rgbLeds.setColor(2, 0, 150, 150);
      rgbLeds.show();
      Serial.println("[mBot] 'e' -> CURVE RIGHT");
      break;

    case 'k':
      // Kick / Shoot: Yellow + beep
      setLeds(150, 150, 0);
      buzzer.tone(1500, 200);
      delay(200);
      buzzer.noTone();
      Serial.println("[mBot] 'k' -> KICK! (Buzzer Beep + Yellow)");
      break;

    case 'c':
      // Celebrate: Rainbow flash
      Serial.println("[mBot] 'c' -> CELEBRATE!");
      for (int i = 0; i < 3; i++) {
        setLeds(150, 0, 0); delay(100);
        setLeds(0, 150, 0); delay(100);
        setLeds(0, 0, 150); delay(100);
      }
      setLeds(0, 0, 0);
      break;

    case ' ':
      // Stop: All LEDs OFF
      setLeds(0, 0, 0);
      Serial.println("[mBot] ' ' -> STOP (LEDs Off)");
      break;

    case '+':
      buzzer.tone(1200, 100);
      delay(100);
      buzzer.noTone();
      Serial.println("[mBot] '+' -> Speed Cap UP");
      break;

    case '-':
      buzzer.tone(800, 100);
      delay(100);
      buzzer.noTone();
      Serial.println("[mBot] '-' -> Speed Cap DOWN");
      break;

    default:
      break;
  }
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    handleCommand(c);
  }

  // Auto-off failsafe if no command for 1.5 seconds
  if (millis() - lastCommandTime > COMM_TIMEOUT_MS) {
    setLeds(0, 0, 0);
  }
}
