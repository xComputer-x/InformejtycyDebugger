import gdb

class StructPprint:

    def __init__(self, val: gdb.Value) -> None:
        self.val = val

    def to_string(self) -> str:
        out = "STRUCT BEGIN\n"
        for field in self.val.type.fields():
            if not field.name:
                continue
            out += f"{field.name} = {self.val[field.name]}\n"
        return out+"STRUCT END\n"

def lookup_pretty_printer(val):
    if val.type.code == gdb.TYPE_CODE_STRUCT:
        return StructPprint(val)
    return None

gdb.pretty_printers.append(lookup_pretty_printer)
