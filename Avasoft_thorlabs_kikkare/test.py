from dotenv import load_dotenv

import time
import ctypes
import threading
import queue
import traceback

COINIT_APARTMENTTHREADED = 0x2

load_dotenv()

class KinesisThread(threading.Thread):
    """
    Runs all Thorlabs .NET calls inside an STA thread.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.cmd_q = queue.Queue()
        self.result_q = queue.Queue()
        self.devices = {}
        self.ready = threading.Event()

    def run(self):
        # ----------------------------------------------------
        # COM in STA BEFORE pythonnet loads any assemblies
        # ----------------------------------------------------
        ctypes.windll.ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)

        try:
            import clr
            import os
            TLABPATH = os.environ.get("THORLABS_PATH")

            clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
            clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
            clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.IntegratedStepperMotorsCLI.dll")
            clr.AddReference(f"{TLABPATH}\\Thorlabs.MotionControl.KCube.SolenoidCLI.dll")

            from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
            from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import CageRotator
            from Thorlabs.MotionControl.KCube.SolenoidCLI import KCubeSolenoid, SolenoidStatus
            from System import Decimal

            self.DeviceManagerCLI = DeviceManagerCLI
            self.CageRotator = CageRotator
            self.KCubeSolenoid = KCubeSolenoid
            self.SolenoidStatus = SolenoidStatus
            self.Decimal = Decimal

            print("Kinesis STA thread initialized.")
            self.ready.set()

            # ----------------------------
            # MAIN COMMAND LOOP
            # ----------------------------
            while True:
                cmd, args = self.cmd_q.get()
                if cmd == "__exit__":
                    break

                try:
                    result = getattr(self, cmd)(*args)
                    self.result_q.put(("ok", result))
                except Exception as e:
                    tb = traceback.format_exc()
                    self.result_q.put(("err", f"{e}\n{tb}"))

        finally:
            ctypes.windll.ole32.CoUninitialize()

    # ---------------------------------------------------------
    # Commands executed inside STA thread
    # ---------------------------------------------------------

    def build_list(self):
        self.DeviceManagerCLI.BuildDeviceList()
        return list(self.DeviceManagerCLI.GetDeviceList())

    def connect_rot(self, serial):
        dev = self.CageRotator.CreateCageRotator(serial)
        dev.Connect(serial)

        if not dev.IsSettingsInitialized():
            dev.WaitForSettingsInitialized(10000)

        dev.StartPolling(200)
        time.sleep(0.3)
        dev.EnableDevice()
        time.sleep(0.3)

        dev.LoadMotorConfiguration(serial)
        self.devices[serial] = dev
        return f"Connected rotation mount {serial}"

    def home(self, serial):
        dev = self.devices[serial]
        print(f"Homing {serial}...")
        dev.Home(60000)
        return "homed"

    def move(self, serial, angle):
        dev = self.devices[serial]
        print(f"Moving {serial} to {angle}°...")
        dev.MoveTo(self.Decimal(angle), 60000)
        return "moved"

    def getpos(self, serial):
        return float(self.devices[serial].GetPosition())

    def connect_shutter(self, serial):
        dev = self.KCubeSolenoid.CreateKCubeSolenoid(serial)
        dev.Connect(serial)

        if not dev.IsSettingsInitialized():
            dev.WaitForSettingsInitialized(10000)

        dev.StartPolling(200)
        time.sleep(0.3)
        dev.EnableDevice()
        time.sleep(0.3)

        self.devices[serial] = dev
        return f"Connected shutter {serial}"

    def shutter(self, serial, state: bool):
        dev = self.devices[serial]
        mode = self.SolenoidStatus.OperatingStates.Active if state else self.SolenoidStatus.OperatingStates.Inactive
        dev.SetOperatingState(mode)
        return f"Shutter {'OPEN' if state else 'CLOSED'}"

    def disconnect_all(self):
        for s, d in self.devices.items():
            try:
                d.StopPolling()
            except:
                pass
            d.Disconnect()
        return "All disconnected"

    # ---------------------------------------------------------
    # Helper to call STA methods externally
    # ---------------------------------------------------------
    def call(self, cmd, *args, timeout=30):
        self.cmd_q.put((cmd, args))
        status, payload = self.result_q.get(timeout=timeout)
        if status == "ok":
            return payload
        else:
            raise RuntimeError(payload)


# =====================================================================
#                              TEST LOGIC
# =====================================================================

if __name__ == "__main__":
    kt = KinesisThread()
    kt.start()
    kt.ready.wait(5)

    print("\nBuilding device list…")
    serials = kt.call("build_list")
    print("Found devices:", serials)

    # Connect rotation mounts
    rot_mounts = [s for s in serials if s.startswith("55")]
    shutters = [s for s in serials if s.startswith("68")]

    for s in rot_mounts:
        print(kt.call("connect_rot", s))

    for s in shutters:
        print(kt.call("connect_shutter", s))

    # Test HOMING
    for s in rot_mounts:
        print(kt.call("home", s))
        print("Position after home:", kt.call("getpos", s))

    # Test moving
    for s in rot_mounts:
        print(kt.call("move", s, 30))
        print("Position:", kt.call("getpos", s))

        print(kt.call("move", s, 0))
        print("Position:", kt.call("getpos", s))

    # Test shutter
    for s in shutters:
        print(kt.call("shutter", s, True))
        time.sleep(1)
        print(kt.call("shutter", s, False))
        time.sleep(1)

    print(kt.call("disconnect_all"))
    kt.call("__exit__")
