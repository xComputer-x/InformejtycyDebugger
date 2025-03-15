import os
import subprocess
from os.path import join

from logger import Logger
from server import MAX_COMPILATION_ERROR_MESSAGE_LENGTH, COMPILATION_TIMEOUT

'''
This function shortens compilation errors (C++ standard library errors suck)
'''
def shorten_bytes(a: bytes) -> bytes:
	out = bytes()
	lines = a.split(b'\n')

	if len(lines) <= MAX_COMPILATION_ERROR_MESSAGE_LENGTH:
		return a
	
	for i in range(MAX_COMPILATION_ERROR_MESSAGE_LENGTH):
		out += lines[i]+b'\n'
	out += b"...and " + bytes(str(len(lines[MAX_COMPILATION_ERROR_MESSAGE_LENGTH:])), "utf-8") + b" line(s) more"

	return out

class Compiler:
	"""
	Class for code compilation
	"""
	def __init__(self, logger: Logger, compiler: str, input_dir: str, debug_output_dir: str):
		"""
		:param compiler: A string that represents the compiler used in commands. Usually g++ or clang++
		:param input_dir: Directory that contains the source code files
		:param output_dir: Directory that will contain the compiled files
		:param logger: Logger instance
		"""
		self.logger = logger
		self.compiler = compiler
		self.input_dir = input_dir
		self.debug_output_dir = debug_output_dir

	def compile(self, filename: str) -> tuple[str, bytes]:
		"""
		Compile a file
		:param filename: Name of the file to compile (must sit in the input directory)
		:return: Name of the compiled file that sits inside the output directory
		"""
		target_filename = filename[:-3] + 'out'	 # file.cpp -> file.out

		command = [self.compiler, "-ggdb3", "-O0", join(self.input_dir, filename), "-Wshadow", "-Werror", "-fno-eliminate-unused-debug-symbols", "-fno-eliminate-unused-debug-types", "-fvar-tracking-assignments", "-fno-omit-frame-pointer", "-fno-inline", "-o", os.path.abspath(join(self.debug_output_dir, target_filename))]

		stdout = bytes()

		try:
			stdout = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=COMPILATION_TIMEOUT).stderr
			stdout = shorten_bytes(stdout)
		except FileNotFoundError:
			self.logger.alert(f"{self.compiler} compiler is not installed!", self.compile)
		except subprocess.TimeoutExpired:
			stdout = b"Your program must compile under %b seconds!" % str(COMPILATION_TIMEOUT).encode("ascii")

		return (target_filename, stdout)
