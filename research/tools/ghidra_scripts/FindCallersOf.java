// Generic: find callers of a given function address and decompile them.
// Address passed as the first script arg (hex, no 0x prefix), output path as second arg.
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

public class FindCallersOf extends GhidraScript {

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long targetAddr = Long.parseLong(args[0], 16);
        String outPath = args[1];

        Address target = currentProgram.getAddressFactory()
            .getDefaultAddressSpace().getAddress(targetAddr);

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            ReferenceManager refMgr = currentProgram.getReferenceManager();
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);
            Set<Function> seen = new LinkedHashSet<>();

            out.println("Callers of " + target + ":");
            ReferenceIterator refs = refMgr.getReferencesTo(target);
            while (refs.hasNext()) {
                Reference ref = refs.next();
                Address fromAddr = ref.getFromAddress();
                Function fn = getFunctionContaining(fromAddr);
                out.println("  ref from " + fromAddr + " in "
                    + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint())
                    + " (" + ref.getReferenceType() + ")");
                if (fn != null) seen.add(fn);
            }
            out.println();
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
