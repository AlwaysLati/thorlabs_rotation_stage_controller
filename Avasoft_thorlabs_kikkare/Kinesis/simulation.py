import time
import clr
from System import Decimal

# Add Thorlabs .NET assemblies
clr.AddReference("C:\\Users\\pdlauo\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Users\\pdlauo\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference("C:\\Users\\pdlauo\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.KCube.SolenoidCLI.dll")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.GenericMotorCLI import SimulationManager
from Thorlabs.MotionControl.KCube.SolenoidCLI import KCubeSolenoid, SolenoidStatus


def main():
    try:
        # --- Initialize simulation environment ---
        print("Initializing Thorlabs Kinesis simulation...")
        SimulationManager.Instance.InitializeSimulations()

        # --- Build simulated device list ---
        DeviceManagerCLI.BuildDeviceList()
        serial_numbers = list(DeviceManagerCLI.GetDeviceList())
        print(f"Simulated devices detected: {serial_numbers}")

        if not serial_numbers:
            print("No simulated devices found! Check that simulations are enabled in Kinesis.")
            return

        # Pick the first simulated device (or use a known simulated serial)
        serial_no = serial_numbers[0]
        print(f"Using simulated serial: {serial_no}")

        # --- Create and connect the simulated device ---
        device = KCubeSolenoid.CreateKCubeSolenoid(serial_no)
        device.Connect(serial_no)

        if not device.IsSettingsInitialized():
            device.WaitForSettingsInitialized(10000)

        # --- Start polling and enable the device ---
        device.StartPolling(250)
        time.sleep(0.25)
        device.EnableDevice()
        time.sleep(0.5)

        print("Device Description:", device.GetDeviceInfo().Description)

        # --- Control the solenoid ---
        print("Setting solenoid ACTIVE...")
        device.SetOperatingMode(SolenoidStatus.OperatingModes.Manual)
        device.SetOperatingState(SolenoidStatus.OperatingStates.Active)
        time.sleep(2)

        print("Setting solenoid INACTIVE...")
        device.SetOperatingState(SolenoidStatus.OperatingStates.Inactive)
        time.sleep(2)

        # --- Cleanup ---
        device.StopPolling()
        device.Disconnect()
        SimulationManager.Instance.UninitializeSimulations()
        print("Simulation complete. Disconnected.")

    except Exception as e:
        print("Error:", e)
        SimulationManager.Instance.UninitializeSimulations()


if __name__ == "__main__":
    main()