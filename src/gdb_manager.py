import os
import re
import time
import pexpect
from typing import Optional, Any
from pygdbmi.gdbmiparser import parse_response
from uuid import uuid4

import docker_response_status as DckStatus
from compiler_manager import Compiler
from docker_manager import DockerManager
from logger import Logger
from server import DEBUG_DIR, DEBUGGER_MEMORY_LIMIT_MB, EXPECT_VALUES_AFTER_GDB_COMMAND, DEBUGDATA_TEMPLATE

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
			"python import sys; sys.path.insert(0, '/usr/share/gcc-13/python')",
			"python from libstdcxx.v6.printers import register_libstdcxx_printers",
			"python register_libstdcxx_printers(gdb.current_objfile())",
			"skip -gfi /usr/include/*",
			"skip -gfi /usr/include/c++/14/*",
			"skip -gfi /usr/include/c++/14/bits/*",
			"set print address off",
			"break *main",
			"run",
		]

		self.compiled_file_name = ""
		self.process: Optional[pexpect.spawnu] = None
		self.container_name: str = ""
		self.stdin_input_file: str = ""

		self.docker_manager = DockerManager(self.debug_dir, self.gdb_printers_dir)
		self.has_been_run: bool = False

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

		global_variables = self.get_global_variables()
		local_variables = self.get_local_variables()
		local_arguments = self.get_local_arguments()

		self.logger.info(f"Global variables: {global_variables}", self.get_server_output_data)
		self.logger.info(f"Local variables: {local_variables}", self.get_server_output_data)
		self.logger.info(f"Local arguments: {local_arguments}", self.get_local_arguments)

		self.logger.info(f"Current function: {current_function}", self.get_server_output_data)
		self.logger.info(f"Current function's return type: {current_function_return_type}", self.get_server_output_data)
		self.logger.info(f"Current function's parameters types: {current_function_params_types}", self.get_server_output_data)
		self.logger.info(f"Current line: {current_line}", self.get_server_output_data)

		return {
			"is_running": True,
			"timeout": False,
    		"runtime_error": False,
    		"runtime_error_details": "",
			"function": current_function,
			"function_return_type": current_function_return_type,
			"function_parameters_types": current_function_params_types,
			"line": current_line,
			"global_variables": global_variables,
			"local_variables": local_variables,
			"arguments": local_arguments
		}

	# Work in progress...
	def get_local_arguments(self) -> list[dict[str: Any]]:
		args_output = self.send_command("info args")[1]
		local_args = []

		if args_output[0]["payload"] == "No arguments.\n":
			return local_args
		
		return local_args

	def get_local_variables(self) -> list[dict[str: Any]]:
		local_output = self.send_command("info locals")[1]
		local_variables = []

		if local_output[0]["payload"] == "No locals.\n":
			return local_variables

		for local in local_output:
			try:
				variable_name = local["payload"].split('=')[0][:-1]

				p_output = self.send_command(f"p {variable_name}")[1]
				p_match = re.match(r"[a-zA-Z 0-9$]+=(.*)", p_output[0]["payload"])
				variable_value = p_match.group(1)[1:]

				whatis_output = self.send_command(f"whatis {variable_name}")[1]
				whatis_match = re.match(r"[a-zA-Z 0-9]+=(.*)", whatis_output[0]["payload"])
				variale_type = whatis_match.group(1)[1:]

				try:
					amount_of_values = [int(element) for element in whatis_output[0]["payload"][:-1].split(' ')[3].replace('[', ' ').replace(']', '').strip().split(' ')]
				except:
					amount_of_values = [1]
				local_variables.append({"variable_supported": True, "variable_type": variale_type, "variable_name": variable_name, "variable_value": variable_value, "amount_of_values": amount_of_values})

			except Exception as e:
				self.logger.warn(f"Local variable {local} couln't be displayed... | {e.__class__.__name__}: {e}", self.get_local_variables)
				local_variables.append({"variable_supported": False, "variable_type": "", "variable_name": "", "variable_value": "", "amount_of_values": ""})

		return local_variables

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
					global_variables.append(self.format_a_variable(variables_output[k]["payload"].split('\t')[1][:-1]))
					k+=1
				break

		return global_variables

	def format_a_variable(self, gdb_output) -> dict[str: Any]:
		try:
			variable_match = re.match(r"(.+?)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*((?:\[[^\]]*\])*)$", re.sub(r"\s*\*", "* ", gdb_output[:-1]))
			
			variable_type = variable_match.group(1)
			variable_name = variable_match.group(2)

			try:
				amount_of_values = [int(match.group(1)) for match in re.finditer(r'\[(\d+)\]', variable_match.group(3))] or [1]
			except:
				amount_of_values = [1]
			
			p_output = self.send_command(f"p {variable_name}")[1]
			p_match = re.match(r"[a-zA-Z 0-9$]+=(.*)", p_output[0]["payload"])
			variable_value = p_match.group(1)[1:]

			return {"variable_supported": True, "variable_type": variable_type, "variable_name": variable_name, "variable_value": variable_value, "amount_of_values": amount_of_values}
		except Exception as e:
			self.logger.warn(f"Global variable {gdb_output} couln't be displayed... | {e.__class__.__name__}: {e}", self.format_a_variable)
		
		return {"variable_supported": False, "variable_type": "", "variable_name": "", "variable_value": "", "amount_of_values": ""}

	def step(self) -> bool:
		self.send_command("step")
		status, program_output = self.send_command("info program")

		if status == "timeout":
			out = dict(DEBUGDATA_TEMPLATE)
			out["is_running"] = False
			out["timeout"] = True
			self.stop()
			return out
		
		if program_output[0]["payload"] == "[Inferior 1 (process 14) exited normally]\n":
			out = dict(DEBUGDATA_TEMPLATE)
			out["is_running"] = False
			self.stop()
			return out
		
		if len(program_output) > 1 and program_output[1]["payload"].startswith(" received signal SIG"):
			out = dict(DEBUGDATA_TEMPLATE)
			out["is_running"] = False
			out["runtime_error"] = True
			out["runtime_error_details"] = program_output[1]["payload"][len(" received signal "):-1]
			self.stop()
			return out

		return_value = self.get_server_output_data()
		return_value["is_running"] = True
		return return_value

	def send_command(self, command: str, whole_output: bool = False) -> tuple[str, list[dict[str: Any]]]:
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
			if command == "run" and self.stdin_input_file:
				command = f"run < {self.stdin_input_file}"

			self.process.sendline(command)

			which_response = EXPECT_VALUES_AFTER_GDB_COMMAND[self.process.expect_exact(EXPECT_VALUES_AFTER_GDB_COMMAND)]
			
			self.logger.spam(f"Command {command} was successfully sent to gdb process!", self.send_command)

		except pexpect.TIMEOUT:
			self.logger.warn(f"Timeout from command {command}", self.send_command)
			return ("timeout", {})

		except Exception as e:
			self.logger.alert(f"Couldn't send {command} command to gdb process | {e.__class__.__name__}: {e}", self.send_command)

		return (which_response, self.get_formatted_gdb_output(whole_output))

	def run(self, input_: str) -> tuple[int, bytes]:
		'''
		Runs debug process (gdb).
		:param input_: stdin to debugged process
		'''

		self.logger.debug("Compiling for debugging", self.run)

		output_file_name, stdout = self.compiler.compile(self.input_file_name)

		if not os.path.exists(os.path.join(self.debug_dir, output_file_name)):
			self.has_been_run = True # If it fails, it should be cleaned
			return (-1, stdout)

		self.container_name = str(uuid4())
		with open(f"{self.debug_dir}/input_{self.container_name}.txt", "w") as f:
			f.write(input_)
		self.stdin_input_file = f"input_{self.container_name}.txt"

		self.logger.debug("Building docker container", self.run)

		self.compiled_file_name = output_file_name
		status, stdout = self.docker_manager.build_for_debugger(self.compiled_file_name, self.input_file_name, self.stdin_input_file)

		self.logger.debug(f"docker build debugger: {status}", self.run)
		self.logger.spam(f"{stdout}", self.run)

		if status in [DckStatus.docker_build_error, DckStatus.internal_docker_manager_error]:
			self.has_been_run = True # If it fails, it should be cleaned
			self.logger.alert(f"Building error: {status}", self.run)
			return (-2, stdout)

		self.process = self.docker_manager.run_for_debugger(self.container_name, DEBUGGER_MEMORY_LIMIT_MB)

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
		
		self.has_been_run = True

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
