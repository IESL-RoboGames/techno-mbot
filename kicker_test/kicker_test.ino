#include <MeMCore.h>
#include <utility/Servo.h>

// =============================================================================
// ⚽ MBOT STRICT 90° KICKER TEST & ARM MOUNTING SKETCH
// =============================================================================
// PHYSICAL CALIBRATION & FIRST-TIME SETUP PROCEDURE:
// 1. Remove the kicker arm/horn from the servo motor shaft.
// 2. Upload this code to the robot.
// 3. On boot, the servo moves to SAFE_REST_ANGLE (180°) and HOLDS it locked.
// 4. While the servo is holding (Blue LED), push your kicker arm onto the
//    shaft in the RETRACTED / TUCKED-AWAY position and tighten the screw.
// 5. When kicking, the arm rotates 90° forward to KICK_FRONT_ANGLE (90°)
//    and snaps immediately back to SAFE_REST_ANGLE (180°).
// 6. Strict hardware safety: The servo is strictly clamped inside [90°, 180°].
//    It is impossible to rotate outside this 90° interval!
// =============================================================================

Servo kickerServo;
MeBuzzer buzzer;
MeRGBLed rgbLeds(0, 2);

const int SERVO_PIN = 9; // mBot Port 4 (Pin 9)

// --- STRICT 90° GEOMETRY BOUNDS ---
const int SAFE_REST_ANGLE  = 180; // Retracted safe starting position (degrees)
const int KICK_FRONT_ANGLE = 90;  // Front-most strike position (degrees)

// Strict safety limits: servo can NEVER move outside [90°, 180°]
const int SERVO_MIN_ANGLE  = 90;  
const int SERVO_MAX_ANGLE  = 180; 

// Calibrated high-speed strike & retract transit times
const int STRIKE_TIME_MS   = 150; // Transit time to 90° front strike at full speed
const int RETRACT_TIME_MS  = 160; // Transit time back to safe rest

unsigned long lastKickTime = 0;
const unsigned long AUTO_KICK_INTERVAL_MS = 3000; // Repeat kick every 3 seconds

void setLeds(uint8_t r, uint8_t g, uint8_t b) {
  rgbLeds.setColor(1, r, g, b);
  rgbLeds.setColor(2, r, g, b);
  rgbLeds.show();
}

// Strictly bounded servo write - guarantees arm never goes outside the 90° window!
void writeSafeAngle(int angle) {
  int safeAngle = constrain(angle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
  kickerServo.write(safeAngle);
}

void performKick() {
  Serial.print(F(">>> KICKING! Swinging 90° forward from "));
  Serial.print(SAFE_REST_ANGLE);
  Serial.print(F("° to front-most "));
  Serial.print(KICK_FRONT_ANGLE);
  Serial.println(F("°..."));

  // 1. Cut LEDs & Buzzer during swing so 100% battery voltage powers the servo
  setLeds(0, 0, 0);
  buzzer.noTone();

  // 2. Full-speed strike forward to front-most angle (180° -> 90°)
  writeSafeAngle(KICK_FRONT_ANGLE);
  delay(STRIKE_TIME_MS);

  // 3. Immediate snap retraction back to safe starting position (90° -> 180°)
  writeSafeAngle(SAFE_REST_ANGLE);
  delay(RETRACT_TIME_MS);

  // 4. Chirp & Green LED AFTER strike is complete
  buzzer.tone(1800, 50);
  delay(50);
  buzzer.noTone();
  setLeds(0, 150, 0); // Green = Ready at Safe Rest

  Serial.println(F(">>> Kick complete. Arm locked at Safe Rest (180°)."));
}

void setup() {
  Serial.begin(115200);

  buzzer.setpin(8);
  rgbLeds.setpin(13);

  // Blue LED indicator = Initializing Safe Position
  setLeds(0, 0, 150);

  Serial.println(F("=================================================="));
  Serial.println(F("🤖 mBot Strict 90° Kicker Test & Arm Calibration"));
  Serial.println(F("=================================================="));

  // 1. Lock servo immediately at SAFE_REST_ANGLE (180°)
  kickerServo.attach(SERVO_PIN);
  writeSafeAngle(SAFE_REST_ANGLE);

  // Audio confirmation: two rising beeps indicating Safe Home is locked
  buzzer.tone(1200, 80); delay(100);
  buzzer.tone(1600, 100); delay(120);
  buzzer.noTone();

  Serial.println(F("[CALIBRATION READY] Servo shaft is now holding SAFE_REST_ANGLE (180°)."));
  Serial.println(F(">> Mount your kicker arm now in the RETRACTED position and screw it in! <<"));
  Serial.println(F(">> The arm will only ever swing forward 90° to the front, and return here. <<"));
  Serial.println(F("=================================================="));

  // Hold safe position for 4 seconds so user can see it stays completely stationary
  delay(4000);

  setLeds(0, 150, 0); // Green = Active
  Serial.println(F("Kicker active. Commands in Serial Monitor (115200 baud):"));
  Serial.println(F("  'k' = Kick forward 90° now and return to safe rest"));
  Serial.println(F("  'o' = Hold at front-most strike position (90°) to check alignment"));
  Serial.println(F("  'p' = Return to safe rest position (180°)"));

  // Initial demonstration kick
  performKick();
  lastKickTime = millis();
}

void loop() {
  // 1. Serial Monitor Commands (115200 baud)
  if (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 'k' || c == ' ') {
      performKick();
      lastKickTime = millis();
    } else if (c == 'o') {
      Serial.println(F("[ALIGNMENT CHECK] Holding at front-most strike position (90°)."));
      setLeds(150, 150, 0); // Yellow
      writeSafeAngle(KICK_FRONT_ANGLE);
    } else if (c == 'p') {
      Serial.println(F("[SAFE REST] Returning to safe rest position (180°)."));
      setLeds(0, 150, 0); // Green
      writeSafeAngle(SAFE_REST_ANGLE);
      lastKickTime = millis();
    }
  }

  // 2. Automatic repeat kick every 3 seconds for continuous visual testing
  if (millis() - lastKickTime >= AUTO_KICK_INTERVAL_MS) {
    performKick();
    lastKickTime = millis();
  }
}
