# This file must be inside /server dictionary,
# otherwise python runned in docker raises an error.

IP: str = "127.0.0.1"
PORT: int = 5000
RECEIVED_DIR: str = "../received"
DEBUG_DIR: str = "../received/debug"
GDB_PRINTERS_DIR: str = "../gdb_printer"
SECRET_KEY: str = "gEe_5+aBG6;{4#X[bK^]k!w,mCLU-Mr" # Secret key used by flask_socketio for security
RECEIVE_DEBUG_PING_TIME: int = 15 # After what time will not pinged Debugger class be deleted
CLEANING_UNUSED_DBG_PROCESSES_TIME: int = 5 # How often should Debugger classes be checked for possible cleaning
