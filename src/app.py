import os
import sys
import time
import eventlet
from threading import Thread, Lock
from flask import Flask, request, Response
from flask_socketio import SocketIO, emit
from uuid import uuid4

from server import IP, PORT, RECEIVED_DIR, DEBUG_DIR, GDB_PRINTERS_DIR, SECRET_KEY, RECEIVE_DEBUG_PING_TIME, CLEANING_UNUSED_DBG_PROCESSES_TIME, DEBUGDATA_TEMPLATE
from compiler_manager import Compiler
from gdb_manager import GDBDebugger
from logger import Logger
from flask_cors import CORS

app = Flask(__name__, static_url_path="", static_folder="static/")
app.config["SECRET_KEY"] = SECRET_KEY
socketio = SocketIO(app, async_mode="eventlet")
CORS(app)

# To nicely display messages
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
logger = Logger(display_logs=True)

# Make sure received directory exists
os.makedirs(RECEIVED_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

# To make sure app.config["debug_processes"] wouldn't be used by two processes in the same time
debug_processes_lock = Lock()

'''
Server functions
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
				if not app.config["debug_processes"][auth].process: # when debug process container is still building
					app.config["debug_processes"][auth].ping()

				if time.time() - app.config["debug_processes"][auth].last_ping_time >= RECEIVE_DEBUG_PING_TIME:
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
To be executed, after the server has started
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
Flask & SocketIO functions
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

	run_exit_code, stdout = debugger_class.run(data["input"])

	emit_name = "started_debugging"
	data_to_be_sent: dict[str: str | bool] = dict(DEBUGDATA_TEMPLATE)

	if run_exit_code == -1:
		data_to_be_sent["compilation_error"] = True
		data_to_be_sent["compilation_error_details"] = stdout.decode("utf-8")
		logger.spam(f"Emitted \"start_debugging\" (with compilation_error) to {request.sid}", handle_debugging)

	elif run_exit_code == -2:
		emit_name = "stopped_debugging"
		data_to_be_sent = {}
		logger.spam(f"Emitted \"stopped_debugging\" to {request.sid}", handle_debugging)

	else:
		data_to_be_sent["authorization"] = auth
		logger.spam(f"Emitted \"start_debugging\" to {request.sid}", handle_debugging)

	emit(emit_name, data_to_be_sent)

	debug_data = debugger_class.get_server_output_data()
	debug_data["status"] = "ok"
	emit("debug_data", debug_data)

# Captures debug class ping. Used to keep debug class alive
@socketio.on('ping')
def handle_debug_ping(data: dict[str: str]) -> None:
	if not "authorization" in data:
		emit("No authorization in request")
		return

	authorization = data["authorization"]
	logger.spam(f"Client pinged debugger with authorization: {authorization}", handle_debug_ping)

	with debug_processes_lock:
		if not check_if_process_alive(authorization):
			emit("pong", {"status": "invalid authorization (or process might have been stopped)"})
			logger.spam(f"Emitted \"pong\" (with invalid authorization) to {request.sid}", handle_debug_ping)
		else:
			app.config["debug_processes"][authorization].ping()

			emit("pong", {"status": "ok"})
			logger.spam(f"Emitted \"pong\" to {request.sid}", handle_debug_ping)

# Captures debugging step
@socketio.on("step")
def handle_stepping(data: dict[str: str]) -> None:
	if not "authorization" in data:
		emit("No authorization in request")
		return

	authorization = data["authorization"]
	logger.spam(f"Client requested stepping with authorization: {authorization}", handle_stepping)

	with debug_processes_lock:
		if not check_if_process_alive(authorization):
			emit("debug_data", {"status": "invalid authorization (or process might have been stopped)"})
			logger.spam(f"Emitted \"debug_data\" (with invalid authorization) to {request.sid}", handle_stepping)
		else:
			output = app.config["debug_processes"][authorization].step()
			output["status"] = "ok"

			emit("debug_data", output)
			logger.spam(f"Emitted \"debug_data\" to {request.sid}", handle_stepping)

# Captures debugging stop
@socketio.on("stop")
def handle_stopping(data: dict[str: str]) -> None:
	if not "authorization" in data:
		emit("No authorization in request")
		return
	
	authorization = data["authorization"]
	logger.spam(f"Client requested stopping with authorization: {authorization}", handle_stepping)

	with debug_processes_lock:
		if not check_if_process_alive(authorization):
			emit("debug_data", {"status": "invalid authorization (or process might have been stopped)"})
			logger.spam(f"Emitted \"debug_data\" (with invalid authorization) to {request.sid}", handle_stepping)
		else:
			output = app.config["debug_processes"][authorization].stop()
			del app.config["debug_processes"][authorization]
			output["status"] = "ok"

			emit("debug_data", output)
			logger.spam(f"Emitted \"debug_data\" to {request.sid}", handle_stepping)

'''
Running the server
'''

if __name__ == "__main__":
	socketio.run(app, host=IP, port=PORT)
