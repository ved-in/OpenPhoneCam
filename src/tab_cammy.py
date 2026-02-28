import json
import cv2
import numpy as np
from PyQt6 import QtGui, QtCore
from PyQt6.QtWidgets import QFileDialog
from ultralytics import YOLO
import time
import pyvirtualcam

# Comments specially for my bbg RudyDaBot ;)
# also read the guide for virtual cam.txt ;)

class TabCammy:
    def __init__(self, ui):
        self.ui = ui

        cap = cv2.VideoCapture(1)

        self.maxFPS = cap.get(cv2.CAP_PROP_FPS)
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

        self.model = YOLO("model.pt") # initialize model. u should understand this i believe so
        self.detection_interval = 1 # My laptop lags when each and every frame updates. Every nth frame will be processed by the CNN model update where n will be the value of this
        self.frame_count = 0        # counts frames.
        self.last_cx = None         # saves previous center position - x
        self.last_cy = None         # saves previous center position - y
        
        self.virtual_cam = None     # Virtual cam obj
        self.virtual_cam_enabled = True # Variable to enable virtual cam or disable it.

    def _start_camera(self):
        self.cap = cv2.VideoCapture(1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.timer.start(int(1000 / self.fps))

        # Pretty self explanatory. Also there is a bug that the virtual cam is resized to 4:3 ratio. I can't seem to find the problem so do check it out ;) 
        # Rudy here - idk man its happily doing doing 4k but we'll see
        if self.virtual_cam_enabled:
            self.virtual_cam = pyvirtualcam.Camera(
                width=self.resolution[0], 
                height=self.resolution[1], 
                fps=int(self.fps),
                fmt=pyvirtualcam.PixelFormat.RGB
            )
            self.ui.textEditStatus.append("VirtualCamera started") 

        self.ui.textEditStatus.append("Camera started")
        self.ui.btnConnect.setEnabled(False)
        self.ui.btnDisconnect.setEnabled(True)

    def _stop_camera(self):
        self.timer.stop()
        if self.cap:
            self.cap.release()
            self.cap = None
        
        if self.virtual_cam is not None:
            self.virtual_cam.close()
            self.virtual_cam = None
        
        self.ui.labelVideoPreview.clear()
        self.ui.textEditStatus.append("Camera stopped")
        self.ui.btnConnect.setEnabled(True)
        self.ui.btnDisconnect.setEnabled(False)


    def _update_frame(self):
        start = time.perf_counter()
        if not self.cap:
            return

        retval, frame_bgr = self.cap.read()
        if not retval:
            return

        frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        
        self.frame_count += 1
        if self.frame_count % self.detection_interval == 0:

            results = self.model(frame, verbose=False) # Returns Results objects in a list. The different elements of this results list point to different detected objects
            if len(results[0].boxes) > 0: # results[n].boxes is a boxes object. Contains methods like xyxy, xywh, etc.
                # xyxy would return xy coordinates of both left upper corner and right lower corner gives a tensor [x1, y1, x2, y2] (i dont know what tensors are so dont ask me) 1 is the upper left one, 2 is the bottom right one
                box = results[0].boxes[0].xyxy[0].cpu().numpy() # our model processing happening in GPU by default but numpy operates in CPU. so .cpu() will move it to cpu memory and .numpy() will convert it to numpy array
                x1, y1, x2, y2 = map(int, box)
                self.last_cx = (x1 + x2) // 2 # mid point
                self.last_cy = (y1 + y2) // 2 # mid point
        
        if self.last_cx is not None and self.last_cy is not None:
            frame = self._center_crop(frame, self.last_cx, self.last_cy)

        if self.aspectRatio and self.aspectRatio != "Auto":
            frame = self._change_image_ratio(frame).copy()

        flip_code = None
        if self.mirror_xaxis and self.mirror_yaxis:
            flip_code = -1
        elif self.mirror_xaxis:
            flip_code = 0
        elif self.mirror_yaxis:
            flip_code = 1
        if flip_code is not None:
            frame = cv2.flip(frame, flip_code)

        frame = np.ascontiguousarray(frame) # I dont really understand it but it will store the frame as a contiguous block of memory but we need contiguous array to be used as a frame.otherwise boom. error.
        
        if self.virtual_cam is not None:
            if frame.shape[1] != self.resolution[0] or frame.shape[0] != self.resolution[1]:
                frame_resized = cv2.resize(frame, (self.resolution[0], self.resolution[1]))
            else:
                frame_resized = frame
            self.virtual_cam.send(frame_resized)
        
        h, w, ch = frame.shape
        qimg = QtGui.QImage(frame.data, w, h, w * ch, QtGui.QImage.Format.Format_RGB888).copy() # I honestly don't understand what the bad-word is going on here. I copied this off stackoverflow
        self.ui.labelVideoPreview.setPixmap(
            QtGui.QPixmap.fromImage(qimg).scaled(
                self.ui.labelVideoPreview.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio
            )
        )
        print(time.perf_counter() - start)

    def _center_crop(self, frame, cx, cy):
        # suppose values of cx cy and everythin else. U wil understand.
        h, w, _ = frame.shape

        crop_w = int(w/2)
        crop_h = int(h/2)

        x1 = max(0, cx - crop_w//2)
        y1 = max(0, cy - crop_h//2)

        x2 = min(w, x1 + crop_w)
        y2 = min(h, y1 + crop_h)

        return frame[y1:y2, x1:x2]


    def _change_image_ratio(self, frame):
        h, w, _ = frame.shape
        parts = self.aspectRatio.split(":")
        target_ratio = float(parts[0]) / float(parts[1])
        current_ratio = w / h

        if current_ratio > target_ratio:
            new_w  = int(h * target_ratio)
            offset = (w - new_w) // 2
            return frame[:, offset:offset + new_w]
        else:
            new_h  = int(w / target_ratio)
            offset = (h - new_h) // 2
            return frame[offset:offset + new_h, :]


    def _update_fps(self):
        try:
            self.fps = int(self.ui.lineEditFPS.text())
        except ValueError:
            return
        if self.cap:
            self._stop_camera()
            self._start_camera()

    def _update_resolution(self):
        try:
            self.resolution = [int(x) for x in self.ui.lineEditResolution.text().split("x")]
        except ValueError:
            return
        if self.cap:
            self._stop_camera()
            self._start_camera()

    def _update_aspect_ratio(self):
        self.aspectRatio = self.ui.comboBoxAspectRatio.currentText()

    def _update_mirror_x(self):
        self.mirror_xaxis = self.ui.checkBoxMirror_xaxis.isChecked()

    def _update_mirror_y(self):
        self.mirror_yaxis = self.ui.checkBoxMirror_yaxis.isChecked()


    def save_settings(self):
        data = {
            "device_ip": self.ui.lineEditIP.text(),
            "port": self.ui.lineEditPort.text(),
            "resolution": self.ui.lineEditResolution.text(),
            "fps": self.ui.lineEditFPS.text(),
            "bitrate": self.ui.spinBoxBitrate.value(),
            "aspect_ratio": self.ui.comboBoxAspectRatio.currentIndex(),
            "enable_audio": self.ui.checkBoxEnableAudio.isChecked(),
            "sample_rate": self.ui.comboBoxSampleRate.currentIndex(),
            "mirror_video_yaxis": self.ui.checkBoxMirror_yaxis.isChecked(),
            "mirror_video_xaxis": self.ui.checkBoxMirror_xaxis.isChecked(),
            "keep_device_awake": self.ui.checkBoxKeepAwake.isChecked(),
        }

        path, _ = QFileDialog.getSaveFileName(
            self.ui, "Save Settings", "saved_settings.json", "JSON Files (*.json)"
        )
        if not path:
            return

        with open(path, "w") as f:
            json.dump(data, f, indent=4)

        self.ui.textEditStatus.append("Settings saved")

    def load_settings(self):
        path, _ = QFileDialog.getOpenFileName(
            self.ui, "Load Settings", "", "JSON Files (*.json)"
        )
        if not path:
            return

        with open(path, "r") as f:
            data = json.load(f)

        self.ui.lineEditIP.setText(data.get("device_ip", ""))
        self.ui.lineEditPort.setText(data.get("port", ""))
        self.ui.lineEditResolution.setText(data.get("resolution", ""))
        self.ui.lineEditFPS.setText(data.get("fps", ""))
        self.ui.spinBoxBitrate.setValue(int(data.get("bitrate", 0)))
        self.ui.comboBoxAspectRatio.setCurrentIndex(int(data.get("aspect_ratio", 0)))
        self.ui.checkBoxEnableAudio.setChecked(bool(data.get("enable_audio", False)))
        self.ui.comboBoxSampleRate.setCurrentIndex(int(data.get("sample_rate", 0)))
        self.ui.checkBoxMirror_yaxis.setChecked(bool(data.get("mirror_video_yaxis", False)))
        self.ui.checkBoxMirror_xaxis.setChecked(bool(data.get("mirror_video_xaxis", False)))
        self.ui.checkBoxKeepAwake.setChecked(bool(data.get("keep_device_awake", False)))

        self.ui.textEditStatus.append("Settings loaded")

