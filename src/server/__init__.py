# This file must be inside /server dictionary,
# otherwise python runned in docker raises an error.
from typing import Any

IP: str = "127.0.0.1" # IP on which server will be run (only for testing, later unicorn affects this value)
PORT: int = 5000 # Port on which server will be run (only for testing, later unicorn affects this value)
RECEIVED_DIR: str = "./received" # Directory for checker result files (old)
DEBUG_DIR: str = "./received" # Directory for debug files
GDB_PRINTERS_DIR: str = "./gdb_printer" # Directory to printers.py used for pprint in gdb
DATA_EXTRACTOR_DIR: str = "./data_extractor" # Directory to main.py used for extracting debug data
SECRET_KEY: str = "gEe_5+aBG6;{4#X[bK^]k!w,mCLU-Mr" # Secret key used by flask_socketio for security
RECEIVE_DEBUG_PING_TIME: int = 15 # After what time will not pinged Debugger class be deleted
CLEANING_UNUSED_DBG_PROCESSES_TIME: int = 1 # How often should Debugger classes be checked for possible cleaning
MAX_COMPILATION_ERROR_MESSAGE_LENGTH: int = 20 # How many lines of compilation error can be displayed
DEBUGGER_MEMORY_LIMIT_MB: int = 128 # Memory limit for debugging process in megabytes
DEBUGGER_CPU_LIMIT: float = 0.3 # How much percent of CPU can a container use
DEBUGGER_TIMEOUT: int = 5 # After what time will pexpect timeout
EXPECT_VALUES_AFTER_GDB_COMMAND: list[str] = ["^done", "^error", "^running", "^connected", "^exit"] # What pexpect should expect from GDB MI send after command
CGROUP_NAME: str = "informejtycy_debugger.slice" # Name of the cgroup
COMPILATION_TIMEOUT: int = 8 # How long can program compile

INIT_DATA_TEMPLATE: dict[str: str | bool] = {
    "compilation_error": False,
    "compilation_error_details": "",
    "authorization": "",
    "status": "ok"
}
# If custom javascript is used, then "additional_gdb_information" might be also present