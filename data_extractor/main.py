'''
This file extracts data from debugged process.
It is much fastet than sending commands, if you wonder.
'''
import gdb # type: ignore
from typing import Optional, Any

DEBUGDATA_TEMPLATE: dict[str: Any] = {
    "is_running": True,
    "timeout": False,
    "runtime_error": False,
    "runtime_error_details": "",
    "function": "",
    "function_return_type": "",
    "line": 0,
    "global_variables": [],
    "local_variables": [],
    "arguments": [],
    "stdout": ""
}

def format_symbol(frame: gdb.Frame, symbol: gdb.Symbol) -> Optional[dict[str: str]]:
	try:
		name = symbol.name
		type_ = str(symbol.type)
		value = frame.read_var(name).format_string()
		
		if len(value) > 400:
			value = f"{value[:400]}..."
			
		return {"variable_name": name, "variable_type": type_, "variable_value": value}
	except Exception:
		return

def main() -> dict[str: Any]:
	debug_data = dict(DEBUGDATA_TEMPLATE)
	with open("/tmp/output", "r") as f:
		debug_data["stdout"] = f.read()
	
	if not gdb.selected_thread():
		debug_data["is_running"] = False
		return
	
	frame = gdb.selected_frame()
	block = frame.block()
	
	local_variables = []
	arguments = []
	global_variables = []
	
	for symbol in block:
		if symbol.is_variable:
			pretty_symbol = format_symbol(frame, symbol)
			if pretty_symbol: local_variables.append(pretty_symbol)
		elif symbol.is_argument:
			pretty_symbol = format_symbol(frame, symbol)
			if pretty_symbol: arguments.append(pretty_symbol)
	
	for symbol in block.global_block:
		if symbol.is_variable:
			pretty_symbol = format_symbol(frame, symbol)
			if pretty_symbol: global_variables.append(pretty_symbol)

	debug_data["function"] = frame.function().name
	debug_data["function_return_type"] =  frame.function().type.target().name
	debug_data["line"] = frame.find_sal().line
	debug_data["global_variables"] = global_variables
	debug_data["local_variables"] = local_variables
	debug_data["arguments"] = arguments

	return debug_data

if __name__ == "__main__":
	print(main())