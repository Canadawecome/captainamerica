import cv2, json
from pathlib import Path

video_path = "vso_clip_001/clip.mp4"
cap = cv2.VideoCapture(video_path)

fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

# Save 5 sample frames at 0s, 15s, 30s, 60s, 80s to see how the scene evolves
for s in [1, 15, 30, 60, 80]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(f"frame_sample_{s}s.jpg", frame)
        print(f"Saved frame_sample_{s}s.jpg")

cap.release()
