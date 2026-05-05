import sys
from PyQt5.QtWidgets import QApplication, QMainWindow
import mainwindow


app = QApplication([])
win = mainwindow.MainWindow()

win.show()

app.exec()

win.close_device()
win.on_btn_galvo_stop_pressed()

del win.ui
