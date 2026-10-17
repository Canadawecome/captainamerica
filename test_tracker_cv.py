import cv2, json
from pathlib import Path

video_path = "vso_clip_001/clip.mp4"
cap = cv2.VideoCapture(video_path)

fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"Video {width}x{height}, {fps} fps, {total_frames} frames ({total_frames/fps:.1f}s)")

# Load body and face cascades
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
upperbody_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_upperbody.xml')
fullbody_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_fullbody.xml')

# Sample 10 frames across the video
detections = []
for sec in [1.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0]:
    frame_idx = int(sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 3)
    bodies = upperbody_cascade.detectMultiScale(gray, 1.1, 2)
    print(f"Sec {sec:.1f}: {len(faces)} faces, {len(bodies)} bodies")
    for (x, y, w, h) in faces:
        print(f"   Face: center=({x + w//2}, {y + h//2}), size=({w}x{h})")
    for (x, y, w, h) in bodies:
        print(f"   UpperBody: center=({x + w//2}, {y + h//2}), size=({w}x{h})")

cap.release()
