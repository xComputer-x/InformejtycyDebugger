import os
import ast
import pexpect
from typing import Optional, Any
from pygdbmi.gdbmiparser import parse_response
from uuid import uuid4
from time import time

import docker_response_status as DckStatus
from compiler_manager import Compiler
from docker_manager import DockerManager
from logger import Logger
from server import DEBUG_DIR, DEBUGGER_MEMORY_LIMIT_MB, EXPECT_VALUES_AFTER_GDB_COMMAND

class GDBDebugger:

	def __init__(self, logger: Logger, compiler: Compiler, debug_dir: str, gdb_printers_dir: str, data_extractor_dir: str, input_file_name: str, ip: str) -> None:
		self.logger = logger
		self.compiler = compiler
		self.received_dir = self.compiler.input_dir
		self.debug_dir = debug_dir
		self.gdb_printers_dir = gdb_printers_dir
		self.data_extractor_dir = data_extractor_dir
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
			"run < input > /tmp/output"
		]

		self.compiled_file_name = ""
		self.process: Optional[pexpect.spawnu] = None
		self.container_name: str = ""
		self.stdin_input_file: str = ""

		self.docker_manager = DockerManager(self.debug_dir, self.gdb_printers_dir, self.data_extractor_dir)
		self.has_been_initialized: bool = False # Was init_process run

	def ping(self) -> None:
		'''
		Updates last time, the class was pinged.
		'''
		self.last_ping_time = time()
	
	def get_formatted_gdb_output(self, whole_output: bool = False) -> list[dict[str:Any]]:
		outputs = []
		for line in self.process.before.split('\n'):
			output = parse_response(line)
			if not whole_output and output["type"] == "console":
				outputs.append(output)
			elif whole_output:
				outputs.append(output)
		return outputs

	def check_state_after_move(self) -> dict[str: Any]:
		status, program_output = self.send_command("info program")

		response = self.send_command("source data_extractor.py")[1][0]["payload"]
		out = ast.literal_eval(response)

		if status == "timeout":
			out["is_running"] = False
			out["timeout"] = True
			self.stop()
			return out

		for output in program_output:
			if output["payload"] == "The program being debugged is not being run.\n":
				out["is_running"] = True
				out["additional_gdb_information"] = f"Błąd GDB: należy uruchomić debugowany program, aby móc wykonywać inne komendy"
				break
			
			if output["payload"] == "[Inferior 1 (process 14) exited normally]\n":
				out["is_running"] = False
				self.stop()
				break
			
			if output["payload"].startswith(" received signal"):
				out["is_running"] = False
				out["runtime_error"] = True
				out["runtime_error_details"] = program_output[1]["payload"][len(" received signal "):-1]
				self.stop()
				break

		return out

	def change_breakpoints(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> list[int]:
		if add_breakpoints != []:
			self.send_command_group([f"break {bp}" for bp in add_breakpoints], EXPECT_VALUES_AFTER_GDB_COMMAND)
		if remove_breakpoints != []:
			self.send_command_group([f"clear {bp}" for bp in remove_breakpoints], EXPECT_VALUES_AFTER_GDB_COMMAND)

	def step(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> dict[str: Any]:
		self.change_breakpoints(add_breakpoints, remove_breakpoints)
		self.send_command("step")
		return self.check_state_after_move()

	def run(self) -> dict[str: Any]:
		self.send_command("run")
		return self.check_state_after_move()
	
	def continue_(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> dict[str: Any]:
		self.change_breakpoints(add_breakpoints, remove_breakpoints)
		self.send_command("continue")
		return self.check_state_after_move()

	def finish(self, add_breakpoints: list[int], remove_breakpoints: list[int]) -> dict[str: Any]:
		self.change_breakpoints(add_breakpoints, remove_breakpoints)
		self.send_command("finish")
		return self.check_state_after_move()

	def send_command(self, command: str, whole_output: bool = False) -> tuple[str, list[dict[str: Any]]]:	
		which_response: str = ""
		try:
			self.process.sendline(command)

			which_response = EXPECT_VALUES_AFTER_GDB_COMMAND[self.process.expect_exact(EXPECT_VALUES_AFTER_GDB_COMMAND)]
			
			self.logger.spam(f"Command {command} was successfully sent to gdb process!", self.send_command)

		except pexpect.TIMEOUT:
			self.logger.warn(f"Timeout from command {command}", self.send_command)
			return ("timeout", {})

		except Exception as e:
			self.logger.alert(f"Couldn't send {command} command to gdb process | {e.__class__.__name__}: {e}", self.send_command)

		formatted_output = self.get_formatted_gdb_output(whole_output)
		return (which_response, formatted_output)

	def send_command_group(self, commands: list[str], expect_what: str | list[str]) -> None:
		self.logger.debug(f"Sending group of commands", self.send_command_group)
		for command in commands:
			self.process.sendline(command)
		self.process.expect_exact(expect_what)

	def init_process(self, input_: str) -> tuple[int, bytes]:
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

		self.send_command_group(self.gdb_init_input, "^running")

		self.has_been_initialized = True

		return (0, bytes())

	def stop(self) -> None:
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
