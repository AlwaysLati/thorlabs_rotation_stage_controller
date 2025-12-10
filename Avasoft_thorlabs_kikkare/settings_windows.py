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