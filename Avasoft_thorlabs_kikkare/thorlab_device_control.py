import clr
import os
import time
import sys
import globals

# Write in file paths of dlls needed.
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.IntegratedStepperMotorsCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.KCube.SolenoidCLI.dll")

# Import functions from dlls.
from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import MotorDirection
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import *
from Thorlabs.MotionControl.KCube.SolenoidCLI import *
from System import Decimal


def connect_all():
    """Attempts to connect to all Thorlabs devices"""

    try:
        # Initialize device list.
        DeviceManagerCLI.BuildDeviceList()
        serial_numbers = DeviceManagerCLI.GetDeviceList()

        if len(serial_numbers) == 0:
            return ["Error", "No devices found"]

        for serial_no in serial_numbers:
            device_type = serial_no[:2]

            if device_type == "55": #Integrated stepper driven rotation stage
                device = CageRotator.CreateCageRotator(serial_no)
                device.Connect(serial_no)

                # Ensure that the device settings have been initialized.
                if not device.IsSettingsInitialized():
                    device.WaitForSettingsInitialized(10000)  # 10 second timeout.
                    assert device.IsSettingsInitialized() is True

                # Start polling loop and enable device.
                device.StartPolling(250)  # 250ms polling rate.
                time.sleep(0.25)
                device.EnableDevice()
                time.sleep(0.25)  # Wait for device to enable.

                device.LoadMotorConfiguration(serial_no,
                                              DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings)

                globals.thorlabs_device_list[serial_no] = device

            elif device_type == "68": #K-Cube solenoid Driver
                device = KCubeSolenoid.CreateKCubeSolenoid(serial_no)
                device.Connect(serial_no)

                # Ensure that the device settings have been initialized.
                if not device.IsSettingsInitialized():
                    device.WaitForSettingsInitialized(10000)  # 10 second timeout.
                    assert device.IsSettingsInitialized() is True

                # Start polling loop and enable device.
                device.StartPolling(250)  # 250ms polling rate.
                time.sleep(0.25)
                device.EnableDevice()
                time.sleep(0.25)  # Wait for device to enable.

                device.SetOperatingMode(SolenoidStatus.OperatingModes.Manual)

                globals.thorlabs_device_list[serial_no] = device

            else:
                return ["Error", "Unknown device found"]

        return ["Info", f"Connected to {len(serial_numbers)} Thorlabs devices"]

    except Exception as e:
        print(e)


def disconnect_all():
    for device in globals.thorlabs_device_list:
        device.StopPolling()
        device.Disconnect()

    return


def toggle_solenoid(serial_no):
    device = globals.thorlabs_device_list.get(serial_no)

    if device is None or serial_no[:2] != "68":
        return

    state = device.GetOperatingState()
    if state == SolenoidStatus.OperatingStates.Active:
        device.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)
    else:
        device.SetOperatingState(SolenoidStatus.OperatingStates.Active)

    return


def home_rotation_mount(serial_no):
    device = globals.thorlabs_device_list.get(serial_no)

    if device is None or serial_no[:2] != "55":
        return ["Error", "Unable to home device"]

    try:
        # 60 second timeout, function will wait until the move completes or the timeout elapses, whichever comes first.
        device.Home(60000)
        return ["Info", "Homed device"]

    except Exception as e:
        print(e)
        return ["Error", "Unable to home device"]


def set_rotation_mount_pos(serial_no, new_pos):
    device = globals.thorlabs_device_list.get(serial_no)

    if device is None or serial_no[:2] != "55":
        return

    try:
        pos = Decimal(new_pos)  # Must be a .NET decimal.
        device.MoveTo(pos, 60000)  # 60 second timeout.

    except Exception as e:
        print(e)

    return
