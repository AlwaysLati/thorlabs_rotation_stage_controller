import sys
import os
import time
import math
from dotenv import load_dotenv
load_dotenv()
PROJECT_PATH = str(os.environ["PROJECT_PATH"])

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5 import QtTest
import pyqtgraph as pg

from avaspec import *
import thorlab_device_control as tlab
from pylinkam import interface, sdk
import globals
import setting_windows as windows
from file_handler import *

SHUTTER_ID = "68250034"


# ----------------- Controller Wrappers ----------------- #

class AvaspecController(QObject):
    new_data = pyqtSignal(list, list)

    def __init__(self):
        super().__init__()
        self.dev_handle = None
        self.pixels = 0
        self.wavelength_full = []
        self.spectraldata = []
        self.wavelength = []

    def connect_device(self):
        AVS_Init(0)
        AVS_GetNrOfDevices()
        mylist = AVS_GetList(1)
        try:
            self.dev_handle = AVS_Activate(mylist[0])
            devcon = AVS_GetParameter(self.dev_handle, 63484)
            self.pixels = devcon.m_Detector_m_NrPixels
            self.wavelength_full = AVS_GetLambda(self.dev_handle)
        except IndexError:
            raise RuntimeError("Avaspec device not found.")

    def measure_scope(self):
        measconfig = MeasConfigType()
        measconfig.m_StartPixel = 0
        measconfig.m_StopPixel = self.pixels - 1
        measconfig.m_IntegrationTime = globals.int_time
        measconfig.m_NrAverages = globals.avg_num
        measconfig.m_Smoothing_m_SmoothPix = globals.smoothing
        AVS_PrepareMeasure(self.dev_handle, measconfig)
        AVS_Measure(self.dev_handle, 0, 1)

        dataready = False
        while not dataready:
            dataready = AVS_PollScan(self.dev_handle)
            QtTest.QTest.qWait(1)

        timestamp, data = AVS_GetScopeData(self.dev_handle)
        self.spectraldata = [d for wl, d in zip(self.wavelength_full, data)
                             if globals.min_wavelength < wl < globals.max_wavelength]
        self.wavelength = [wl for wl in self.wavelength_full
                           if globals.min_wavelength < wl < globals.max_wavelength]

        self.new_data.emit(self.wavelength, self.spectraldata)

    def calculate_absorbance(self, ref_id):
        ref = globals.referencedata.get(ref_id)
        self.measure_scope()
        try:
            return [-math.log10((s - d) / (r - d)) for r, s, d in
                    zip(ref, self.spectraldata, globals.darkdata)]
        except (ValueError, ZeroDivisionError):
            return [0.0] * len(self.spectraldata)

    def calculate_transmittance(self, ref_id):
        ref = globals.referencedata.get(ref_id)
        self.measure_scope()
        try:
            return [100 * ((s - d) / (r - d)) for r, s, d in
                    zip(ref, self.spectraldata, globals.darkdata)]
        except (ValueError, ZeroDivisionError):
            return [100.0] * len(self.spectraldata)


class ThorlabsController:
    @staticmethod
    def connect_all():
        return tlab.connect_all()

    @staticmethod
    def set_rotation_positions(positions):
        for mount_id, pos in positions.items():
            tlab.set_rotation_mount_pos(mount_id, int(pos))

    @staticmethod
    def open_shutter(shutter_id):
        tlab.open_shutter(shutter_id)

    @staticmethod
    def close_shutter(shutter_id):
        tlab.close_shutter(shutter_id)


class LinkamController:
    def __init__(self):
        self.wrapper = None
        self.connection = None

    def connect(self):
        self.wrapper = sdk.SDKWrapper()
        self.connection = self.wrapper.connect()

    def set_humidity(self, RH, plateau_tolerance=1):
        # Implementation similar to original
        pass


# ----------------- Worker Thread ----------------- #

class MeasurementWorker(QThread):
    data_ready = pyqtSignal(list, list)

    def __init__(self, avaspec: AvaspecController, mode="Scope", ref_id="",
                 mount_combinations=None, shutter_timers=None, filename="result"):
        super().__init__()
        self.avaspec = avaspec
        self.mode = mode
        self.ref_id = ref_id
        self.mount_combinations = mount_combinations or {}
        self.shutter_timers = shutter_timers or []
        self.filename = filename
        self.running = True
        self.paused = False
        self.pause_cond = QWaitCondition()
        self.mutex = QMutex()

    def run(self):
        for open_time in self.shutter_timers:
            if not self.running:
                break
            self._wait_if_paused()

            # Default mount positions
            for mount_id, pos in globals.mount_default_angles.items():
                tlab.set_rotation_mount_pos(mount_id, pos)

            # Open shutter
            tlab.open_shutter(SHUTTER_ID)
            for _ in range(int(open_time * 10)):
                if not self.running:
                    break
                self._wait_if_paused()
                QtTest.QTest.qWait(100)
            tlab.close_shutter(SHUTTER_ID)

            for combo_id, positions in self.mount_combinations.items():
                if not self.running:
                    break
                self._wait_if_paused()
                for mount_id, pos in positions.items():
                    tlab.set_rotation_mount_pos(mount_id, int(pos))

                if self.mode == "Absorbance":
                    spectra = self.avaspec.calculate_absorbance(combo_id)
                    ylabel = "Absorbance"
                elif self.mode == "Transmittance":
                    spectra = self.avaspec.calculate_transmittance(combo_id)
                    ylabel = "Transmittance"
                else:
                    self.avaspec.measure_scope()
                    spectra = self.avaspec.spectraldata
                    ylabel = "Counts (#)"

                saveToNewFile(f"{self.filename}_{int(open_time)}s_{combo_id}",
                              f"Results_{ylabel}", self.avaspec.wavelength, spectra)
                self.data_ready.emit(self.avaspec.wavelength, spectra)
                time.sleep(0.01)

    def stop(self):
        self.running = False
        self.resume()
        self.wait()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False
        self.pause_cond.wakeAll()

    def _wait_if_paused(self):
        self.mutex.lock()
        while self.paused:
            self.pause_cond.wait(self.mutex)
        self.mutex.unlock()


# ----------------- Main Window ----------------- #

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Avaspec / Thorlabs Automation")
        self.graph = pg.PlotWidget()
        self.setCentralWidget(self.graph)

        # Controllers
        self.avaspec = AvaspecController()
        self.thorlabs = ThorlabsController()
        self.linkam = LinkamController()

        self.measurement_thread = None
        self.line = self.graph.plot([0], [0], pen=pg.mkPen('b', width=1.2))

        # GUI Elements (buttons, combo boxes)
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.filename_edit = QLineEdit("result")
        self.mode_box = QComboBox()
        self.mode_box.addItems(["Scope", "Absorbance", "Transmittance"])

        layout = QVBoxLayout()
        layout.addWidget(self.graph)
        layout.addWidget(self.filename_edit)
        layout.addWidget(self.mode_box)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.pause_btn)
        layout.addWidget(self.stop_btn)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Signals
        self.start_btn.clicked.connect(self.start_measurement)
        self.pause_btn.clicked.connect(self.pause_or_resume)
        self.stop_btn.clicked.connect(self.stop_measurement)
        self.avaspec.new_data.connect(self.update_plot)

        self.paused = False

    @pyqtSlot(list, list)
    def update_plot(self, x, y):
        self.line.setData(x, y)

    def start_measurement(self):
        filename = self.filename_edit.text()
        mode = self.mode_box.currentText()
        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop()

        self.measurement_thread = MeasurementWorker(
            self.avaspec,
            mode=mode,
            mount_combinations=globals.mount_position_combinations,
            shutter_timers=globals.solenoid_open_timers,
            filename=filename
        )
        self.measurement_thread.data_ready.connect(self.update_plot)
        self.measurement_thread.start()
        self.paused = False
        self.pause_btn.setText("Pause")

    def pause_or_resume(self):
        if not self.measurement_thread:
            return
        if self.paused:
            self.measurement_thread.resume()
            self.paused = False
            self.pause_btn.setText("Pause")
        else:
            self.measurement_thread.pause()
            self.paused = True
            self.pause_btn.setText("Resume")

    def stop_measurement(self):
        if self.measurement_thread:
            self.measurement_thread.stop()


# ----------------- Main ----------------- #

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
