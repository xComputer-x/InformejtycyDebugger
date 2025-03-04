import os
import re
import time
import pexpect
from typing import Optional, Any
from pygdbmi.gdbmiparser import parse_response

import docker_response_status as DckStatus
from compiler_manager import Compiler
from docker_manager import DockerManager
from logger import Logger
from server import DEBUG_DIR, DEBUGGER_MEMORY_LIMIT_MB, EXPECT_VALUES_AFTER_GDB_COMMAND


'''

If vectors and other C++ standard library structures are not printing nicely,
put this in self.gdb_init_input between "set debuginfod enabled off" and "break main".

"python",
"import sys",
"sys.path.insert(0, '/usr/share/gcc/python/')",
"from libstcxx.v6.printers import register_libstdcxx_printers",
"register_libstdcxx_printers(None)",
"end",

'''

class GDBDebugger:
	'''
	Class for managing debug process (gdb).
	'''

	def __init__(self, logger: Logger, compiler: Compiler, debug_dir: str, gdb_printers_dir: str, input_file_name: str) -> None:
		self.logger = logger
		self.compiler = compiler
		self.received_dir = self.compiler.input_dir
		self.debug_dir = debug_dir
		self.gdb_printers_dir = gdb_printers_dir
		self.input_file_name = input_file_name

		self.last_ping_time: int = time.time() # time in seconds from the last time client pinged this class

		self.gdb_init_input = [
			"set substitute-path /home/adam/repos/InformejtycyDebugger/./received /app",
			"break *main",
			"run",
		]

		self.compiled_file_name = ""
		self.process: Optional[pexpect.spawnu] = None
		self.container_name: str = ""
		self.stdin_input_file: str = ""

		self.docker_manager = DockerManager(self.debug_dir, self.gdb_printers_dir)

	def ping(self) -> None:
		'''
		Updates last time, the class was pinged.
		'''
		self.last_ping_time = time.time()
	
	def get_formatted_gdb_output(self, whole_output: bool = False) -> list[dict[str: Any]]:
		outputs = []
		for line in self.process.before.split('\n'):
			output = parse_response(line)
			if not whole_output and output["type"] == "console":
				outputs.append(output)
			elif whole_output:
				outputs.append(output)
		return outputs
	
	def get_server_output_data(self) -> dict[str: Any]:
		frame_output = self.send_command("frame")[1][-2:]
		current_function = frame_output[0]["payload"].split(' ')[2]
		current_line = int(frame_output[1]["payload"].split('\t')[0]) 

		whatis_output = self.send_command(f"whatis {current_function}")[1]
		current_function_return_type = whatis_output[0]["payload"].split(' ')[2]
		current_function_params_types = whatis_output[0]["payload"].split(' ')[3][:-1]
		current_function_params_types = current_function_params_types if current_function_params_types != "(void)" else "()"

		self.logger.spam(f"Global variables: {self.get_global_variables()}", self.get_server_output_data)

		self.logger.info(f"Current function: {current_function}", self.get_server_output_data)
		self.logger.info(f"Current function's return type: {current_function_return_type}", self.get_server_output_data)
		self.logger.info(f"Current function's parameters types: {current_function_params_types}", self.get_server_output_data)
		self.logger.info(f"Current line: {current_line}", self.get_server_output_data)

	def get_global_variables(self) -> list[dict[str: Any]]:
		variables_output = self.send_command("info variables")[1]
		global_variables = []

		for i in range(len(variables_output)):
			if variables_output[i]["payload"] == "\nNon-debugging symbols:\n":
				break
			
			if variables_output[i]["payload"] == "\nFile " and variables_output[i+1]["payload"].startswith(DEBUG_DIR):
				k = i+1

				while not variables_output[k]["payload"].startswith("\nFile") and not variables_output[k]["payload"] == "\nNon-debugging symbols:\n":
					if variables_output[k]["payload"].startswith(DEBUG_DIR):
						k+=1
						continue
					global_variables.append(self.format_a_variable(variables_output[k]["payload"]))
					k+=1
				break

		return global_variables

	def format_a_variable(self, gdb_output) -> dict[str: Any]:
		try:
			variable_match = re.match(r"(.+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\])*)$", re.sub(r"\s*\*", "* ", gdb_output[:-2].split('\t')[1]))
			
			variable_type = variable_match.group(1)
			variable_name = variable_match.group(2)

			try:
				amount_of_values = [int(match.group(1)) for match in re.finditer(r'\[(\d+)\]', variable_match.group(3))] or 1
			except:
				amount_of_values = 1
			
			p_output = self.send_command(f"p {variable_name}")[1]
			variable_value = p_output[0]["payload"].split('=')[1][1:-1]

			return {"variable_supported": True, "variable_type": variable_type, "variable_name": variable_name, "variable_value": variable_value, "amount_of_values": amount_of_values}
		except Exception as e:
			self.logger.warn(f"Variable {gdb_output} couln't be displayed... | {e.__class__.__name__}: {e}", self.format_a_variable)
		
		return {"variable_supported": False, "variable_type": "", "variable_name": "", "variable_value": "", "amount_of_values": ""}

	def send_command(self, command: str) -> tuple[str, list[dict[str: Any]]]:
		'''
		Executes gdb command.
		:param command: command, to be executed
		:return two strings. The first one telling which response
		was received (member of EXPECT_VALUES_AFTER_GDB_COMMAND
		constant). The second one telling about output received
		by pexpect.
		'''
		which_response: str = ""
		try:
			self.process.sendline(command)

			which_response = EXPECT_VALUES_AFTER_GDB_COMMAND[self.process.expect_exact(EXPECT_VALUES_AFTER_GDB_COMMAND)]
			
			self.logger.spam(f"Command {command} was successfully sent to gdb process!", self.send_command)

		except Exception as e:
			self.logger.alert(f"Couldn't send {command} command to gdb process | {e.__class__.__name__}: {e}", self.send_command)

		return (which_response, self.get_formatted_gdb_output())

	def run(self, input_: str) -> tuple[int, bytes]:
		'''
		Runs debug process (gdb).
		:param input_: stdin to debugged process
		'''

		self.logger.debug("Compiling for debugging", self.run)

		output_file_name, stdout = self.compiler.compile(self.input_file_name)

		if not os.path.exists(os.path.join(self.debug_dir, output_file_name)):
			return (-1, stdout)

		self.logger.debug("Building docker container", self.run)

		self.compiled_file_name = output_file_name
		status, stdout = self.docker_manager.build_for_debugger(self.compiled_file_name, self.input_file_name)

		self.logger.debug(f"docker build debugger: {status}", self.run)
		self.logger.spam(f"{stdout}", self.run)

		if status in [DckStatus.docker_build_error, DckStatus.internal_docker_manager_error]:
			self.logger.alert(f"Building error: {status}", self.run)
			return (-2, stdout)

		self.process, self.container_name, self.stdin_input_file = self.docker_manager.run_for_debugger(input_, DEBUGGER_MEMORY_LIMIT_MB)

		try:
			self.process.expect_exact("(gdb)")
			self.logger.spam(self.process.before, self.run)
			self.logger.debug(f"Process has been correctly started!", self.run)
		except:
			self.logger.spam(self.process.before, self.run)
			self.logger.alert("Starting went wrong...", self.run)

		self.logger.debug(f"Sending initalizing commands", self.run)
		for command in self.gdb_init_input:
			self.logger.spam(self.send_command(command)[1], self.run)
		
		self.get_server_output_data()

		return (0, bytes())

	def stop(self) -> None:
		'''
		Stops debug process (gdb) and deinitalizes the class.
		'''
		self.logger.debug(f"Stopping container {self.container_name}", self.stop)

		if self.compiled_file_name:
			os.remove(os.path.join(self.debug_dir, self.compiled_file_name))
			self.compiled_file_name = ""
		
		if os.path.exists(os.path.join(self.received_dir, self.input_file_name)) and self.input_file_name != "":
			os.remove(os.path.join(self.received_dir, self.input_file_name))

		if os.path.exists(os.path.join(self.debug_dir, self.stdin_input_file)) and self.stdin_input_file != "":
			os.remove(os.path.join(self.debug_dir, self.stdin_input_file))

		self.docker_manager.stop_container(self.container_name)
		if self.process:
			self.process.close(force=True)
			self.process = None
