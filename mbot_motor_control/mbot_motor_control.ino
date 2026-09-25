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
const int SERVO_PIN = A0;
const int SERVO_REST_ANGLE = 0;      // Rest / retracted position (degrees)
const int SERVO_KICK_ANGLE = 90;     // Kick / extended strike position (degrees)
const int SERVO_KICK_DELAY_MS = 250; // Milliseconds to hold extended position during kick
// Safety: speed limiting
const int MAX_SPEED = 150;
const int SPEED_STEP = 20; // how much +/- changes the cap per keypress
int currentSpeedCap = 100; // starting speed (<= MAX_SPEED)

// Safety: smooth acceleration / deceleration
int currentLeftSpeed = 0;
int currentRightSpeed = 0;
const int RAMP_STEP = 15;  // speed change per ramp tick (bigger = snappier)
const int RAMP_DELAY = 20; // ms to wait between each of those steps

// Every time a valid command arrives we reset this timer. If too long passes
// with no command, we stop the robot. This is the same mechanism the
// Bluetooth/gesture layer will reuse later.
unsigned long lastCommandTime = 0;
const unsigned long COMM_TIMEOUT_MS = 800; // stop if silent for this long

// ramp both motors smoothly toward a target

void setMotorSpeeds(int targetLeft, int targetRight) {
  // Clamp targets to the safety cap
  targetLeft = constrain(targetLeft, -currentSpeedCap, currentSpeedCap);
  targetRight = constrain(targetRight, -currentSpeedCap, currentSpeedCap);

  // Ramp both motors together, one step at a time, until both reach target
  while (currentLeftSpeed != targetLeft || currentRightSpeed != targetRight) {
    currentLeftSpeed = stepToward(currentLeftSpeed, targetLeft, RAMP_STEP);
    currentRightSpeed = stepToward(currentRightSpeed, targetRight, RAMP_STEP);

    leftMotor.run(-currentLeftSpeed);  // flip to (currentLeftSpeed) if needed
    rightMotor.run(currentRightSpeed); // flip to (-currentRightSpeed) if needed

    delay(RAMP_DELAY);
  }
}

int stepToward(int current, int target, int step) {
  if (current < target)
    return min(current + step, target);
  if (current > target)
    return max(current - step, target);
  return current;
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
  setMotorSpeeds(currentSpeedCap, currentSpeedCap); 
  setLeds(0, 150, 0); // Green
}
void moveBackward() { 
  setMotorSpeeds(-currentSpeedCap, -currentSpeedCap); 
  setLeds(150, 0, 0); // Red
}

// In place pivot: wheels spin opposite directions
void turnLeft() { 
  setMotorSpeeds(-currentSpeedCap, currentSpeedCap); 
  rgbLeds.setColor(1, 0, 0, 150);
  rgbLeds.setColor(2, 0, 0, 0);
  rgbLeds.show();
}
void turnRight() { 
  setMotorSpeeds(currentSpeedCap, -currentSpeedCap); 
  rgbLeds.setColor(1, 0, 0, 0);
  rgbLeds.setColor(2, 0, 0, 150);
  rgbLeds.show();
}

// Gentle arc turn: one wheel slower, not reversed - useful for approaching the
// ball at an angle rather than spinning on the spot
void curveLeft() { 
  setMotorSpeeds(currentSpeedCap / 3, currentSpeedCap); 
  rgbLeds.setColor(1, 0, 150, 150);
  rgbLeds.setColor(2, 0, 50, 50);
  rgbLeds.show();
}
void curveRight() { 
  setMotorSpeeds(currentSpeedCap, currentSpeedCap / 3); 
  rgbLeds.setColor(1, 0, 50, 50);
  rgbLeds.setColor(2, 0, 150, 150);
  rgbLeds.show();
}

// "Turn around" - pivot ~180 degrees. Duration is a starting estimate;

const unsigned long ROTATE_180_MS = 650; // should tune this
void rotate180() {
  setMotorSpeeds(-currentSpeedCap, currentSpeedCap); // start pivoting
  setLeds(150, 150, 0); // Yellow

  delay(ROTATE_180_MS);
  stopRobot();
}

// Extra "special functionality": quick side-to-side wiggle, e.g. after a goal
void celebrate() {
  for (int i = 0; i < 2; i++) {
    setMotorSpeeds(-80, 80);
    setLeds(150, 0, 0);
    delay(150);
    setMotorSpeeds(80, -80);
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
void kick() {
  setLeds(150, 150, 0); // Yellow indicator while kicking
  buzzer.tone(1500, 150);
  setServoAngle(SERVO_KICK_ANGLE);
  delay(SERVO_KICK_DELAY_MS);
  setServoAngle(SERVO_REST_ANGLE);
  delay(150); // Give time for servo arm to retract
  buzzer.noTone();
  stopRobot();
}

// SERIAL TEST HARNESS - stand-in for gesture/Bluetooth input for now

void handleCommand(char c) {
  lastCommandTime = millis();
  switch (c) {
  case 'w':
    moveForward();
    break;
  case 's':
    moveBackward();
    break;
  case 'a':
    turnLeft();
    break;
  case 'd':
    turnRight();
    break;
  case 'q':
    curveLeft();
    break;
  case 'e':
    curveRight();
    break;
  case 'x':
    rotate180();
    break;
  case 'c':
    celebrate();
    break;
  case 'k':
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

  // Communication/signal loss failsafe: if no command received recently, force
  // stop. (Right now "silence" just means no one typed anything - once
  // Bluetooth is in, this same check will catch a dropped wireless link.)
  if (millis() - lastCommandTime > COMM_TIMEOUT_MS &&
      (currentLeftSpeed != 0 || currentRightSpeed != 0)) {
    stopRobot();
  }
}
