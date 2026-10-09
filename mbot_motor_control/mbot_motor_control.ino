#include <MeMCore.h>
#include <EEPROM.h>

// Motor objects: adjust ports accordingly
MeDCMotor leftMotor(M1);
MeDCMotor rightMotor(M2);

// Onboard RGB LEDs (Port 0 on mCore, 2 LEDs: 1=Left, 2=Right)
MeRGBLed rgbLeds(0, 2);

// Onboard Buzzer
MeBuzzer buzzer;

// Servo on pin A0 (mBot Port 4 Pin A0 / analog header A0)
// Uses standard Arduino Servo driver bundled in Makeblock to prevent duplicate symbol linker conflicts
#include <utility/Servo.h>
Servo kickerServo;
const int SERVO_PIN = 9;
const int SERVO_REST_ANGLE = 0;      // Rest / retracted position (degrees)
int kickAngle = 90;                  // Kick / extended strike position (degrees) - calibratable!
const int SERVO_KICK_DELAY_MS = 250; // Milliseconds to hold extended position during kick

// =============================================================================
// ⚙️ SPEED & POWER CONFIGURATION INTERFACE (CALIBRATABLE AT RUNTIME)
// =============================================================================
// Note: mBot DC motor speed ranges from 0 (stopped) to 255 (100% full battery power).
const int FULL_POWER = 255;

// --- MASTER OVERRIDE ---
// Set to true to force ALL functions to run at 100% Full Power (255) at once.
// Set to false to use individual calibrated speeds below.
const bool ALL_FULL_POWER = false;

// --- CALIBRATABLE ROBOT PARAMETERS (Saved to EEPROM) ---
int forwardSpeed     = 150;  // Forward speed (30 to 255)
int backwardSpeed    = 130;  // Backward speed (30 to 255)
int turnSpeed        = 98;   // In-place pivot speed (30 to 255)
int curveSpeed       = 150;  // Arc turn outer wheel speed (30 to 255)
int curveInnerRatio  = 50;   // Inner wheel % of outer wheel (10 to 95)
int motorTrim        = 0;    // Steering trim balance (-50 to +50: + corrects left pull, - corrects right pull)
unsigned long rotate180Ms = 650; // Duration for 180° turnaround spin (ms)
int celebrateSpeed   = 100;  // Victory wiggle speed (0 to 255)

// --- MOTOR ACCELERATION RAMPING ---
const int RAMP_STEP  = 15; // Speed change per ramp step (bigger = snappier, e.g. 255 = instant)
const int RAMP_DELAY = 20; // Milliseconds to wait between each ramp step

// --- RUNTIME SPEED LIMITER (+ / - keys) ---
bool ENABLE_RUNTIME_SPEED_CAP = true;
const int  MAX_SPEED          = 255;
const int  SPEED_STEP         = 15;
int        currentSpeedCap    = 255;

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
    kickAngle       = constrain(cfg.kickAngle, 20, 180);
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
  return ALL_FULL_POWER ? FULL_POWER : forwardSpeed;
}

inline int getBackwardSpeed() {
  return ALL_FULL_POWER ? FULL_POWER : backwardSpeed;
}

inline int getTurnSpeed() {
  return ALL_FULL_POWER ? FULL_POWER : turnSpeed;
}

inline int getCurveOuterSpeed() {
  return ALL_FULL_POWER ? FULL_POWER : curveSpeed;
}

inline int getCurveInnerSpeed() {
  return (getCurveOuterSpeed() * constrain(curveInnerRatio, 0, 100)) / 100;
}

inline int getRotate180Speed() {
  return ALL_FULL_POWER ? FULL_POWER : 150;
}

// Safety: smooth acceleration / deceleration tracking
int currentLeftSpeed = 0;
int currentRightSpeed = 0;

// Communication failsafe timer
unsigned long lastCommandTime = 0;
const unsigned long COMM_TIMEOUT_MS = 800; // stop if silent for this long

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
  // Positive motorTrim: slows left / boosts right (fixes pulling left)
  // Negative motorTrim: slows right / boosts left (fixes pulling right)
  if (motorTrim != 0) {
    if (targetLeft > 0)       targetLeft = constrain(targetLeft - motorTrim, 0, FULL_POWER);
    else if (targetLeft < 0)  targetLeft = constrain(targetLeft + motorTrim, -FULL_POWER, 0);

    if (targetRight > 0)      targetRight = constrain(targetRight + motorTrim, 0, FULL_POWER);
    else if (targetRight < 0) targetRight = constrain(targetRight - motorTrim, -FULL_POWER, 0);
  }

  // Clamp targets to safety limit (-255 to 255, or currentSpeedCap if runtime cap is enabled)
  int cap = ENABLE_RUNTIME_SPEED_CAP ? currentSpeedCap : FULL_POWER;
  targetLeft = constrain(targetLeft, -cap, cap);
  targetRight = constrain(targetRight, -cap, cap);

  // Ramp both motors together, one step at a time, until both reach target
  while (currentLeftSpeed != targetLeft || currentRightSpeed != targetRight) {
    currentLeftSpeed = stepToward(currentLeftSpeed, targetLeft, RAMP_STEP);
    currentRightSpeed = stepToward(currentRightSpeed, targetRight, RAMP_STEP);

    leftMotor.run(-currentLeftSpeed);  // flip to (currentLeftSpeed) if needed
    rightMotor.run(currentRightSpeed); // flip to (-currentRightSpeed) if needed

    delay(RAMP_DELAY);
  }
}

// MOVEMENT FUNCTIONS
void setLeds(uint8_t red, uint8_t green, uint8_t blue) {
  rgbLeds.setColor(1, red, green, blue);
  rgbLeds.setColor(2, red, green, blue);
  rgbLeds.show();
}

void stopRobot() { 
  setMotorSpeeds(0, 0); 
  setLeds(0, 0, 0);
}

void moveForward() { 
  int spd = getForwardSpeed();
  setMotorSpeeds(spd, spd); 
  setLeds(0, 150, 0); // Green
}

void moveBackward() { 
  int spd = getBackwardSpeed();
  setMotorSpeeds(-spd, -spd); 
  setLeds(150, 0, 0); // Red
}

// In-place pivot: wheels spin opposite directions
void turnLeft() { 
  int spd = getTurnSpeed();
  setMotorSpeeds(-spd, spd); 
  rgbLeds.setColor(1, 0, 0, 150);
  rgbLeds.setColor(2, 0, 0, 0);
  rgbLeds.show();
}

void turnRight() { 
  int spd = getTurnSpeed();
  setMotorSpeeds(spd, -spd); 
  rgbLeds.setColor(1, 0, 0, 0);
  rgbLeds.setColor(2, 0, 0, 150);
  rgbLeds.show();
}

// Gentle forward arc turns: moves forward while curving in target direction
void curveLeft() { 
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(innerSpd, outerSpd); 
  rgbLeds.setColor(1, 0, 150, 150);
  rgbLeds.setColor(2, 0, 50, 50);
  rgbLeds.show();
}

void curveRight() { 
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(outerSpd, innerSpd); 
  rgbLeds.setColor(1, 0, 50, 50);
  rgbLeds.setColor(2, 0, 150, 150);
  rgbLeds.show();
}

// Gentle backward arc turns: moves backward while curving in target direction
void curveBackLeft() { 
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(-innerSpd, -outerSpd); 
  rgbLeds.setColor(1, 150, 0, 50);
  rgbLeds.setColor(2, 50, 0, 0);
  rgbLeds.show();
}

void curveBackRight() { 
  int outerSpd = getCurveOuterSpeed();
  int innerSpd = getCurveInnerSpeed();
  setMotorSpeeds(-outerSpd, -innerSpd); 
  rgbLeds.setColor(1, 50, 0, 0);
  rgbLeds.setColor(2, 150, 0, 50);
  rgbLeds.show();
}

// "Turn around" - pivot ~180 degrees
void rotate180() {
  int spd = getRotate180Speed();
  setMotorSpeeds(-spd, spd); // start pivoting
  setLeds(150, 150, 0); // Yellow

  delay(rotate180Ms);
  stopRobot();
}

// Extra "special functionality": quick side-to-side wiggle, e.g. after a goal
void celebrate() {
  for (int i = 0; i < 2; i++) {
    setMotorSpeeds(-celebrateSpeed, celebrateSpeed);
    setLeds(150, 0, 0);
    delay(150);
    setMotorSpeeds(celebrateSpeed, -celebrateSpeed);
    setLeds(0, 150, 0);
    delay(150);
  }
  stopRobot();
}

// SERVO / KICKER FUNCTIONS
void setServoAngle(int angle) {
  kickerServo.write(constrain(angle, 0, 180));
}

void resetServo() {
  setServoAngle(SERVO_REST_ANGLE);
}

// Full kick sequence: swing forward to strike the ball, then retract
unsigned long lastKickTime = 0;
const unsigned long KICK_COOLDOWN_MS = 500; // Debounce: prevent rapid-fire repeated kicks

void kick() {
  if (millis() - lastKickTime < KICK_COOLDOWN_MS) {
    return; // Ignore if called again too quickly
  }
  lastKickTime = millis();

  setLeds(150, 150, 0); // Yellow indicator while kicking
  buzzer.tone(1500, 150);
  setServoAngle(kickAngle);
  delay(SERVO_KICK_DELAY_MS);
  setServoAngle(SERVO_REST_ANGLE);
  delay(150); // Give time for servo arm to retract
  buzzer.noTone();
  stopRobot();

  // Clear any extra 'k' commands queued during the kick delay
  while (Serial.available() > 0) {
    Serial.read();
  }
  lastCommandTime = millis();
}

// =============================================================================
// 🎛️ CALIBRATION ENGINE (RUNTIME KEY / SERIAL CALIBRATION)
// =============================================================================

void printCalibration() {
  Serial.println(F("\n=================================="));
  Serial.println(F("🤖 mBot Football Calibration"));
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
      case 'K': kickAngle = constrain(val, 20, 180); break;
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
        kickAngle = constrain(kickAngle + (isPlus ? 5 : -5), 20, 180);
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
// COMMAND HANDLER & SERIAL PROTOCOL
// =============================================================================

void handleCommand(char c) {
  lastCommandTime = millis();
  switch (c) {
  case 'w':
  case 'F': // Standard RC forward
    moveForward();
    break;
  case 's':
  case 'B': // Standard RC backward
    moveBackward();
    break;
  case 'a':
  case 'L': // Standard RC left
    turnLeft();
    break;
  case 'd':
  case 'R': // Standard RC right
    turnRight();
    break;
  case 'q':
  case 'G': // Standard RC forward-left
    curveLeft();
    break;
  case 'e':
  case 'I': // Standard RC forward-right
    curveRight();
    break;
  case 'z':
  case 'H': // Standard RC backward-left
    curveBackLeft();
    break;
  case 'c':
  case 'J': // Standard RC backward-right
    curveBackRight();
    break;
  case 'x':
    rotate180();
    break;
  case 'v':
  case 'C': // Goal celebration wiggle (v for Victory)
    celebrate();
    break;
  case 'k':
  case 'X': // Standard RC action / button
  case 'V': // Standard RC horn button
    kick();
    break;
  case 'o':
    // Calibration helper: open/deploy kicker
    setServoAngle(kickAngle);
    break;
  case 'p':
    // Calibration helper: reset/retract kicker
    resetServo();
    break;
  case ' ':
  case 'S': // Standard RC stop
  case 'D': // Standard RC stop all
    stopRobot();
    break;
  case '+':
    currentSpeedCap = min(currentSpeedCap + SPEED_STEP, MAX_SPEED);
    beepHigh();
    Serial.print(F("[CAL] Speed Cap: ")); Serial.println(currentSpeedCap);
    break;
  case '-':
    currentSpeedCap = max(currentSpeedCap - SPEED_STEP, 0);
    beepLow();
    Serial.print(F("[CAL] Speed Cap: ")); Serial.println(currentSpeedCap);
    break;
  default:
    break; // ignore newline/unrecognized characters
  }
}

void setup() {
  Serial.begin(115200);
  
  // Initialize RGB LEDs
  rgbLeds.setpin(13); // mCore onboard RGB pin
  setLeds(0, 0, 0);   // All off

  // Startup beep
  buzzer.setpin(8); // mCore onboard Buzzer pin
  buzzer.tone(1000, 200);
  delay(200);
  buzzer.noTone();
  
  // Initialize Kicker Servo on Pin A0
  kickerServo.attach(SERVO_PIN);
  resetServo();

  // Load persistent calibration from EEPROM if available
  loadConfigFromEEPROM();

  Serial.println(F("mBot motor & servo control ready."));
  Serial.println(F("w/s/a/d = move, q/e = arc fwd, z/c = arc back, x = turn around, space = stop"));
  Serial.println(F("v = celebrate, k = kick, o/p = servo open/close, +/- = speed cap"));
  Serial.println(F("Calibration: Send #? for status, #SAVE to EEPROM, #RESET for defaults"));
  lastCommandTime = millis();
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

  // Communication failsafe:
  // Disabled for Mobile App control so the robot doesn't stop after 800ms while holding.
  // The robot stops immediately when the button is released (sending 'S' / space) or stop is pressed.
  /*
  if (millis() - lastCommandTime > COMM_TIMEOUT_MS &&
      (currentLeftSpeed != 0 || currentRightSpeed != 0)) {
    stopRobot();
  }
  */
}

