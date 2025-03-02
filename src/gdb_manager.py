import os
import time
import pexpect
from uuid import uuid4
from pprint import pprint
from typing import Optional

import docker_response_status as DckStatus
from compiler_manager import Compiler
from docker_manager import DockerManager
from logger import Logger
from server import DEBUGGER_MEMORY_LIMIT_MB

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
			"set debuginfod enabled off",
			"python",
			"import sys",
			"sys.path.insert(0, '/usr/share/gcc/python/')",
			"from libstcxx.v6.printers import register_libstdcxx_printers",
			"register_libstdcxx_printers(None)",
			"end",
			"break main",
			"run"
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

	def pprint_response(self, response: dict) -> None:
		pprint(response)

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
		status, stdout = self.docker_manager.build_for_debugger(self.compiled_file_name)

		self.logger.debug(f"docker build debugger: {status}", self.run)
		self.logger.spam(f"{stdout}", self.run)

		if status in [DckStatus.docker_build_error, DckStatus.internal_docker_manager_error]:
			self.logger.alert(f"Building error: {status}", self.run)
			return (-2, stdout)

		self.process, self.container_name, self.stdin_input_file = self.docker_manager.run_for_debugger(input_, DEBUGGER_MEMORY_LIMIT_MB)

		try:
			self.process.expect_exact("(gdb)")
			self.logger.debug(f"Process has been correctly started!", self.run)
		except:
			self.logger.alert("Starting went wrong...", self.run)

		self.logger.spam(self.process.before, self.run)

		return (0, bytes())

	def stop(self) -> None:
		'''
		Stops debug process (gdb) and deinitalizes the class.
		'''
		self.logger.debug(f"Stopping container {self.container_name}", self.stop)

		if self.compiled_file_name:
			os.remove(os.path.join(self.debug_dir, self.compiled_file_name))
			self.compiled_file_name = ""
		
		if os.path.exists(os.path.join(self.received_dir, self.input_file_name)):
			os.remove(os.path.join(self.received_dir, self.input_file_name))

		if os.path.exists(os.path.join(self.debug_dir, self.stdin_input_file)):
			os.remove(os.path.join(self.debug_dir, self.stdin_input_file))

		if self.process:
			self.process.close(force=True)
			self.process = None
		self.docker_manager.stop_container(self.container_name)
