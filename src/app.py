'''
Server for informejtycy online debugger (https://informejtycy.pl);
Server is made using Flask with Eventlet and SocketIO technology;
Should be run with gunicorn on IP 0.0.0.0 (port 5000 is already in use for checker);
Under the hood, online debugger is GNU GDB with machine interface MI3. To communicate with interactive GDB it uses pexpect module;
Demo can be found on http://127.0.0.1:5000/debugger.html;
'''

import os
import sys
import time
import eventlet
from threading import Thread, Lock
from flask import Flask, request
from flask_socketio import SocketIO, emit
from uuid import uuid4
from typing import Callable, Optional

from server import IP, PORT, RECEIVED_DIR, DEBUG_DIR, GDB_PRINTERS_DIR, SECRET_KEY, RECEIVE_DEBUG_PING_TIME, CLEANING_UNUSED_DBG_PROCESSES_TIME, DEBUGDATA_TEMPLATE
from compiler_manager import Compiler
from gdb_manager import GDBDebugger
from logger import Logger
from flask_cors import CORS

# Flask configuration initialization
app = Flask(__name__, static_url_path="", static_folder="static/")
app.config["SECRET_KEY"] = SECRET_KEY
socketio = SocketIO(app, async_mode="eventlet")
CORS(app)

# To nicely display messages
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
logger = Logger(display_logs=True, display_layer=0)

# Make sure received directory exists
os.makedirs(RECEIVED_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

# To make sure app.config["debug_processes"] wouldn't be used by two processes in the same time
debug_processes_lock = Lock()

'''
================================================
|                                              |
|               Server functions               |
|                                              |
===============================================|
'''

# Creates a .cpp source code file for debugging
def make_cpp_file_for_debugger(code: str) -> tuple[str, str]:
	auth = str(uuid4())
	file_name = f"{auth}.cpp"
	with open(os.path.join(RECEIVED_DIR, file_name), 'w') as f:
		f.write(code)
	return file_name, auth

# Cleans debug processes from app.config["debug_processes"], if they wasn't pinged for a long time
def clean_unused_debug_processes() -> None:
	while True:
		eventlet.sleep(CLEANING_UNUSED_DBG_PROCESSES_TIME)
		with debug_processes_lock:
			for auth in dict(app.config["debug_processes"]): # dict(...) to make copy
				if not app.config["debug_processes"][auth].has_been_run: # when debug process container is still building
					app.config["debug_processes"][auth].ping()

				elif (time.time() - app.config["debug_processes"][auth].last_ping_time >= RECEIVE_DEBUG_PING_TIME	# Not pinged for long enough
						or not app.config["debug_processes"][auth].process											# Debug class was stopped, but not cleaned
						or not app.config["debug_processes"][auth].process.isalive()):								# Process was stopped, but debug class was not stopped
					logger.spam(f"GDBDebugger with '{auth}' wasn't pinged for {RECEIVE_DEBUG_PING_TIME} seconds. Cleaning...", clean_unused_debug_processes)

					app.config["debug_processes"][auth].stop()
					del app.config["debug_processes"][auth]
					
					logger.spam(f"Cleaned successfully!", clean_unused_debug_processes)

def check_if_process_alive(authorization: str) -> bool:
	if not authorization in app.config["debug_processes"]:
		return False

	if not app.config["debug_processes"][authorization].process:
		del app.config["debug_processes"][authorization]
		return False
	
	return True

'''
================================================
|                                              |
| To be executed, after the server has started |
|                                              |
===============================================|
'''

# For logger, in case something is logged outside of function scope
def main() -> None:
	pass

# Setups server, after app.run() is called.
with app.app_context():
	compiler = Compiler(logger, 'g++', RECEIVED_DIR, DEBUG_DIR)
	
	logger.info("Starting cleaning process", main)

	lt = Thread(target=clean_unused_debug_processes)
	lt.start()

	logger.info(f"Cleaning process has started", main)

	# For debugging
	# Server use it to indentify debugging processes
	app.config["debug_processes"]: dict[str: GDBDebugger] = {} # type: ignore

	logger.info(f"Server is running on {IP}:{PORT}", main)

'''
================================================
|                                              |
|         Flask & SocketIO functions           |
|                                              |
===============================================|
'''

# Captures websocket connection for debugging.
@socketio.on('connect')
def handle_connect() -> None:
	logger.info(f"Client connected: {request.sid}", handle_connect)

# Captures websocket disconnection.
@socketio.on('disconnect')
def handle_disconnect() -> None:
	logger.info(f"Client disconnected: {request.sid}", handle_disconnect)

# Captures websocket debugging request.
@socketio.on('start_debugging')
def handle_debugging(data: dict[str: str]) -> None:
	if not "code" in data or not "input" in data:
		emit("No code and/or input in request")
		return
	
	logger.debug(f"Client requested debugging: {request.sid}", handle_debugging)
	logger.debug(f"Data: {data}", handle_debugging)

	file_name, auth = make_cpp_file_for_debugger(data["code"])

	debugger_class = GDBDebugger(logger, compiler, DEBUG_DIR, GDB_PRINTERS_DIR, file_name)
	app.config["debug_processes"][auth] = debugger_class
	run_exit_code, stdout = debugger_class.init_process(data["input"])

	data_to_be_sent: dict[str: str | bool] = dict(DEBUGDATA_TEMPLATE)

	if run_exit_code == -1:
		data_to_be_sent["compilation_error"] = True
		data_to_be_sent["compilation_error_details"] = stdout.decode("utf-8")
		emit("started_debugging", data_to_be_sent)
		logger.spam(f"Emitted \"start_debugging\" (with compilation_error) to {request.sid}", handle_debugging)

	elif run_exit_code == -2:
		data_to_be_sent = {}
		emit("stopped_debugging", data_to_be_sent)
		logger.spam(f"Emitted \"stopped_debugging\" to {request.sid}", handle_debugging)

	else:
		data_to_be_sent["authorization"] = auth
		emit("started_debugging", data_to_be_sent)
		logger.spam(f"Emitted \"start_debugging\" to {request.sid}", handle_debugging)

# Base for debugger actions handling functions
def debugger_action(what_client_did: str, method_name: str, from_: Callable[[dict[str: str]], None], data: dict[str: str], is_expecting_breakpoints: bool = True) -> None:
	if not "authorization" in data:
		emit("debug_data", {"status": "No authorization in request!"})
		return

	if is_expecting_breakpoints:
		if not "add_breakpoints" in data or not "remove_breakpoints" in data: emit("No breakpoints changes in request!"); return
		if type(data["add_breakpoints"]) != list or type(data["add_breakpoints"]) != list: emit("Invalid breakpoints add/remove type!"); return
		
		for bpi in range(len(data["add_breakpoints"])): 
			try:
				data["add_breakpoints"][bpi] = int(data["add_breakpoints"][bpi])
			except:
				emit("debug_data", {"status": "Breakpoints changes should be integers!"})
				return
		
		for bpi in range(len(data["remove_breakpoints"])):
			try:
				data["remove_breakpoints"][bpi] = int(data["remove_breakpoints"][bpi])
			except:
				emit("debug_data", {"status": "Breakpoints changes should be integers!"})
				return

	authorization = data["authorization"]
	logger.spam(f"Client {what_client_did}, with authorization: {authorization}", from_)

	with debug_processes_lock:
		if not check_if_process_alive(authorization):
			emit("debug_data", {"status": "invalid authorization (or process might have been stopped)"})
			logger.spam(f"Emitted \"debug_data\" (with invalid authorization) to {request.sid}", from_)
		else:
			method = getattr(app.config["debug_processes"][authorization], method_name)
			output: Optional[str] = None

			if is_expecting_breakpoints: output = method(data["add_breakpoints"], data["remove_breakpoints"])
			else: output = method()

			if not output:
				output = dict(DEBUGDATA_TEMPLATE)
			output["status"] = "ok"

			emit("debug_data", output)
			logger.spam(f"Emitted \"debug_data\" to {request.sid}", from_)

# Captures debug class ping. Used to keep debug class alive
@socketio.on('ping')
def handle_debug_ping(data: dict[str: str]) -> None:
	debugger_action("pinged debugger class", "ping", handle_debug_ping, data, is_expecting_breakpoints=False)

# Captures running debugged program
@socketio.on("run")
def handle_running(data: dict[str: str]) -> None:
	debugger_action("requested running debugged code", "run", handle_running, data)

# Captures continuing execution
@socketio.on("continue")
def handle_continuing(data: dict[str: str]) -> None:
	debugger_action("requested continuing debugged code", "continue_", handle_continuing, data)

# Captures stepping in debugged code
@socketio.on("step")
def handle_stepping(data: dict[str: str]) -> None:
	debugger_action("requested stepping", "step", handle_stepping, data)

# Captures finishing debugged function
@socketio.on("finish")
def handle_finishing(data: dict[str: str]) -> None:
	debugger_action("requested finishing", "finish", handle_finishing, data)

# Captures debugging stop
@socketio.on("stop")
def handle_stopping(data: dict[str: str]) -> None:
	debugger_action("requested stopping", "stop", handle_stopping, data, is_expecting_breakpoints=False)

'''
================================================
|                                              |
|             Running the server               |
|                                              |
===============================================|
'''

if __name__ == "__main__":
	socketio.run(app, host=IP, port=PORT)
