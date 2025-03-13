import os
import re
import pexpect
from typing import Optional, Any
from pygdbmi.gdbmiparser import parse_response
from uuid import uuid4
from time import time

import docker_response_status as DckStatus
from compiler_manager import Compiler
from docker_manager import DockerManager
from logger import Logger
from server import DEBUG_DIR, DEBUGGER_MEMORY_LIMIT_MB, EXPECT_VALUES_AFTER_GDB_COMMAND, DEBUGDATA_TEMPLATE

class GDBDebugger:
	'''
	Class for managing debug process (gdb).
	'''

	def __init__(self, logger: Logger, compiler: Compiler, debug_dir: str, gdb_printers_dir: str, input_file_name: str, ip: str) -> None:
		self.logger = logger
		self.compiler = compiler
		self.received_dir = self.compiler.input_dir
		self.debug_dir = debug_dir
		self.gdb_printers_dir = gdb_printers_dir
		self.input_file_name = input_file_name
		self.ip = ip

		self.last_ping_time: int = time() # time in seconds from the last time client pinged this class

		self.gdb_init_input = [
			"python import sys; sys.path.insert(0, '/usr/share/gcc/13/python')",
			"python from libstdcxx.v6.printers import register_libstdcxx_printers",
			"python register_libstdcxx_printers(None)",
			"skip -gfi /usr/include/*",
			"skip -gfi /usr/include/c++/14/*",
			"skip -gfi /usr/include/c++/14/bits/*",
			"break *main",
			"run"
		]

		self.compiled_file_name = ""
		self.process: Optional[pexpect.spawnu] = None
		self.container_name: str = ""
		self.stdin_input_file: str = ""

		self.docker_manager = DockerManager(self.debug_dir, self.gdb_printers_dir)
		self.has_been_initialized: bool = False # Was init_process run

	def ping(self) -> None:
		'''
		Updates last time, the class was pinged.
		'''
		self.last_ping_time = time()
	
	def get_formatted_gdb_output(self, whole_output: bool = False, catch_stdout: bool = False) -> tuple[list[dict[str:Any]], list[dict[str: Any]]]:
		outputs = []
		program_stdout = []
		for line in self.process.before.split('\n'):
			output = parse_response(line)
			if not whole_output and output["type"] == "console":
				outputs.append(output)
			elif catch_stdout and output["type"] == "output":
				program_stdout.append(output)
			elif whole_output:
				outputs.append(output)
		return (outputs, program_stdout)
	
	def get_server_output_data(self) -> dict[str: Any]:
		frame_output = self.send_command("frame")[1][-2:]
		frame_match = re.match(r".+\s+((.+::)+)*([a-zA-Z_0-9]+).*\s+\(.*\).+:(\d+)", frame_output[0]["payload"])
		current_function = frame_match.group(3)
		current_line = int(frame_match.group(4))

		whatis_output = self.send_command(f"whatis {current_function}")[1]
		whatis_match = re.match(r".+=\s+(.+)\s+\(.+", whatis_output[0]["payload"])
		current_function_return_type = whatis_match.group(1)

		global_variables = self.get_global_variables()
		local_variables = self.get_local_variables()
		local_arguments = self.get_local_arguments()

		self.logger.info(f"Global variables: {global_variables}", self.get_server_output_data)
		self.logger.info(f"Local variables: {local_variables}", self.get_server_output_data)
		self.logger.info(f"Local arguments: {local_arguments}", self.get_local_arguments)

		self.logger.info(f"Current function: {current_function}", self.get_server_output_data)
		self.logger.info(f"Current function's return type: {current_function_return_type}", self.get_server_output_data)
		self.logger.info(f"Current line: {current_line}", self.get_server_output_data)

		return {
			"is_running": True,
			"timeout": False,
    		"runtime_error": False,
    		"runtime_error_details": "",
			"function": current_function,
			"function_return_type": current_function_return_type,
			"line": current_line,
			"global_variables": global_variables,
			"local_variables": local_variables,
			"arguments": local_arguments
		}

	def get_local_arguments(self) -> list[dict[str: Any]]:
		return self.get_non_global_variables("args", "No arguments.\n")

	def get_local_variables(self) -> list[dict[str: Any]]:
		return self.get_non_global_variables("local", "No locals.\n")

	def get_non_global_variables(self, what_variable_type: str, no_smth_message: str) -> list[dict[str: Any]]:
		output = self.send_command(f"info {what_variable_type}")[1]
		variables = []

		if output[0]["payload"] == no_smth_message:
			return []

		for var in output:
			try:
				variable_name = var["payload"].split('=')[0][:-1]

				p_output = self.send_command(f"p {variable_name}")[1]
				p_match = re.match(r"[a-zA-Z 0-9$]+=(.*)", p_output[0]["payload"])
				variable_value = p_match.group(1)[1:]

				whatis_output = self.send_command(f"whatis {variable_name}")[1]
				whatis_match = re.match(r"[a-zA-Z 0-9]+=(.*)", whatis_output[0]["payload"])
				variale_type = whatis_match.group(1)[1:]

				whatis_match = re.match(r"(.+\s+=\s+.+\s)((\[\d+\])+)", whatis_output[0]["payload"])

				if not whatis_match:
					amount_of_values = [1]
				else:
					amount_of_values = [int(element) for element in whatis_match.group(2)[1:-1].split('][')]
					
				variables.append({"variable_supported": True, "variable_type": variale_type, "variable_name": variable_name, "variable_value": variable_value, "amount_of_values": amount_of_values})

			except Exception as e:
				self.logger.warn(f"{what_variable_type} variable {var} couln't be displayed... | {e.__class__.__name__}: {e}", self.get_non_global_variables)
				variables.append({"variable_supported": False, "variable_type": "", "variable_name": "", "variable_value": "", "amount_of_values": ""})

		return variables

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

	def check_state_after_move(self, program_stdout: list[dict[str: Any]]) -> dict[str: Any]:
		status, program_output = self.send_command("info program")

		if status == "timeout":
			out = dict(DEBUGDATA_TEMPLATE)
			out["is_running"] = False
			out["timeout"] = True
			self.stop()
			return out

		for output in program_output:
			if output["payload"] == "The program being debugged is not being run.\n":
				out = dict(DEBUGDATA_TEMPLATE)
				out["is_running"] = True
				out["additional_gdb_information"] = f"Błąd GDB: należy uruchomić debugowany program, aby móc wykonywać inne komendy"
				return out
			
			if output["payload"] == "[Inferior 1 (process 14) exited normally]\n":
				out = dict(DEBUGDATA_TEMPLATE)
				out["is_running"] = False
				self.stop()
				return out
			
			if output["payload"].startswith(" received signal"):
				out = dict(DEBUGDATA_TEMPLATE)
				out["is_running"] = False
				out["runtime_error"] = True
				out["runtime_error_details"] = program_output[1]["payload"][len(" received signal "):-1]
				self.stop()
				return out

		return_value = self.get_server_output_data()
		return_value["is_running"] = True
		return_value["stdout"] = program_stdout
		return return_value

	def change_breakpoints(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> list[int]:
		for bp in add_breakpoints:
			break_output = self.send_command(f"break {bp}")[1]
			self.logger.spam(break_output, self.change_breakpoints)
		
		for bp in remove_breakpoints:
			clear_output = self.send_command(f"clear {bp}")[1]
			self.logger.spam(clear_output, self.change_breakpoints)

	def step(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> dict[str: Any]:
		self.change_breakpoints(add_breakpoints, remove_breakpoints)
		program_stdout = self.send_command("step", catch_stdout=True)[2]
		return self.check_state_after_move(program_stdout)

	def run(self) -> dict[str: Any]:
		program_stdout = self.send_command("run", catch_stdout=True)[2]
		return self.check_state_after_move(program_stdout)
	
	def continue_(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> dict[str: Any]:
		self.change_breakpoints(add_breakpoints, remove_breakpoints)
		program_stdout = self.send_command("continue", catch_stdout=True)[2]
		return self.check_state_after_move(program_stdout)

	def finish(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> dict[str: Any]:
		self.change_breakpoints(add_breakpoints, remove_breakpoints)
		program_stdout = self.send_command("finish", catch_stdout=True)[2]
		return self.check_state_after_move(program_stdout)

	def send_command(self, command: str, whole_output: bool = False, catch_stdout: bool = False) -> tuple[str, list[dict[str: Any]]] | tuple[str, list[dict[str: Any]], list[dict[str: Any]]]:	
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

		formatted_output, program_stdout = self.get_formatted_gdb_output(whole_output, catch_stdout)
		if catch_stdout:
			return (which_response, formatted_output, program_stdout)
		return (which_response, formatted_output)

	def send_initializing_commands(self, commands: list[str]) -> None:
		self.logger.debug(f"Sending initalizing commands", self.init_process)
		for command in commands:
			if commands == "run": self.process.sendline(f"run < {self.stdin_input_file}")
			else: self.process.sendline(command)
		self.process.expect_exact("^running")

	def init_process(self, input_: str) -> tuple[int, bytes]:
		'''
		Runs debug process (gdb).
		:param input_: stdin to debugged process
		'''

		self.logger.debug("Compiling for debugging", self.init_process)

		output_file_name, stdout = self.compiler.compile(self.input_file_name)

		if not os.path.exists(os.path.join(self.debug_dir, output_file_name)):
			self.has_been_initialized = True # If it fails, it should be cleaned
			return (-1, stdout)

		self.container_name = str(uuid4())
		with open(f"{self.debug_dir}/input_{self.container_name}.txt", "w") as f:
			f.write(input_)
		self.stdin_input_file = f"input_{self.container_name}.txt"

		self.logger.debug("Building docker container", self.init_process)

		self.compiled_file_name = output_file_name
		status, stdout = self.docker_manager.build_for_debugger(self.compiled_file_name, self.input_file_name, self.stdin_input_file)

		self.logger.debug(f"docker build debugger: {status}", self.init_process)
		self.logger.spam(f"{stdout}", self.init_process)

		if status in [DckStatus.docker_build_error, DckStatus.internal_docker_manager_error]:
			self.has_been_initialized = True # If it fails, it should be cleaned
			self.logger.alert(f"Building error: {status}", self.init_process)
			return (-2, stdout)

		self.process = self.docker_manager.run_for_debugger(self.container_name, DEBUGGER_MEMORY_LIMIT_MB)

		try:
			self.process.expect_exact("(gdb)")
			self.logger.spam(self.process.before, self.init_process)
			self.logger.debug(f"Process has been correctly started!", self.init_process)
		except:
			self.logger.spam(self.process.before, self.init_process)
			self.logger.alert("Starting went wrong...", self.init_process)

		self.send_initializing_commands(self.gdb_init_input)

		self.has_been_initialized = True

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
