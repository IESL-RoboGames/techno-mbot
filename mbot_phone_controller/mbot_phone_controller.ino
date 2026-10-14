#include <MeMCore.h>
#include <EEPROM.h>
#include <utility/Servo.h>

// =============================================================================
// 📱 MBOT DEDICATED PHONE GAMEPAD CONTROLLER + LAPTOP CALIBRATION
// =============================================================================
// Specifically tailored for "BT Car Controller" (and all standard Bluetooth RC apps).
// Features:
// 1. Exact BT Car Controller Protocol (F/B/L/R/G/I/H/J, S/D, X, V, W, U, 0-9, q).
// 2. Continuous Drive: Does NOT stop prematurely; drives smoothly until button released.
// 3. Smart Kicking: Running Kick (LEDs OFF to prevent brownout) when moving forward;
//    Stationary Kick when stopped.
// 4. Goal Celebration: Side-to-side victory dance with buzzer fanfare & festive LEDs.
// 5. Built-in Laptop Calibration: Full EEPROM persistent calibration engine via
//    laptop Serial Monitor or the companion Python script!
//
// Baud Rate: 115200 (Default mBot Bluetooth speed)
// =============================================================================

// Hardware drivers
MeDCMotor leftMotor(M1);
MeDCMotor rightMotor(M2);
MeRGBLed  rgbLeds(0, 2); // Onboard RGB LEDs (Pin 13)
MeBuzzer  buzzer;        // Onboard Buzzer (Pin 8)
Servo     kickerServo;

// Pin definitions
const int SERVO_PIN = 9; // mBot Port 4 Pin 9 (Header A0)

// --- STRICT 90° KICKER SAFETY BOUNDS ---
const int SERVO_REST_ANGLE       = 180; // Safe retracted rest angle
const int SERVO_MIN_LIMIT        = 90;  // Front strike angle limit
const int SERVO_MAX_LIMIT        = 180; // Back rest limit
int       kickAngle              = 90;  // Strike angle (calibratable)
const int SERVO_KICK_DELAY_MS    = 150; // Transit time to 90° strike
const int SERVO_RETRACT_DELAY_MS = 160; // Retract transit time back to 180°

// --- MOTOR ACCELERATION RAMPING ---
const int FULL_POWER = 255;
const int MAX_SPEED  = 255;
const int RAMP_STEP  = 15; // Speed change per ramp step (bigger = snappier)
const int RAMP_DELAY = 20; // Milliseconds to wait between each ramp step

// --- CALIBRATABLE ROBOT PARAMETERS (Saved to EEPROM) ---
int forwardSpeed     = 150;  // Forward speed (30 to 255)
int backwardSpeed    = 130;  // Backward speed (30 to 255)
int turnSpeed        = 98;   // In-place pivot speed (30 to 255)
int curveSpeed       = 150;  // Arc turn outer wheel speed (30 to 255)
int curveInnerRatio  = 50;   // Inner wheel % of outer wheel (10 to 95)
int motorTrim        = 0;    // Steering trim balance (-50 to +50: + corrects left pull, - corrects right pull)
unsigned long rotate180Ms = 650; // Duration for 180° turnaround spin (ms)
int celebrateSpeed   = 100;  // Victory wiggle speed (0 to 255)
int currentSpeedCap  = 255;  // Global speed cap limit

// State tracking
int  currentLeftSpeed   = 0;
int  currentRightSpeed  = 0;
bool isDrivingForward   = false;
bool headlightsOn       = false;

// Kicker debouncing
unsigned long lastKickTime        = 0;
const unsigned long KICK_COOLDOWN = 450; // ms

// =============================================================================
// 💾 EEPROM PERSISTENT STORAGE
// =============================================================================
const uint16_t EEPROM_MAGIC = 0x4D42; // "MB" (mBot identifier)
const int EEPROM_START_ADDR = 0;

struct RobotConfig {
  uint16_t magic;
  int forwardSpeed;
  int backwardSpeed;
  int turnSpeed;
  int curveOuterSpeed;
  int curveInnerRatio;
  int motorTrim;
  unsigned long rotate180Ms;
  int kickAngle;
  int speedCap;
};

void saveConfigToEEPROM() {
  RobotConfig cfg;
  cfg.magic           = EEPROM_MAGIC;
  cfg.forwardSpeed    = forwardSpeed;
  cfg.backwardSpeed   = backwardSpeed;
  cfg.turnSpeed       = turnSpeed;
  cfg.curveOuterSpeed = curveSpeed;
  cfg.curveInnerRatio = curveInnerRatio;
  cfg.motorTrim       = motorTrim;
  cfg.rotate180Ms     = rotate180Ms;
  cfg.kickAngle       = kickAngle;
  cfg.speedCap        = currentSpeedCap;
  EEPROM.put(EEPROM_START_ADDR, cfg);

  // Sound confirmation: double rising chirp
  buzzer.tone(1400, 70); delay(80);
  buzzer.tone(2000, 100); delay(100);
  buzzer.noTone();
}

void loadConfigFromEEPROM() {
  RobotConfig cfg;
  EEPROM.get(EEPROM_START_ADDR, cfg);
  if (cfg.magic == EEPROM_MAGIC) {
    forwardSpeed    = constrain(cfg.forwardSpeed, 30, 255);
    backwardSpeed   = constrain(cfg.backwardSpeed, 30, 255);
    turnSpeed       = constrain(cfg.turnSpeed, 30, 255);
    curveSpeed      = constrain(cfg.curveOuterSpeed, 30, 255);
    curveInnerRatio = constrain(cfg.curveInnerRatio, 10, 95);
    motorTrim       = constrain(cfg.motorTrim, -50, 50);
    rotate180Ms     = constrain(cfg.rotate180Ms, 100, 3000);
    kickAngle       = constrain(cfg.kickAngle, SERVO_MIN_LIMIT, SERVO_MAX_LIMIT);
    currentSpeedCap = constrain(cfg.speedCap, 30, 255);
    Serial.println(F("[EEPROM] Restored saved calibration parameters."));
  } else {
    Serial.println(F("[EEPROM] No saved calibration found. Using defaults."));
  }
}

void resetConfigToDefaults() {
  forwardSpeed    = 150;
  backwardSpeed   = 130;
  turnSpeed       = 98;
  curveSpeed      = 150;
  curveInnerRatio = 50;
  motorTrim       = 0;
  rotate180Ms     = 650;
  kickAngle       = 90;
  currentSpeedCap = 255;
  saveConfigToEEPROM();
}

// =============================================================================
// Helper functions to resolve final speeds
// =============================================================================
inline int getForwardSpeed() {
  return min(forwardSpeed, currentSpeedCap);
}

inline int getBackwardSpeed() {
  return min(backwardSpeed, currentSpeedCap);
}

inline int getTurnSpeed() {
  return min(turnSpeed, currentSpeedCap);
}

inline int getCurveOuterSpeed() {
  return min(curveSpeed, currentSpeedCap);
}

inline int getCurveInnerSpeed() {
  return (getCurveOuterSpeed() * constrain(curveInnerRatio, 0, 100)) / 100;
}

int stepToward(int current, int target, int step) {
  if (current < target)
    return min(current + step, target);
  if (current > target)
    return max(current - step, target);
  return current;
}

// Ramp both motors smoothly toward target speeds with motorTrim compensation
void setMotorSpeeds(int targetLeft, int targetRight) {
  // Apply steering balance trim to compensate for motor differences
  if (motorTrim != 0) {
    if (targetLeft > 0)       targetLeft = constrain(targetLeft - motorTrim, 0, FULL_POWER);
    else if (targetLeft < 0)  targetLeft = constrain(targetLeft + motorTrim, -FULL_POWER, 0);

    if (targetRight > 0)      targetRight = constrain(targetRight + motorTrim, 0, FULL_POWER);
    else if (targetRight < 0) targetRight = constrain(targetRight - motorTrim, -FULL_POWER, 0);
  }

  // Clamp targets to currentSpeedCap
  targetLeft  = constrain(targetLeft, -currentSpeedCap, currentSpeedCap);
  targetRight = constrain(targetRight, -currentSpeedCap, currentSpeedCap);

  // Ramp both motors together, one step at a time, until both reach target
  while (currentLeftSpeed != targetLeft || currentRightSpeed != targetRight) {
    currentLeftSpeed  = stepToward(currentLeftSpeed, targetLeft, RAMP_STEP);
    currentRightSpeed = stepToward(currentRightSpeed, targetRight, RAMP_STEP);

    leftMotor.run(-currentLeftSpeed);  // Left motor is inverted
    rightMotor.run(currentRightSpeed);

    delay(RAMP_DELAY);
  }
}

// =============================================================================
// MOTOR & LED CONTROLS
// =============================================================================

void setLeds(uint8_t red, uint8_t green, uint8_t blue) {
  rgbLeds.setColor(1, red, green, blue);
  rgbLeds.setColor(2, red, green, blue);
  rgbLeds.show();
}

void stopRobot() {
  isDrivingForward = false;
  setMotorSpeeds(0, 0);
  if (!headlightsOn) {
    setLeds(0, 0, 0);
  } else {
    setLeds(120, 120, 120); // Maintain headlights if active
  }
}

void moveForward() {
  isDrivingForward = true;
  int spd = getForwardSpeed();
  setMotorSpeeds(spd, spd);
  setLeds(0, 150, 0); // Green forward indicator
}

void moveBackward() {
  isDrivingForward = false;
  int spd = getBackwardSpeed();
  setMotorSpeeds(-spd, -spd);
  setLeds(150, 0, 0); // Red reverse indicator
}

void turnLeft() {
  isDrivingForward = false;
  int spd = getTurnSpeed();
  setMotorSpeeds(-spd, spd);
  rgbLeds.setColor(1, 0, 0, 150);
  rgbLeds.setColor(2, 0, 0, 0);
  rgbLeds.show();
}

void turnRight() {
  isDrivingForward = false;
  int spd = getTurnSpeed();
  setMotorSpeeds(spd, -spd);
  rgbLeds.setColor(1, 0, 0, 0);
  rgbLeds.setColor(2, 0, 0, 150);
  rgbLeds.show();
}

void curveLeft() {
  isDrivingForward = true;
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(innerSpd, outerSpd);
  rgbLeds.setColor(1, 0, 150, 150);
  rgbLeds.setColor(2, 0, 50, 50);
  rgbLeds.show();
}

void curveRight() {
  isDrivingForward = true;
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(outerSpd, innerSpd);
  rgbLeds.setColor(1, 0, 50, 50);
  rgbLeds.setColor(2, 0, 150, 150);
  rgbLeds.show();
}

void curveBackLeft() {
  isDrivingForward = false;
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(-innerSpd, -outerSpd);
  rgbLeds.setColor(1, 150, 0, 50);
  rgbLeds.setColor(2, 50, 0, 0);
  rgbLeds.show();
}

void curveBackRight() {
  isDrivingForward = false;
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(-outerSpd, -innerSpd);
  rgbLeds.setColor(1, 50, 0, 0);
  rgbLeds.setColor(2, 150, 0, 50);
  rgbLeds.show();
}

void rotate180() {
  isDrivingForward = false;
  int spd = getTurnSpeed();
  setMotorSpeeds(-spd, spd);
  setLeds(150, 150, 0);
  delay(rotate180Ms);
  stopRobot();
}

// =============================================================================
// SERVO KICKER FUNCTIONS
// =============================================================================

void setServoAngle(int angle) {
  kickerServo.write(constrain(angle, SERVO_MIN_LIMIT, SERVO_MAX_LIMIT));
}

void resetServo() {
  setServoAngle(SERVO_REST_ANGLE);
}

// 1. Stationary Kick: kicks from a stop
void stationaryKick() {
  if (millis() - lastKickTime < KICK_COOLDOWN) return;
  lastKickTime = millis();

  stopRobot();
  setLeds(150, 150, 0); // Yellow indicator while kicking
  buzzer.noTone();

  // Strike forward 90°
  setServoAngle(kickAngle);
  delay(SERVO_KICK_DELAY_MS);

  // Retract to safe rest position
  setServoAngle(SERVO_REST_ANGLE);
  delay(SERVO_RETRACT_DELAY_MS);

  // Audio chirp
  buzzer.tone(1800, 50);
  delay(50);
  buzzer.noTone();

  stopRobot();
  setLeds(0, 0, 0);
}

// 2. Running Kick: drives forward into the ball WHILE striking!
// NOTE: LEDs are kept strictly OFF during running kick to eliminate voltage sag
// on low battery when DC motors and kicker servo draw peak current simultaneously.
void runningKick() {
  if (millis() - lastKickTime < KICK_COOLDOWN) return;
  lastKickTime = millis();

  // Power forward with LEDs off to conserve current
  int spd = getForwardSpeed();
  setMotorSpeeds(spd, spd);
  setLeds(0, 0, 0); // No lights when kicking forward
  buzzer.noTone();

  // Strike forward 90° WHILE wheels are charging forward
  setServoAngle(kickAngle);
  delay(SERVO_KICK_DELAY_MS);

  // Retract back to safe rest position
  setServoAngle(SERVO_REST_ANGLE);
  delay(SERVO_RETRACT_DELAY_MS);

  // Audio chirp after strike completes
  buzzer.tone(2000, 50);
  delay(50);
  buzzer.noTone();

  // Continue driving forward smoothly without lights
  setMotorSpeeds(spd, spd);
  setLeds(0, 0, 0);
}

// Smart Kick: picks running kick if driving forward, or stationary kick if stopped
void triggerKick() {
  if (isDrivingForward) {
    runningKick();
  } else {
    stationaryKick();
  }
}

// =============================================================================
// 🎉 CELEBRATION DANCE & MUSIC (GOAL VICTORY FANFARE)
// =============================================================================
const uint16_t NOTE_C5 = 523;
const uint16_t NOTE_E5 = 659;
const uint16_t NOTE_G5 = 784;
const uint16_t NOTE_C6 = 1047;

void celebrateStep(int dir, uint16_t noteFreq, uint16_t noteDuration, uint8_t r, uint8_t g, uint8_t b) {
  int left = 0;
  int right = 0;
  if (dir < 0) {
    left = -celebrateSpeed;
    right = celebrateSpeed;
  } else if (dir > 0) {
    left = celebrateSpeed;
    right = -celebrateSpeed;
  }
  currentLeftSpeed  = left;
  currentRightSpeed = right;
  leftMotor.run(-currentLeftSpeed);
  rightMotor.run(currentRightSpeed);

  setLeds(r, g, b);

  if (noteFreq > 0) {
    buzzer.tone(noteFreq, noteDuration);
  } else {
    delay(noteDuration);
  }
  buzzer.noTone();
  delay(15);
}

void celebrate() {
  // Upbeat 6-step victory fanfare synchronized with side-to-side turns and festive LEDs
  celebrateStep(-1, NOTE_C5, 120, 150, 0, 150); // Turn Left  | C5 | Magenta
  celebrateStep( 1, NOTE_E5, 120, 0, 150, 150); // Turn Right | E5 | Cyan
  celebrateStep(-1, NOTE_G5, 120, 150, 150, 0); // Turn Left  | G5 | Yellow
  celebrateStep( 1, NOTE_C6, 200, 0, 150, 0);   // Turn Right | C6 | Green
  celebrateStep(-1, NOTE_G5, 120, 0, 0, 150);   // Turn Left  | G5 | Blue
  celebrateStep( 1, NOTE_C6, 350, 150, 100, 0); // Turn Right | C6 (Triumphant finish!) | Gold

  buzzer.noTone();
  stopRobot();
}

void honkHorn() {
  // Quick double honk
  buzzer.tone(1400, 80); delay(90);
  buzzer.tone(1400, 120); delay(120);
  buzzer.noTone();
}

// =============================================================================
// 🎛️ CALIBRATION ENGINE (RUNTIME LAPTOP KEYS / SERIAL CALIBRATION)
// =============================================================================

void printCalibration() {
  Serial.println(F("\n=================================="));
  Serial.println(F("📱 mBot Phone & Calibration Status"));
  Serial.println(F("=================================="));
  Serial.print(F(" [W] Forward Speed:    ")); Serial.println(forwardSpeed);
  Serial.print(F(" [S] Backward Speed:   ")); Serial.println(backwardSpeed);
  Serial.print(F(" [A] Turn Speed:       ")); Serial.println(turnSpeed);
  Serial.print(F(" [Q] Curve Ratio:      ")); Serial.print(curveInnerRatio); Serial.println(F("%"));
  Serial.print(F(" [O] Curve Outer Spd:  ")); Serial.println(curveSpeed);
  Serial.print(F(" [T] Motor Trim (L/R): ")); Serial.println(motorTrim);
  Serial.print(F(" [X] 180 Spin Time:    ")); Serial.print(rotate180Ms); Serial.println(F(" ms"));
  Serial.print(F(" [K] Kick Angle:       ")); Serial.print(kickAngle); Serial.println(F(" deg"));
  Serial.print(F(" [+] Speed Cap:        ")); Serial.println(currentSpeedCap);
  Serial.println(F(" Commands: #SAVE to store in EEPROM, #RESET for defaults"));
  Serial.println(F("=================================="));
}

void beepHigh() {
  buzzer.tone(1500, 70);
  delay(70);
  buzzer.noTone();
}

void beepLow() {
  buzzer.tone(800, 70);
  delay(70);
  buzzer.noTone();
}

void processCalibrationCommand(const char* cmd) {
  if (cmd == NULL || strlen(cmd) == 0) return;

  if (strcmp(cmd, "?") == 0 || strcmp(cmd, "STATUS") == 0) {
    printCalibration();
    return;
  }
  if (strcasecmp(cmd, "SAVE") == 0) {
    saveConfigToEEPROM();
    Serial.println(F("[CAL] Saved configuration to EEPROM!"));
    return;
  }
  if (strcasecmp(cmd, "RESET") == 0) {
    resetConfigToDefaults();
    Serial.println(F("[CAL] Reset all parameters to factory defaults!"));
    return;
  }

  char key = toupper(cmd[0]);
  char op  = cmd[1];

  // Direct value assignment support: e.g. "W:180", "T:5"
  if (op == ':') {
    int val = atoi(&cmd[2]);
    switch (key) {
      case 'W': forwardSpeed = constrain(val, 30, 255); break;
      case 'S': backwardSpeed = constrain(val, 30, 255); break;
      case 'A':
      case 'D': turnSpeed = constrain(val, 30, 255); break;
      case 'Q':
      case 'E': curveInnerRatio = constrain(val, 10, 95); break;
      case 'O': curveSpeed = constrain(val, 30, 255); break;
      case 'T': motorTrim = constrain(val, -50, 50); break;
      case 'X': rotate180Ms = constrain(val, 100, 3000); break;
      case 'K': kickAngle = constrain(val, SERVO_MIN_LIMIT, SERVO_MAX_LIMIT); break;
      case 'C': currentSpeedCap = constrain(val, 30, 255); break;
      default: return;
    }
    beepHigh();
    Serial.print(F("[CAL] Set ")); Serial.print(key); Serial.print(F(" to ")); Serial.println(val);
    return;
  }

  // Step adjustments: '+' or '-'
  if (op == '+' || op == '-') {
    bool isPlus = (op == '+');
    switch (key) {
      case 'W':
        forwardSpeed = constrain(forwardSpeed + (isPlus ? 10 : -10), 30, 255);
        Serial.print(F("[CAL] Forward Speed: ")); Serial.println(forwardSpeed);
        break;
      case 'S':
        backwardSpeed = constrain(backwardSpeed + (isPlus ? 10 : -10), 30, 255);
        Serial.print(F("[CAL] Backward Speed: ")); Serial.println(backwardSpeed);
        break;
      case 'A':
      case 'D':
        turnSpeed = constrain(turnSpeed + (isPlus ? 5 : -5), 30, 255);
        Serial.print(F("[CAL] Turn Speed: ")); Serial.println(turnSpeed);
        break;
      case 'Q':
      case 'E':
        curveInnerRatio = constrain(curveInnerRatio + (isPlus ? 5 : -5), 10, 95);
        Serial.print(F("[CAL] Curve Inner %: ")); Serial.print(curveInnerRatio); Serial.println(F("%"));
        break;
      case 'O':
        curveSpeed = constrain(curveSpeed + (isPlus ? 10 : -10), 30, 255);
        Serial.print(F("[CAL] Curve Outer Speed: ")); Serial.println(curveSpeed);
        break;
      case 'T':
        motorTrim = constrain(motorTrim + (isPlus ? 2 : -2), -50, 50);
        Serial.print(F("[CAL] Motor Trim: ")); Serial.println(motorTrim);
        break;
      case 'X':
        rotate180Ms = constrain(rotate180Ms + (isPlus ? 25 : -25), 100, 3000);
        Serial.print(F("[CAL] 180 Spin Time: ")); Serial.print(rotate180Ms); Serial.println(F(" ms"));
        break;
      case 'K':
        kickAngle = constrain(kickAngle + (isPlus ? 5 : -5), SERVO_MIN_LIMIT, SERVO_MAX_LIMIT);
        Serial.print(F("[CAL] Kick Angle: ")); Serial.println(kickAngle);
        break;
      case 'C':
        currentSpeedCap = constrain(currentSpeedCap + (isPlus ? 15 : -15), 30, 255);
        Serial.print(F("[CAL] Speed Cap: ")); Serial.println(currentSpeedCap);
        break;
      default:
        return;
    }
    if (isPlus) beepHigh();
    else beepLow();
  }
}

// =============================================================================
// 🎮 PHONE (BT CAR CONTROLLER) & LAPTOP COMMAND HANDLER
// =============================================================================

void handleCommand(char c) {
  switch (c) {
    // --- DIRECTION CONTROLS (BT Car Controller App & Laptop Keys) ---
    case 'F': // BT Car Controller Forward
      moveForward();
      break;

    case 'B': // BT Car Controller Backward
    case 's': // Laptop Backward
      moveBackward();
      break;

    case 'L': // BT Car Controller Spin Left
    case 'a': // Laptop Left
      turnLeft();
      break;

    case 'R': // BT Car Controller Spin Right
    case 'd': // Laptop Right
      turnRight();
      break;

    case 'G': // BT Car Controller Forward-Left Arc
      curveLeft();
      break;

    case 'H': // BT Car Controller Forward-Right Arc
      curveRight();
      break;

    case 'I': // BT Car Controller Backward-Left Arc
      curveBackLeft();
      break;

    case 'J': // BT Car Controller Backward-Right Arc
      curveBackRight();
      break;

    // --- STOP CONTROLS (Fires when phone button is released) ---
    case 'S': // BT Car Controller Stop on release
    case 'D': // BT Car Controller Stop all
    case ' ': // Spacebar Stop
      stopRobot();
      break;

    // --- KICK CONTROLS (Mapped to 'Y', plus 'V', 'X', 'k') ---
    case 'Y': // Mapped to Y for phone controller -> Fire Kicker!
    case 'V': // Horn icon -> Fire Kicker!
    case 'X': // Extra button -> Fire Kicker!
    case 'k': // Laptop key -> Fire Kicker!
      triggerKick();
      break;

    case 'y': // Button release codes -> Ignore!
    case 'v':
    case 'x':
      break;

    // --- CELEBRATION CONTROLS (Mapped to 'Z', plus 'W', 'U', 'C') ---
    case 'Z': // Mapped to Z for phone controller -> Victory Celebration dance & fanfare!
    case 'W': // Icon next to forward/backward -> Celebrate!
    case 'U': // Back lights / hazard -> Celebrate!
    case 'C': // Direct celebration command
      celebrate();
      break;

    case 'z': // Button release codes -> Ignore!
    case 'w':
    case 'u':
      break;

    // --- LAPTOP TEST DRIVE SHORTCUTS ---
    case 'j': // Laptop running kick
      runningKick();
      break;

    case 'q': // Laptop curve left
      curveLeft();
      break;

    case 'e': // Laptop curve right
      curveRight();
      break;

    case 'c': // Laptop back-right
      curveBackRight();
      break;

    // --- SPEED SLIDER FROM BT CAR CONTROLLER (0 to 9, q) ---
    case '0': currentSpeedCap = 0;   stopRobot(); break;
    case '1': currentSpeedCap = 65;  beepHigh();  break;
    case '2': currentSpeedCap = 85;  beepHigh();  break;
    case '3': currentSpeedCap = 105; beepHigh();  break;
    case '4': currentSpeedCap = 130; beepHigh();  break;
    case '5': currentSpeedCap = 155; beepHigh();  break;
    case '6': currentSpeedCap = 180; beepHigh();  break;
    case '7': currentSpeedCap = 205; beepHigh();  break;
    case '8': currentSpeedCap = 230; beepHigh();  break;
    case '9': currentSpeedCap = 255; beepHigh();  break;

    // --- SPEED STEPPERS (+ / -) ---
    case '+':
      currentSpeedCap = min(currentSpeedCap + 15, MAX_SPEED);
      beepHigh();
      Serial.print(F("[CAL] Speed Cap: ")); Serial.println(currentSpeedCap);
      break;
    case '-':
      currentSpeedCap = max(currentSpeedCap - 15, 0);
      beepLow();
      Serial.print(F("[CAL] Speed Cap: ")); Serial.println(currentSpeedCap);
      break;

    default:
      break;
  }
}

// =============================================================================
// SETUP & MAIN LOOP
// =============================================================================

void setup() {
  Serial.begin(115200);

  // Initialize LEDs & Buzzer
  rgbLeds.setpin(13);
  setLeds(0, 0, 0);

  buzzer.setpin(8);
  buzzer.tone(1000, 200);
  delay(200);
  buzzer.noTone();

  // Load persistent calibration from EEPROM
  loadConfigFromEEPROM();

  // Initialize Kicker Servo on Pin A0 at rest position (180°)
  kickerServo.attach(SERVO_PIN);
  resetServo();

  Serial.println(F("========================================"));
  Serial.println(F("📱 mBot Phone Gamepad Controller Ready"));
  Serial.println(F("Compatible with 'BT Car Controller' App"));
  Serial.println(F("Baud: 115200 | Bluetooth SPP"));
  Serial.println(F("F/B/L/R = Move, S = Stop"));
  Serial.println(F("X = Kick, U/C = Celebrate, V = Horn"));
  Serial.println(F("Calibration: Send #? for status, #SAVE / #RESET"));
  Serial.println(F("========================================"));
}

char cmdBuffer[16];
uint8_t cmdIdx = 0;
bool inCmdMode = false;

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (inCmdMode) {
      if (c == '\n' || c == '\r' || cmdIdx >= sizeof(cmdBuffer) - 1) {
        cmdBuffer[cmdIdx] = '\0';
        if (cmdIdx > 0) {
          processCalibrationCommand(cmdBuffer);
        }
        inCmdMode = false;
        cmdIdx = 0;
      } else {
        cmdBuffer[cmdIdx++] = c;
      }
    } else {
      if (c == '#') {
        inCmdMode = true;
        cmdIdx = 0;
      } else {
        handleCommand(c);
      }
    }
  }

  // NOTE: Watchdog timeout is intentionally omitted so the robot drives smoothly
  // while the button is held in BT Car Controller, and stops when released ('S').
}
