import sys
import time
import random
import threading
import subprocess

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6 import uic

battery_value = 0
battery_lock = threading.Lock()

tempSerialNumber = "RZCY50F8R8T"


class BatteryUpdater(threading.Thread):
    def __init__(self, stop_event):
        super().__init__(daemon=True)   # <-- no positional args
        self.stop_event = stop_event

    def run(self):
        global battery_value
        while not self.stop_event.is_set():
            with battery_lock:
                try:
                    result = subprocess.run(
                        ["adb", "-s", self.serialNumber.text(), "shell", "dumpsys", "battery"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    battery_info = result.stdout
                    for line in battery_info.splitlines():
                        if "level:" in line:
                            battery_value = int(line.split(":")[1].strip())
                            break
                except Exception as e:
                    print(f"Error reading battery level: {e}")
            time.sleep(1)



class BatteryReader(QThread):
    value_changed = pyqtSignal(int)

    def __init__(self, stop_event):
        super().__init__()          # <-- no args
        self.stop_event = stop_event

    def run(self):
        global battery_value
        while not self.stop_event.is_set():
            with battery_lock:
                value = battery_value
            self.value_changed.emit(value)
            time.sleep(1)

class Controller(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("mainWindow.ui", self)  # <-- your .ui file

        # Progress bar setup
        self.batyPercentage.setRange(0, 100)
        self.batyPercentage.setValue(0)
        self.batyPercentage.setFormat("%p%")

        # State
        self.running = False
        self.stop_event = None
        self.updater = None
        self.reader = None

        # Initial UI state
        self.set_disconnected_ui()

        # Button hookup
        self.connectionButton.clicked.connect(self.toggle_system)

    # =========================
    # Toggle logic
    # =========================
    def toggle_system(self):
        if not self.running:
            self.start_system()
        else:
            self.stop_system()

    def start_system(self):
        serial = self.serialNumber.text().strip()

        if not serial:
            self.deviceConnectionStatus.setText("No serial number")
            self.deviceConnectionStatus.setStyleSheet("color: orange;")
            return

        print(f"Connecting to device {serial}")

        self.stop_event = threading.Event()

        self.updater = BatteryUpdater(self.stop_event)
        self.updater.start()

        self.reader = BatteryReader(self.stop_event)
        self.reader.value_changed.connect(self.update_battery)
        self.reader.start()

        self.connectionButton.setText("Disconnect")
        self.set_connected_ui()

        self.running = True

    def stop_system(self):
        print("Disconnecting")

        self.stop_event.set()

        if self.reader:
            self.reader.wait()

        self.batyPercentage.setValue(0)

        self.connectionButton.setText("Connect")
        self.set_disconnected_ui()

        self.running = False
import sys
import time
import random
import threading
import subprocess

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6 import uic

battery_value = 0
battery_lock = threading.Lock()

tempSerialNumber = "RZCY50F8R8T"


class BatteryUpdater(threading.Thread):
    def __init__(self, stop_event, serial):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.serial = serial  # <-- plain string, not UI

    def run(self):
        global battery_value
        while not self.stop_event.is_set():
            try:
                result = subprocess.run(
                    ["adb", "-s", self.serial, "shell", "dumpsys", "battery"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                for line in result.stdout.splitlines():
                    if "level:" in line:
                        with battery_lock:
                            battery_value = int(line.split(":")[1].strip())
                        break

            except Exception as e:
                print(f"Error reading battery level: {e}")

            time.sleep(1)




class BatteryReader(QThread):
    value_changed = pyqtSignal(int)

    def __init__(self, stop_event):
        super().__init__()          # <-- no args
        self.stop_event = stop_event

    def run(self):
        global battery_value
        while not self.stop_event.is_set():
            with battery_lock:
                value = battery_value
            self.value_changed.emit(value)
            time.sleep(1)

class Controller(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("mainWindow.ui", self)  # <-- your .ui file

        # Progress bar setup
        self.batyPercentage.setRange(0, 100)
        self.batyPercentage.setValue(0)
        self.batyPercentage.setFormat("%p%")

        # State
        self.running = False
        self.stop_event = None
        self.updater = None
        self.reader = None

        # Initial UI state
        self.set_disconnected_ui()

        # Button hookup
        self.connectionButton.clicked.connect(self.toggle_system)

    # =========================
    # Toggle logic
    # =========================
    def toggle_system(self):
        if not self.running:
            self.start_system()
        else:
            self.stop_system()

    def start_system(self):
        serial = self.serialNumber.text().strip()

        if not serial:
            self.deviceConnectionStatus.setText("No serial number")
            self.deviceConnectionStatus.setStyleSheet("color: orange;")
            return

        print(f"Connecting to device {serial}")

        self.stop_event = threading.Event()

        self.updater = BatteryUpdater(self.stop_event, serial)
        
        self.updater.start()


        self.reader = BatteryReader(self.stop_event)
        self.reader.value_changed.connect(self.update_battery)
        self.reader.start()

        self.connectionButton.setText("Disconnect")
        self.set_connected_ui()

        self.running = True

    def stop_system(self):
        print("Disconnecting")

        self.stop_event.set()

        if self.reader:
            self.reader.wait()

        self.batyPercentage.setValue(0)

        self.connectionButton.setText("Connect")
        self.set_disconnected_ui()

        self.running = False

    # =========================
    # UI helpers
    # =========================
    def set_connected_ui(self):
        self.deviceConnectionStatus.setText("Connected")
        self.deviceConnectionStatus.setStyleSheet("color: green; font-weight: bold;")

    def set_disconnected_ui(self):
        self.deviceConnectionStatus.setText("Disconnected")
        self.deviceConnectionStatus.setStyleSheet("color: red; font-weight: bold;")
    def update_battery(self, value):
        self.batyPercentage.setValue(value)

    def closeEvent(self, event):
        if self.running:
            self.stop_system()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Controller()
    window.show()
    sys.exit(app.exec())

    # =========================
    # UI helpers
    # =========================
    def set_connected_ui(self):
        self.deviceConnectionStatus.setText("Connected")
        self.deviceConnectionStatus.setStyleSheet("color: green; font-weight: bold;")

    def set_disconnected_ui(self):
        self.deviceConnectionStatus.setText("Disconnected")
        self.deviceConnectionStatus.setStyleSheet("color: red; font-weight: bold;")
    def update_battery(self, value):
        self.batyPercentage.setValue(value)

    def closeEvent(self, event):
        if self.running:
            self.stop_system()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Controller()
    window.show()
    sys.exit(app.exec())
