from PyQt6 import QtCore
import subprocess
import shlex
import time


class TabMain(QtCore.QObject):
    def __init__(self, ui):
        super().__init__(ui)
        self.ui = ui

        self.scrcpyProcess = None
        self.connected_serial = None

        self.refreshTimer = QtCore.QTimer(self.ui)
        self.refreshTimer.setInterval(2000)
        self.refreshTimer.timeout.connect(self.refresh)

        self.ui.refreshButtonADB.clicked.connect(self.list_adb_devices)
        self.ui.connectButtonADB.clicked.connect(self.connect_to_device)
        self.ui.disconnectButtonADB.clicked.connect(self.disconnect_device)
        self.ui.buttonStartScrcpy.clicked.connect(self.start_scrcpy)
        self.ui.buttonStopScrcpy.clicked.connect(self.stop_scrcpy)
        self.ui.switchToTCPIP.clicked.connect(self.switch_scrcpy_tcp_ip)

    def log(self, text):
        self.ui.textTerminal.append(text)

    def read_process_output(self, process):
        out = process.readAllStandardOutput().data().decode(errors="replace")
        err = process.readAllStandardError().data().decode(errors="replace")
        if out:
            for line in out.splitlines():
                self.log(f"[scrcpy] {line}")
        if err:
            for line in err.splitlines():
                self.log(f"[scrcpy-err] {line}")

    def list_adb_devices(self):
        self.ui.listADBDevices.clear()
        completed = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
        lines = completed.stdout.strip().splitlines()
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 1:
                serial = parts[0]
                self.ui.listADBDevices.addItem(serial)

    def connect_to_device(self):
        item = self.ui.listADBDevices.currentItem()
        if not item:
            self.log("No device selected.")
            return
        self.connected_serial = item.text()
        self.log(f"Connected to {self.connected_serial}")
        self.refreshTimer.start()

    def disconnect_device(self):
        self.refreshTimer.stop()
        self.stop_scrcpy()
        self.connected_serial = None
        self.ui.batteryPercentage.setValue(0)
        self.log("Device disconnected.")

    def refresh(self):
        if not self.connected_serial:
            return
        if self.scrcpyProcess and self.scrcpyProcess.state() == QtCore.QProcess.ProcessState.NotRunning:
            self.log("scrcpy process ended.")
            self.scrcpyProcess = None
        self.refresh_battery()

    def refresh_battery(self):
        result = subprocess.run([
            "adb", "-s", self.connected_serial, "shell", "dumpsys", "battery"
        ], capture_output=True, text=True, timeout=3)
        if result.returncode != 0 or not result.stdout:
            self.log("Device lost during battery check.")
            self.disconnect_device()
            return
        for line in result.stdout.splitlines():
            if "level:" in line:
                level = int(line.split(":", 1)[1].strip())
                self.ui.batteryPercentage.setValue(level)

    def get_extra_options(self):
        args = []
        bitrate = self.ui.lineBitrate.text().strip()
        if bitrate:
            args += ["-b", bitrate]
        fps = self.ui.lineFPS.text().strip()
        if fps:
            args += ["--max-fps", fps]
        disable_control = self.ui.lineDisableControl.text().strip().lower()
        if disable_control in ("true", "1", "yes", "y"):
            args.append("--no-control")
        other = self.ui.lineOther.text().strip()
        if other:
            args += shlex.split(other)
        return args

    def start_scrcpy(self):
        if self.scrcpyProcess:
            self.log("scrcpy is already running.")
            return

        item = self.ui.listADBDevices.currentItem()
        if not item and not self.connected_serial:
            self.log("No device selected.")
            return

        serial = self.connected_serial or item.text()
        arguments = ["-s", serial] + self.get_extra_options()

        self.scrcpyProcess = QtCore.QProcess(self.ui)
        self.scrcpyProcess.setProgram("scrcpy")
        self.scrcpyProcess.setArguments(arguments)

        self.scrcpyProcess.readyReadStandardOutput.connect(
            lambda: self.read_process_output(self.scrcpyProcess)
        )
        self.scrcpyProcess.readyReadStandardError.connect(
            lambda: self.read_process_output(self.scrcpyProcess)
        )
        self.scrcpyProcess.finished.connect(self.on_scrcpy_finished)

        self.scrcpyProcess.start()

        self.log(f"scrcpy started: scrcpy {' '.join(arguments)}")


    def on_scrcpy_finished(self):
        self.log(f"scrcpy finished")
        self.scrcpyProcess = None

    def stop_scrcpy(self):
        if self.scrcpyProcess:
            self.scrcpyProcess.terminate()
            if not self.scrcpyProcess.waitForFinished(1000):
                self.scrcpyProcess.kill()
            self.scrcpyProcess = None
            self.log("scrcpy stopped.")

    def switch_scrcpy_tcp_ip(self):
        item = self.ui.listADBDevices.currentItem()
        if not item and not self.connected_serial:
            self.log("No device selected for TCP/IP switch.")
            return
        serial = self.connected_serial or item.text()
        try:
            self.log(f"Enabling adb tcpip on {serial}...")
            subprocess.run(["adb", "-s", serial, "tcpip", "5555"], check=True, capture_output=True, text=True, timeout=6)
        except Exception as e:
            self.log(f"tcpip enable failed: {e}")
            return
        
        time.sleep(1.0)
        completed = subprocess.run(["adb", "-s", serial, "shell", "ip", "route", "get", "1"], capture_output=True, text=True, timeout=3)
        out = completed.stdout or completed.stderr or ""
        tokens = out.split()
        for i, t in enumerate(tokens):
            if t == "src" and i + 1 < len(tokens):
                ip = tokens[i + 1]
                break
            
        addr = f"{ip}:5555"
        self.log(f"Connecting to {addr}...")
        completed = subprocess.run(["adb", "connect", addr], capture_output=True, text=True, timeout=6)
        if completed.returncode != 0:
            self.log(f"adb connect failed: {completed.stdout or completed.stderr}")
            return
        
        time.sleep(0.6)
        self.list_adb_devices()
        found_serial = None
        for i in range(self.ui.listADBDevices.count()):
            txt = self.ui.listADBDevices.item(i).text()
            if addr in txt or txt.startswith(ip + ":"):
                found_serial = txt
                break
        if not found_serial:
            found_serial = addr
        self.connected_serial = found_serial
        self.log(f"Wireless device ready: {found_serial}")
        self.stop_scrcpy()
        self.start_scrcpy()
        self.list_adb_devices()

