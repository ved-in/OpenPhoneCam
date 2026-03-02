import cv2
import numpy as np
from PyQt6 import QtGui, QtCore
from PyQt6.QtCore import QThread, pyqtSignal
from ultralytics import YOLO
import pyvirtualcam
import threading
import time
import subprocess
import os

device_index = 0

CONFIG = {
    "inference_size": (416, 234),
    "face_y_bias": 0.35,
    "history_size": 5,
    "max_misses": 5,
    "max_jump_fraction": 0.12,
    "pan_activation_radius": 5,
    "pan_alpha": 0.06,
    "target_face_fraction": 0.2,
    "zoom_alpha": 0.04,
    "crop_min_fraction": 0.1,
    "crop_max_fraction": 0.95,
    "loopback_video_nr": 10,
    "loopback_card_label": "OpenPhoneCam",
}


def ensure_v4l2loopback():
    device_path = f"/dev/video{CONFIG['loopback_video_nr']}"

    if os.path.exists(device_path):
        print(f"Using existing loopback device: {device_path}")
        return True

    print("Creating v4l2loopback device...")
    result = subprocess.run(
        [
            "sudo", "modprobe", "v4l2loopback",
            "devices=1",
            f"video_nr={CONFIG['loopback_video_nr']}",
            f"card_label={CONFIG['loopback_card_label']}",
            "exclusive_caps=1",
        ]
    )

    if result.returncode != 0:
        print("modprobe failed.")
        return False

    time.sleep(0.5)
    return os.path.exists(device_path)


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
                cy = y1 + (y2 - y1) * CONFIG["face_y_bias"]

                cx *= scale_x
                cy *= scale_y
                face_w = (x2 - x1) * scale_x
                
                self.detection_ready.emit((int(cx), int(cy), face_w))

            else:
                self.detection_ready.emit(None)
                    
    def stop(self):
        self.running = False
        self.quit()
        self.wait()


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
                fh, fw = frame.shape[:2]
                if fw != self.width or fh != self.height:
                    frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)
                self.cam.send(frame)

            elapsed = time.perf_counter() - start
            sleep_time = max(0, frame_time - elapsed)
            time.sleep(sleep_time)

        self.cam.close()

    def stop(self):
        self.running = False
        self.wait()


class TabCammy:
    def __init__(self, ui):
        self.frame_count = 0
        self.fps_timer_start = time.perf_counter()
        self.ui = ui

        cap = cv2.VideoCapture(device_index)
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
        self.timer.timeout.connect(self.update_frame)

        self.ui.btnConnect.clicked.connect(self.start_camera)
        self.ui.btnDisconnect.clicked.connect(self.stop_camera)

        self.ui.lineEditFPS.editingFinished.connect(self.update_settings)
        self.ui.lineEditResolution.editingFinished.connect(self.update_settings)
        self.ui.comboBoxAspectRatio.currentIndexChanged.connect(self.update_settings)

        self.ui.checkBoxMirror_xaxis.stateChanged.connect(self.update_mirror)
        self.ui.checkBoxMirror_yaxis.stateChanged.connect(self.update_mirror)

        self.model = YOLO("model.pt")
        self.inference_size = CONFIG["inference_size"]

        self.target_cx = None
        self.target_cy = None
        self.current_cx = None
        self.current_cy = None
        self.history = []
        self.history_size = CONFIG["history_size"]
        self.miss_count = 0
        self.max_misses = CONFIG["max_misses"]

        self.target_crop_w = None
        self.target_crop_h = None
        self.current_crop_w = None
        self.current_crop_h = None

        self.virtual_cam = None
        self.virtual_cam_enabled = True

        self.yolo_worker = None
        self.virtual_cam_worker = None

        self.last_out_w = None
        self.last_out_h = None

        self.output_width = 1920
        self.output_height = 1080
        self.preview_width = 960
        self.preview_height = 540


    def start_camera(self):

        self.cap = cv2.VideoCapture(device_index)

        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 9999)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 9999)

        max_res = (
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        )

        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print("Camera running at:", actual_width, "x", actual_height)

        self.output_width = actual_width
        self.output_height = actual_height
        self.preview_width = actual_width // 2
        self.preview_height = actual_height // 2

        self.resolution = [actual_width, actual_height]

        self.yolo_worker = YoloWorker(self.model, self.inference_size)
        self.yolo_worker.detection_ready.connect(self.update_center)
        self.yolo_worker.start()

        if self.virtual_cam_enabled:
            if not ensure_v4l2loopback():
                print("Virtual camera disabled: no v4l2loopback device available.")
                self.virtual_cam_enabled = False
            else:
                out_w, out_h = self.compute_output_dims()
                self.virtual_cam_worker = VirtualCamWorker(out_w, out_h, int(self.fps))
                self.virtual_cam_worker.start()
                self.last_out_w = out_w
                self.last_out_h = out_h

        self.timer.start(int(1000 / self.fps))

        self.ui.btnConnect.setEnabled(False)
        self.ui.btnDisconnect.setEnabled(True)

    def stop_camera(self):
        self.timer.stop()

        if self.cap:
            self.cap.release()
            self.cap = None

        if self.virtual_cam_worker is not None:
            self.virtual_cam_worker.stop()
            self.virtual_cam_worker = None

        if self.yolo_worker is not None:
            self.yolo_worker.stop()
            self.yolo_worker = None

        self.target_cx = None
        self.target_cy = None
        self.current_cx = None
        self.current_cy = None
        self.history.clear()
        self.target_crop_w = None
        self.target_crop_h = None
        self.current_crop_w = None
        self.current_crop_h = None
        self.last_out_w = None
        self.last_out_h = None

        self.ui.btnConnect.setEnabled(True)
        self.ui.btnDisconnect.setEnabled(False)

    def update_center(self, center):
        if center is None:
            self.miss_count += 1

            if self.miss_count > self.max_misses:
                self.target_cx = None
                self.target_cy = None
                self.current_cx = None
                self.current_cy = None
                self.history.clear()
                self.target_crop_w = None
                self.target_crop_h = None

            return

        self.miss_count = 0
        cx, cy, face_w = center
        raw_crop_w = face_w / CONFIG["target_face_fraction"]

        if self.aspectRatio and self.aspectRatio != "Auto":
            target_ratio = self.get_target_ratio()
        else:
            frame_h = self.resolution[1]
            frame_w = self.resolution[0]
            target_ratio = frame_w / frame_h if frame_h > 0 else 16 / 9

        raw_crop_h = raw_crop_w / target_ratio

        frame_w = self.resolution[0]
        frame_h = self.resolution[1]
        max_crop_w = frame_w * CONFIG["crop_max_fraction"]
        min_crop_w = frame_w * CONFIG["crop_min_fraction"]
        raw_crop_w = max(min_crop_w, min(max_crop_w, raw_crop_w))
        raw_crop_h = raw_crop_w / target_ratio

        if raw_crop_h > frame_h:
            raw_crop_h = frame_h
            raw_crop_w = raw_crop_h * target_ratio

        self.target_crop_w = raw_crop_w
        self.target_crop_h = raw_crop_h

        if self.target_cx is None or self.target_cy is None:
            self.target_cx = cx
            self.target_cy = cy
            self.history = [(cx, cy)]
            return

        dx = cx - self.target_cx
        dy = cy - self.target_cy

        frame_w = self.resolution[0]
        frame_h = self.resolution[1]
        diag = (frame_w**2 + frame_h**2)
        max_jump = diag * CONFIG["max_jump_fraction"]
        distance = (dx**2 + dy**2)

        if distance > max_jump:
            self.target_cx = cx
            self.target_cy = cy
            self.history = [(cx, cy)]
            return

        self.history.append((cx, cy))
        if len(self.history) > self.history_size:
            self.history.pop(0)

        self.target_cx = round(sum(p[0] for p in self.history) / len(self.history), 2)
        self.target_cy = round(sum(p[1] for p in self.history) / len(self.history), 2)

    def update_frame(self):
        if not self.cap:
            return

        ret, frame_bgr = self.cap.read()
        if not ret:
            return

        frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        if self.yolo_worker is not None:
            self.yolo_worker.update_frame(frame)

        if self.target_cx is None or self.target_cy is None:
            pass

        elif self.current_cx is None or self.current_cy is None:
            self.current_cx = float(self.target_cx)
            self.current_cy = float(self.target_cy)
        else:
            dx = self.target_cx - self.current_cx
            dy = self.target_cy - self.current_cy
            distance = (dx**2 + dy**2) ** 0.5

            if distance > CONFIG["pan_activation_radius"]:
                self.current_cx = self.current_cx * (1 - CONFIG["pan_alpha"]) + self.target_cx * CONFIG["pan_alpha"]
                self.current_cy = self.current_cy * (1 - CONFIG["pan_alpha"]) + self.target_cy * CONFIG["pan_alpha"]

        fh, fw = frame.shape[:2]

        if self.target_crop_w is not None:
            if self.current_crop_w is None:
                self.current_crop_w = self.target_crop_w
                self.current_crop_h = self.target_crop_h
            else:
                self.current_crop_w += (self.target_crop_w - self.current_crop_w) * CONFIG["zoom_alpha"]
                self.current_crop_h += (self.target_crop_h - self.current_crop_h) * CONFIG["zoom_alpha"]

        if self.current_cx is not None and self.current_cy is not None and self.current_crop_w is not None:
            frame = self.process_frame(frame, self.current_cx, self.current_cy, int(self.current_crop_w), int(self.current_crop_h))
        else:
            if self.aspectRatio and self.aspectRatio != "Auto":
                target_ratio = self.get_target_ratio()
                if (fw / fh) > target_ratio:
                    crop_w = int(fh * target_ratio)
                    crop_h = fh
                else:
                    crop_w = fw
                    crop_h = int(fw / target_ratio)
                frame = self.process_frame(frame, fw / 2, fh / 2, crop_w, crop_h)

        out_w = self.last_out_w or self.output_width
        out_h = self.last_out_h or self.output_height

        output_frame = cv2.resize(
            frame,
            (out_w, out_h),
            interpolation=cv2.INTER_AREA
        )

        flip_code = None
        if self.mirror_xaxis and self.mirror_yaxis:
            flip_code = -1
        elif self.mirror_xaxis:
            flip_code = 0
        elif self.mirror_yaxis:
            flip_code = 1

        if flip_code is not None:
            output_frame = cv2.flip(output_frame, flip_code)

        output_frame = np.ascontiguousarray(output_frame)

        if self.virtual_cam_worker is not None:
            self.virtual_cam_worker.update_frame(output_frame)

        preview_frame = cv2.resize(
            output_frame,
            (out_w // 2, out_h // 2),
            interpolation=cv2.INTER_AREA
        )

        h, w, ch = preview_frame.shape
        qimg = QtGui.QImage(
            preview_frame.data,
            w, h,
            w * ch,
            QtGui.QImage.Format.Format_RGB888
        )

        self.ui.labelVideoPreview.setPixmap(QtGui.QPixmap.fromImage(qimg))

    def process_frame(self, frame, cx, cy, crop_w, crop_h):
        h, w = frame.shape[:2]
        crop_w = max(1, min(crop_w, w))
        crop_h = max(1, min(crop_h, h))

        x1 = int(round(max(0, min(cx - crop_w / 2, w - crop_w))))
        y1 = int(round(max(0, min(cy - crop_h / 2, h - crop_h))))

        return frame[y1:y1 + crop_h, x1:x1 + crop_w]

    def compute_output_dims(self):
        if not self.aspectRatio or self.aspectRatio == "Auto":
            return self.output_width, self.output_height
        target_ratio = self.get_target_ratio()
        if (self.output_width / self.output_height) > target_ratio:
            out_w = int(self.output_height * target_ratio)
            out_h = self.output_height
        else:
            out_w = self.output_width
            out_h = int(self.output_width / target_ratio)
        out_w -= out_w % 2
        out_h -= out_h % 2
        return out_w, out_h

    def restart_virtual_cam(self, width, height):
        if not self.virtual_cam_enabled:
            return

        if self.virtual_cam_worker is not None:
            self.virtual_cam_worker.stop()
            self.virtual_cam_worker = None

        subprocess.run(["sudo", "rmmod", "v4l2loopback"],
                       capture_output=True)

        if not ensure_v4l2loopback():
            print("Virtual camera restart failed.")
            self.virtual_cam_enabled = False
            return

        self.virtual_cam_worker = VirtualCamWorker(width, height, int(self.fps))
        self.virtual_cam_worker.start()
        self.last_out_w = width
        self.last_out_h = height
        print(f"Virtual cam restarted at {width}x{height}")

    def update_settings(self):
        try:
            self.fps = int(self.ui.lineEditFPS.text())
        except ValueError:
            pass
        try:
            self.resolution = [int(x) for x in self.ui.lineEditResolution.text().split("x")]
        except ValueError:
            pass
        self.aspectRatio = self.ui.comboBoxAspectRatio.currentText()

        if self.cap is not None:
            out_w, out_h = self.compute_output_dims()
            if out_w != self.last_out_w or out_h != self.last_out_h:
                self.restart_virtual_cam(out_w, out_h)

    def update_mirror(self):
        self.mirror_xaxis = self.ui.checkBoxMirror_xaxis.isChecked()
        self.mirror_yaxis = self.ui.checkBoxMirror_yaxis.isChecked()

    def get_target_ratio(self):
        parts = self.aspectRatio.split(":")
        return float(parts[0]) / float(parts[1])