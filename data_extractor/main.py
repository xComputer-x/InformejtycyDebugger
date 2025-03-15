import gdb
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
    "stdout": []
}

def format_symbol(frame: gdb.Frame, symbol: gdb.Symbol) -> Optional[dict[str: str]]:
	try:
		name = symbol.name
		type_ = str(symbol.type)
		# print(type_, str(type_))
		value = frame.read_var(name).format_string()
		
		if len(value) > 200:
			value = f"{value[:400]}..."
			
		return {"name": name, "type": type_, "value": value}
	except Exception as e:
		return

def main() -> None:
	debug_data = dict(DEBUGDATA_TEMPLATE)
	if not gdb.selected_thread():
		debug_data["is_running"] = False
		print(debug_data)
		return
	
	with open("output.txt", "r") as f:
		print(f.read())
	
	frame = gdb.selected_frame()
	debug_data = {}
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
	
	print(debug_data)

if __name__ == "__main__":
	main()