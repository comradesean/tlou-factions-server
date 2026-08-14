// Dump N vtable slots (PPC32 ABI: each slot holds a pointer to an .opd descriptor,
// {code_addr, toc_addr}; the real function entry is the word AT that address) starting
// at a given raw vtable address, and decompile each resolved function.
// Args: vtableAddrHex outPath numSlots [slotStrideHexDefault4]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpVtableAt extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long vtableAddrVal = Long.parseLong(args[0], 16);
        String outPath = args[1];
        int numSlots = Integer.parseInt(args[2]);
        int stride = args.length > 3 ? Integer.parseInt(args[3], 16) : 4;

        Memory mem = currentProgram.getMemory();
        var space = currentProgram.getAddressFactory().getDefaultAddressSpace();
        Address vtable = space.getAddress(vtableAddrVal);

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            out.println("vtable base = " + vtable);
            for (int i = 0; i < numSlots; i++) {
                int s = i * stride;
                Address slotPtrAddr = vtable.add(s);
                int opdPtr;
                try {
                    opdPtr = mem.getInt(slotPtrAddr);
                } catch (Exception e) {
                    out.println("[vtable+0x" + Integer.toHexString(s) + "] (unreadable)");
                    continue;
                }
                Address opdAddr = space.getAddress(opdPtr & 0xffffffffL);
                int codeAddrVal;
                try {
                    codeAddrVal = mem.getInt(opdAddr);
                } catch (Exception e) {
                    out.println("[vtable+0x" + Integer.toHexString(s) + "] opd=" + opdAddr + " (unreadable code word)");
                    continue;
                }
                Address codeAddr = space.getAddress(codeAddrVal & 0xffffffffL);
                Function fn = getFunctionAt(codeAddr);
                if (fn == null) fn = getFunctionContaining(codeAddr);
                out.println("[vtable+0x" + Integer.toHexString(s) + "] opd=" + opdAddr + " code=" + codeAddr
                    + " fn=" + (fn == null ? "(none)" : fn.getName() + "@" + fn.getEntryPoint()));
                if (fn != null) {
                    DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
                    if (res.decompileCompleted() && res.getDecompiledFunction() != null) {
                        out.println(res.getDecompiledFunction().getC());
                    } else {
                        out.println("(decompilation failed: " + res.getErrorMessage() + ")");
                    }
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
