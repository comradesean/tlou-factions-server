// Resolve and dump the 115-entry NetEvent factory/allocator jump table used by
// FUN_0038ec00 (called from FUN_00acecd0 as FUN_0038ec00(opcode) to allocate a
// blank NetEvent-derived object for a given net_event_type id before deserializing
// it from the wire).
//
// Decompiled dispatch (FUN_0038ec00, ram 0038ec00):
//   if (param_1 < 0x73) {
//     T = *(int *)(PTR_DAT_012fdef4 + -0x7ee4);      // table base, read from TOC slot
//     uVar8 = (*(code *)(*(int *)(T + param_1*4) + T))();  // relative-offset jump table
//     return uVar8;
//   }
// i.e. table entries are 32-bit offsets *relative to the table's own base address*
// (classic PPC PIC switch-table idiom), not absolute pointers.
//
// This script:
//   1. reads the pointer stored at address 0x012fdef4 (the "PTR_DAT_012fdef4" TOC value)
//   2. computes slot = that_value + (-0x7ee4), reads the table base address from there
//   3. walks 115 (0x73) entries: reads a relative i32 offset, adds table base -> function addr
//   4. resolves/creates a function at that address and prints opcode index -> function name
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpNetEventFactoryTable extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        Memory mem = currentProgram.getMemory();
        var space = currentProgram.getAddressFactory().getDefaultAddressSpace();

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            Address ptrDatAddr = space.getAddress(0x012fdef4L);
            int base = mem.getInt(ptrDatAddr);
            out.println("PTR_DAT_012fdef4 value = 0x" + Integer.toHexString(base));

            long slot = (base + (-0x7ee4)) & 0xffffffffL;
            Address slotAddr = space.getAddress(slot);
            int tableBase = mem.getInt(slotAddr);
            out.println("table base (slot " + slotAddr + ") = 0x" + Integer.toHexString(tableBase));
            out.println();

            Address tableBaseAddr = space.getAddress(tableBase & 0xffffffffL);
            for (int i = 0; i < 0x73; i++) {
                Address entryAddr = tableBaseAddr.add(i * 4L);
                int rel = mem.getInt(entryAddr);
                long target = (tableBase + rel) & 0xffffffffL;
                Address targetAddr = space.getAddress(target);
                Function fn = getFunctionAt(targetAddr);
                String fname;
                if (fn != null) {
                    fname = fn.getName();
                } else {
                    fn = getFunctionContaining(targetAddr);
                    if (fn != null) {
                        fname = fn.getName() + "+0x" + Long.toHexString(target - fn.getEntryPoint().getOffset());
                    } else {
                        fname = "(no function; may need disassembly)";
                    }
                }
                out.println("[" + i + "] " + targetAddr + "  " + fname);
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
