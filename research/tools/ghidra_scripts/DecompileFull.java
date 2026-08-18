// Decompile one function fully (no size/time shortcuts) to a file.
// Args: addrHex outPath
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DecompileFull extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long a = Long.parseLong(args[0], 16);
        String outPath = args[1];
        Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
        Function fn = getFunctionAt(addr);
        if (fn == null) fn = getFunctionContaining(addr);

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            if (fn == null) { out.println("(no function at " + addr + ")"); return; }
            DecompInterface decomp = new DecompInterface();
            DecompileOptions opts = new DecompileOptions();
            opts.setMaxPayloadMBytes(200);
            decomp.setOptions(opts);
            decomp.openProgram(currentProgram);
            out.println("---- " + fn.getName() + " @ " + fn.getEntryPoint() + " ----");
            DecompileResults res = decomp.decompileFunction(fn, 300, monitor);
            out.println("completed=" + res.decompileCompleted() + " errmsg=[" + res.getErrorMessage() + "]");
            if (res.decompileCompleted() && res.getDecompiledFunction() != null) {
                out.println(res.getDecompiledFunction().getC());
            } else {
                out.println("(decompilation failed: " + res.getErrorMessage() + ")");
            }
            decomp.dispose();
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
