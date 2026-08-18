// Finds the 5 sibling service-name strings (heartbeat-server, leaderboard-server,
// invite-server, facebook-server, single-player-server), their xref functions,
// and decompiles those functions plus any function containing a reference TO
// one of those functions (one level up), to find the connect/hello call site
// for each service by analogy with ticket-server's FUN_00acc424 call in
// FUN_003557a8 at 0x00355f84.
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
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class FindSiblingServers extends GhidraScript {

    private static final List<String> TARGET_STRINGS = Arrays.asList(
        "heartbeat-server",
        "leaderboard-server",
        "invite-server",
        "facebook-server",
        "single-player-server"
    );

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/sibling_servers_report.txt";

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

            for (String s : TARGET_STRINGS) {
                Address strAddr = findFirst(s);
                out.println("==== STRING: " + s + " ====");
                if (strAddr == null) {
                    out.println("   not found\n");
                    continue;
                }
                out.println("   address: " + strAddr);
                ReferenceIterator refs = refMgr.getReferencesTo(strAddr);
                boolean any = false;
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    any = true;
                    Function fn = getFunctionContaining(ref.getFromAddress());
                    out.println("   ref from " + ref.getFromAddress() + " in "
                        + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                    if (fn != null) seen.add(fn);
                }
                if (!any) out.println("   (no direct code refs - may be pointed to only via a data/TOC table)");
                out.println();
            }

            out.println("==== DECOMPILED (" + seen.size() + " functions) ====\n");
            for (Function fn : seen) {
                out.println("---- " + fn.getName() + " @ " + fn.getEntryPoint() + " ----");
                DecompileResults res = decomp.decompileFunction(fn, 90, monitor);
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
