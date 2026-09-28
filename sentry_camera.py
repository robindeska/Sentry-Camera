"""Raspberry Pi pan-tilt face tracker with a Flask video stream."""

from flask import Flask, Response
from picamera2 import Picamera2
from gpiozero import AngularServo
from gpiozero.pins.pigpio import PiGPIOFactory
import cv2
import time

app = Flask(__name__)

factory = PiGPIOFactory()

pan_servo = AngularServo(
    12,
    min_angle=-90,
    max_angle=90,
    min_pulse_width=0.0005,
    max_pulse_width=0.0025,
    pin_factory=factory
)

tilt_servo = AngularServo(
    13,
    min_angle=-90,
    max_angle=90,
    min_pulse_width=0.0005,
    max_pulse_width=0.0025,
    pin_factory=factory
)

pan_angle = 0
tilt_angle = 0

pan_servo.angle = pan_angle
tilt_servo.angle = tilt_angle

camera = Picamera2()

camera.configure(
    camera.create_preview_configuration(
        main={
            "size": (320, 240),
            "format": "RGB888"
        }
    )
)

camera.start()

time.sleep(2)

face_cascade = cv2.CascadeClassifier(
    "/usr/share/opencv4/haarcascades/"
    "haarcascade_frontalface_default.xml"
)

smoothed_x = 160
smoothed_y = 120

SMOOTHING = 0.45

DEADZONE_X = 15
DEADZONE_Y = 12

GAIN_X = 0.05
GAIN_Y = 0.04

MAX_MOVE_X = 5
MAX_MOVE_Y = 3


def generate_frames():
    global pan_angle
    global tilt_angle
    global smoothed_x
    global smoothed_y

    while True:
        frame = camera.capture_array()

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_RGB2GRAY
        )

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(50, 50)
        )

        center_x = frame.shape[1] // 2
        center_y = frame.shape[0] // 2

        # Draw tracking center lines
        cv2.line(
            frame,
            (center_x, 0),
            (center_x, frame.shape[0]),
            (255, 0, 0),
            1
        )

        cv2.line(
            frame,
            (0, center_y),
            (frame.shape[1], center_y),
            (255, 0, 0),
            1
        )

        if len(faces) > 0:
            # Track largest detected face
            x, y, w, h = max(
                faces,
                key=lambda f: f[2] * f[3]
            )

            face_x = x + w // 2
            face_y = y + h // 2

            # Draw face box
            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

            # Smooth face position
            smoothed_x = (
                SMOOTHING * face_x
                + (1 - SMOOTHING) * smoothed_x
            )

            smoothed_y = (
                SMOOTHING * face_y
                + (1 - SMOOTHING) * smoothed_y
            )

            error_x = smoothed_x - center_x
            error_y = smoothed_y - center_y

            # PAN CONTROL
            if abs(error_x) > DEADZONE_X:
                move_x = error_x * GAIN_X

                move_x = max(
                    -MAX_MOVE_X,
                    min(MAX_MOVE_X, move_x)
                )

                pan_angle -= move_x

                pan_angle = max(
                    -45,
                    min(45, pan_angle)
                )

                pan_servo.angle = pan_angle

            # TILT CONTROL
            if abs(error_y) > DEADZONE_Y:
                move_y = error_y * GAIN_Y

                move_y = max(
                    -MAX_MOVE_Y,
                    min(MAX_MOVE_Y, move_y)
                )

                # Direction reversed for our physical mount
                tilt_angle += move_y

                tilt_angle = max(
                    -35,
                    min(35, tilt_angle)
                )

                tilt_servo.angle = tilt_angle

        # Convert frame for browser stream
        ok, buffer = cv2.imencode(
            ".jpg",
            frame
        )

        if not ok:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + buffer.tobytes()
            + b"\r\n"
        )


@app.route("/")
def index():
    return """
    <html>
        <body>
            <h2>Sentry Camera</h2>
            <img src="/video_feed">
        </body>
    </html>
    """


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

