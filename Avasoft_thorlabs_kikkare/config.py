import os
from dotenv import load_dotenv

load_dotenv()
PROJECT_PATH = os.environ["PROJECT_PATH"]
TLABPATH = os.environ["THORLABS_PATH"]
AVAPATH = str(os.environ["AVASPEC_PATH"])