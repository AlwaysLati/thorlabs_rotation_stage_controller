import os
from config import PROJECT_PATH


def save_to_new_file(file_name, folder, x, y):
    """
    Saves a list of values to a new file --> overwrites an existing file of the name.

    :param file_name: str, creates a .txt file with this name and saves the spectrum data to it
    :param folder: str, folder to save data to
    :param x [float], input list of spectrum values to save
    :param y [float], input list of time/wavelength values corresponding to spectrum values
    :return:
    """

    complete_file_path = os.path.join(PROJECT_PATH, folder)

    if not os.path.exists(f"{complete_file_path}"):
        os.makedirs(f"{complete_file_path}")

    try:
        with open(f"{complete_file_path}\\{file_name}.txt", "w") as fh:
            for n in range(len(y)):
                fh.write(f"{x[n]:.1f}\t{y[n]}\n")
    except IndexError:
        return


def read_shutter_timers():
    file_output = []

    complete_file_path = os.path.join(PROJECT_PATH, "shutter_timer.txt")
    if not os.path.exists(complete_file_path):
        return []

    try:
        with open(f"{complete_file_path}", "r") as fh:
            for line in fh:
                file_output.append(int(line.strip()))

        return file_output

    except ValueError:
        return []
