// Decompile a fixed list of functions by address. Args: outPath addr1 addr2 ...
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DecompileByAddresses extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);
            for (int i = 1; i < args.length; i++) {
                long a = Long.parseLong(args[i], 16);
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
                Function fn = getFunctionAt(addr);
                if (fn == null) fn = getFunctionContaining(addr);
                out.println("---- " + addr + " (" + (fn == null ? "no function" : fn.getName()) + ") ----");
                if (fn == null) { out.println("(no function)\n"); continue; }
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
