from PyQt6 import QtWidgets, QtGui, QtCore, uic
from PyQt6.QtWidgets import QFileDialog
import json

import sys
import cv2

class Cammy(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('cammy.ui', self)

        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FPS, 9999999)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 9999999)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 9999999)
        
        self.maxFPS = self.cap.get(cv2.CAP_PROP_FPS)
        self.maxW = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.maxH = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.cap.release        
        self.cap = None

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)
        
        self.btnConnect.clicked.connect(self.start_camera)
        self.btnDisconnect.clicked.connect(self.stop_camera)

        self.fps = self.maxFPS
        self.lineEditFPS.setText(f"{int(self.maxFPS)}")
        self.lineEditFPS.editingFinished.connect(self.update_fps)
        
        self.aspectRatio = None
        self.comboBoxAspectRatio.currentIndexChanged.connect(self.update_aspect_ratio)

        self.resolution = [self.maxW, self.maxH]
        self.lineEditResolution.setText(f"{self.resolution[0]}x{self.resolution[1]}")
        self.lineEditResolution.editingFinished.connect(self.update_resolution)

        self.mirror_xaxis = False
        self.mirror_yaxis = False
        self.checkBoxMirror_xaxis.stateChanged.connect(self.checkBoxMirror_xaxis_update)
        self.checkBoxMirror_yaxis.stateChanged.connect(self.checkBoxMirror_yaxis_update)

        self.cap_res_x = None
        self.cap_res_y = None

        self.actionSaveSettings.triggered.connect(self.save_settings)
        self.actionLoadSettings.triggered.connect(self.load_settings)
        self.actionExit.triggered.connect(self.exit)


    def save_settings(self):
        self.data = {
            "device_ip" : self.lineEditIP.text(),
            "port" : self.lineEditPort.text(),
            "resolution" : self.lineEditResolution.text(),
            "fps" : self.lineEditFPS.text(),
            "bitrate" : self.spinBoxBitrate.value(),
            "aspect_ratio" : self.comboBoxAspectRatio.currentIndex(),
            "enable_audio" : self.checkBoxEnableAudio.isChecked(),
            "sample_rate" : self.comboBoxSampleRate.currentIndex(),
            "mirror_video_yaxis" : self.checkBoxMirror_yaxis.isChecked(),
            "mirror_video_xaxis" : self.checkBoxMirror_xaxis.isChecked(),
            "keep_device_update" : self.checkBoxKeepAwake.isChecked()
        }

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Settings",
            "saved_settings.json",
            "JSON Files (*.json)"
        )

        if not path:
            return

        with open(path, "w") as f:
            json.dump(self.data, f, indent=4)

    def load_settings(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Settings",
            "",
            "JSON Files (*.json)"
        )

        if not path:
            return

        with open(path, "r") as f:
            data = json.load(f)

        self.lineEditIP.setText(data.get("device_ip", ""))
        self.lineEditPort.setText(data.get("port", ""))
        self.lineEditResolution.setText(data.get("resolution", ""))
        self.lineEditFPS.setText(data.get("fps", ""))
        self.spinBoxBitrate.setValue(int(data.get("bitrate", 0)))
        self.comboBoxAspectRatio.setCurrentIndex(int(data.get("aspect_ratio", 0)))
        self.checkBoxEnableAudio.setChecked(bool(data.get("enable_audio", False)))
        self.comboBoxSampleRate.setCurrentIndex(int(data.get("sample_rate", 0)))
        self.checkBoxMirror_yaxis.setChecked(bool(data.get("mirror_video_yaxis", False)))
        self.checkBoxMirror_xaxis.setChecked(bool(data.get("mirror_video_xaxis", False)))
        self.checkBoxKeepAwake.setChecked(bool(data.get("keep_device_update", False)))
        self.textEditStatus.append("Settings loaded")

    def exit(self):
        sys.exit()


    def checkBoxMirror_xaxis_update(self):
        self.mirror_xaxis = self.checkBoxMirror_xaxis.isChecked()

    def checkBoxMirror_yaxis_update(self):
        self.mirror_yaxis = self.checkBoxMirror_yaxis.isChecked()

    def update_fps(self):
        self.fps = int(self.lineEditFPS.text())
        if self.cap:
            self.stop_camera()
            self.start_camera()

    def update_resolution(self):
        self.resolution = [int(x) for x in self.lineEditResolution.text().split('x')]
        if self.cap:
            self.stop_camera()
            self.start_camera()

    def start_camera(self):
        self.cap = cv2.VideoCapture(0)
        self.timer.start(int(1000/self.fps))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        print(int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
        print(int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

        self.textEditStatus.append("Camera started")
        self.btnConnect.setEnabled(False)
        self.btnDisconnect.setEnabled(True)
        
    def stop_camera(self):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        self.labelVideoPreview.clear()
        self.textEditStatus.append("Camera stopped")
        self.btnConnect.setEnabled(True)
        self.btnDisconnect.setEnabled(False)
        
    def update_frame(self):
        retval, image_cv2_BGR = self.cap.read()

        if retval:
            frame_RGB = cv2.cvtColor(image_cv2_BGR, cv2.COLOR_BGR2RGB)
            
            if self.aspectRatio and self.aspectRatio != 'Auto':
                frame_RGB = self.change_image_ratio(frame_RGB).copy()
            
            h, w, ch = frame_RGB.shape

            self.cap_res_x = w
            self.cap_res_y = h

            flip_code = None
            if self.mirror_xaxis and self.mirror_yaxis:
                flip_code = -1
            elif self.mirror_xaxis:
                flip_code = 0
            elif self.mirror_yaxis:
                flip_code = 1

            if flip_code is not None:
                frame_RGB = cv2.flip(frame_RGB, flip_code)


            frame_pyqt = QtGui.QImage(frame_RGB.data, w, h, w * ch, QtGui.QImage.Format.Format_RGB888)

            self.labelVideoPreview.setPixmap(QtGui.QPixmap.fromImage(frame_pyqt).scaled(
                self.labelVideoPreview.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio))

    def update_aspect_ratio(self):
        self.aspectRatio = self.comboBoxAspectRatio.currentText()

    def change_image_ratio(self, frame):
        h, w, ch = frame.shape

        parts = self.aspectRatio.split(':')
        target_ratio = float(parts[0])/float(parts[1])

        current_ratio = w/h

        if current_ratio > target_ratio:
            width = int(h * target_ratio)
            offset = (w - width)//2
            return frame[:, offset:offset+width]
        else:
            height = int(w / target_ratio)
            offset = (h - height)//2
            return frame[offset:offset+height, :]


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = Cammy()
    window.show()
    sys.exit(app.exec())