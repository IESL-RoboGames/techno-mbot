#include <MeMCore.h>

// Motor objects: shoul adjust ports accordingly
MeDCMotor leftMotor(M1);
MeDCMotor rightMotor(M2);

// Safety: speed limiting 
const int MAX_SPEED   = 150;   
const int SPEED_STEP  = 20;    // how much +/- changes the cap per keypress
int currentSpeedCap   = 100;   // starting speed (<= MAX_SPEED)

// Safety: smooth acceleration / deceleration
int currentLeftSpeed  = 0;
int currentRightSpeed = 0;
const int RAMP_STEP   = 15;    // speed change per ramp tick (bigger = snappier)
const int RAMP_DELAY  = 20;    // ms to wait between each of those steps

// Every time a valid command arrives we reset this timer. If too long passes with no command, we stop the robot. This is the same mechanism the Bluetooth/gesture layer will reuse later.
unsigned long lastCommandTime = 0;
const unsigned long COMM_TIMEOUT_MS = 800; // stop if silent for this long


// ramp both motors smoothly toward a target

void setMotorSpeeds(int targetLeft, int targetRight) {
  // Clamp targets to the safety cap
  targetLeft  = constrain(targetLeft, -currentSpeedCap, currentSpeedCap);
  targetRight = constrain(targetRight, -currentSpeedCap, currentSpeedCap);

  // Ramp both motors together, one step at a time, until both reach target
  while (currentLeftSpeed != targetLeft || currentRightSpeed != targetRight) {
    currentLeftSpeed  = stepToward(currentLeftSpeed, targetLeft, RAMP_STEP);
    currentRightSpeed = stepToward(currentRightSpeed, targetRight, RAMP_STEP);

    leftMotor.run(-currentLeftSpeed);   // flip to (currentLeftSpeed) if needed
    rightMotor.run(currentRightSpeed);  // flip to (-currentRightSpeed) if needed

    delay(RAMP_DELAY);
  }
}

int stepToward(int current, int target, int step) {
  if (current < target) return min(current + step, target);
  if (current > target) return max(current - step, target);
  return current;
}

// MOVEMENT FUNCTIONS 

void moveForward()  { setMotorSpeeds(currentSpeedCap, currentSpeedCap); }
void moveBackward() { setMotorSpeeds(-currentSpeedCap, -currentSpeedCap); }

// In place pivot: wheels spin opposite directions
void turnLeft()  { setMotorSpeeds(-currentSpeedCap, currentSpeedCap); }
void turnRight() { setMotorSpeeds(currentSpeedCap, -currentSpeedCap); }

// Gentle arc turn: one wheel slower, not reversed - useful for approaching the ball at an angle rather than spinning on the spot
void curveLeft()  { setMotorSpeeds(currentSpeedCap / 3, currentSpeedCap); }
void curveRight() { setMotorSpeeds(currentSpeedCap, currentSpeedCap / 3); }

// "Turn around" - pivot ~180 degrees. Duration is a starting estimate;

const unsigned long ROTATE_180_MS = 650; //should tune this
void rotate180() {
  setMotorSpeeds(-currentSpeedCap, currentSpeedCap); // start pivoting
  delay(ROTATE_180_MS);
  stopRobot();
}

void stopRobot() {
  setMotorSpeeds(0, 0);
}

// Extra "special functionality": quick side-to-side wiggle, e.g. after a goal
void celebrate() {
  for (int i = 0; i < 2; i++) {
    setMotorSpeeds(-80, 80);
    delay(150);
    setMotorSpeeds(80, -80);
    delay(150);
  }
  stopRobot();
}

// SERIAL TEST HARNESS - stand-in for gesture/Bluetooth input for now

void handleCommand(char c) {
  lastCommandTime = millis();
  switch (c) {
    case 'w': moveForward();  break;
    case 's': moveBackward(); break;
    case 'a': turnLeft();     break;
    case 'd': turnRight();    break;
    case 'q': curveLeft();    break;
    case 'e': curveRight();   break;
    case 'x': rotate180();    break;
    case 'c': celebrate();    break;
    case ' ': stopRobot();    break;
    case '+':
      currentSpeedCap = min(currentSpeedCap + SPEED_STEP, MAX_SPEED);
      Serial.print("Speed cap: "); Serial.println(currentSpeedCap);
      break;
    case '-':
      currentSpeedCap = max(currentSpeedCap - SPEED_STEP, 0);
      Serial.print("Speed cap: "); Serial.println(currentSpeedCap);
      break;
    default:
      break; // ignore newline/unrecognized characters
  }
}

void setup() {
  Serial.begin(9600);
  Serial.println("mBot motor control ready.");
  Serial.println("w/s/a/d = move, q/e = curve, x = turn around, space = stop, c = celebrate, +/- = speed cap");
  lastCommandTime = millis();
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    handleCommand(c);
  }

  // Communication/signal loss failsafe: if no command received recently, force stop.
  // (Right now "silence" just means no one typed anything - once Bluetooth is in, this same check will catch a dropped wireless link.)
  if (millis() - lastCommandTime > COMM_TIMEOUT_MS &&
      (currentLeftSpeed != 0 || currentRightSpeed != 0)) {
    stopRobot();
  }
}
