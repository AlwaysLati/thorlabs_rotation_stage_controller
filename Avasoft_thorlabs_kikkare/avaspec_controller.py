import math
import time

# Avaspec: only import what's used in AvaspecController
from avaspec import (
    AVS_Init, AVS_GetNrOfDevices, AVS_GetList, AVS_Activate,
    AVS_GetParameter, AVS_GetLambda, AVS_UseHighResAdc,
    AVS_PrepareMeasure, AVS_Measure, AVS_PollScan,
    AVS_GetScopeData, AVS_StopMeasure, AVS_SetDigOut,
    AvsIdentityType, DeviceConfigType, MeasConfigType
)


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