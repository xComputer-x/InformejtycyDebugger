from __future__ import unicode_literals

import pexpect
import subprocess
from uuid import uuid4

import docker_response_status as DckStatus

class DockerManager():
	
	def __init__(self, debug_dir: str, gdb_printers_dir: str) -> None:
		self.debug_dir = debug_dir
		self.gdb_printers_dir = gdb_printers_dir
		
		self.debug_image_name = "informejtycy_debugger"
	
	'''
	For debugger
	'''

	def build_for_debugger(self, executable_file_name: str) -> tuple[str, bytes]:
		try:
			stdout = subprocess.check_output(["cp", f"{self.gdb_printers_dir}/printers.py", self.debug_dir])
		except:
			return (DckStatus.internal_docker_manager_error, b"")

		content = "\n".join([
			f"# This file was automatically generated by {__name__}",
			f"FROM alpine:latest",
			f"RUN apk add --no-cache gdb",												# Installing gdb
			f"RUN mkdir app",															# Make work directory
			f"RUN addgroup -S appgroup && adduser -S appuser -G appgroup",				# Make user without root permissions
			f"RUN mkdir -p /usr/share/gcc/python/libstdcxx/v6/",						# Making directory for printers.py (gdb pretty print)
			f"COPY ./printers.py /usr/share/gcc/python/libstdcxx/v6/printers.py", 		# Copying printers.py
			f"COPY {executable_file_name} app/a.out",									# Copying executable .out
			f"RUN chown appuser:appgroup /app/a.out",									# User is owner of this executable
			f"RUN chmod 500 /app/a.out",												# Permissions
			f"USER appuser",															# Set current user to created user
		])

		status = ""
		stdout = bytes()

		with open(f"{self.debug_dir}/dockerfile", "w") as f:
			f.write(content)

		try:
			stdout = subprocess.check_output(["docker", "build", "-t", self.debug_image_name, self.debug_dir], stderr=subprocess.STDOUT)
			status = DckStatus.success
		except FileNotFoundError:
			status = DckStatus.internal_docker_manager_error
		except:
			status = DckStatus.docker_build_error

		return (status, stdout)

	def run_for_debugger(self, input_: str, memory_limit_MB: int) -> tuple[pexpect.spawnu, str, str]:
		container_name = str(uuid4())

		with open(f"{self.debug_dir}/input_{container_name}.txt", "w") as f:
			f.write(input_)

		process = pexpect.spawnu("docker", ["run", "--rm", "--cap-drop=ALL", "--cap-add=SYS_PTRACE", "--security-opt", "seccomp=unconfined", "--memory-swap=256m", "--read-only", "-v", "/tmp/tmp", "--cpus=1", "--network=none", "--memory", f"{memory_limit_MB}m", "--name", container_name, "-it", self.debug_image_name, "gdb", "/app/a.out", "--interpreter=mi3"], timeout=5)

		return (process, container_name, f"input_{container_name}.txt")

	'''
	Additional methods.
	'''

	def stop_container(self, container_name: str) -> None:
		subprocess.run(["docker", "kill", container_name])

	def clear_images(self) -> tuple[str, bytes]:
		status = ""
		stdout = bytes()
		
		try:
			stdout = subprocess.check_output(["docker", "system", "prune"], input='y'.encode('utf-8'))
			status = DckStatus.success
		except Exception as e:
			status = DckStatus.server_error
		
		return (status, stdout)
