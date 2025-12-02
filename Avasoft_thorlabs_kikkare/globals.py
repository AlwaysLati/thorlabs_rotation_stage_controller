from collections import defaultdict

""" Avaspec Data """
dev_handle = 0
pixels = 4096
wavelength_full = [0.0] * 4096
wavelength = [0.0] * 4096
spectraldata = [0.0] * 4096
#referencedata = [0.0] * 4096
darkdata = [0.0] * 4096

referencedata = dict()


""" Avaspec  Parameters """
int_time = 5
avg_num = 0
min_wavelength = 0
max_wavelength = 0
smoothing = 3
stopscanning = True

min_integral = 0
max_integral = 0
integral_multiplier = 0

""" Thorlabs Devices"""
thorlabs_device_list = dict()   # "device_id" : Device
rotation_mount_positions = defaultdict(list)   # "device_id" : [position]
mount_position_combinations = defaultdict(dict)
mount_default_angles = dict()

solenoid_open_timers = list()

""" Linkam stuff """
save_every_n = 0
meas_per_RH = 0
save_to_folder = ""

RH_range = [50]
setpoint_tolerance = 0.01
