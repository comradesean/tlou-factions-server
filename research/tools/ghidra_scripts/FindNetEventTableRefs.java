// Finds what code references the recovered NetEvent name table (base 0x012238e0,
// 116 x 4-byte pointers) and decompiles those functions - this is very likely the
// debug-logging or dispatch function that indexes the table by opcode.
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

public class FindNetEventTableRefs extends GhidraScript {

    private static final long TABLE_BASE = 0x012238e0L;
    private static final int TABLE_ENTRIES = 116;

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/netevent_table_refs_report.txt";

    @Override
    protected void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(OUT_PATH));
        try {
            ReferenceManager refMgr = currentProgram.getReferenceManager();
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);
            Set<Function> seen = new LinkedHashSet<>();

            for (int i = 0; i < TABLE_ENTRIES; i++) {
                Address slot = currentProgram.getAddressFactory()
                    .getDefaultAddressSpace().getAddress(TABLE_BASE + (long) i * 4);
                ReferenceIterator refs = refMgr.getReferencesTo(slot);
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Address fromAddr = ref.getFromAddress();
                    Function fn = getFunctionContaining(fromAddr);
                    out.println("slot[" + i + "] " + slot + " <- ref from " + fromAddr
                        + " in " + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                    if (fn != null) seen.add(fn);
                }
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
        println("Wrote report to " + OUT_PATH);
    }
}
