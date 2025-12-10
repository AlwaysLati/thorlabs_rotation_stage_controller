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
from timeit import default_timer as timer

from avaspec import *
import thorlab_device_control as tlab
from pylinkam import interface, sdk
import globals
import setting_windows as windows
from file_handler import *

TLABPATH = str(os.environ["THORLABS_PATH"])

# Write in file paths of dlls needed.
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference(f"{TLABPATH}\\ThorLabs.MotionControl.IntegratedStepperMotorsCLI.dll")
clr.AddReference(f"{TLABPATH}\\ThorLabs.MotionControl.KCube.SolenoidCLI.dll")

# Import functions from dlls.
from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import MotorDirection
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import *
from Thorlabs.MotionControl.KCube.SolenoidCLI import *
from System import Decimal

# ----------------- DEVICE CONTROLLERS ----------------- #

class AvaspecController:
    def __init__(self):
        """ Avaspec Data """
        self.dev_handle = 0
        self.pixels = 4096
        self.wavelength_full = [0.0] * 4096
        self.wavelength = [0.0] * 4096
        self.spectraldata = [0.0] * 4096
        self.darkdata = [0.0] * 4096
        self.referencedata = dict()

        """ Avaspec  Parameters """
        self.int_time = 5
        self.avg_num = 0
        self.min_wavelength = 0
        self.max_wavelength = 0
        self.smoothing = 3
        self.stopscanning = True

    def connect_device(self):
        """
        Modified method from Avasoft PyQt5 demo. Attempts to connect to an Avaspec spectrometer.

        :return: int, Device serial number
        """
        ret = AVS_Init(0)
        ret = AVS_GetNrOfDevices()
        mylist = AvsIdentityType()
        mylist = AVS_GetList(1)

        try:
            serial_number = str(mylist[0].SerialNumber.decode("utf-8"))
        except IndexError:
            return 0

        self.dev_handle = AVS_Activate(mylist[0])
        devcon = DeviceConfigType()
        devcon = AVS_GetParameter(self.dev_handle, 63484)
        self.pixels = devcon.m_Detector_m_NrPixels
        self.wavelength_full = AVS_GetLambda(self.dev_handle)

        return serial_number

    def save_reference(self, combo_id=""):
        self.ttl_on()
        time.sleep(0.001)

        self.measure_scope()

        self.ttl_off()
        time.sleep(0.001)

        reference_data = self.spectraldata
        self.referencedata[combo_id] = reference_data

        saveToNewFile(f"reference_{combo_id}", "ref", self.wavelength, reference_data)

        return self.wavelength, reference_data

    def save_dark(self):
        self.ttl_off()
        time.sleep(0.001)

        self.measure_scope()
        self.darkdata = self.spectraldata

        saveToNewFile(f"reference_dark", "ref", self.wavelength, self.darkdata)

        return self.wavelength, self.darkdata

    def measure_scope(self, ref_id=""):
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
        nummeas = 1  # Performs only a single measurement

        ret = AVS_Measure(self.dev_handle, 0, nummeas)
        dataready = False
        while dataready == False:
            dataready = (AVS_PollScan(self.dev_handle) == True)
            time.sleep(0.001)

        timestamp, data = AVS_GetScopeData(self.dev_handle)
        AVS_StopMeasure(self.dev_handle)

        self.spectraldata = [d for wl, d in zip(self.wavelength_full, data)
                             if self.min_wavelength < wl < self.max_wavelength]
        self.wavelength = [wl for wl in self.wavelength_full
                           if self.min_wavelength < wl < self.max_wavelength]


        return self.wavelength, self.spectraldata

    def measure_absorbance(self, ref_id=""):
        ref = self.referencedata.get(ref_id)
        self.measure_scope()

        # Absorbance formula from Avasoft 8 documentation
        try:
            abs_spectra = [-math.log10((s - d) / (r - d)) for r, s, d in
                           zip(ref, self.spectraldata, self.darkdata)]
        except (ValueError, ZeroDivisionError):  # Catches any errors and returns a list full of zeros
            abs_spectra = [0.0] * len(self.spectraldata)

        return self.wavelength, abs_spectra

    def measure_transmittance(self, ref_id=""):
        ref = self.referencedata.get(ref_id)
        self.measure_scope()

        # Absorbance formula from Avasoft 8 documentation
        try:
            trans_spectra = [100 * ((s - d) / (r - d)) for r, s, d in zip(ref, self.spectraldata, self.darkdata)]
        except (ValueError, ZeroDivisionError):  # Catches any errors and returns a list full of zeros
            trans_spectra = [100.0] * len(self.spectraldata)

        return self.wavelength, trans_spectra

    def ttl_on(self):
        """Set TTL output HIGH (light on)."""
        ret = AVS_SetDigOut(self.dev_handle, 3, 1)
        if ret < 0:
            raise RuntimeError(f"AVS_SetDigOut returned {ret}")
        return ret

    def ttl_off(self):
        """Set TTL output LOW (light off)."""
        ret = AVS_SetDigOut(self.dev_handle, 3, 0)
        if ret < 0:
            raise RuntimeError(f"AVS_SetDigOut returned {ret}")
        return ret


class ThorlabsController:
    def __init__(self):
        """ Thorlabs Devices"""
        self.device_list = dict()  # "device_id" : Device
        self.rotation_mount_positions = defaultdict(list)  # "device_id" : [position]
        self.mount_position_combos = defaultdict(dict)
        self.mount_default_angles = dict()
        self.solenoid_open_timers = list()

    def connect_devices(self):
        """Attempts to connect to all Thorlabs devices"""

        try:
            # Initialize device list.
            DeviceManagerCLI.BuildDeviceList()
            serial_numbers = DeviceManagerCLI.GetDeviceList()

            if len(serial_numbers) == 0:
                return ["Error", "No devices found"]

            for serial_no in serial_numbers:
                device_type = serial_no[:2]

                if device_type == "55":  # Integrated stepper driven rotation stage
                    self.connect_mount(serial_no)

                elif device_type == "68":  # K-Cube solenoid Driver
                    self.connect_solenoid(serial_no)

                else:
                    return ["Error", "Unknown device found"]

            return ["Info", f"Connected to {len(serial_numbers)} Thorlabs devices"]

        except Exception as e:
            print(e)
            self.disconnect_all()
            return ["Error", f"{e}"]

    def connect_mount(self, serial_no):
        device = CageRotator.CreateCageRotator(serial_no)
        device.Connect(serial_no)

        # Ensure that the device settings have been initialized.
        if not device.IsSettingsInitialized():
            print("mount")
            device.WaitForSettingsInitialized(10000)  # 10 second timeout.
            assert device.IsSettingsInitialized() is True

        # Start polling loop and enable device.
        device.StartPolling(250)  # 250ms polling rate.
        time.sleep(0.25)
        device.EnableDevice()
        time.sleep(0.25)  # Wait for device to enable.

        device.LoadMotorConfiguration(serial_no, DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings)

        self.device_list[serial_no] = device

    def connect_solenoid(self, serial_no):
        device = KCubeSolenoid.CreateKCubeSolenoid(serial_no)
        device.Connect(serial_no)

        # Ensure that the device settings have been initialized.
        if not device.IsSettingsInitialized():
            print("solenoid")
            device.WaitForSettingsInitialized(10000)  # 10 second timeout.
            assert device.IsSettingsInitialized() is True

        # Start polling loop and enable device.
        device.StartPolling(250)  # 250ms polling rate.
        time.sleep(0.25)
        device.EnableDevice()
        time.sleep(0.25)  # Wait for device to enable.

        device.SetOperatingMode(SolenoidStatus.OperatingModes.Manual)

        self.device_list[serial_no] = device

    def disconnect_all(self):
        for device_id, device in self.device_list.items():
            if device_id[:2] == "55":
                device.StopImmediate()
            device.StopPolling()
            device.Disconnect()
            time.sleep(0.25)

        return

    def toggle_shutter(self, serial_no):
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != "68":
            return

        state = device.GetOperatingState()
        if state == SolenoidStatus.OperatingStates.Active:
            device.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)
        else:
            device.SetOperatingState(SolenoidStatus.OperatingStates.Active)

        return

    def open_shutter(self, serial_no):
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != "68":
            return

        device.SetOperatingState(SolenoidStatus.OperatingStates.Active)

        time.sleep(0.25)
        return

    def close_shutter(self, serial_no):
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != "68":
            return

        device.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)

        time.sleep(0.25)
        return

    def home_mount(self, serial_no):
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != "55":
            return ["Error", "Unable to home device"]

        try:
            # 60 second timeout, function will wait until the move completes or the timeout elapses, whichever comes first.
            device.Home(60000)
            return ["Info", "Homed device"]

        except Exception as e:
            print(e)
            return ["Error", "Unable to home device"]

    def set_mount_pos(self, serial_no, new_pos):
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != "55":
            return

        try:
            pos = Decimal(new_pos)  # Must be a .NET decimal.
            device.MoveTo(pos, 60000)  # 60 second timeout.

        except Exception as e:
            print(e)

        return


# ------------------- WORKER THREAD ------------------- #

class MeasurementWorker(QThread):
    data_ready = pyqtSignal(list, list)

    def __init__(self, avaspec: AvaspecController, thorlabs: ThorlabsController,
                 calculation_mode="Scope", measurement_mode="Cont", filename="result"):
        super().__init__()
        self.avaspec = avaspec
        self.thorlabs = thorlabs
        self.mode = calculation_mode
        self.measurement_mode = measurement_mode
        self.filename = filename
        self.running = True
        self.paused = False
        self.pause_cond = QWaitCondition()
        self.mutex = QMutex()

    def run(self):
        measurement_func = self.avaspec.measure_scope()
        if self.mode == "Absorbance":
            measurement_func = self.avaspec.measure_absorbance()
        elif self.mode == "Transmittance":
            measurement_func = self.avaspec.measure_transmittance()

        if self.measurement_mode == "Cont":
            self.run_continuous(measurement_func)
        elif self.measurement_mode == "Series":
            self.run_series(measurement_func)


    def run_continuous(self, func):
        self.avaspec.ttl_on()
        QtTest.QTest.qWait(100)

        while self.running:
            wl, data = func()
            self.data_ready.emit(wl, data)
            time.sleep(0.01)

        self.avaspec.ttl_off()
        QtTest.QTest.qWait(100)


    def run_series(self, func):
        self.thorlabs.solenoid_open_timers = readShutterTimers()

        cumulative_time = 0

        for t in self.thorlabs.solenoid_open_timers:
            if not self.running:
                break
            self.wait_if_paused()

            for mount_id, pos in self.thorlabs.mount_default_angles.items():
                self.thorlabs.set_mount_pos(mount_id, pos)

            self.thorlabs.open_shutter("68250034")

            for i in range(int(t * 10)):
                if not self.running:
                    break
                self.wait_if_paused()
                QtTest.QTest.qWait(t * 100)
            self.thorlabs.close_shutter("68250034")

            cumulative_time += t

            for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():
                for mount_id, position in pos_combination.items():
                    self.thorlabs.set_mount_pos(mount_id, int(position))

                self.avaspec.ttl_on()
                QtTest.QTest.qWait(100)

                output_spectra = func(pos_combination_id)

                self.avaspec.ttl_off()
                QtTest.QTest.qWait(100)

                saveToNewFile(f"{self.filename}_{cumulative_time}s_{pos_combination_id}",
                              f"Results_{self.mode}", self.avaspec.wavelength, output_spectra)

                self.data_ready.emit(self.avaspec.wavelength, output_spectra)

    def stop(self):
        self.running = False
        self.resume()
        self.wait()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False
        self.pause_cond.wakeAll()

    def wait_if_paused(self):
        self.mutex.lock()
        while self.paused:
            self.pause_cond.wait(self.mutex)
        self.mutex.unlock()


# -------------------- MAIN WINDOW -------------------- #

main_ui_class, main_baseclass = pg.Qt.loadUiType("main_window.ui")
class MainWindow(main_ui_class, main_baseclass):
    newdata = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avaspec / Thorlabs Automation thing")

        # Controllers
        self.avaspec = AvaspecController()
        self.thorlabs = ThorlabsController()

        # Connecting action triggers from the window selection bar to show/hide the specified setting windows
        self.ava_settings_window = windows.AvaSettingWindow()
        self.actionAvasoft.triggered.connect(
            lambda checked: self.toggleWindow(self.ava_settings_window)
        )
        self.actionAvasoft.setEnabled(False)

        self.mount_settings_window = windows.RotationMountSettingWindow()
        self.actionRotation_Mount.triggered.connect(
            lambda checked: self.toggleWindow(self.mount_settings_window)
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
        self.fileNameEdit.textChanged.connect(self.saveFile_changed)

        self.testRotBtn.clicked.connect(self.ChangePosition)
        self.testShutterBtn.clicked.connect(self.ToggleShutter)

        # Initializing data plotting
        self.graph.setBackground("w")
        self.initPlot(None, None, None, "", "")

        self.paused = False
        self.file_name_to_save = ""


    def closeEvent(self, event):
        """
        Called right before the program is shut down - ensures that all thorlabs devices will be disconnected
        properly. Causes issues with later connectivity otherwise.
        """
        self.StopMeasBtn_clicked()
        self.thorlabs.disconnect_all()
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
        ret = self.avaspec.connect_device()

        if ret == 0:
            QMessageBox.information(self, "Error", "Could not find a device")
            return
        else:
            QMessageBox.information(self, "Info", "Found Serialnumber: " + ret)

            self.StartMeasBtn.setEnabled(True)
            self.SaveRefBtn.setEnabled(True)
            self.SaveDrkBtn.setEnabled(True)
            self.connectAvasoft.setEnabled(False)
            self.actionAvasoft.setEnabled(True)

        return

    @pyqtSlot()
    def ConnectThorlabsBtn_clicked(self):
        msg = self.thorlabs.connect_devices()
        QMessageBox.information(self, msg[0], msg[1])

        if msg[0] == "Error":
            return
        else:
            self.mount_settings_window.AddTabs()
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

        if self.measurement_mode == "Scope":

            self.initPlot(globals.min_wavelength, globals.max_wavelength, None, "Wavelength (nm)", "Counts (#)")

            ttl_on(globals.dev_handle)
            QtTest.QTest.qWait(100)

            while True:
                if globals.stopscanning:
                    break
                self.measureScope()
                self.plot(globals.wavelength, globals.spectraldata)
                time.sleep(0.01)

            ttl_off(globals.dev_handle)
            QtTest.QTest.qWait(100)

            ret = AVS_StopMeasure(globals.dev_handle)

        elif len(globals.referencedata) > 0:
            wl_range = [0, 0]
            y_label = ""
            measurement_func = self.measureAbs

            if self.measurement_mode == "Absorbance":
                wl_range = [0, 3]
                y_label = "Absorbance"
                measurement_func = self.measureAbs

            elif self.measurement_mode == "Transmittance":
                wl_range = [0, 110]
                y_label = "Transmittance"
                measurement_func = self.measureTransmittance

            self.initPlot(globals.min_wavelength, globals.max_wavelength, wl_range, "Wavelength (nm)", y_label)

            globals.solenoid_open_timers = readShutterTimers()

            cumulative_time = 0

            for open_timer in globals.solenoid_open_timers:
                for mount_id, pos in globals.mount_default_angles.items():
                    tlab.set_rotation_mount_pos(mount_id, pos)

                tlab.open_shutter("68250034")
                QtTest.QTest.qWait(open_timer * 1000)
                cumulative_time += open_timer
                tlab.close_shutter("68250034")

                for pos_combination_id, pos_combination in globals.mount_position_combinations.items():
                    for mount_id, position in pos_combination.items():
                        tlab.set_rotation_mount_pos(mount_id, int(position))

                    ttl_on(globals.dev_handle)
                    QtTest.QTest.qWait(100)

                    output_spectra = measurement_func(globals.referencedata[pos_combination_id])

                    ttl_off(globals.dev_handle)
                    QtTest.QTest.qWait(100)

                    ret = AVS_StopMeasure(globals.dev_handle)

                    saveToNewFile(f"{self.file_name_to_save}_{cumulative_time}s_{pos_combination_id}",
                                  f"Results_{y_label}", globals.wavelength, output_spectra)

                    self.plot(globals.wavelength, output_spectra)
                    self.repaint()
                    time.sleep(0.01)

            self.StopMeasBtn_clicked()

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

            self.open_shutter_for = timer() - self.timer_start
            tlab.close_shutter("68250034")

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

    def saveFile_changed(self):
        self.file_name_to_save = self.fileNameEdit.currentText()



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
