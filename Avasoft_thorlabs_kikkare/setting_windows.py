from PyQt5.QtWidgets import *
from PyQt5 import QtTest

import pyqtgraph as pg
from itertools import product

from avaspec import *
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


rotation_mount_widget_class, rotation_mount_widget_baseclass = pg.Qt.loadUiType("rotation_mount_settings_widget.ui")
class RotationMountWidget(rotation_mount_widget_class, rotation_mount_widget_baseclass):
    def __init__(self, device_id):
        super().__init__()
        self.setupUi(self)

        self.StartPos.valueChanged.connect(self.PosParams_changed)
        self.EndPos.valueChanged.connect(self.PosParams_changed)
        self.RotationStep.valueChanged.connect(self.PosParams_changed)
        #self.saveBtn.clicked.connect(self.TestBtn)

        self.device_id = device_id

        self.PosParams_changed()

    def PosParams_changed(self):
        min_pos = int(self.StartPos.value())
        max_pos = int(self.EndPos.value())
        pos_interval = int(self.RotationStep.value())

        pos_list = []
        for pos in range(min_pos, max_pos, pos_interval):
            pos_list.append(pos)
        globals.rotation_mount_positions[self.device_id] = pos_list


    def TestBtn(self):
        pass


rotation_mount_ui_class, rotation_mount_baseclass = pg.Qt.loadUiType("rotation_mount_settings_window.ui")
class RotationMountSettingWindow(rotation_mount_ui_class, rotation_mount_baseclass):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Thorlabs Rotation Mount Settings")

        #self.SavePositionListBtn.clicked.connect(self.savePositions)

        self.tabs = dict()

    @pyqtSlot()
    def AddTabs(self):
        for device_id in globals.thorlabs_device_list.keys():
            if device_id[:2] == "55":
                new_rotation_mount = RotationMountWidget(device_id)
                self.tabs[device_id] = new_rotation_mount
                self.RotationMountSelection.addTab(new_rotation_mount, f"{device_id}")
        return

    def calculatePositionCombinations(self):
        # No mount positions saved
        if len(globals.rotation_mount_positions) == 0:
            return

        # Creating unique identifiers for every position of each mount
        all_rotation_mount_positions = list()
        for mount_id, positions in globals.rotation_mount_positions.items():
            pos_ids = list()
            for pos in positions:
                pos_ids.append(f"{mount_id}_{pos}")
            all_rotation_mount_positions.append(pos_ids)

        for unique_pos_combination in product(*all_rotation_mount_positions):
            pos_combination_id = ""
            pos_combination = dict()

            for i in unique_pos_combination:
                mount_id = i.split('_')[0]
                pos = i.split('_')[1]
                pos_combination[mount_id] = pos
                pos_combination_id += f"{pos}_"

            globals.mount_position_combinations[pos_combination_id] = pos_combination


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
