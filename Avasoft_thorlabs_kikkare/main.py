import sys
import platform
import os
from PyQt5 import uic
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import pyqtgraph as pg
from avaspec import *
import time
import math
from statistics import *
from pylinkam import interface, sdk
import globals


ava_ui_class, ava_baseclass = pg.Qt.loadUiType("ava_settings_window.ui")
class AvaSettingWindow(ava_ui_class, ava_baseclass):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avasoft 8 Settings")

        globals.int_time = self.IntTime.value()
        globals.avg_num = self.NumAvg.value()
        globals.min_wavelength = self.MinWavelength.value()
        globals.max_wavelength = self.MaxWavelength.value()
        globals.min_integral = self.IntMin.value()
        globals.max_integral = self.IntMax.value()
        globals.integral_multiplier = self.IntMultiplier.value()
        globals.save_every_n = self.SaveEveryN.value()
        globals.meas_per_RH = self.MeasPerRH.value()

        self.IntTime.valueChanged.connect(self.IntTime_changed)
        self.NumAvg.valueChanged.connect(self.NumAvg_changed)
        self.MinWavelength.valueChanged.connect(self.MinWavelength_changed)
        self.MaxWavelength.valueChanged.connect(self.MaxWavelength_changed)
        self.IntMin.valueChanged.connect(self.IntMin_changed)
        self.IntMax.valueChanged.connect(self.IntMax_changed)
        self.IntMultiplier.valueChanged.connect(self.IntMultiplier_changed)
        self.SaveEveryN.valueChanged.connect(self.SaveEveryN_changed)
        self.MeasPerRH.valueChanged.connect(self.MeasPerRH_changed)
        self.SaveToFolderEdt.textEdited.connect(self.SaveToFolder_changed)

    def IntTime_changed(self):
        globals.int_time = int(self.IntTime.value())

    def NumAvg_changed(self):
        globals.avg_num = int(self.NumAvg.value())

    def MinWavelength_changed(self):
        globals.min_wavelength = int(self.MinWavelength.value())

    def MaxWavelength_changed(self):
        globals.max_wavelength = int(self.MaxWavelength.value())

    def IntMin_changed(self):
        globals.min_integral = int(self.IntMin.value())

    def IntMax_changed(self):
        globals.max_integral = int(self.IntMax.value())

    def IntMultiplier_changed(self):
        globals.integral_multiplier = float(self.IntMultiplier.value())

    def SaveEveryN_changed(self):
        globals.save_every_n = int(self.SaveEveryN.value())

    def MeasPerRH_changed(self):
        globals.meas_per_RH = int(self.MeasPerRH.value())

    def SaveToFolder_changed(self):
        globals.save_to_folder = self.SaveToFolderEdt.text()


link_ui_class, link_baseclass = pg.Qt.loadUiType("link_settings_window.ui")
class LinkSettingWindow(link_ui_class, link_baseclass):
    """
    TODO: Add functionality to modify the profile used to approach a setpoint in the setRH function
    """
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("LINK Settings")

        self.SaveRHBtn.clicked.connect(self.readRHRange)
        self.SetpointTol.valueChanged.connect(self.SetpointTolerance_changed)

    def readRHRange(self):
        line = self.RHRangeEdt.text()
        values = line.split(",")

        rh_range = []
        for rh in values:
            try:
                if 0 < float(rh) < 100:
                    rh_range.append(float(rh))
            except ValueError:
                QMessageBox.information(self, "Error", "Invalid format.\n"
                                                       "Input only accepts numbers separated by commas ( , )\n"
                                                       "For decimals, use dots ( . )")
                return

        globals.RH_range = rh_range

    def SetpointTolerance_changed(self):
        globals.setpoint_tolerance = float(self.SetpointTol.value())


led_ui_class, led_baseclass = pg.Qt.loadUiType("led_settings_window.ui")
class LedSettingWindow(led_ui_class, led_baseclass):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("CoolLED Settings")


main_ui_class, main_baseclass = pg.Qt.loadUiType("main_window.ui")
class MainWindow(main_ui_class, main_baseclass):
    newdata = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Pystyspekkarin Automointi Kikkare")

        self.ava_settings_window = AvaSettingWindow()
        self.actionAvasoft.triggered.connect(
            lambda checked : self.toggleWindow(self.ava_settings_window)
        )

        self.link_settings_window = LinkSettingWindow()
        self.actionLinkam_RH95.triggered.connect(
            lambda checked : self.toggleWindow(self.link_settings_window)
        )

        self.led_settings_window = LedSettingWindow()
        self.actionCoolLED.triggered.connect(
            lambda checked: self.toggleWindow(self.led_settings_window)
        )

        self.StartMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(False)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.measurement_mode = self.SelectModeBox.currentText()
        self.newdata.connect(self.handleNewData)

        self.StartMeasBtn.clicked.connect(self.StartMeasBtn_clicked)
        self.StopMeasBtn.clicked.connect(self.StopMeasBtn_clicked)
        self.SaveRefBtn.clicked.connect(self.SaveRefBtn_clicked)
        self.SaveDrkBtn.clicked.connect(self.SaveDrkBtn_clicked)
        self.SelectModeBox.currentTextChanged.connect(self.Mode_changed)
        self.connectAvasoft.triggered.connect(self.OpenCommBtn_clicked)

        self.graph.setBackground("w")
        self.initPlot(None, None, None, "", "")
        
    @pyqtSlot()
    def toggleWindow(self, window):
        if window.isVisible():
            window.hide()
        else:
            window.show()

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
        return

    @pyqtSlot()
    def StartMeasBtn_clicked(self):
        """
        Main method for running all measurements depending on the mode selected.
        TODO: Despaghettify

        :return:
        """
        self.ava_settings_window.hide()

        self.StartMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(True)
        self.SelectModeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        if self.measurement_mode == "Scope":

            self.initPlot(globals.min_wavelength, globals.max_wavelength, None, "Wavelength (nm)", "Counts (#)")
            while True:
                if globals.stopscanning:
                    break
                self.measureScope()
                self.plot(globals.wavelength, globals.spectraldata)
                time.sleep(0.01)

        elif self.measurement_mode == "Absorbance":

            self.initPlot(globals.min_wavelength, globals.max_wavelength,None,"Wavelength (nm)","Absorbance")
            while True:
                if globals.stopscanning:
                    break

                abs_spectra = self.measureAbs()
                self.plot(globals.wavelength,abs_spectra)
                time.sleep(0.01)


        self.StartMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(True)
        self.menuBar.setEnabled(True)
        return

    @pyqtSlot()
    def StopMeasBtn_clicked(self):
        """
        Completely stops all ongoing measurements as well as RH changes

        :return:
        """
        ret = AVS_StopMeasure(globals.dev_handle)
        globals.stopscanning = True
        self.StartMeasBtn.setEnabled(True)
        self.repaint()
        return

    @pyqtSlot()
    def SaveRefBtn_clicked(self):
        """
        Saves and plots reference spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """
        self.measureScope()
        saveToNewFile("Reference", globals.wavelength, globals.spectraldata)
        globals.referencedata = readFile(self, "Reference.txt")[1]

        self.initPlot(globals.min_wavelength, globals.max_wavelength,None,"Wavelength (nm)","Counts (#)")
        self.plot(globals.wavelength,globals.referencedata)

        time.sleep(0.001)
        return

    @pyqtSlot()
    def SaveDrkBtn_clicked(self):
        """
        Saves and plots dark spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """
        self.measureScope()
        saveToNewFile("Dark", globals.wavelength, globals.spectraldata)
        globals.darkdata = readFile(self, "Dark.txt")[1]

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
            time.sleep(0.001)

        self.newdata.emit() # Retrieves and saves the measurement to global variables
        self.repaint()
        time.sleep(0.001)
        qApp.processEvents()  # allows clicking of the StopMeasBtn to be seen
        self.repaint()
        return

    @pyqtSlot()
    def measureAbs(self):
        """
        Calculates a sample's absorbance spectrum by comparing its scope to previously saved reference and dark files.

        :return:
        """
        ref = readFile(self, "Reference.txt")[1]
        drk = readFile(self, "Dark.txt")[1]
        self.measureScope()

        # Absorbance formula from Avasoft 8 documentation
        try:
            abs_spectra = [-math.log10((s - d) / (r - d)) for r, s, d in zip(ref, globals.spectraldata, drk)]
        except (ValueError, ZeroDivisionError): # Catches any errors and returns a list full of zeros
            abs_spectra = [0.0] * len(globals.spectraldata)
            # abs = [0 for _ in range(len(globals.spectraldata))]
        return abs_spectra

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
            time.sleep(1)

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
                    time.sleep(1)
                    return
                else:
                    time.sleep(5)

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


def pulseLED(wavelength,pulse):
    """
    TODO: Implement CoolLED light pulse control. Use the CoolLED_control.py file as a guide. Depending on how the LED
    TODO: control is implemented it might not make sense to do this in a separate function

    :param wavelength:
    :param pulse:
    :return:
    """
    return


def saveToNewFile(file_name, x, y):
    """
    Saves a list of values to a new file --> overwrites an existing file of the name. Mainly used for saving
    reference and dark spectra.

    :param file_name: str, creates a .txt file with this name and saves the spectrum data to it
    :param x [float], input list of spectrum values to save
    :param y [float], input list of time/wavelength values corresponding to spectrum values
    :return:
    """

    """
    if os.path.exists(f"{file_name}.txt"):
        i = 1
        while os.path.exists(f"{file_name}%s.txt" % i):
            i += 1
        fh = f"{file_name}%s" % i
    else:
        fh = file_name
    """

    try:
        with open(f"{file_name}.txt", "w") as fh:
            for n in range(len(y)):
                fh.write(f"{x[n]:.1f}\t{y[n]}\n")
    except IndexError:
        return



def readFile(parent, file_name):
    """
    Reads a spectrum/wavelength file and returns them as to separate lists

    :param parent: PyQt widget for returning possible errors
    :param file_name: str, file to be read
    :return:
    """
    try:
        with open(file_name, "r") as fh:
            wavelength = []
            spectrum = []
            for line in fh:
                div_line = line.split("\t")
                wavelength.append(float(div_line[0]))
                spectrum.append(float(div_line[1].strip()))

        return wavelength, spectrum
    except FileNotFoundError:
        QMessageBox.information(parent, "Error", "Unable to read file with name '" + file_name + "'")


def main():
    # Initializing the PyQt application window
    app = QApplication(sys.argv)
    app.lastWindowClosed.connect(app.quit)
    window = MainWindow()
    window.show()

    app.exec()


if __name__ == "__main__":
    main()
