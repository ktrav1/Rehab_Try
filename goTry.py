import cv2
import numpy as np
import time
import os
import math
import socket
import json
import urllib.request
from mediapipe.tasks.python import vision
from mediapipe.tasks.python import BaseOptions
from mediapipe import Image, ImageFormat

# --- 1. NETWORK UDP SETUP ---
UDP_IP = "127.0.0.1"
UDP_PORT = 4242
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# --- 2. MODEL DOWNLOAD ---
MODEL_PATH = "pose_landmarker_lite.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

if not os.path.exists(MODEL_PATH):
    print(f"Downloading model to {MODEL_PATH}...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

# --- 3. MEDIAPIPE INITIALIZATION ---
RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST = 12, 14, 16
smoothed_angle = 60.0
ALPHA_SMOOTHING = 0.25

def calculate_angle(a, b, c):
    a, b, c = np.array(a), np.array(b), np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    return 360 - angle if angle > 180.0 else angle

options = vision.PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=vision.RunningMode.VIDEO,
    num_poses=1,
)
landmarker = vision.PoseLandmarker.create_from_options(options)
cap = cv2.VideoCapture(0)
start_time = time.time()

print("--- REHAB VISION TELEMETRY STARTED ---")

while cap.isOpened():
    ok, frame = cap.read()
    if not ok:
        break

    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = Image(image_format=ImageFormat.SRGB, data=rgb_frame)

    timestamp_ms = int((time.time() - start_time) * 1000)
    result = landmarker.detect_for_video(mp_image, timestamp_ms)
    
    tracking_valid = False
    
    if result.pose_landmarks and len(result.pose_landmarks) > 0:
        lm = result.pose_landmarks[0]
        s_lm, e_lm, w_lm = lm[RIGHT_SHOULDER], lm[RIGHT_ELBOW], lm[RIGHT_WRIST]

        MIN_VISIBILITY = 0.25
        s_vis = getattr(s_lm, 'visibility', 0.0)
        e_vis = getattr(e_lm, 'visibility', 0.0)
        w_vis = getattr(w_lm, 'visibility', 0.0)

        # Ensure landmarks exist, meet visibility score, and are inside webcam frame boundaries
        points_visible = (s_vis > MIN_VISIBILITY and e_vis > MIN_VISIBILITY and w_vis > MIN_VISIBILITY)
        in_bounds = (
            0.0 <= e_lm.x <= 1.0 and 0.0 <= e_lm.y <= 1.0 and
            0.0 <= w_lm.x <= 1.0 and 0.0 <= w_lm.y <= 1.0
        )

        if points_visible and in_bounds:
            tracking_valid = True
            # Raw angle calculation
            raw_angle = calculate_angle([s_lm.x, s_lm.y], [e_lm.x, e_lm.y], [w_lm.x, w_lm.y])

# Snap near-straight extension angles directly to 180° to eliminate collinear jitter
            if raw_angle > 168.0:
                raw_angle = 180.0

# Apply exponential smoothing
            smoothed_angle = (ALPHA_SMOOTHING * raw_angle) + ((1.0 - ALPHA_SMOOTHING) * smoothed_angle)

    # Telemetry JSON packet
    data_packet = {
        "timestamp": round(time.time(), 3),
        "angle": round(smoothed_angle, 2),
        "tracking_valid": tracking_valid
    }

    # Print live telemetry directly to console
    status = "VALID" if tracking_valid else "OUT_OF_FRAME"
    print(f"[{data_packet['timestamp']}] Elbow Extension Angle: {data_packet['angle']}° | Status: {status}")

    # Send data via UDP to Godot
    sock.sendto(json.dumps(data_packet).encode(), (UDP_IP, UDP_PORT))

    cv2.imshow("Webcam Stream", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()