// Find every function whose name starts with "cellVoice" or "sceNpSignaling", list their
// entry addresses, then find + decompile every caller of each. Purpose: see what the
// CALLERS do with the return value (branch on error vs ignore) right after the call,
// to determine whether cellVoice failures actually gate progression anywhere.
// Args: outPath namePrefix1 [namePrefix2 ...]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.address.Address;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class FindCellVoiceCallers extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            ReferenceManager refMgr = currentProgram.getReferenceManager();
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);
            Set<Function> callers = new LinkedHashSet<>();

            FunctionIterator fns = currentProgram.getFunctionManager().getFunctions(true);
            for (Function f : fns) {
                String nm = f.getName();
                boolean match = false;
                for (int i = 1; i < args.length; i++) {
                    if (nm.contains(args[i])) { match = true; break; }
                }
                if (!match) continue;
                out.println("==== stub " + nm + " @ " + f.getEntryPoint() + " ====");
                ReferenceIterator refs = refMgr.getReferencesTo(f.getEntryPoint());
                boolean any = false;
                while (refs.hasNext()) {
                    any = true;
                    Reference ref = refs.next();
                    Address fromAddr = ref.getFromAddress();
                    Function caller = getFunctionContaining(fromAddr);
                    out.println("  called from " + fromAddr + " in " + (caller == null ? "<none>" : caller.getName() + " @ " + caller.getEntryPoint()));
                    if (caller != null) callers.add(caller);
                }
                if (!any) out.println("  (no callers found)");
            }

            out.println();
            out.println("==== DECOMPILED CALLERS (" + callers.size() + ") ====");
            for (Function fn : callers) {
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
