# ---------------- Standard library imports ----------------
import os
import sys
import time
import math
from itertools import product
from collections import defaultdict

# ---------------- Third-party imports ----------------
from dotenv import load_dotenv
from PyQt6 import uic, QtTest
from PyQt6.QtCore import QThread, QWaitCondition, QMutex, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox
import pyqtgraph as pg

# ---------------- .NET / Thorlabs imports ----------------
import clr

# Load environment variables
load_dotenv()
PROJECT_PATH = os.environ["PROJECT_PATH"]
TLABPATH = os.environ["THORLABS_PATH"]

# Add references to required DLLs
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.IntegratedStepperMotorsCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.KCube.SolenoidCLI.dll")

# Import only required classes/functions from DLLs
from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import *
from Thorlabs.MotionControl.KCube.SolenoidCLI import *
from System import Decimal

# ---------------- Local module imports ----------------

# Avaspec: only import what's used in AvaspecController
from avaspec import (
    AVS_Init, AVS_GetNrOfDevices, AVS_GetList, AVS_Activate,
    AVS_GetParameter, AVS_GetLambda, AVS_UseHighResAdc,
    AVS_PrepareMeasure, AVS_Measure, AVS_PollScan,
    AVS_GetScopeData, AVS_StopMeasure, AVS_SetDigOut,
    AvsIdentityType, DeviceConfigType, MeasConfigType
)


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
        self.avg_num = 1
        self.min_wavelength = 300
        self.max_wavelength = 700
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

        save_to_new_file(f"reference_{combo_id}", "ref", self.wavelength, reference_data)

        return self.wavelength, reference_data

    def save_dark(self):
        self.ttl_off()
        time.sleep(0.001)

        self.measure_scope()
        self.darkdata = self.spectraldata

        save_to_new_file(f"reference_dark", "ref", self.wavelength, self.darkdata)

        return self.wavelength, self.darkdata

    def measure_scope(self, ref_id=""):
        ret = AVS_UseHighResAdc(self.dev_handle, True)
        measconfig = MeasConfigType()
        measconfig.m_StartPixel = 0
        measconfig.m_StopPixel = self.pixels - 1
        measconfig.m_IntegrationTime = self.int_time
        measconfig.m_IntegrationDelay = 0
        measconfig.m_NrAverages = self.avg_num
        measconfig.m_CorDynDark_m_Enable = 0  # nesting of types does NOT work!!
        measconfig.m_CorDynDark_m_ForgetPercentage = 0
        measconfig.m_Smoothing_m_SmoothPix = self.smoothing
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
        ret = AVS_PrepareMeasure(self.dev_handle, measconfig)
        nummeas = 1  # Performs only a single measurement

        ret = AVS_Measure(self.dev_handle, 0, nummeas)
        dataready = False
        while not dataready:
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

    def update_params(self, new_params):
        if len(new_params) != 4:
            return

        self.int_time = new_params[0]
        self.avg_num = new_params[1]
        self.min_wavelength = new_params[2]
        self.max_wavelength = new_params[3]


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

    def update_mount_positions(self, dev_id, new_positions):
        self.rotation_mount_positions[dev_id] = new_positions

    def update_mount_position_combos(self, combo_id, combo_dict):
        self.mount_position_combos[combo_id] = combo_dict

    def update_mount_default_angle(self, dev_id, new_angle):
        self.mount_default_angles[dev_id] = new_angle


# ------------------- WORKER THREAD ------------------- #

class MeasurementWorker(QThread):
    data_ready = pyqtSignal(list, list)
    measurement_finished = pyqtSignal()

    def __init__(self, avaspec: AvaspecController, thorlabs: ThorlabsController,
                 measurement_mode="Scope", measurement_type="Single", filename="result"):
        super().__init__()
        self.avaspec = avaspec
        self.thorlabs = thorlabs
        self.measurement_mode = measurement_mode
        self.measurement_type = measurement_type
        self.filename = filename
        self.running = True
        self.paused = False
        self.pause_cond = QWaitCondition()
        self.mutex = QMutex()

    def run(self):
        measurement_func = self.avaspec.measure_scope
        if self.measurement_mode == "Absorbance":
            measurement_func = self.avaspec.measure_absorbance
        elif self.measurement_mode == "Transmittance":
            measurement_func = self.avaspec.measure_transmittance
        else:
            measurement_func = self.avaspec.measure_scope

        if self.measurement_type == "Continuous":
            self.run_continuous(measurement_func)
        elif self.measurement_type == "Series":
            self.run_series(measurement_func)
        elif self.measurement_type == "Reference":
            self.run_reference()
        else:
            self.run_single(measurement_func)

    def run_single(self, meas_function):
        self.avaspec.ttl_on()
        QtTest.QTest.qWait(100)

        wl, data = meas_function()
        self.data_ready.emit(wl, data)
        time.sleep(0.01)

        self.avaspec.ttl_off()
        QtTest.QTest.qWait(100)

        self.measurement_finished.emit()

    def run_continuous(self, meas_function):
        self.avaspec.ttl_on()
        QtTest.QTest.qWait(100)

        while self.running:
            wl, data = meas_function()
            self.data_ready.emit(wl, data)
            time.sleep(0.01)

        self.avaspec.ttl_off()
        QtTest.QTest.qWait(100)

    def run_series(self, meas_function):
        self.thorlabs.solenoid_open_timers = read_shutter_timers()

        cumulative_time = 0

        for t in self.thorlabs.solenoid_open_timers:
            if not self.running:
                break
            self.wait_if_paused()

            """ #0 Setting default rotation mount positions in preparation for illumination """
            for mount_id, pos in self.thorlabs.mount_default_angles.items():
                self.thorlabs.set_mount_pos(mount_id, pos)

            """ #1 Sample illumination """
            self.thorlabs.open_shutter("68250034")
            for i in range(int(t * 10)):
                if not self.running:
                    break
                if self.paused:
                    self.thorlabs.close_shutter("68250034")
                self.wait_if_paused()
                if not self.paused:
                    self.thorlabs.open_shutter("68250034")
                QtTest.QTest.qWait(t * 100)
            self.thorlabs.close_shutter("68250034")

            cumulative_time += t

            for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():
                """ #2 Setting rotation mount positions for measurement """
                for mount_id, position in pos_combination.items():
                    self.thorlabs.set_mount_pos(mount_id, int(position))

                """ #3 Measurement """
                self.avaspec.ttl_on()
                QtTest.QTest.qWait(100)

                wl, data = meas_function(pos_combination_id)

                self.avaspec.ttl_off()
                QtTest.QTest.qWait(100)

                save_to_new_file(f"{self.filename}_{cumulative_time}s_{pos_combination_id}",
                              f"Results_{self.measurement_mode}", wl, data)

                self.data_ready.emit(wl, data)

        self.measurement_finished.emit()

    def run_reference(self):
        for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():
            for mount_id, position in pos_combination.items():
                self.thorlabs.set_mount_pos(mount_id, int(position))

            wl, data = self.avaspec.save_reference(pos_combination_id)

            self.data_ready.emit(wl, data)

        self.measurement_finished.emit()

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

main_ui_class, main_baseclass = uic.loadUiType("main_window.ui")
class MainWindow(main_ui_class, main_baseclass):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avaspec / Thorlabs Automation thing")

        # Initializing device controllers
        self.avaspec = AvaspecController()
        self.thorlabs = ThorlabsController()
        self.measurement_thread = None
        self.paused = False

        # Connecting action triggers from the window selection bar to show/hide the specified setting windows
        self.ava_settings_window = AvaSettingWindow()
        self.actionAvasoft.triggered.connect(
            lambda checked: self.toggle_window(self.ava_settings_window)
        )
        self.ava_settings_window.settings_changed.connect(self.avaspec.update_params)
        self.actionAvasoft.setEnabled(False)

        self.mount_settings_window = RotationMountSettingWindow()
        self.actionRotation_Mount.triggered.connect(
            lambda checked: self.toggle_window(self.mount_settings_window)
        )
        self.mount_settings_window.settings_changed.connect(self.thorlabs.update_mount_position_combos)
        self.actionRotation_Mount.setEnabled(False)

        # Initializing button states
        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(False)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)

        # Connecting button events to methods
        self.StartMeasBtn.clicked.connect(self.start_measurement_btn_clicked)
        self.PauseMeasBtn.clicked.connect(self.pause_measurement_btn_clicked)
        self.StopMeasBtn.clicked.connect(self.stop_measurement_btn_clicked)
        self.SaveRefBtn.clicked.connect(self.save_ref_btn_clicked)
        self.SaveDrkBtn.clicked.connect(self.save_dark_btn_clicked)
        self.connectAvasoft.triggered.connect(self.open_comm_btn_clicked)
        self.connectThorlabs.triggered.connect(self.connect_thorlabs_btn_clicked)
        self.fileNameEdit.textChanged.connect(self.save_file_changed)

        self.testRotBtn.clicked.connect(self.change_positions)
        self.testShutterBtn.clicked.connect(self.toggle_shutter)

        # Initializing data plotting
        self.line = None
        self.graph.setBackground("w")
        self.init_plot(None, None, None, "", "")

        self.file_name_to_save = ""

    def closeEvent(self, event):
        """
        Called right before the program is shut down - ensures that all thorlabs devices will be disconnected
        properly. Causes issues with later connectivity otherwise.
        """
        self.stop_measurement_btn_clicked()
        self.thorlabs.disconnect_all()
        event.accept()

    @pyqtSlot()
    def toggle_window(self, window):
        if window.isVisible():
            window.hide()
        else:
            window.show()

    @pyqtSlot()
    def change_positions(self):
        dev_id = "55360064"
        pos_list = self.thorlabs.rotation_mount_positions.get(dev_id)

        if pos_list is None:
            print("Error")
            return

        for pos in pos_list:
            self.thorlabs.set_mount_pos(dev_id, pos)

    @pyqtSlot()
    def toggle_shutter(self):
        self.testShutterBtn.setEnabled(False)
        self.thorlabs.solenoid_open_timers = read_shutter_timers()

        for shutter_open_for in self.thorlabs.solenoid_open_timers:
            self.thorlabs.open_shutter("68250034")
            print(shutter_open_for)
            QtTest.QTest.qWait(shutter_open_for*1000)
            self.thorlabs.close_shutter("68250034")

        self.testShutterBtn.setEnabled(True)

    @pyqtSlot()
    def open_comm_btn_clicked(self):
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
    def connect_thorlabs_btn_clicked(self):
        msg = self.thorlabs.connect_devices()
        QMessageBox.information(self, msg[0], msg[1])

        if msg[0] == "Error":
            return
        else:
            for dev_id, devive in self.thorlabs.device_list.items():
                if dev_id[:2] == "55":
                    mount = self.mount_settings_window.add_tab(dev_id)
                    mount.home_mount_signal.connect(self.thorlabs.home_mount)
                    mount.update_mount_default_angles.connect(self.thorlabs.update_mount_default_angle)
                    mount.update_mount_positions.connect(self.thorlabs.update_mount_positions)

            self.connectThorlabs.setEnabled(False)
            self.actionRotation_Mount.setEnabled(True)

    @pyqtSlot()
    def start_measurement_btn_clicked(self):
        """
        Main method for running all measurements depending on the mode selected.

        :return:
        """

        measurement_mode = self.SelectModeBox.currentText()
        measurement_type = self.SelectTypeBox.currentText()

        self.ava_settings_window.hide()

        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(False)
        self.SelectTypeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        if measurement_mode == "Absorbance":
            y_lim = [0, 3]
        elif measurement_mode == "Transmittance":
            y_lim = [0, 110]
        else:
            y_lim = None

        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, y_lim,
                       "Wavelength (nm)", measurement_mode)

        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop()

        self.measurement_thread = MeasurementWorker(self.avaspec, self.thorlabs,
                                                    measurement_mode, measurement_type,
                                                    self.file_name_to_save)

        self.measurement_thread.data_ready.connect(self.plot)
        self.measurement_thread.measurement_finished.connect(self.stop_measurement_btn_clicked)
        self.measurement_thread.start()

    @pyqtSlot()
    def pause_measurement_btn_clicked(self):
        if not self.measurement_thread:
            return
        if self.paused:
            self.measurement_thread.resume()
            self.paused = False
            self.PauseMeasBtn.setText("Pause Measurement")
        else:
            self.measurement_thread.pause()
            self.paused = True
            self.PauseMeasBtn.setText("Continue Measurement")

    @pyqtSlot()
    def stop_measurement_btn_clicked(self):
        """
        Completely stops all ongoing measurements as well as RH changes

        :return:
        """
        if self.measurement_thread:
            self.measurement_thread.stop()

        self.PauseMeasBtn.setText("Pause Measurement")

        self.StartMeasBtn.setEnabled(True)
        self.PauseMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(False)
        self.SaveRefBtn.setEnabled(True)
        self.SaveDrkBtn.setEnabled(True)
        self.SelectModeBox.setEnabled(True)
        self.SelectTypeBox.setEnabled(True)
        self.menuBar.setEnabled(True)

    @pyqtSlot()
    def save_ref_btn_clicked(self):
        """
        Saves and plots reference spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """
        self.ava_settings_window.hide()

        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(False)
        self.SelectTypeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, None,
                       "Wavelength (nm)", "Scope")

        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop()

        self.measurement_thread = MeasurementWorker(self.avaspec, self.thorlabs,
                                                    "Scope", "Reference",
                                                    self.file_name_to_save)
        self.measurement_thread.measurement_finished.connect(self.stop_measurement_btn_clicked)
        self.measurement_thread.start()

    @pyqtSlot()
    def save_dark_btn_clicked(self):
        """
        Saves and plots dark spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """
        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, None,
                       "Wavelength (nm)", "Scope")

        wl, data = self.avaspec.save_dark()
        self.plot(wl, data)

    @pyqtSlot()
    def init_plot(self, min_x, max_x, yrange, x_label, y_label):
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

        pen = pg.mkPen(color=(0, 0, 0), width=1.1, style=Qt.PenStyle.SolidLine)
        self.graph.setLabel("left", f"{y_label}")
        self.graph.setLabel("bottom", f"{x_label}")
        if max_x:
            self.graph.setXRange(min_x, max_x)
        if yrange:
            self.graph.setYRange(yrange[0], yrange[1])
        self.graph.showGrid(x=True, y=True)

        self.line = self.graph.plot([0], [0], pen=pen)

    @pyqtSlot()
    def plot(self, x, y):
        self.line.setData(x, y)
        self.repaint()

    @pyqtSlot()
    def update_plot_range(self, min_x, max_x):
        self.graph.setXRange(min_x, max_x)

    def save_file_changed(self):
        self.file_name_to_save = self.fileNameEdit.text()


# -------------------- SETTING WINDOWS ---------------- #

ava_ui_class, ava_baseclass = uic.loadUiType("ava_settings_window.ui")
class AvaSettingWindow(ava_ui_class, ava_baseclass):
    settings_changed = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avasoft 8 Settings")

        self.IntTime.valueChanged.connect(self.parameter_changed)
        self.NumAvg.valueChanged.connect(self.parameter_changed)
        self.MinWavelength.valueChanged.connect(self.parameter_changed)
        self.MaxWavelength.valueChanged.connect(self.parameter_changed)

    def parameter_changed(self):
        int_time = self.IntTime.value()
        avg_num = self.NumAvg.value()
        min_wavelength = self.MinWavelength.value()
        max_wavelength = self.MaxWavelength.value()

        self.settings_changed.emit([int_time, avg_num, min_wavelength, max_wavelength])


rotation_mount_widget_class, rotation_mount_widget_baseclass = uic.loadUiType("rotation_mount_settings_widget.ui")
class RotationMountWidget(rotation_mount_widget_class, rotation_mount_widget_baseclass):
    update_mount_positions = pyqtSignal(str, list)
    update_mount_default_angles = pyqtSignal(str, int)
    home_mount_signal = pyqtSignal(str)

    def __init__(self, device_id):
        super().__init__()
        self.setupUi(self)

        self.StartPos.valueChanged.connect(self.position_params_changed)
        self.EndPos.valueChanged.connect(self.position_params_changed)
        self.RotationStep.valueChanged.connect(self.position_params_changed)
        self.DefaultAngle.valueChanged.connect(self.default_angle_changed)
        self.HomeDevBtn.clicked.connect(self.home_device)

        self.device_id = device_id
        self.pos_list = []
        self.update_positions()

    def update_positions(self):
        min_pos = int(self.StartPos.value())
        max_pos = int(self.EndPos.value())
        pos_interval = int(self.RotationStep.value())

        self.pos_list.clear()
        for pos in range(min_pos, max_pos, pos_interval):
            self.pos_list.append(pos)

    def position_params_changed(self):
        self.update_positions()
        self.update_mount_positions.emit(self.device_id, self.pos_list)

    def default_angle_changed(self):
        new_angle = int(self.DefaultAngle.value())
        self.update_mount_default_angles.emit(self.device_id, new_angle)

    def home_device(self):
        self.home_mount_signal.emit(self.device_id)


rotation_mount_ui_class, rotation_mount_baseclass = uic.loadUiType("rotation_mount_settings_window.ui")
class RotationMountSettingWindow(rotation_mount_ui_class, rotation_mount_baseclass):
    settings_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Thorlabs Rotation Mount Settings")

        self.tabs = dict()

    @pyqtSlot()
    def add_tab(self, dev_id):
        new_rotation_mount = RotationMountWidget(dev_id)
        self.tabs[dev_id] = new_rotation_mount
        self.RotationMountSelection.addTab(new_rotation_mount, f"{dev_id}")
        new_rotation_mount.update_mount_positions.connect(self.calculate_pos_combinations)

        return new_rotation_mount

    def calculate_pos_combinations(self, dev_id, pos_list):
        # Creating unique identifiers for every position of each mount
        all_rotation_mount_positions = list()
        for dev_id, mount in self.tabs.items():
            pos_ids = list()
            for pos in mount.pos_list:
                pos_ids.append(f"{dev_id}_{pos}")
            all_rotation_mount_positions.append(pos_ids)

        mount_position_combinations = defaultdict(dict)

        for unique_pos_combination in product(*all_rotation_mount_positions):
            pos_combination_id = ""
            pos_combination = dict()

            for i in unique_pos_combination:
                mount_id = i.split('_')[0]
                pos = i.split('_')[1]
                pos_combination[mount_id] = pos
                pos_combination_id += f"{pos}_"

            mount_position_combinations[pos_combination_id] = pos_combination

        self.settings_changed.emit(mount_position_combinations)
  

# --------------- FILE HANDLING ----------------------#      
        
        
def save_to_new_file(file_name, folder, x, y):
    """
    Saves a list of values to a new file --> overwrites an existing file of the name.

    :param file_name: str, creates a .txt file with this name and saves the spectrum data to it
    :param folder: str, folder to save data to
    :param x [float], input list of spectrum values to save
    :param y [float], input list of time/wavelength values corresponding to spectrum values
    :return:
    """

    complete_file_path = os.path.join(PROJECT_PATH, folder)

    if not os.path.exists(f"{complete_file_path}"):
        os.makedirs(f"{complete_file_path}")

    try:
        with open(f"{complete_file_path}\\{file_name}.txt", "w") as fh:
            for n in range(len(y)):
                fh.write(f"{x[n]:.1f}\t{y[n]}\n")
    except IndexError:
        return


def read_shutter_timers():
    file_output = []

    complete_file_path = os.path.join(PROJECT_PATH, "shutter_timer.txt")
    if not os.path.exists(complete_file_path):
        return []

    try:
        with open(f"{complete_file_path}", "r") as fh:
            for line in fh:
                file_output.append(int(line.strip()))

        return file_output

    except ValueError:
        return []


# ---------------------- MAIN ---------------------- #

def main():
    # Initializing the PyQt application window
    app = QApplication(sys.argv)
    app.lastWindowClosed.connect(app.quit)
    window = MainWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    main()
