#include <MeMCore.h>

// Motor objects: shoul adjust ports accordingly
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
const int SERVO_KICK_ANGLE = 90;     // Kick / extended strike position (degrees)
const int SERVO_KICK_DELAY_MS = 250; // Milliseconds to hold extended position during kick
// =============================================================================
// ⚙️ SPEED & POWER CONFIGURATION INTERFACE (CHANGE ALL SPEEDS HERE)
// =============================================================================
// Note: mBot DC motor speed ranges from 0 (stopped) to 255 (100% full battery power).
const int FULL_POWER = 255;

// --- MASTER OVERRIDE ---
// Set to true to force ALL functions to run at 100% Full Power (255) at once.
// Set to false to use the individual function settings below.
const bool ALL_FULL_POWER = false;

// --- INDIVIDUAL FUNCTION SETTINGS ---
// For each function, set *_FULL_POWER to true for 255, or false to use the specific speed.

// 1. Forward ('w', 'F')
const bool FORWARD_FULL_POWER    = true; // true = 255 (Full Power), false = use FORWARD_SPEED
const int  FORWARD_SPEED         = 150;   // Specific speed (0 to 255)

// 2. Backward ('s', 'B')
const bool BACKWARD_FULL_POWER   = true; // true = 255 (Full Power), false = use BACKWARD_SPEED
const int  BACKWARD_SPEED        = 130;   // Specific speed (0 to 255)

// 3. In-Place Pivot Turn ('a', 'd', 'L', 'R')
const bool TURN_FULL_POWER       = false; // true = 255 (Full Power), false = use TURN_SPEED
const int  TURN_SPEED            = 98;   // Specific speed (0 to 255)

// 4. Curve / Arc Turn ('q', 'e', 'G', 'I')
const bool CURVE_FULL_POWER      = true; // true = outer wheel at 255, false = use CURVE_SPEED
const int  CURVE_SPEED           = 150;   // Outer wheel speed (0 to 255)
const int  CURVE_INNER_RATIO     = 50;    // Inner wheel % of outer wheel (e.g. 50 = half speed, 70 = wider/gentler arc)

// 5. 180-Degree Turn-Around Spin ('x')
const bool ROTATE180_FULL_POWER  = false; // true = 255 (Full Power), false = use ROTATE180_SPEED
const int  ROTATE180_SPEED       = 150;   // Specific speed (0 to 255)
const unsigned long ROTATE_180_MS = 650;  // Milliseconds to spin for 180 degrees

// 6. Celebration Wiggle ('c')
const int  CELEBRATE_SPEED       = 100;   // Speed during victory wiggle (0 to 255)

// --- MOTOR ACCELERATION RAMPING ---
const int RAMP_STEP  = 15; // Speed change per ramp step (bigger = snappier, e.g. 255 = instant)
const int RAMP_DELAY = 20; // Milliseconds to wait between each ramp step

// --- RUNTIME SPEED LIMITER (+ / - keys) ---
// If true, pressing '+' and '-' in serial/Bluetooth caps all speeds to currentSpeedCap.
// If false, each function runs strictly at its configured speed above.
const bool ENABLE_RUNTIME_SPEED_CAP = false;
const int  MAX_SPEED                = 255;
const int  SPEED_STEP               = 20;
int        currentSpeedCap          = 255;

// =============================================================================
// Helper functions to resolve final speeds
// =============================================================================
inline int getForwardSpeed() {
  return (ALL_FULL_POWER || FORWARD_FULL_POWER) ? FULL_POWER : FORWARD_SPEED;
}

inline int getBackwardSpeed() {
  return (ALL_FULL_POWER || BACKWARD_FULL_POWER) ? FULL_POWER : BACKWARD_SPEED;
}

inline int getTurnSpeed() {
  return (ALL_FULL_POWER || TURN_FULL_POWER) ? FULL_POWER : TURN_SPEED;
}

inline int getCurveOuterSpeed() {
  return (ALL_FULL_POWER || CURVE_FULL_POWER) ? FULL_POWER : CURVE_SPEED;
}

inline int getCurveInnerSpeed() {
  return (getCurveOuterSpeed() * constrain(CURVE_INNER_RATIO, 0, 100)) / 100;
}

inline int getRotate180Speed() {
  return (ALL_FULL_POWER || ROTATE180_FULL_POWER) ? FULL_POWER : ROTATE180_SPEED;
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

// Ramp both motors smoothly toward target speeds
void setMotorSpeeds(int targetLeft, int targetRight) {
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

// Gentle arc turn: moves forward while curving slightly in the target direction
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

// "Turn around" - pivot ~180 degrees
void rotate180() {
  int spd = getRotate180Speed();
  setMotorSpeeds(-spd, spd); // start pivoting
  setLeds(150, 150, 0); // Yellow

  delay(ROTATE_180_MS);
  stopRobot();
}

// Extra "special functionality": quick side-to-side wiggle, e.g. after a goal
void celebrate() {
  for (int i = 0; i < 2; i++) {
    setMotorSpeeds(-CELEBRATE_SPEED, CELEBRATE_SPEED);
    setLeds(150, 0, 0);
    delay(150);
    setMotorSpeeds(CELEBRATE_SPEED, -CELEBRATE_SPEED);
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
  setServoAngle(SERVO_KICK_ANGLE);
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

// SERIAL TEST HARNESS - stand-in for gesture/Bluetooth input for now

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
  case 'x':
    rotate180();
    break;
  case 'c':
    celebrate();
    break;
  case 'k':
  case 'X': // Standard RC action / button
  case 'V': // Standard RC horn button
    kick();
    break;
  case 'o':
    // Calibration helper: open/deploy kicker
    setServoAngle(SERVO_KICK_ANGLE);
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
    buzzer.tone(1200, 100);
    delay(100);
    buzzer.noTone();
    break;
  case '-':
    currentSpeedCap = max(currentSpeedCap - SPEED_STEP, 0);
    buzzer.tone(800, 100);
    delay(100);
    buzzer.noTone();
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

  Serial.println("mBot motor & servo control ready.");
  Serial.println("w/s/a/d = move, q/e = curve, x = turn around, space = stop, "
                 "c = celebrate, k = kick (servo), o/p = servo open/close, +/- = speed cap");
  lastCommandTime = millis();
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    handleCommand(c);
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
