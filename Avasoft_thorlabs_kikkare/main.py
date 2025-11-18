import sys
import platform
import os
from dotenv import load_dotenv
load_dotenv()
PROJECT_PATH = str(os.environ["PROJECT_PATH"])

from PyQt5 import uic
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import QtTest

import pyqtgraph as pg
import time
import math
from statistics import *
from itertools import product
from collections import defaultdict

from avaspec import *
import thorlab_device_control as tlab
from pylinkam import interface, sdk
import globals
import setting_windows as windows
from file_handler import *


main_ui_class, main_baseclass = pg.Qt.loadUiType("main_window.ui")
class MainWindow(main_ui_class, main_baseclass):
    newdata = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avaspec / Thorlabs Automation thing")

        # Connecting action triggers from the window selection bar to show/hide the specified setting windows
        self.ava_settings_window = windows.AvaSettingWindow()
        self.actionAvasoft.triggered.connect(
            lambda checked: self.toggleWindow(self.ava_settings_window)
        )
        self.actionAvasoft.setEnabled(False)

        self.rotation_mount_settings_window = windows.RotationMountSettingWindow()
        self.actionRotation_Mount.triggered.connect(
            lambda checked: self.toggleWindow(self.rotation_mount_settings_window)
        )
        self.actionRotation_Mount.setEnabled(False)

        self.link_settings_window = windows.LinkSettingWindow()
        self.actionLinkam_RH95.triggered.connect(
            lambda checked: self.toggleWindow(self.link_settings_window)
        )
        self.actionLinkam_RH95.setEnabled(False)

        # Initializing button states
        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(False)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.measurement_mode = self.SelectModeBox.currentText()
        self.newdata.connect(self.handleNewData)

        # Connecting button events to methods
        self.StartMeasBtn.clicked.connect(self.StartMeasBtn_clicked)
        self.PauseMeasBtn.clicked.connect(self.PauseMeasBtn_clicked)
        self.StopMeasBtn.clicked.connect(self.StopMeasBtn_clicked)
        self.SaveRefBtn.clicked.connect(self.SaveRefBtn_clicked)
        self.SaveDrkBtn.clicked.connect(self.SaveDrkBtn_clicked)
        self.SelectModeBox.currentTextChanged.connect(self.Mode_changed)
        self.connectAvasoft.triggered.connect(self.OpenCommBtn_clicked)
        self.connectThorlabs.triggered.connect(self.ConnectThorlabsBtn_clicked)

        self.testRotBtn.clicked.connect(self.ChangePosition)
        self.testShutterBtn.clicked.connect(self.ToggleShutter)

        # Initializing data plotting
        self.graph.setBackground("w")
        self.initPlot(None, None, None, "", "")

        self.measurement_paused = False

    def closeEvent(self, event):
        """
        Called right before the program is shut down - ensures that all thorlabs devices will be disconnected
        properly. Causes issues with later connectivity otherwise.
        """
        self.StopMeasBtn_clicked()
        tlab.disconnect_all()
        event.accept()

    @pyqtSlot()
    def toggleWindow(self, window):
        if window.isVisible():
            window.hide()
        else:
            window.show()

    @pyqtSlot()
    def ChangePosition(self):
        id = "55360064"
        pos_list = globals.rotation_mount_positions.get(id)

        if pos_list is None:
            print("Error")
            return

        for pos in pos_list:
            tlab.set_rotation_mount_pos(id, pos)

    @pyqtSlot()
    def ToggleShutter(self):
        self.testShutterBtn.setEnabled(False)
        globals.solenoid_open_timers = readShutterTimers()

        for shutter_open_for in globals.solenoid_open_timers:
            tlab.open_shutter("68250034")
            print(shutter_open_for)
            QtTest.QTest.qWait(shutter_open_for*1000)
            tlab.close_shutter("68250034")

        self.testShutterBtn.setEnabled(True)

    @pyqtSlot()
    def OpenCommBtn_clicked(self):
        """
        Modified method from Avasoft PyQt5 demo. Attempts to connect to an Avaspec spectrometer.

        :return:
        """
        ret = AVS_Init(0)
        ret = AVS_GetNrOfDevices()
        mylist = AvsIdentityType()
        mylist = AVS_GetList(1)
        try:
            serienummer = str(mylist[0].SerialNumber.decode("utf-8"))
            QMessageBox.information(self, "Info", "Found Serialnumber: " + serienummer)
        except IndexError:
            QMessageBox.information(self, "Error", "Could not find a device")
            return
        globals.dev_handle = AVS_Activate(mylist[0])
        devcon = DeviceConfigType()
        devcon = AVS_GetParameter(globals.dev_handle, 63484)
        globals.pixels = devcon.m_Detector_m_NrPixels
        globals.wavelength_full = AVS_GetLambda(globals.dev_handle)
        self.StartMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(True)
        self.SaveDrkBtn.setEnabled(True)
        self.connectAvasoft.setEnabled(False)
        self.actionAvasoft.setEnabled(True)
        return

    @pyqtSlot()
    def ConnectThorlabsBtn_clicked(self):
        msg = tlab.connect_all()
        QMessageBox.information(self, msg[0], msg[1])

        if msg[0] == "Error":
            return
        else:
            self.rotation_mount_settings_window.AddTabs()
            self.connectThorlabs.setEnabled(False)
            self.actionRotation_Mount.setEnabled(True)
        return

    @pyqtSlot()
    def StartMeasBtn_clicked(self):
        """
        Main method for running all measurements depending on the mode selected.

        :return:
        """
        self.ava_settings_window.hide()

        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        globals.stopscanning = False

        ttl_on(globals.dev_handle)
        QtTest.QTest.qWait(100)

        if self.measurement_mode == "Scope":

            self.initPlot(globals.min_wavelength, globals.max_wavelength, None, "Wavelength (nm)", "Counts (#)")
            while True:
                if globals.stopscanning:
                    break
                self.measureScope()
                self.plot(globals.wavelength, globals.spectraldata)
                time.sleep(0.01)

        elif self.measurement_mode == "Absorbance" and len(globals.referencedata) > 0:

            self.initPlot(globals.min_wavelength, globals.max_wavelength,[0,3],"Wavelength (nm)","Absorbance")
            while True:
                if globals.stopscanning:
                    break

                abs_spectra = self.measureAbs("")
                self.plot(globals.wavelength, abs_spectra)
                time.sleep(0.01)

        elif self.measurement_mode == "Transmittance" and len(globals.referencedata) > 0:

            self.initPlot(globals.min_wavelength, globals.max_wavelength,[0,110],"Wavelength (nm)","Transmittance")
            while True:
                if globals.stopscanning:
                    break

                trans_spectra = self.measureTransmittance("")
                self.plot(globals.wavelength, trans_spectra)
                time.sleep(0.01)

        ret = AVS_StopMeasure(globals.dev_handle)

        ttl_off(globals.dev_handle)
        QtTest.QTest.qWait(100)

        self.StartMeasBtn.setEnabled(True)
        self.PauseMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(False)
        self.SaveRefBtn.setEnabled(True)
        self.SaveDrkBtn.setEnabled(True)
        self.SelectModeBox.setEnabled(True)
        self.menuBar.setEnabled(True)
        return

    @pyqtSlot()
    def PauseMeasBtn_clicked(self):
        if self.measurement_paused:
            self.measurement_paused = False
            self.PauseMeasBtn.setText("Pause Measurement")

        else:
            self.measurement_paused = True
            self.StartMeasBtn.setEnabled(False)
            self.PauseMeasBtn.setText("Continue Measurement")

            while self.measurement_paused:
                QtTest.QTest.qWait(100)

    @pyqtSlot()
    def StopMeasBtn_clicked(self):
        """
        Completely stops all ongoing measurements as well as RH changes

        :return:
        """
        globals.stopscanning = True
        self.measurement_paused = False
        self.StartMeasBtn.setEnabled(True)
        self.PauseMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setText("Pause Measurement")
        self.StartMeasBtn.setEnabled(False)
        self.repaint()

        return

    @pyqtSlot()
    def SaveRefBtn_clicked(self):
        """
        Saves and plots reference spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """

        self.rotation_mount_settings_window.calculatePositionCombinations()

        self.initPlot(globals.min_wavelength, globals.max_wavelength, None, "Wavelength (nm)", "Counts (#)")

        if len(globals.mount_position_combinations) == 0:

            ttl_on(globals.dev_handle)
            QtTest.QTest.qWait(100)

            self.measureScope()

            ttl_off(globals.dev_handle)
            QtTest.QTest.qWait(100)

            reference_data = globals.spectraldata
            globals.referencedata[""] = reference_data

            saveToNewFile(f"reference", "ref", globals.wavelength, reference_data)

            self.initPlot(globals.min_wavelength, globals.max_wavelength, None, "Wavelength (nm)", "Counts (#)")
            self.plot(globals.wavelength, reference_data)

            time.sleep(0.001)

        else:
            for pos_combination_id, pos_combination in globals.mount_position_combinations.items():
                for mount_id, position in pos_combination.items():
                    print(position)
                    tlab.set_rotation_mount_pos(mount_id, int(position))

                ttl_on(globals.dev_handle)
                QtTest.QTest.qWait(100)

                self.measureScope()

                ttl_off(globals.dev_handle)
                QtTest.QTest.qWait(100)

                reference_data = globals.spectraldata
                globals.referencedata[pos_combination_id] = reference_data

                saveToNewFile(f"reference_{pos_combination_id}", "ref", globals.wavelength, reference_data)

                self.plot(globals.wavelength, reference_data)
                self.repaint()

                time.sleep(0.001)

        return

    @pyqtSlot()
    def SaveDrkBtn_clicked(self):
        """
        Saves and plots dark spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """
        ttl_off(globals.dev_handle)
        QtTest.QTest.qWait(100)

        self.measureScope()
        globals.darkdata = globals.spectraldata

        self.initPlot(globals.min_wavelength, globals.max_wavelength, None, "Wavelength (nm)", "Counts (#)")
        self.plot(globals.wavelength, globals.darkdata)

        time.sleep(0.001)
        return

    @pyqtSlot()
    def Mode_changed(self):
        self.measurement_mode = self.SelectModeBox.currentText()

    @pyqtSlot()
    def measureScope(self):
        """
        Modified method from Avasoft PyQt5 demo. Performs a measurement defined by the measconfig object. All variables
        shown must be defined, even though a large portion of them are unnecessary.

        :return:
        """
        self.repaint()
        ret = AVS_UseHighResAdc(globals.dev_handle, True)
        measconfig = MeasConfigType()
        measconfig.m_StartPixel = 0
        measconfig.m_StopPixel = globals.pixels - 1
        measconfig.m_IntegrationTime = globals.int_time
        measconfig.m_IntegrationDelay = 0
        measconfig.m_NrAverages = globals.avg_num
        measconfig.m_CorDynDark_m_Enable = 0  # nesting of types does NOT work!!
        measconfig.m_CorDynDark_m_ForgetPercentage = 0
        measconfig.m_Smoothing_m_SmoothPix = globals.smoothing
        measconfig.m_Smoothing_m_SmoothModel = 0
        measconfig.m_SaturationDetection = 0
        measconfig.m_Trigger_m_Mode = 0
        measconfig.m_Trigger_m_Source = 0
        measconfig.m_Trigger_m_SourceType = 0
        measconfig.m_Control_m_StrobeControl = 0
        measconfig.m_Control_m_LaserDelay = 0
        measconfig.m_Control_m_LaserWidth = 0
        measconfig.m_Control_m_LaserWaveLength = 785.0
        measconfig.m_Control_m_StoreToRam = 0
        ret = AVS_PrepareMeasure(globals.dev_handle, measconfig)
        nummeas = 1 # Performs only a single measurement

        ret = AVS_Measure(globals.dev_handle, 0, nummeas)
        dataready = False
        while (dataready == False):
            dataready = (AVS_PollScan(globals.dev_handle) == True)
            QtTest.QTest.qWait(1)

        self.newdata.emit() # Retrieves and saves the measurement to global variables
        self.repaint()
        time.sleep(0.001)
        qApp.processEvents()  # allows clicking of the StopMeasBtn to be seen
        self.repaint()
        return

    @pyqtSlot()
    def measureAbs(self, ref_id):
        """
        Calculates a sample's absorbance spectrum by comparing its scope to previously saved reference and dark files.

        :return:
        """
        ref = globals.referencedata.get(ref_id)
        self.measureScope()

        # Absorbance formula from Avasoft 8 documentation
        try:
            abs_spectra = [-math.log10((s - d) / (r - d)) for r, s, d in zip(ref, globals.spectraldata, globals.darkdata)]
        except (ValueError, ZeroDivisionError): # Catches any errors and returns a list full of zeros
            abs_spectra = [0.0] * len(globals.spectraldata)
            # abs = [0 for _ in range(len(globals.spectraldata))]
        return abs_spectra

    @pyqtSlot()
    def measureTransmittance(self, ref_id):
        """
        Calculates a sample's transmittance spectrum by comparing its scope to previously saved reference and dark files.

        :return:
        """
        ref = globals.referencedata.get(ref_id)
        self.measureScope()

        # Absorbance formula from Avasoft 8 documentation
        try:
            trans_spectra = [100 * ((s - d ) / (r - d)) for r, s, d in zip(ref, globals.spectraldata, globals.darkdata)]
        except (ValueError, ZeroDivisionError):  # Catches any errors and returns a list full of zeros
            trans_spectra = [100.0] * len(globals.spectraldata)
            # abs = [0 for _ in range(len(globals.spectraldata))]
        return trans_spectra

    @pyqtSlot()
    def handleNewData(self):
        """
        Modified method from Avasoft PyQt5 demo. Retrieves data from every pixel in the spectroscope (4096 in total)
        recorded during the last performed measurement. Filters out all wavelengths outside a given wavelength range.

        :return:
        """
        timestamp = 0
        ret = AVS_GetScopeData(globals.dev_handle)
        timestamp = ret[0]
        spectral_data = []
        wavelength = []
        for n in range(len(globals.wavelength_full)):
            if globals.min_wavelength < globals.wavelength_full[n] < globals.max_wavelength:
                spectral_data.append(ret[1][n])
                wavelength.append(globals.wavelength_full[n])
        globals.spectraldata = spectral_data
        globals.wavelength = wavelength
        # QMessageBox.information(self,"Info","Received data")
        time.sleep(0.001)
        qApp.processEvents()  # allows repaint to occur between scans
        return

    @pyqtSlot()
    def initPlot(self,min_x,max_x,yrange,x_label,y_label):
        """
        Initialises pyqtgraph with given parameters

        :param min_x: float, lowest x value shown
        :param max_x: float, largest x value shown
        :param yrange: [min_y, max_y]
        :param x_label: str,
        :param y_label: str,
        :return:
        """
        self.graph.clear()

        pen = pg.mkPen(color=(0,0,0), width=1.1, style=Qt.SolidLine)
        self.graph.setLabel("left", f"{y_label}")
        self.graph.setLabel("bottom", f"{x_label}")
        if max_x:
            self.graph.setXRange(min_x,max_x)
        if yrange:
            self.graph.setYRange(yrange[0],yrange[1])
        self.graph.showGrid(x=True, y=True)

        self.line = self.graph.plot([0],[0], pen=pen)

    @pyqtSlot()
    def plot(self,x,y):
        self.line.setData(x,y)

    @pyqtSlot()
    def updatePlotRange(self,min_x,max_x):
        self.graph.setXRange(min_x,max_x)



def setRH(RH,plateau_tolerance):
    """
    Connects to the Linkam RH95 humidity controller and attempts to set a given RH value. Slowly approaches
    the desired value by dynamically changing the setpoint until the measured RH has stabilized for long enough.

    :param RH: int, relative humidity setpoint
    :param plateau_tolerance: int, acceptable range for RH to stabilize to
    :return:
    """
    with sdk.SDKWrapper() as wrapper:
        with wrapper.connect() as connection:
            # Every message sent to the RH controller needs to be followed by short wait to ensure it goes through
            connection.enable_humidity(True)
            QtTest.QTest.qWait(1000)

            # Determining an initial RH setpoint based on how far away the current RH value is
            init_rh = connection.get_value(interface.StageValueType.HUMIDITY)
            if init_rh < RH - 10:
                humidity_setpoint = RH - 10
            elif init_rh > RH + 10:
                humidity_setpoint = RH + 10
            elif init_rh < RH:
                humidity_setpoint = RH - 5
            else:
                humidity_setpoint = RH + 5

            connection.set_value(interface.StageValueType.MANUAL_HUMIDITY_SETPOINT, humidity_setpoint)

            n = 0
            while True:
                if globals.stopscanning:
                    return
                if n == 6:
                    # Returns if RH has remained the same for 30 s
                    connection.set_value(interface.StageValueType.MANUAL_HUMIDITY_SETPOINT, RH)
                    QtTest.QTest.qWait(1000)
                    return
                else:
                    QtTest.QTest.qWait(5000)

                # Increment by one, if the measured RH close enough to the setpoint. Reset count otherwise
                current_rh = connection.get_value(interface.StageValueType.HUMIDITY)
                if RH - plateau_tolerance < current_rh < RH + plateau_tolerance:
                    n += 1
                else:
                    n = 0

                # Updating the RH setpoint, if a new threshold was reached
                temp_rh_setpoint = humidity_setpoint
                if humidity_setpoint < current_rh < RH:
                    humidity_setpoint += (RH - humidity_setpoint)/2
                elif RH < current_rh < humidity_setpoint:
                    humidity_setpoint -= (humidity_setpoint - RH)/2

                if temp_rh_setpoint != humidity_setpoint:
                    print(f"Current RH Setpoint = {humidity_setpoint}")
                    connection.set_value(interface.StageValueType.MANUAL_HUMIDITY_SETPOINT, humidity_setpoint)


def main():
    # Initializing the PyQt application window
    app = QApplication(sys.argv)
    app.lastWindowClosed.connect(app.quit)
    window = MainWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    main()
