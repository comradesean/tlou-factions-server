// Find real references to one or more addresses using Ghidra's own reference
// manager (accurate now that a full analysis pass has resolved TOC-relative
// constant loads into synthetic address references), then decompile every
// distinct referencing function. Args: outPath addrHex [addrHex ...]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class GetReferencesTo extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            ReferenceManager refMgr = currentProgram.getReferenceManager();
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);
            Set<Function> seen = new LinkedHashSet<>();

            for (int i = 1; i < args.length; i++) {
                long a = Long.parseLong(args[i].startsWith("0x") ? args[i].substring(2) : args[i], 16);
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
                out.println("==== references to " + addr + " ====");
                ReferenceIterator refs = refMgr.getReferencesTo(addr);
                boolean any = false;
                while (refs.hasNext()) {
                    any = true;
                    Reference ref = refs.next();
                    Address fromAddr = ref.getFromAddress();
                    Function fn = getFunctionContaining(fromAddr);
                    out.println("  ref from " + fromAddr + " in " + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                    if (fn != null) seen.add(fn);
                }
                if (!any) out.println("  (no references found)");
                out.println();
            }

            out.println("==== DECOMPILED (" + seen.size() + " functions) ====");
            for (Function fn : seen) {
                out.println("---- " + fn.getName() + " @ " + fn.getEntryPoint() + " ----");
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
