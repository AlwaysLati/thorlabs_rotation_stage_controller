import time
from collections import defaultdict

import clr

clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.IntegratedStepperMotorsCLI.dll")
clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.KCube.SolenoidCLI.dll")

from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import *
from Thorlabs.MotionControl.KCube.SolenoidCLI import *
from System import Decimal


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
