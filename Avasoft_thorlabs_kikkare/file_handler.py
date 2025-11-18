import os
from dotenv import load_dotenv
load_dotenv()
PROJECT_PATH = str(os.environ["PROJECT_PATH"])

def saveToNewFile(file_name, folder, x, y):
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

    complete_file_path = os.path.join(PROJECT_PATH, folder)

    if not os.path.exists(f"{complete_file_path}"):
        os.makedirs(f"{complete_file_path}")

    try:
        with open(f"{complete_file_path}\\{file_name}.txt", "w") as fh:
            for n in range(len(y)):
                fh.write(f"{x[n]:.1f}\t{y[n]}\n")
    except IndexError:
        return


def readShutterTimers():
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


def readSpectrumFile(parent, file_name):
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
