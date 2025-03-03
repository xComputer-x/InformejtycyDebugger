# This file must be inside /server dictionary,
# otherwise python runned in docker raises an error.
from typing import Any

IP: str = "127.0.0.1"
PORT: int = 5000
RECEIVED_DIR: str = "./received"
DEBUG_DIR: str = "./received"
GDB_PRINTERS_DIR: str = "./gdb_printer"
SECRET_KEY: str = "gEe_5+aBG6;{4#X[bK^]k!w,mCLU-Mr" # Secret key used by flask_socketio for security
RECEIVE_DEBUG_PING_TIME: int = 15 # After what time will not pinged Debugger class be deleted
CLEANING_UNUSED_DBG_PROCESSES_TIME: int = 5 # How often should Debugger classes be checked for possible cleaning
MAX_COMPILATION_ERROR_MESSAGE_LENGTH: int = 20 # How many bytes of error can be displayed
DEBUGGER_MEMORY_LIMIT_MB: int = 128 # Memory limit for debugging process in megabytes
DEBUGGER_TIMEOUT: int = 5 # After what time will pexpect timeout
EXPECT_VALUES_AFTER_GDB_COMMAND: list[str] = ["^done", "^error", "^running", "^connected", "^exit"]

STARTED_DEBUGGING_RESPONSE_TEMPLATE: dict[str: Any] = {
    "authorization": "", "compilation_error": False, "compilation_error_details": "",
    "global_variables": {}, "function": "", "function_type": "", "line": "", "local_variables": {}
}
DEBUG_ACTION_RESPONSE_TEMPLATE: dict[str: Any] = {
    "is_running": True, "function": "", "function_type": "", "line": "", "local_variables": {}
}