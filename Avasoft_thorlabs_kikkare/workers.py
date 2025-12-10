from PyQt6.QtCore import QThread, QWaitCondition, QMutex, pyqtSignal
import time
from utils import save_to_new_file, read_shutter_timers

class MeasurementWorker(QThread):
    data_ready = pyqtSignal(list, list)
    measurement_finished = pyqtSignal()

    def __init__(self, avaspec: AvaspecController, thorlabs: ThorlabsController,
                 measurement_mode="Scope", measurement_type="Single", filename="result"):
        super().__init__()
        self.avaspec = avaspec
        self.thorlabs = thorlabs
        self.measurement_mode = measurement_mode
        self.measurement_type = measurement_type
        self.filename = filename
        self.running = True
        self.paused = False
        self.pause_cond = QWaitCondition()
        self.mutex = QMutex()

    def run(self):
        measurement_func = self.avaspec.measure_scope
        if self.measurement_mode == "Absorbance":
            measurement_func = self.avaspec.measure_absorbance
        elif self.measurement_mode == "Transmittance":
            measurement_func = self.avaspec.measure_transmittance
        else:
            measurement_func = self.avaspec.measure_scope

        if self.measurement_type == "Continuous":
            self.run_continuous(measurement_func)
        elif self.measurement_type == "Series":
            self.run_series(measurement_func)
        elif self.measurement_type == "Reference":
            self.run_reference()
        else:
            self.run_single(measurement_func)

    def run_single(self, meas_function):
        self.avaspec.ttl_on()
        QtTest.QTest.qWait(100)

        wl, data = meas_function()
        self.data_ready.emit(wl, data)
        time.sleep(0.01)

        self.avaspec.ttl_off()
        QtTest.QTest.qWait(100)

        self.measurement_finished.emit()

    def run_continuous(self, meas_function):
        self.avaspec.ttl_on()
        QtTest.QTest.qWait(100)

        while self.running:
            wl, data = meas_function()
            self.data_ready.emit(wl, data)
            time.sleep(0.01)

        self.avaspec.ttl_off()
        QtTest.QTest.qWait(100)

    def run_series(self, meas_function):
        self.thorlabs.solenoid_open_timers = read_shutter_timers()

        cumulative_time = 0

        for t in self.thorlabs.solenoid_open_timers:
            if not self.running:
                break
            self.wait_if_paused()

            """ #0 Setting default rotation mount positions in preparation for illumination """
            for mount_id, pos in self.thorlabs.mount_default_angles.items():
                self.thorlabs.set_mount_pos(mount_id, pos)

            """ #1 Sample illumination """
            self.thorlabs.open_shutter("68250034")
            for i in range(int(t * 10)):
                if not self.running:
                    break
                if self.paused:
                    self.thorlabs.close_shutter("68250034")
                self.wait_if_paused()
                if not self.paused:
                    self.thorlabs.open_shutter("68250034")
                QtTest.QTest.qWait(t * 100)
            self.thorlabs.close_shutter("68250034")

            cumulative_time += t

            for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():
                """ #2 Setting rotation mount positions for measurement """
                for mount_id, position in pos_combination.items():
                    self.thorlabs.set_mount_pos(mount_id, int(position))

                """ #3 Measurement """
                self.avaspec.ttl_on()
                QtTest.QTest.qWait(100)

                wl, data = meas_function(pos_combination_id)

                self.avaspec.ttl_off()
                QtTest.QTest.qWait(100)

                save_to_new_file(f"{self.filename}_{cumulative_time}s_{pos_combination_id}",
                              f"Results_{self.measurement_mode}", wl, data)

                self.data_ready.emit(wl, data)

        self.measurement_finished.emit()

    def run_reference(self):
        for pos_combination_id, pos_combination in self.thorlabs.mount_position_combos.items():
            for mount_id, position in pos_combination.items():
                self.thorlabs.set_mount_pos(mount_id, int(position))

            wl, data = self.avaspec.save_reference(pos_combination_id)

            self.data_ready.emit(wl, data)

        self.measurement_finished.emit()

    def stop(self):
        self.running = False
        self.resume()
        self.wait()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False
        self.pause_cond.wakeAll()

    def wait_if_paused(self):
        self.mutex.lock()
        while self.paused:
            self.pause_cond.wait(self.mutex)
        self.mutex.unlock()
