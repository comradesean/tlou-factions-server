// Decompile all 115 entries of the NetEvent factory/allocator jump table
// (base 0x38ec40, resolved by DumpNetEventFactoryTable.java) in index (=opcode) order.
// These addresses aren't yet recognized as Functions (no prior analysis pass covered
// them), so this script creates a function at each entry before decompiling it.
// Args: outPath
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DecompileFactoryTrampolines extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        Memory mem = currentProgram.getMemory();
        var space = currentProgram.getAddressFactory().getDefaultAddressSpace();

        Address ptrDatAddr = space.getAddress(0x012fdef4L);
        int base = mem.getInt(ptrDatAddr);
        long slot = (base + (-0x7ee4)) & 0xffffffffL;
        Address slotAddr = space.getAddress(slot);
        int tableBase = mem.getInt(slotAddr);
        Address tableBaseAddr = space.getAddress(tableBase & 0xffffffffL);

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            for (int i = 0; i < 0x73; i++) {
                Address entryAddr = tableBaseAddr.add(i * 4L);
                int rel = mem.getInt(entryAddr);
                long target = (tableBase + rel) & 0xffffffffL;
                Address targetAddr = space.getAddress(target);

                Function fn = getFunctionAt(targetAddr);
                if (fn == null) {
                    disassemble(targetAddr);
                    fn = createFunction(targetAddr, "NetEventFactory_" + i);
                }
                out.println("==== [" + i + "] " + targetAddr + " ====");
                if (fn == null) {
                    out.println("(could not create function)\n");
                    continue;
                }
                DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
                if (res.decompileCompleted() && res.getDecompiledFunction() != null) {
                    out.println(res.getDecompiledFunction().getC());
                } else {
                    out.println("(decompilation failed: " + res.getErrorMessage() + ")");
                }
                out.println();
            }
            decomp.dispose();
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
