import json
import cv2
import numpy as np
from PyQt6 import QtGui, QtCore
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtCore import QThread, pyqtSignal
from ultralytics import YOLO
import pyvirtualcam
import threading
import time
import subprocess
import re

device_index = 2 # edit this please vedant, right here

# ==============================
# YOLO WORKER THREAD
# ==============================

class YoloWorker(QThread):
    detection_ready = pyqtSignal(object)

    def __init__(self, model, inference_size):
        super().__init__()
        self.model = model
        self.inference_size = inference_size
        self.frame = None
        self.lock = threading.Lock()
        self.running = True

    def update_frame(self, frame):
        with self.lock:
            self.frame = frame.copy()

    def run(self):
        while self.running:
            if self.frame is None:
                self.msleep(1)
                continue

            with self.lock:
                frame = self.frame
                self.frame = None

            h, w = frame.shape[:2]
            small = cv2.resize(frame, self.inference_size)

            scale_x = w / self.inference_size[0]
            scale_y = h / self.inference_size[1]

            results = self.model(small, verbose=False)

            if len(results[0].boxes) > 0:

                boxes = results[0].boxes.xyxy.cpu().numpy()
                box = boxes[0]

                x1, y1, x2, y2 = box[:4]

                cx = (x1 + x2) / 2
                cy = y1 + (y2 - y1) * 0.35

                cx *= scale_x
                cy *= scale_y

                self.detection_ready.emit((int(cx), int(cy)))

            else:
                self.detection_ready.emit(None)
                    
    def stop(self):
        self.running = False
        self.quit()
        self.wait()

# VIRTUAL CAM CLASS

class VirtualCamWorker(QThread):
    def __init__(self, width, height, fps):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps

        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.cam = None

    def update_frame(self, frame):
        with self.lock:
            self.frame = frame.copy()

    def run(self):
        self.cam = pyvirtualcam.Camera(
            width=self.width,
            height=self.height,
            fps=self.fps,
            fmt=pyvirtualcam.PixelFormat.RGB
        )

        frame_time = 1 / self.fps

        while self.running:
            start = time.perf_counter()

            with self.lock:
                frame = self.frame

            if frame is not None:
                if frame.shape[1] != self.width or frame.shape[0] != self.height:
                    frame = cv2.resize(frame, (self.width, self.height))

                self.cam.send(frame)

            elapsed = time.perf_counter() - start
            sleep_time = max(0, frame_time - elapsed)
            time.sleep(sleep_time)

        self.cam.close()

    def stop(self):
        self.running = False
        self.wait()

# ==============================
# MAIN CAMERA CLASS
# ==============================

class TabCammy:
    def __init__(self, ui):
        self.ui = ui

        cap = cv2.VideoCapture(2)
        self.maxFPS = cap.get(cv2.CAP_PROP_FPS) or 30
        self.maxW = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.maxH = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        self.cap = None
        self.fps = self.maxFPS
        self.resolution = [self.maxW, self.maxH]
        self.aspectRatio = None
        self.mirror_xaxis = False
        self.mirror_yaxis = False

        self.ui.lineEditFPS.setText(f"{int(self.maxFPS)}")
        self.ui.lineEditResolution.setText(f"{self.maxW}x{self.maxH}")

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_frame)

        self.ui.btnConnect.clicked.connect(self._start_camera)
        self.ui.btnDisconnect.clicked.connect(self._stop_camera)

        self.ui.lineEditFPS.editingFinished.connect(self._update_fps)
        self.ui.lineEditResolution.editingFinished.connect(self._update_resolution)
        self.ui.comboBoxAspectRatio.currentIndexChanged.connect(self._update_aspect_ratio)

        self.ui.checkBoxMirror_xaxis.stateChanged.connect(self._update_mirror_x)
        self.ui.checkBoxMirror_yaxis.stateChanged.connect(self._update_mirror_y)

        # ===== YOLO =====
        self.model = YOLO("model.pt")  # use .to("cuda") if available
        self.inference_size = (416, 234)

        self.target_cx = None
        self.target_cy = None
        self.current_cx = None
        self.current_cy = None
        self.smoothing_alpha = 0.08
        self.history = []
        self.history_size = 5
        self.miss_count = 0
        self.max_misses = 5

        # ===== Virtual Cam =====
        self.virtual_cam = None
        self.virtual_cam_enabled = True

        # ====== Attributes for class ======

        self.yolo_worker = None
        self.virtual_cam_worker = None

        # ===== Output resolution =====
        self.output_width = 1920
        self.output_height = 1080
        self.preview_width = 960
        self.preview_height = 540


    def _get_max_resolution(self, device_index):
        device_path = f"/dev/video{device_index}"

        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--list-formats-ext"],
                capture_output=True,
                text=True
            )

            output = result.stdout

            resolutions = re.findall(r"Size: Discrete (\d+)x(\d+)", output)

            if not resolutions:
                return None

            # Convert to integers
            resolutions = [(int(w), int(h)) for w, h in resolutions]

            # Pick highest pixel count
            max_res = max(resolutions, key=lambda x: x[0] * x[1])

            return max_res

        except Exception as e:
            print("Resolution detection failed:", e)
            return None

    # ==============================
    # CAMERA CONTROL
    # ==============================

    def _start_camera(self):

        self.cap = cv2.VideoCapture(device_index)

        # Optional: unlock higher resolutions (important for many webcams)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        # Acquire highest resolution
        max_res = self._get_max_resolution(device_index)

        if max_res : 
            print("Maximum resolution is ", max_res)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, max_res[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, max_res[1])
        else : 
            print("Couldnt detect max resolution, defaulting...")

        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        # Get ACTUAL resolution camera accepted
        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print("Camera running at:", actual_width, "x", actual_height)

        # Match output to input
        self.output_width = actual_width
        self.output_height = actual_height

        # Preview smaller
        self.preview_width = actual_width // 2
        self.preview_height = actual_height // 2

        # Start YOLO
        self.yolo_worker = YoloWorker(self.model, self.inference_size)
        self.yolo_worker.detection_ready.connect(self._update_center)
        self.yolo_worker.start()

        # Start virtual cam with REAL resolution
        if self.virtual_cam_enabled:
            self.virtual_cam_worker = VirtualCamWorker(
                self.output_width,
                self.output_height,
                int(self.fps)
            )
            self.virtual_cam_worker.start()

        self.timer.start(int(1000 / self.fps))

        self.ui.btnConnect.setEnabled(False)
        self.ui.btnDisconnect.setEnabled(True)

    def _stop_camera(self):
        self.timer.stop()

        if self.cap:
            self.cap.release()
            self.cap = None

        if hasattr(self, "virtual_cam_worker") and self.virtual_cam_worker is not None: # double trouble again, this double check is for safety ion wanna nuke my stuff dawg
            self.virtual_cam_worker.stop()
            self.virtual_cam_worker = None

        if hasattr(self, "yolo_worker") and self.yolo_worker is not None: # double trouble - checks if yolo worker attribute even exists otherwise attributeerror would nuke the program :P
            self.yolo_worker.stop()
            self.yolo_worker = None
        
        #resets coordinates, just to prevent some jarring snapping in the beginning
        self.target_cx = None
        self.target_cy = None
        self.current_cx = None
        self.current_cy = None
        self.history.clear()

        self.ui.btnConnect.setEnabled(True)
        self.ui.btnDisconnect.setEnabled(False)

    # ==============================
    # CENTER UPDATE FROM THREAD
    # ==============================

    def _update_center(self, center):

        # --------- HANDLE MISSED DETECTIONS ----------
        if center is None:
            self.miss_count += 1

            if self.miss_count > self.max_misses:
                self.target_cx = None
                self.target_cy = None
                self.current_cx = None
                self.current_cy = None
                self.history.clear()

            return

        # --------- VALID DETECTION ----------
        self.miss_count = 0

        cx, cy = center

        # First detection
        if self.target_cx is None or self.target_cy is None:
            self.target_cx = cx
            self.target_cy = cy
            self.history = [(cx, cy)]
            return

        # Jump rejection
        dx = cx - self.target_cx
        dy = cy - self.target_cy

        frame_w = self.resolution[0]
        frame_h = self.resolution[1]
        diag = (frame_w**2 + frame_h**2) ** 0.5
        max_jump = diag * 0.12
        distance = (dx**2 + dy**2) ** 0.5

        if distance > max_jump:
        # snap to new position
            self.target_cx = cx
            self.target_cy = cy
            self.history = [(cx, cy)]
            return

        # History smoothing
        self.history.append((cx, cy))
        if len(self.history) > self.history_size:
            self.history.pop(0)

        self.target_cx = round(self.target_cx, 2)
        self.target_cy = round(self.target_cy, 2)
    # ==============================
    # FRAME LOOP (NOW NON-BLOCKING)
    # ==============================

    def _update_frame(self):
        if not self.cap:
            return

        ret, frame_bgr = self.cap.read()
        if not ret:
            return

        frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        # Send frame to YOLO thread
        self.yolo_worker.update_frame(frame)

        # Smooth tracking and crop

        # If we have no target yet, do nothing
        if self.target_cx is None or self.target_cy is None:
            pass

        # If target exists but current not initialized → initialize
        elif self.current_cx is None or self.current_cy is None:
            self.current_cx = float(self.target_cx)
            self.current_cy = float(self.target_cy)

        # If both exist → interpolate
        else:
            dx = self.target_cx - self.current_cx
            dy = self.target_cy - self.current_cy

            distance = (dx**2 + dy**2) ** 0.5

            # Small activation threshold
            activation_radius = 5   # <- try 6 to 10 range

            if distance > activation_radius:
                alpha = 0.06
                self.current_cx = self.current_cx * (1 - alpha) + self.target_cx * alpha
                self.current_cy = self.current_cy * (1 - alpha) + self.target_cy * alpha

        # Crop only if current center exists
        if self.current_cx is not None and self.current_cy is not None:
            frame = self._center_crop(
            frame,
            self.current_cx,
            self.current_cy
        )

        cropped = frame

        # Downscale cropped 4K region to 1080p for output
        output_frame = cv2.resize(
            cropped,
            (self.output_width, self.output_height),
            interpolation=cv2.INTER_AREA
        )

        # Aspect ratio
        if self.aspectRatio and self.aspectRatio != "Auto":
            frame = self._change_image_ratio(frame)

        # Mirror
        flip_code = None
        if self.mirror_xaxis and self.mirror_yaxis:
            flip_code = -1
        elif self.mirror_xaxis:
            flip_code = 0
        elif self.mirror_yaxis:
            flip_code = 1

        if flip_code is not None:
            frame = cv2.flip(frame, flip_code)

        frame = np.ascontiguousarray(frame)

        # Virtual cam
        if hasattr(self, "virtual_cam_worker"):
            self.virtual_cam_worker.update_frame(output_frame)

        # Preview and resize because you dont need to see the full output just for a preview, this is for optimization
        preview_frame = cv2.resize(
            output_frame,
            (self.preview_width, self.preview_height),
             interpolation=cv2.INTER_AREA
            )

        h, w, ch = preview_frame.shape
        qimg = QtGui.QImage(
            preview_frame.data,
            w,
            h,
            w * ch,
            QtGui.QImage.Format.Format_RGB888
        )

        self.ui.labelVideoPreview.setPixmap(
            QtGui.QPixmap.fromImage(qimg)
        )

    # ==============================
    # CROPPING
    # ==============================

    def _center_crop(self, frame, cx, cy):
        h, w = frame.shape[:2]
        crop_scale = 0.5
        crop_w = int(w * crop_scale)
        crop_h = int(h * crop_scale)

        x1 = cx - crop_w / 2
        y1 = cy - crop_h / 2

        x1 = max(0, min(x1, w - crop_w))
        y1 = max(0, min(y1, h - crop_h))

        x1 = int(round(x1))
        y1 = int(round(y1))

        return frame[y1:y1 + crop_h, x1:x1 + crop_w]

    def _change_image_ratio(self, frame):
        h, w = frame.shape[:2]
        parts = self.aspectRatio.split(":")
        target_ratio = float(parts[0]) / float(parts[1])
        current_ratio = w / h

        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            offset = (w - new_w) // 2
            return frame[:, offset:offset + new_w]
        else:
            new_h = int(w / target_ratio)
            offset = (h - new_h) // 2
            return frame[offset:offset + new_h, :]

    # ==============================
    # SETTINGS
    # ==============================

    def _update_fps(self):
        try:
            self.fps = int(self.ui.lineEditFPS.text())
        except ValueError:
            return

    def _update_resolution(self):
        try:
            self.resolution = [int(x) for x in self.ui.lineEditResolution.text().split("x")]
        except ValueError:
            return

    def _update_aspect_ratio(self):
        self.aspectRatio = self.ui.comboBoxAspectRatio.currentText()

    def _update_mirror_x(self):
        self.mirror_xaxis = self.ui.checkBoxMirror_xaxis.isChecked()

    def _update_mirror_y(self):
        self.mirror_yaxis = self.ui.checkBoxMirror_yaxis.isChecked()# Small preview frame (never send 4K to Qt)