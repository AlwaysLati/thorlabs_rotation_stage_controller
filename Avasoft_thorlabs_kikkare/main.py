# ---------------- Standard library imports ----------------
# Importing built-in Python modules used throughout the program
import os
import sys
import time
import math
from itertools import product
from collections import defaultdict

# ---------------- Third-party imports ----------------
# External libraries required for GUI, plotting, and environment handling
from dotenv import load_dotenv
from PyQt6 import uic, QtTest
from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
import pyqtgraph as pg

# ---------------- .NET / Thorlabs imports ----------------
# "clr" enables interaction with .NET assemblies (required for Thorlabs devices)
import clr

# Load environment variables from .env file
load_dotenv()
PROJECT_PATH = os.environ.get("PROJECT_PATH")
if not PROJECT_PATH:
    raise RuntimeError("PROJECT_PATH not set in environment or .env")

TLABPATH = os.environ.get("THORLABS_PATH")
if not TLABPATH:
    raise RuntimeError("THORLABS_PATH not set in environment or .env")

# Add references to .NET DLLs for Thorlabs device communication
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.IntegratedStepperMotorsCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.KCube.SolenoidCLI.dll")

# Importing .NET classes relating to motion and device control
from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import *
from Thorlabs.MotionControl.KCube.SolenoidCLI import *
from System import Decimal

# ---------------- Local module imports ----------------
# Importing Avaspec spectrometer control functions from the local avaspec module
from avaspec import (
    AVS_Init, AVS_GetNrOfDevices, AVS_GetList, AVS_Activate,
    AVS_GetParameter, AVS_GetLambda, AVS_UseHighResAdc,
    AVS_PrepareMeasure, AVS_Measure, AVS_PollScan,
    AVS_GetScopeData, AVS_StopMeasure, AVS_SetDigOut,
    AvsIdentityType, DeviceConfigType, MeasConfigType
)

# ---------------- Global constants --------------------
MOUNT_PREFIX = "55"
SOLENOID_PREFIX = "68"
POLARIZER_MOUNT_ID = "55360064"
STAGE_MOUNT_ID = "55536954"
SOLENOID_ID = "68250034"

# ----------------- DEVICE CONTROLLERS ----------------- #

class AvaspecController:
    """Controls the Avaspec spectrometer device."""

    def __init__(self):
        """Initialize default configuration and data buffers."""
        # Spectrometer handle and data buffers
        self.dev_handle = 0
        self.pixels = 4096
        self.wavelength_full = [0.0] * 4096
        self.wavelength = [0.0] * 4096
        self.spectraldata = [0.0] * 4096
        self.darkdata = [0.0] * 4096
        self.referencedata = dict({"": [0.0] * 4096})  # Stores reference spectra by ID

        # Measurement parameters
        self.int_time = 5
        self.avg_num = 1
        self.min_wavelength = 300
        self.max_wavelength = 700
        self.smoothing = 3
        self.dynamic_dark = 1
        self.stopscanning = True

    def connect_device(self):
        """
        Connects to the first available Avaspec spectrometer.
        Returns the serial number if successful, 0 otherwise.
        """
        ret = AVS_Init(0)  # Initialize USB communication
        ret = AVS_GetNrOfDevices()  # Count available devices
        mylist = AVS_GetList(1)  # Get device list (first device only)

        # Attempt to read device serial number
        try:
            serial_number = str(mylist[0].SerialNumber.decode("utf-8"))
        except IndexError:
            return 0  # No device found

        # Activate device and retrieve wavelength/pixel info
        self.dev_handle = AVS_Activate(mylist[0])
        devcon = DeviceConfigType()
        devcon = AVS_GetParameter(self.dev_handle, 63484)
        self.pixels = devcon.m_Detector_m_NrPixels   # Set actual number of pixels

        # Retrieve full wavelength calibration
        self.wavelength_full = AVS_GetLambda(self.dev_handle)

        return serial_number

    def save_reference(self, combo_id=""):
        """Captures a reference spectrum and saves it."""
        self.ttl_on()  # Turn illumination on
        time.sleep(0.1)

        self.measure_scope()  # Perform measurement

        self.ttl_off()
        time.sleep(0.1)

        reference_data = self.spectraldata
        self.referencedata[combo_id] = reference_data  # Store reference

        # Save to file
        save_to_new_file(f"reference_{combo_id}", "ref", self.wavelength, reference_data)

        return self.wavelength, reference_data

    def save_dark(self):
        """Captures and saves dark current measurement."""
        self.ttl_off()
        QtTest.QTest.qWait(100)

        self.measure_scope()  # Capture dark data
        self.darkdata = self.spectraldata

        save_to_new_file(f"reference_dark", "ref", self.wavelength, self.darkdata)

        return self.wavelength, self.darkdata

    def measure_scope(self, ref_id=""):
        """
        Performs a single scope measurement (raw spectral intensity).
        """

        # Enable high-resolution ADC
        ret = AVS_UseHighResAdc(self.dev_handle, True)

        # Configure measurement parameters
        measconfig = MeasConfigType()
        measconfig.m_StartPixel = 0
        measconfig.m_StopPixel = self.pixels - 1
        measconfig.m_IntegrationTime = self.int_time
        measconfig.m_IntegrationDelay = 0
        measconfig.m_NrAverages = self.avg_num
        measconfig.m_CorDynDark_m_Enable = self.dynamic_dark  # nesting of types does NOT work!!
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

        # Prepare spectrometer for measurement
        ret = AVS_PrepareMeasure(self.dev_handle, measconfig)
        nummeas = 1  # Performs only a single measurement

        # Trigger measurement
        ret = AVS_Measure(self.dev_handle, 0, nummeas)
        dataready = False

        # Poll device until data is ready
        while not dataready:
            dataready = AVS_PollScan(self.dev_handle)
            time.sleep(0.001)

        # Retrieve spectrum
        timestamp, data = AVS_GetScopeData(self.dev_handle)
        AVS_StopMeasure(self.dev_handle)

        # Filter spectrum to desired wavelength range
        self.spectraldata = [d for wl, d in zip(self.wavelength_full, data)
                             if self.min_wavelength < wl < self.max_wavelength]
        self.wavelength = [wl for wl in self.wavelength_full
                           if self.min_wavelength < wl < self.max_wavelength]

        return self.wavelength, self.spectraldata

    def measure_absorbance(self, ref_id=""):
        """
        Computes absorbance spectrum using:
            A = -log10( (Sample - Dark) / (Reference - Dark) )
        """
        if ref_id == "":
            ref_id = next(iter(self.referencedata))

        ref = self.referencedata.get(ref_id)
        if ref is None:
            return

        self.measure_scope()

        # Absorbance formula from Avasoft 8 documentation
        try:
            abs_spectra = [-math.log10((s - d) / (r - d)) for r, s, d in
                           zip(ref, self.spectraldata, self.darkdata)]
        except (ValueError, ZeroDivisionError):  # Catches any errors and returns a list full of zeros
            abs_spectra = [0.0] * len(self.spectraldata)

        return self.wavelength, abs_spectra

    def measure_transmittance(self, ref_id=""):
        """
        Computes transmittance spectrum using:
            T (%) = 100 * (Sample - Dark) / (Reference - Dark)
        """
        if ref_id == "":
            ref_id = next(iter(self.referencedata))

        ref = self.referencedata.get(ref_id)
        if ref is None:
            return

        self.measure_scope()

        # Absorbance formula from Avasoft 8 documentation
        try:
            trans_spectra = [100 * ((s - d) / (r - d)) for r, s, d in zip(ref, self.spectraldata, self.darkdata)]
        except (ValueError, ZeroDivisionError):  # Catches any errors and returns a list full of zeros
            trans_spectra = [100.0] * len(self.spectraldata)

        return self.wavelength, trans_spectra

    def ttl_on(self):
        """Sets digital output high to activate illumination."""
        ret = AVS_SetDigOut(self.dev_handle, 3, 1)
        if ret < 0:
            raise RuntimeError(f"AVS_SetDigOut returned {ret}")
        return ret

    def ttl_off(self):
        """Sets digital output low to disable illumination."""
        ret = AVS_SetDigOut(self.dev_handle, 3, 0)
        if ret < 0:
            raise RuntimeError(f"AVS_SetDigOut returned {ret}")
        return ret

    def update_params(self, new_params):
        """Updates integration time, averaging number, and wavelength limits."""
        if len(new_params) != 6:
            return

        self.int_time = new_params[0]
        self.avg_num = new_params[1]
        self.min_wavelength = new_params[2]
        self.max_wavelength = new_params[3]
        self.smoothing = new_params[4]
        self.dynamic_dark = new_params[5]


class ThorlabsController:
    """Handles connection and control of Thorlabs rotation mounts and solenoids."""

    def __init__(self):
        """Initialize device states and parameter storage."""
        self.device_list = dict()  # Maps serial numbers to device objects
        self.rotation_mount_positions = defaultdict(list)  # "device_id" : [position]
        self.mount_position_combos = defaultdict(dict)  # "combo_id" : dict("device_id" : [position])
        self.mount_default_angles = dict()
        self.solenoid_open_timers = list()

    def connect_devices(self):
        """
        Connects to all Thorlabs devices and categorizes them by type.
        Returns status message.
        """
        try:
            # Initialize device list.
            DeviceManagerCLI.BuildDeviceList()
            serial_numbers = DeviceManagerCLI.GetDeviceList()

            if len(serial_numbers) == 0:
                return ["Error", "No devices found"]

            for serial_no in serial_numbers:
                device_type = serial_no[:2]

                if device_type == MOUNT_PREFIX:  # Integrated stepper driven rotation stage
                    self.connect_mount(serial_no)

                elif device_type == SOLENOID_PREFIX:  # K-Cube solenoid Driver
                    self.connect_solenoid(serial_no)

                else:
                    return ["Error", "Unknown device found"]

            return ["Info", f"Connected to {len(serial_numbers)} Thorlabs devices"]

        except Exception as e:
            print(e)
            self.disconnect_all()
            return ["Error", f"{e}"]

    def connect_mount(self, serial_no):
        """Initializes and configures a Thorlabs rotation mount."""
        device = CageRotator.CreateCageRotator(serial_no)
        device.Connect(serial_no)

        # Ensure settings loaded
        if not device.IsSettingsInitialized():
            device.WaitForSettingsInitialized(10000)  # 10 second timeout.
            assert device.IsSettingsInitialized() is True

        # Start communication polling
        device.StartPolling(250)  # 250ms polling rate.
        time.sleep(0.25)
        device.EnableDevice()
        time.sleep(0.25)  # Wait for device to enable.

        # Load config from device file
        device.LoadMotorConfiguration(serial_no, DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings)

        self.device_list[serial_no] = device

    def connect_solenoid(self, serial_no):
        """Initializes a Thorlabs KCube solenoid controller."""
        device = KCubeSolenoid.CreateKCubeSolenoid(serial_no)
        device.Connect(serial_no)

        # Ensure settings loaded
        if not device.IsSettingsInitialized():
            device.WaitForSettingsInitialized(10000)  # 10 second timeout.
            assert device.IsSettingsInitialized() is True

        # Start polling loop and enable device.
        device.StartPolling(250)  # 250ms polling rate.
        time.sleep(0.25)
        device.EnableDevice()
        time.sleep(0.25)  # Wait for device to enable.

        # Set manually controlled mode
        device.SetOperatingMode(SolenoidStatus.OperatingModes.Manual)

        self.device_list[serial_no] = device

    def disconnect_all(self):
        """Safely disconnects all connected Thorlabs devices."""
        for device_id, device in self.device_list.items():
            try:
                if device_id[:2] == MOUNT_PREFIX:
                    device.StopImmediate()
                device.StopPolling()
                device.Disconnect()
                time.sleep(0.25)

            except Exception as e:
                print(e)
        return

    def toggle_shutter(self, serial_no):
        """Toggles solenoid shutter on/off."""
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != SOLENOID_PREFIX:
            return

        state = device.GetOperatingState()
        if state == SolenoidStatus.OperatingStates.Active:
            device.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)
        else:
            device.SetOperatingState(SolenoidStatus.OperatingStates.Active)

    def open_shutter(self, serial_no):
        """Opens solenoid shutter."""
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != SOLENOID_PREFIX:
            return

        device.SetOperatingState(SolenoidStatus.OperatingStates.Active)
        time.sleep(0.25)

    def close_shutter(self, serial_no):
        """Closes solenoid shutter."""
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != SOLENOID_PREFIX:
            return

        device.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)
        time.sleep(0.25)

    def home_mount(self, serial_no):
        """Homes a rotation mount to its reference position."""
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != MOUNT_PREFIX:
            return ["Error", "Unable to home device"]

        try:
            # 60 second timeout, function will wait until the move completes
            # or the timeout elapses, whichever comes first.
            device.Home(60000)
            return ["Info", "Homed device"]

        except Exception as e:
            print(e)
            return ["Error", "Unable to home device"]

    def set_mount_pos(self, serial_no, new_pos):
        """Moves a rotation mount to a specific angle."""
        device = self.device_list.get(serial_no)

        if device is None or serial_no[:2] != MOUNT_PREFIX:
            return

        try:
            pos = Decimal(new_pos)  # Must be a .NET decimal.
            device.MoveTo(pos, 60000)  # 60 second timeout.

        except Exception as e:
            print(e)

    def update_mount_positions(self, dev_id, new_positions):
        """Stores rotation mount position list for later automation."""
        self.rotation_mount_positions[dev_id] = new_positions

    def update_mount_position_combos(self, combos_dict):
        """Stores all mount combinations for automated measurements."""
        self.mount_position_combos = combos_dict

    def update_mount_default_angle(self, dev_id, new_angle):
        """Sets default pre-measurement angle for mount."""
        self.mount_default_angles[dev_id] = new_angle


# ------------------- WORKER THREAD ------------------- #

class MeasurementWorker(QThread):
    """
    Runs measurement operations in the background so the UI remains responsive.
    """
    data_ready = pyqtSignal(list, list)  # Emitted after each measurement
    measurement_finished = pyqtSignal()  # Emitted when measurement ends

    def __init__(self, avaspec: AvaspecController, thorlabs: ThorlabsController,
                 measurement_mode="Scope", measurement_type="Single", filename="result"):
        super().__init__()
        self.avaspec = avaspec
        self.thorlabs = thorlabs
        self.measurement_mode = measurement_mode
        self.measurement_type = measurement_type
        self.filename = filename

        # Thread control flags
        self.running = True
        self.paused = False
        self.pause_cond = QWaitCondition()
        self.mutex = QMutex()

    def run(self):
        """Main thread entry point. Chooses measurement type to execute."""
        # Select correct measurement function
        if self.measurement_mode == "Absorbance":
            measurement_func = self.avaspec.measure_absorbance
        elif self.measurement_mode == "Transmittance":
            measurement_func = self.avaspec.measure_transmittance
        else:
            measurement_func = self.avaspec.measure_scope

        # Choose how measurement will run
        if self.measurement_type == "Continuous":
            self.run_continuous(measurement_func)
        elif self.measurement_type == "Series":
            self.run_series(measurement_func)
        elif self.measurement_type == "Reference":
            self.run_reference()
        else:
            self.run_single(measurement_func)

    def run_single(self, meas_function):
        """Runs one single measurement cycle."""
        self.avaspec.ttl_on()
        time.sleep(0.1)

        wl, data = meas_function()
        self.data_ready.emit(wl, data)  # Send data to UI
        time.sleep(0.01)

        self.avaspec.ttl_off()
        time.sleep(0.1)

        self.measurement_finished.emit()

    def run_continuous(self, meas_function):
        """Continuously measures until stopped."""
        self.avaspec.ttl_on()
        time.sleep(0.1)

        while self.running:
            self.wait_if_paused()
            wl, data = meas_function()
            self.data_ready.emit(wl, data)
            time.sleep(0.01)

        self.avaspec.ttl_off()
        time.sleep(0.1)

    def run_series(self, meas_function):
        """
        Runs multistep automated measurements:
        1. Open shutter for timed illumination
        2. Change rotation mount positions
        3. Measure & save at each configuration
        """
        self.thorlabs.solenoid_open_timers = read_shutter_timers()

        cumulative_time = 0

        for t in self.thorlabs.solenoid_open_timers:
            if not self.running:
                break
            self.wait_if_paused()

            # 0) Move mounts to default illumination positions
            for mount_id, pos in self.thorlabs.mount_default_angles.items():
                self.thorlabs.set_mount_pos(mount_id, pos)

            # 1) Illuminate sample for duration t
            self.thorlabs.open_shutter(SOLENOID_ID)
            elapsed = 0.0
            step = 0.1
            while elapsed < t and self.running:
                if self.paused:
                    self.thorlabs.close_shutter(SOLENOID_ID)
                    self.wait_if_paused()
                    # when resume returns, reopen shutter
                    if not self.running:
                        break
                    self.thorlabs.open_shutter(SOLENOID_ID)
                time.sleep(step)
                elapsed += step
            self.thorlabs.close_shutter(SOLENOID_ID)

            cumulative_time += t

            # 2) Iterate through all mount combinations and measure
            for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():
                if not self.running:
                    break
                self.wait_if_paused()

                # Move mounts to new positions
                for mount_id, position in pos_combination.items():
                    if not self.running:
                        break
                    self.wait_if_paused()
                    self.thorlabs.set_mount_pos(mount_id, int(position))

                # 3) Perform measurement
                self.avaspec.ttl_on()
                time.sleep(0.1)

                wl, data = meas_function(pos_combination_id)

                self.avaspec.ttl_off()
                time.sleep(0.1)

                # Save result
                save_to_new_file(f"{self.filename}_{cumulative_time}s_{pos_combination_id}",
                              f"Results_{self.measurement_mode}", wl, data)

                self.data_ready.emit(wl, data)

        self.measurement_finished.emit()

    def run_reference(self):
        """Measures and saves reference spectra for all mount configurations."""
        self.avaspec.referencedata.clear()

        if len(self.thorlabs.mount_position_combos) == 0:
            wl, data = self.avaspec.save_reference("")
            self.data_ready.emit(wl, data)

        else:
            for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():
                if not self.running:
                    break
                self.wait_if_paused()

                # Move mounts to reference positions
                for mount_id, position in pos_combination.items():
                    if not self.running:
                        break
                    self.wait_if_paused()

                    self.thorlabs.set_mount_pos(mount_id, int(position))

                wl, data = self.avaspec.save_reference(pos_combination_id)

                self.data_ready.emit(wl, data)

        self.measurement_finished.emit()

    def stop(self):
        """Stops the running thread and unpauses if necessary."""
        self.running = False
        self.resume()
        self.wait()  # Wait for thread to exit cleanly

    def pause(self):
        """Pauses ongoing measurement."""
        self.paused = True

    def resume(self):
        """Resumes measurement from paused state."""
        self.mutex.lock()
        self.paused = False
        self.pause_cond.wakeAll()
        self.mutex.unlock()

    def wait_if_paused(self):
        """Blocks thread while paused."""
        self.mutex.lock()
        while self.paused:
            self.pause_cond.wait(self.mutex)
        self.mutex.unlock()


class DeviceTestWorker(QThread):
    test_finished = pyqtSignal(str)  # Emitted when test ends

    def __init__(self, thorlabs: ThorlabsController, device_id):
        super().__init__()
        self.thorlabs = thorlabs
        self.device_id = device_id
        self.device_type = device_id[:2]

        # Thread control flags
        self.running = True
        self.paused = False
        self.pause_cond = QWaitCondition()
        self.mutex = QMutex()

    def run(self):
        """Main thread entry point. Chooses device to test."""
        # Select correct measurement function
        if self.device_type == SOLENOID_PREFIX:
            self.test_solenoid()
        elif self.device_type == MOUNT_PREFIX:
            self.test_mount()

    def test_solenoid(self):
        """Opens/closes solenoid based on timers in the shutter_timer file."""
        shutter_timers = read_shutter_timers()

        for t in shutter_timers:

            if not self.running:
                break

            print(f"Shutter open for {t} seconds.")

            # Illuminate sample for duration t
            self.thorlabs.open_shutter(self.device_id)
            elapsed = 0.0
            step = 0.1
            while elapsed < t and self.running:
                time.sleep(step)
                elapsed += step
            self.thorlabs.close_shutter(self.device_id)

        self.test_finished.emit(self.device_id)

    def test_mount(self):
        """Test function: moves a mount through all stored positions."""
        # Iterate through all mount combinations and measure
        for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():

            # Move mounts to new positions
            for mount_id, position in pos_combination.items():
                print(f"{mount_id}: {position}")
                self.thorlabs.set_mount_pos(mount_id, int(position))

        self.test_finished.emit(self.device_id)

    def stop(self):
        """Stops the running thread and unpauses if necessary."""
        self.running = False
        self.wait()  # Wait for thread to exit cleanly


# -------------------- MAIN WINDOW -------------------- #

try:
    main_ui_class, main_baseclass = uic.loadUiType("main_window.ui")
except Exception as e:
    raise RuntimeError(f"Failed to load UI 'main_window.ui': {e}")


class MainWindow(main_ui_class, main_baseclass):
    """The main GUI window controlling all functionality."""

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avaspec / Thorlabs Automation thing")

        # Initialize controllers
        self.avaspec = AvaspecController()
        self.thorlabs = ThorlabsController()
        self.measurement_thread = None
        self.paused = False

        # Initialize and connect settings windows
        self.ava_settings_window = AvaSettingWindow()
        self.actionAvasoft.triggered.connect(
            lambda checked: self.toggle_window(self.ava_settings_window)
        )
        self.ava_settings_window.settings_changed.connect(self.avaspec.update_params)
        self.actionAvasoft.setEnabled(False)

        self.mount_settings_window = RotationMountSettingWindow(self.thorlabs)
        self.actionRotation_Mount.triggered.connect(
            lambda checked: self.toggle_window(self.mount_settings_window)
        )
        self.mount_settings_window.settings_changed.connect(self.thorlabs.update_mount_position_combos)
        self.actionRotation_Mount.setEnabled(False)

        self.solenoid_settings_window = SolenoidSettingWindow(self.thorlabs)
        self.actionSolenoid.triggered.connect(
            lambda checked: self.toggle_window(self.solenoid_settings_window)
        )
        self.actionSolenoid.setEnabled(False)


        # Disable measurement buttons until devices are connected
        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(False)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)

        # Connect buttons to handler functions
        self.StartMeasBtn.clicked.connect(self.start_measurement_btn_clicked)
        self.PauseMeasBtn.clicked.connect(self.pause_measurement_btn_clicked)
        self.StopMeasBtn.clicked.connect(self.stop_measurement_btn_clicked)
        self.SaveRefBtn.clicked.connect(self.save_ref_btn_clicked)
        self.SaveDrkBtn.clicked.connect(self.save_dark_btn_clicked)
        self.connectAvasoft.triggered.connect(self.open_comm_btn_clicked)
        self.connectThorlabs.triggered.connect(self.connect_thorlabs_btn_clicked)
        self.fileNameEdit.textChanged.connect(self.save_file_changed)

        # Setup plot window
        self.line = None
        self.graph.setBackground("w")
        self.init_plot(None, None, None, "", "")

        self.file_name_to_save = ""

    def closeEvent(self, event):
        """Ensures all devices are safely disconnected on program exit."""
        try:
            if self.measurement_thread and self.measurement_thread.isRunning():
                self.measurement_thread.stop()
        except Exception as e:
            print(e)

        self.thorlabs.disconnect_all()

        self.ava_settings_window.close()
        self.mount_settings_window.close()

        event.accept()

    @pyqtSlot()
    def toggle_window(self, window):
        """Shows or hides a settings window."""
        if window.isVisible():
            window.hide()
        else:
            window.show()

    @pyqtSlot()
    def open_comm_btn_clicked(self):
        """Attempts to connect to Avaspec spectrometer."""
        ret = self.avaspec.connect_device()

        if ret == 0:
            QMessageBox.information(self, "Error", "Could not find a device")
            return
        else:
            QMessageBox.information(self, "Info", "Found Serialnumber: " + str(ret))

            self.StartMeasBtn.setEnabled(True)
            self.SaveRefBtn.setEnabled(True)
            self.SaveDrkBtn.setEnabled(True)
            self.connectAvasoft.setEnabled(False)
            self.actionAvasoft.setEnabled(True)

        return

    @pyqtSlot()
    def connect_thorlabs_btn_clicked(self):
        """Connects to Thorlabs devices and sets up rotation mount tabs."""
        msg = self.thorlabs.connect_devices()
        QMessageBox.information(self, msg[0], msg[1])

        if msg[0] == "Error":
            return

        # For each rotation mount, add a settings tab to the window
        for dev_id, device in self.thorlabs.device_list.items():
            if dev_id[:2] == MOUNT_PREFIX:
                mount = self.mount_settings_window.add_tab(dev_id)
                mount.home_mount_signal.connect(self.thorlabs.home_mount)
                mount.set_pos_signal.connect(self.thorlabs.set_mount_pos)
                mount.update_mount_default_angles.connect(self.thorlabs.update_mount_default_angle)
                mount.update_mount_positions.connect(self.thorlabs.update_mount_positions)

                mount.position_params_changed()
                mount.default_angle_changed()

            elif dev_id[:2] == SOLENOID_PREFIX:
                self.solenoid_settings_window.add_tab(dev_id)

        self.connectThorlabs.setEnabled(False)
        self.actionRotation_Mount.setEnabled(True)
        self.actionSolenoid.setEnabled(True)

    @pyqtSlot()
    def start_measurement_btn_clicked(self):
        """Starts measurements based on the selected mode and type."""

        measurement_mode = self.SelectModeBox.currentText()
        measurement_type = self.SelectTypeBox.currentText()

        # Hide settings window so user can't modify parameters during measurement
        self.ava_settings_window.close()
        self.mount_settings_window.close()

        # Disable controls during measurement
        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(False)
        self.SelectTypeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        # Set Y-axis limits depending on experiment type
        if measurement_mode == "Absorbance":
            y_lim = [0, 3]
        elif measurement_mode == "Transmittance":
            y_lim = [0, 110]
        else:
            y_lim = None

        # Prepare plot for incoming data
        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, y_lim,
                       "Wavelength (nm)", measurement_mode)

        # Stop previous thread if running
        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop()

        # Create and start measurement thread
        self.measurement_thread = MeasurementWorker(self.avaspec, self.thorlabs,
                                                    measurement_mode, measurement_type,
                                                    self.file_name_to_save)

        self.measurement_thread.data_ready.connect(self.plot)
        self.measurement_thread.measurement_finished.connect(self.stop_measurement_btn_clicked)
        self.measurement_thread.start()

    @pyqtSlot()
    def pause_measurement_btn_clicked(self):
        """Pauses or resumes measurement."""
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
        """Stops measurement thread and resets UI."""
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
        """Runs reference measurement via worker thread."""
        self.ava_settings_window.hide()

        # Lock UI
        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(False)
        self.SelectTypeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        # Plot as raw scope measurement
        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, None,
                       "Wavelength (nm)", "Scope")

        # Stop previous measurement if still active
        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop()

        # Start reference measurement
        self.measurement_thread = MeasurementWorker(self.avaspec, self.thorlabs,
                                                    "Scope", "Reference",
                                                    self.file_name_to_save)

        self.measurement_thread.data_ready.connect(self.plot)
        self.measurement_thread.measurement_finished.connect(self.stop_measurement_btn_clicked)
        self.measurement_thread.start()

    @pyqtSlot()
    def save_dark_btn_clicked(self):
        """Captures and plots dark spectrum."""
        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, None,
                       "Wavelength (nm)", "Scope")

        wl, data = self.avaspec.save_dark()
        self.plot(wl, data)

    def init_plot(self, min_x, max_x, yrange, x_label, y_label):
        """Initializes plot axis, ranges, labels, and line object."""
        self.graph.clear()

        pen = pg.mkPen(color=(0, 0, 0), width=1.1, style=Qt.PenStyle.SolidLine)
        self.graph.setLabel("left", f"{y_label}")
        self.graph.setLabel("bottom", f"{x_label}")

        # Configure axes
        if max_x:
            self.graph.setXRange(min_x, max_x)
        if yrange:
            self.graph.setYRange(yrange[0], yrange[1])

        self.graph.showGrid(x=True, y=True)

        # Create line plot object
        self.line = self.graph.plot([0], [0], pen=pen)

    def plot(self, x, y):
        """Plots current measurement."""
        self.line.setData(x, y)
        self.repaint()

    def update_plot_range(self, min_x, max_x):
        """Allows dynamic updating of X-axis."""
        self.graph.setXRange(min_x, max_x)

    def save_file_changed(self, text=None):
        """Updates output filename as user types."""
        if text is None:
            self.file_name_to_save = self.fileNameEdit.text()
        else:
            self.file_name_to_save = text


# -------------------- SETTING WINDOWS ---------------- #

try:
    ava_ui_class, ava_baseclass = uic.loadUiType("ava_settings_window.ui")
except Exception as e:
    raise RuntimeError(f"Failed to load UI 'ava_settings_window.ui': {e}")


class AvaSettingWindow(ava_ui_class, ava_baseclass):
    """Window for adjusting Avaspec measurement parameters."""
    settings_changed = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avasoft 8 Settings")

        # Emit updated parameters whenever user changes values
        self.IntTime.valueChanged.connect(self.parameter_changed)
        self.NumAvg.valueChanged.connect(self.parameter_changed)
        self.MinWavelength.valueChanged.connect(self.parameter_changed)
        self.MaxWavelength.valueChanged.connect(self.parameter_changed)
        self.Smoothing.valueChanged.connect(self.parameter_changed)
        self.dynDarkCheckBox.stateChanged.connect(self.parameter_changed)

    @pyqtSlot()
    def parameter_changed(self):
        """Sends updated spectrometer parameters to main window."""
        int_time = self.IntTime.value()
        avg_num = self.NumAvg.value()
        min_wavelength = self.MinWavelength.value()
        max_wavelength = self.MaxWavelength.value()
        smoothing = self.Smoothing.value()
        if self.dynDarkCheckBox.isChecked():
            dyn_dark = 1
        else:
            dyn_dark = 0

        self.settings_changed.emit([int_time, avg_num, min_wavelength, max_wavelength, smoothing, dyn_dark])


try:
    rotation_mount_widget_class, rotation_mount_widget_baseclass = uic.loadUiType("rotation_mount_settings_widget.ui")
except Exception as e:
    raise RuntimeError(f"Failed to load UI 'rotation_mount_settings_widget.ui': {e}")


class RotationMountWidget(rotation_mount_widget_class, rotation_mount_widget_baseclass):
    """Widget that controls settings for a single rotation mount."""
    update_mount_positions = pyqtSignal(str, list)
    update_mount_default_angles = pyqtSignal(str, int)
    home_mount_signal = pyqtSignal(str)
    set_pos_signal = pyqtSignal(str, int)
    test_mount_signal = pyqtSignal(str)

    def __init__(self, device_id):
        super().__init__()
        self.setupUi(self)

        # Connect UI events
        self.StartPos.valueChanged.connect(self.position_params_changed)
        self.EndPos.valueChanged.connect(self.position_params_changed)
        self.RotationStep.valueChanged.connect(self.position_params_changed)
        self.DefaultAngle.valueChanged.connect(self.default_angle_changed)
        self.HomeDevBtn.clicked.connect(self.home_device)
        self.setPosBtn.clicked.connect(self.set_pos)
        self.testMountBtn.clicked.connect(self.test_mount)

        self.device_id = device_id
        self.pos_list = []

    def update_positions(self):
        """Generates list of valid rotation positions for this mount."""
        min_pos = int(self.StartPos.value())
        max_pos = int(self.EndPos.value())
        pos_interval = int(self.RotationStep.value()) or 1
        self.pos_list = list(range(min_pos, max_pos + 1, pos_interval))

    @pyqtSlot()
    def position_params_changed(self):
        """Updates list of positions and informs main window."""
        self.update_positions()
        self.update_mount_positions.emit(self.device_id, self.pos_list)

    @pyqtSlot()
    def default_angle_changed(self):
        """Informs main window about updated default angle."""
        new_angle = int(self.DefaultAngle.value())
        self.update_mount_default_angles.emit(self.device_id, new_angle)

    @pyqtSlot()
    def home_device(self):
        """Requests mount homing."""
        self.home_mount_signal.emit(self.device_id)

    @pyqtSlot()
    def set_pos(self):
        pos = self.manualPos.value()
        self.set_pos_signal.emit(self.device_id, pos)

    @pyqtSlot()
    def test_mount(self):
        self.test_mount_signal.emit(self.device_id)


try:
    rotation_mount_ui_class, rotation_mount_baseclass = uic.loadUiType("rotation_mount_settings_window.ui")
except Exception as e:
    raise RuntimeError(f"Failed to load UI 'rotation_mount_settings_window.ui': {e}")


class RotationMountSettingWindow(rotation_mount_ui_class, rotation_mount_baseclass):
    """Window that manages multiple rotation mount widgets."""
    settings_changed = pyqtSignal(object)

    def __init__(self, thorlabs: ThorlabsController):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Thorlabs Rotation Mount Settings")

        self.thorlabs = thorlabs
        self.test_thread = None
        self.tabs = dict()

    @pyqtSlot()
    def add_tab(self, dev_id):
        """Adds a new rotation mount tab."""
        new_rotation_mount = RotationMountWidget(dev_id)
        self.tabs[dev_id] = new_rotation_mount

        if dev_id == POLARIZER_MOUNT_ID:
            tab_name = "Polarizer Rotation Mount"
        else:
            tab_name = "Sample Rotation Mount"

        self.RotationMountSelection.addTab(new_rotation_mount, f"{tab_name}")

        new_rotation_mount.update_mount_positions.connect(self.calculate_pos_combinations)
        new_rotation_mount.test_mount_signal.connect(self.test_mount)

        return new_rotation_mount

    def calculate_pos_combinations(self, device_id, position_list):
        """
        Creates combinations of positions from all mounts.
        Used in automated measurement sequences.
        """
        all_rotation_mount_positions = []

        # Build list of possible position labels for each device
        for dev_id, mount in self.tabs.items():
            pos_ids = list()
            for pos in mount.pos_list:
                pos_ids.append(f"{dev_id}_{pos}")
            all_rotation_mount_positions.append(pos_ids)

        mount_position_combinations = defaultdict(dict)

        # Create Cartesian product of all position lists
        for unique_pos_combination in product(*all_rotation_mount_positions):
            pos_combination = dict()

            parts = []
            for i in unique_pos_combination:
                mount_id = i.split('_')[0]
                pos = i.split('_')[1]
                pos_combination[mount_id] = pos
                parts.append(pos)
            pos_combination_id = "_".join(parts)

            mount_position_combinations[pos_combination_id] = pos_combination

        self.settings_changed.emit(mount_position_combinations)

    def test_mount(self, dev_id):
        device = self.tabs[dev_id]

        if self.test_thread and self.test_thread.isRunning():
            self.stop_test(dev_id)
            return

        self.RotationMountSelection.setEnabled(False)
        device.testMountBtn.setText("Stop Test")

        # Create and start measurement thread
        self.test_thread = DeviceTestWorker(self.thorlabs, dev_id)
        self.test_thread.test_finished.connect(self.stop_test)
        self.test_thread.start()

    def toggle_shutter(self, dev_id):
        self.thorlabs.toggle_shutter(dev_id)

    def stop_test(self, dev_id):
        device = self.tabs[dev_id]
        self.test_thread.stop()
        self.RotationMountSelection.setEnabled(True)
        device.testMountBtn.setText("Test Rotation Mount(s)")


try:
    solenoid_widget_class, solenoid_widget_baseclass = uic.loadUiType("solenoid_settings_widget.ui")
except Exception as e:
    raise RuntimeError(f"Failed to load UI 'solenoid_settings_widget.ui': {e}")


class SolenoidWidget(solenoid_widget_class, solenoid_widget_baseclass):
    """Widget that controls settings for a single rotation mount."""
    toggle = pyqtSignal(str)
    test = pyqtSignal(str)

    def __init__(self, device_id):
        super().__init__()
        self.setupUi(self)

        self.toggleSolenoidBtn.clicked.connect(self.toggle_solenoid_btn_clicked)
        self.testSolenoidBtn.clicked.connect(self.test_solenoid_btn_clicked)

        self.device_id = device_id

    @pyqtSlot()
    def toggle_solenoid_btn_clicked(self):
        self.toggle.emit(self.device_id)

    @pyqtSlot()
    def test_solenoid_btn_clicked(self):
        self.test.emit(self.device_id)


try:
    solenoid_ui_class, solenoid_baseclass = uic.loadUiType("solenoid_settings_window.ui")
except Exception as e:
    raise RuntimeError(f"Failed to load UI 'solenoid_settings_window.ui': {e}")


class SolenoidSettingWindow(solenoid_ui_class, solenoid_baseclass):
    """Window that manages multiple rotation mount widgets."""

    def __init__(self, thorlabs: ThorlabsController):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Thorlabs Solenoid Settings")

        self.thorlabs = thorlabs
        self.test_thread = None
        self.tabs = dict()

    def closeEvent(self, event):
        try:
            if self.test_thread and self.test_thread.isRunning():
                self.test_thread.stop()
        except Exception as e:
            print(e)

        event.accept()

    @pyqtSlot()
    def add_tab(self, dev_id):
        """Adds a new rotation mount tab."""
        new_solenoid = SolenoidWidget(dev_id)
        self.tabs[dev_id] = new_solenoid

        self.SolenoidSelection.addTab(new_solenoid, f"{dev_id}")

        new_solenoid.toggle.connect(self.toggle_shutter)
        new_solenoid.test.connect(self.test_shutter)

    def test_shutter(self, dev_id):
        device = self.tabs[dev_id]

        if self.test_thread and self.test_thread.isRunning():
            self.stop_test(dev_id)
            return

        self.SolenoidSelection.setEnabled(False)
        device.toggleSolenoidBtn.setEnabled(False)
        device.testSolenoidBtn.setText("Stop Test")

        # Create and start measurement thread
        self.test_thread = DeviceTestWorker(self.thorlabs, dev_id)
        self.test_thread.test_finished.connect(self.stop_test)
        self.test_thread.start()

    def toggle_shutter(self, dev_id):
        self.thorlabs.toggle_shutter(dev_id)

    def stop_test(self, dev_id):
        device = self.tabs[dev_id]
        self.test_thread.stop()
        self.SolenoidSelection.setEnabled(True)
        device.toggleSolenoidBtn.setEnabled(True)
        device.testSolenoidBtn.setText("Test Solenoid Timers")


# --------------- FILE HANDLING ----------------------#      
        
        
def save_to_new_file(file_name, folder, x, y):
    """
    Saves X–Y data (spectrum) into a new text file, overwriting existing file.
    Each line: WAV\tVALUE
    """
    complete_folder = os.path.join(PROJECT_PATH, folder)
    os.makedirs(complete_folder, exist_ok=True)
    path = os.path.join(complete_folder, f"{file_name}.txt")
    if len(x) != len(y):
        raise ValueError("x and y must be same length")
    with open(path, "w", encoding="utf-8") as fh:
        for xv, yv in zip(x, y):
            fh.write(f"{xv:.1f}\t{yv:.6g}\n")


def read_shutter_timers():
    """
    Reads list of shutter open times (in seconds)
    from shutter_timer.txt.
    """
    path = os.path.join(PROJECT_PATH, "shutter_timer.txt")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            try:
                out.append(int(s))
            except ValueError:
                # log or skip invalid lines
                continue
    return out


# ---------------------- MAIN ---------------------- #

def main():
    """Starts application and loads main window."""
    app = QApplication(sys.argv)
    app.lastWindowClosed.connect(app.quit)
    window = MainWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    main()
