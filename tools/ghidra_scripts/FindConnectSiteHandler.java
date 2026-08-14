// Finds the exact "connect to %s:%i ..." call site and decompiles the
// containing function - this is the actual socket connect()/send() logic
// for the ticket-server handshake, distinct from the giant NetInit
// orchestrator found via the "ticket-server" string alone.
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

public class FindConnectSiteHandler extends GhidraScript {

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/connect_site_report.txt";

    private Address findFirst(String s) throws Exception {
        return currentProgram.getMemory().findBytes(
            currentProgram.getMinAddress(), s.getBytes("US-ASCII"), null, true, monitor);
    }

    @Override
    protected void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(OUT_PATH));
        try {
            ReferenceManager refMgr = currentProgram.getReferenceManager();
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);
            Set<Function> seen = new LinkedHashSet<>();

            String s = "connect to %s:%i ...";
            Address strAddr = findFirst(s);
            out.println("STRING: " + s);
            if (strAddr == null) {
                out.println("not found");
            } else {
                out.println("address: " + strAddr);
                ReferenceIterator refs = refMgr.getReferencesTo(strAddr);
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function fn = getFunctionContaining(ref.getFromAddress());
                    out.println("ref from " + ref.getFromAddress() + " in "
                        + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                    if (fn != null) seen.add(fn);
                }
            }
            out.println();

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
