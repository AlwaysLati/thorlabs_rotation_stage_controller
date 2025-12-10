import avaspec_controller
import thorlabs_controller
import workers


main_ui_class, main_baseclass = uic.loadUiType("main_window.ui")
class MainWindow(main_ui_class, main_baseclass):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowTitle("Avaspec / Thorlabs Automation thing")

        # Initializing device controllers
        self.avaspec = AvaspecController()
        self.thorlabs = ThorlabsController()
        self.measurement_thread = None
        self.paused = False

        # Connecting action triggers from the window selection bar to show/hide the specified setting windows
        self.ava_settings_window = AvaSettingWindow()
        self.actionAvasoft.triggered.connect(
            lambda checked: self.toggle_window(self.ava_settings_window)
        )
        self.ava_settings_window.settings_changed.connect(self.avaspec.update_params)
        self.actionAvasoft.setEnabled(False)

        self.mount_settings_window = RotationMountSettingWindow()
        self.actionRotation_Mount.triggered.connect(
            lambda checked: self.toggle_window(self.mount_settings_window)
        )
        self.mount_settings_window.settings_changed.connect(self.thorlabs.update_mount_position_combos)
        self.actionRotation_Mount.setEnabled(False)

        # Initializing button states
        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(False)
        self.StopMeasBtn.setEnabled(False)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)

        # Connecting button events to methods
        self.StartMeasBtn.clicked.connect(self.start_measurement_btn_clicked)
        self.PauseMeasBtn.clicked.connect(self.pause_measurement_btn_clicked)
        self.StopMeasBtn.clicked.connect(self.stop_measurement_btn_clicked)
        self.SaveRefBtn.clicked.connect(self.save_ref_btn_clicked)
        self.SaveDrkBtn.clicked.connect(self.save_dark_btn_clicked)
        self.connectAvasoft.triggered.connect(self.open_comm_btn_clicked)
        self.connectThorlabs.triggered.connect(self.connect_thorlabs_btn_clicked)
        self.fileNameEdit.textChanged.connect(self.save_file_changed)

        self.testRotBtn.clicked.connect(self.change_positions)
        self.testShutterBtn.clicked.connect(self.toggle_shutter)

        # Initializing data plotting
        self.line = None
        self.graph.setBackground("w")
        self.init_plot(None, None, None, "", "")

        self.file_name_to_save = ""

    def closeEvent(self, event):
        """
        Called right before the program is shut down - ensures that all thorlabs devices will be disconnected
        properly. Causes issues with later connectivity otherwise.
        """
        self.stop_measurement_btn_clicked()
        self.thorlabs.disconnect_all()
        event.accept()

    @pyqtSlot()
    def toggle_window(self, window):
        if window.isVisible():
            window.hide()
        else:
            window.show()

    @pyqtSlot()
    def change_positions(self):
        dev_id = "55360064"
        pos_list = self.thorlabs.rotation_mount_positions.get(dev_id)

        if pos_list is None:
            print("Error")
            return

        for pos in pos_list:
            self.thorlabs.set_mount_pos(dev_id, pos)

    @pyqtSlot()
    def toggle_shutter(self):
        self.testShutterBtn.setEnabled(False)
        self.thorlabs.solenoid_open_timers = read_shutter_timers()

        for shutter_open_for in self.thorlabs.solenoid_open_timers:
            self.thorlabs.open_shutter("68250034")
            print(shutter_open_for)
            QtTest.QTest.qWait(shutter_open_for*1000)
            self.thorlabs.close_shutter("68250034")

        self.testShutterBtn.setEnabled(True)

    @pyqtSlot()
    def open_comm_btn_clicked(self):
        """
        Modified method from Avasoft PyQt5 demo. Attempts to connect to an Avaspec spectrometer.

        :return:
        """
        ret = self.avaspec.connect_device()

        if ret == 0:
            QMessageBox.information(self, "Error", "Could not find a device")
            return
        else:
            QMessageBox.information(self, "Info", "Found Serialnumber: " + ret)

            self.StartMeasBtn.setEnabled(True)
            self.SaveRefBtn.setEnabled(True)
            self.SaveDrkBtn.setEnabled(True)
            self.connectAvasoft.setEnabled(False)
            self.actionAvasoft.setEnabled(True)

        return

    @pyqtSlot()
    def connect_thorlabs_btn_clicked(self):
        msg = self.thorlabs.connect_devices()
        QMessageBox.information(self, msg[0], msg[1])

        if msg[0] == "Error":
            return
        else:
            for dev_id, devive in self.thorlabs.device_list.items():
                if dev_id[:2] == "55":
                    mount = self.mount_settings_window.add_tab(dev_id)
                    mount.home_mount_signal.connect(self.thorlabs.home_mount)
                    mount.update_mount_default_angles.connect(self.thorlabs.update_mount_default_angle)
                    mount.update_mount_positions.connect(self.thorlabs.update_mount_positions)

            self.connectThorlabs.setEnabled(False)
            self.actionRotation_Mount.setEnabled(True)

    @pyqtSlot()
    def start_measurement_btn_clicked(self):
        """
        Main method for running all measurements depending on the mode selected.

        :return:
        """

        measurement_mode = self.SelectModeBox.currentText()
        measurement_type = self.SelectTypeBox.currentText()

        self.ava_settings_window.hide()

        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(False)
        self.SelectTypeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        if measurement_mode == "Absorbance":
            y_lim = [0, 3]
        elif measurement_mode == "Transmittance":
            y_lim = [0, 110]
        else:
            y_lim = None

        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, y_lim,
                       "Wavelength (nm)", measurement_mode)

        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop()

        self.measurement_thread = MeasurementWorker(self.avaspec, self.thorlabs,
                                                    measurement_mode, measurement_type,
                                                    self.file_name_to_save)

        self.measurement_thread.data_ready.connect(self.plot)
        self.measurement_thread.measurement_finished.connect(self.stop_measurement_btn_clicked)
        self.measurement_thread.start()

    @pyqtSlot()
    def pause_measurement_btn_clicked(self):
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
        """
        Completely stops all ongoing measurements as well as RH changes

        :return:
        """
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
        """
        Saves and plots reference spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """
        self.ava_settings_window.hide()

        self.StartMeasBtn.setEnabled(False)
        self.PauseMeasBtn.setEnabled(True)
        self.StopMeasBtn.setEnabled(True)
        self.SaveRefBtn.setEnabled(False)
        self.SaveDrkBtn.setEnabled(False)
        self.SelectModeBox.setEnabled(False)
        self.SelectTypeBox.setEnabled(False)
        self.menuBar.setEnabled(False)

        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, None,
                       "Wavelength (nm)", "Scope")

        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop()

        self.measurement_thread = MeasurementWorker(self.avaspec, self.thorlabs,
                                                    "Scope", "Reference",
                                                    self.file_name_to_save)
        self.measurement_thread.measurement_finished.connect(self.stop_measurement_btn_clicked)
        self.measurement_thread.start()

    @pyqtSlot()
    def save_dark_btn_clicked(self):
        """
        Saves and plots dark spectra. Always draws spectra as scope, independent of the mode selected.

        :return:
        """
        self.init_plot(self.avaspec.min_wavelength, self.avaspec.max_wavelength, None,
                       "Wavelength (nm)", "Scope")

        wl, data = self.avaspec.save_dark()
        self.plot(wl, data)

    @pyqtSlot()
    def init_plot(self, min_x, max_x, yrange, x_label, y_label):
        """
        Initialises pyqtgraph with given parameters

        :param min_x: float, lowest x value shown
        :param max_x: float, largest x value shown
        :param yrange: [min_y, max_y]
        :param x_label: str,
        :param y_label: str,
        :return:
        """
        self.graph.clear()

        pen = pg.mkPen(color=(0, 0, 0), width=1.1, style=Qt.PenStyle.SolidLine)
        self.graph.setLabel("left", f"{y_label}")
        self.graph.setLabel("bottom", f"{x_label}")
        if max_x:
            self.graph.setXRange(min_x, max_x)
        if yrange:
            self.graph.setYRange(yrange[0], yrange[1])
        self.graph.showGrid(x=True, y=True)

        self.line = self.graph.plot([0], [0], pen=pen)

    @pyqtSlot()
    def plot(self, x, y):
        self.line.setData(x, y)
        self.repaint()

    @pyqtSlot()
    def update_plot_range(self, min_x, max_x):
        self.graph.setXRange(min_x, max_x)

    def save_file_changed(self):
        self.file_name_to_save = self.fileNameEdit.text()