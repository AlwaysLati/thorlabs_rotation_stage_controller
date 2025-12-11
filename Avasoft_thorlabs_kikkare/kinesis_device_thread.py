# ---------- kinesis_device_thread.py ----------
import threading
import queue
import ctypes
import time
import traceback

# Command tuple form: (cmd_name, args_tuple, kwargs_dict, response_event, response_container)
# response_event is threading.Event or None; response_container is a dict to hold results or exceptions.

COINIT_APARTMENTTHREADED = 0x2

class KinesisDeviceThread(threading.Thread):
    """Run all Thorlabs .NET / Kinesis interactions inside this STA thread."""

    def __init__(self):
        super().__init__(daemon=True)
        self.cmd_q = queue.Queue()
        self._stop_requested = threading.Event()
        self.devices = {}  # serial -> device object
        self.kinesis = {}  # hold references to imported modules if needed
        self.started_event = threading.Event()

    def run(self):
        try:
            # Initialize COM for this thread as STA BEFORE any pythonnet/clr operations.
            res = ctypes.windll.ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
            # res may be 0 (S_OK) or 1 (S_FALSE) if already initialized. Accept both.
            # Import clr and Thorlabs assemblies here (inside STA thread)
            import clr
            # Adjust this path to your THORLABS path or ensure env var is set.
            from os import environ
            tlab = environ.get("THORLABS_PATH", r"C:\Program Files\Thorlabs\Kinesis")
            # Add references (catch errors)
            clr.AddReference(f"{tlab}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
            clr.AddReference(f"{tlab}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
            clr.AddReference(f"{tlab}\\Thorlabs.MotionControl.IntegratedStepperMotorsCLI.dll")
            clr.AddReference(f"{tlab}\\Thorlabs.MotionControl.KCube.SolenoidCLI.dll")

            # Import needed classes (inside thread)
            from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
            from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import CageRotator
            from Thorlabs.MotionControl.KCube.SolenoidCLI import KCubeSolenoid, SolenoidStatus
            # Save references so other methods can access them (optional)
            self.kinesis['DeviceManagerCLI'] = DeviceManagerCLI
            self.kinesis['CageRotator'] = CageRotator
            self.kinesis['KCubeSolenoid'] = KCubeSolenoid
            self.kinesis['SolenoidStatus'] = SolenoidStatus

            # Signal that thread is ready to accept commands
            self.started_event.set()

            # Main loop: handle commands until stop requested
            while not self._stop_requested.is_set():
                try:
                    cmd, args, kwargs, resp_event, resp_container = self.cmd_q.get(timeout=0.2)
                except queue.Empty:
                    continue

                try:
                    result = self._handle_command(cmd, *args, **(kwargs or {}))
                    if resp_container is not None:
                        resp_container['result'] = result
                except Exception as e:
                    # store exception to be raised in caller
                    if resp_container is not None:
                        resp_container['exc'] = e
                        resp_container['traceback'] = traceback.format_exc()
                finally:
                    if resp_event is not None:
                        resp_event.set()

        finally:
            # Uninitialize COM for thread
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    def stop(self, wait=True):
        self._stop_requested.set()
        # enqueue a no-op to break any pending get() immediately
        self.cmd_q.put(("__stop__", (), {}, None, None))
        if wait:
            self.join(timeout=5)

    # Public helper to submit a command and optionally wait for the result
    def submit(self, cmd, *args, wait=True, timeout=30, **kwargs):
        resp_event = threading.Event() if wait else None
        resp_container = {} if wait else None
        self.cmd_q.put((cmd, args, kwargs, resp_event, resp_container))
        if not wait:
            return None
        ok = resp_event.wait(timeout=timeout)
        if not ok:
            raise TimeoutError(f"Timed out waiting for command '{cmd}' result")
        # If an exception was set on the worker side, raise it here
        if 'exc' in (resp_container or {}):
            # attach remote traceback for debugging
            tb = resp_container.get('traceback', '')
            raise RuntimeError(f"Exception in device thread: {resp_container['exc']}\n{tb}")
        return resp_container.get('result', None)

    # Internal command handler running inside STA thread:
    def _handle_command(self, cmd, *args, **kwargs):
        # Implement the commands you need here. Examples:
        if cmd == "__stop__":
            return None

        if cmd == "build_device_list":
            DeviceManagerCLI = self.kinesis['DeviceManagerCLI']
            DeviceManagerCLI.BuildDeviceList()
            return DeviceManagerCLI.GetDeviceList()

        if cmd == "connect_mount":
            serial = args[0]
            CageRotator = self.kinesis['CageRotator']
            device = CageRotator.CreateCageRotator(serial)
            device.Connect(serial)
            # Wait settings initialized
            if not device.IsSettingsInitialized():
                device.WaitForSettingsInitialized(10000)
            device.StartPolling(250)
            time.sleep(0.25)
            device.EnableDevice()
            time.sleep(0.25)
            device.LoadMotorConfiguration(serial, 0)  # UseFileSettings enum value (or correct one)
            self.devices[serial] = device
            return True

        if cmd == "home":
            serial = args[0]
            timeout_ms = kwargs.get('timeout_ms', 60000)
            device = self.devices.get(serial)
            if device is None:
                raise RuntimeError("Device not connected")
            device.Home(timeout_ms)
            return True

        if cmd == "move_to":
            serial, pos, timeout_ms = args
            device = self.devices.get(serial)
            if device is None:
                raise RuntimeError("Device not connected")
            from System import Decimal
            device.MoveTo(Decimal(pos), int(timeout_ms))
            return True

        if cmd == "get_position":
            serial = args[0]
            device = self.devices.get(serial)
            return device.GetPosition() if device is not None else None

        if cmd == "connect_solenoid":
            serial = args[0]
            KCubeSolenoid = self.kinesis['KCubeSolenoid']
            device = KCubeSolenoid.CreateKCubeSolenoid(serial)
            device.Connect(serial)
            if not device.IsSettingsInitialized():
                device.WaitForSettingsInitialized(10000)
            device.StartPolling(250)
            time.sleep(0.25)
            device.EnableDevice()
            time.sleep(0.25)
            device.SetOperatingMode(self.kinesis['SolenoidStatus'].OperatingModes.Manual)
            self.devices[serial] = device
            return True

        if cmd == "set_shutter":
            serial, open_state = args
            device = self.devices.get(serial)
            if device is None:
                raise RuntimeError("Solenoid not connected")
            if open_state:
                device.SetOperatingState(self.kinesis['SolenoidStatus'].OperatingStates.Active)
            else:
                device.SetOperatingState(self.kinesis['SolenoidStatus'].OperatingStates.Inactive)
            return True

        if cmd == "disconnect_all":
            for serial, dev in list(self.devices.items()):
                try:
                    # Stop polling/stop movement if applicable
                    if serial[:2] == "55":
                        try:
                            dev.StopImmediate()
                        except Exception:
                            pass
                    try:
                        dev.StopPolling()
                    except Exception:
                        pass
                    dev.Disconnect()
                except Exception:
                    pass
                finally:
                    self.devices.pop(serial, None)
            return True

        raise RuntimeError(f"Unknown command '{cmd}'")
