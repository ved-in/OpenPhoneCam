import sys
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import uic

from tab_main import TabMain
from tab_settings import TabSettings
from tab_cammy import TabCammy
from tab_about import TabAbout

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("mainwindow.ui", self)
        self.tab_main = TabMain(self)
        self.tab_settings = TabSettings(self)
        self.tab_cammy = TabCammy(self)
        self.tab_about = TabAbout(self)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
