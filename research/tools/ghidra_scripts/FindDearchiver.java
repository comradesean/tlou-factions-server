import ghidra.app.script.GhidraScript;
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

public class FindDearchiver extends GhidraScript {
    private static final List<String> TARGETS = Arrays.asList(
        "sizeof(fios::dearchiver) <= Memory::GetSize(ALLOCATION_FIOS_DEARCHIVER_MEM)",
        "ALLOCATION_FIOS_DEARCHIVER_MEM",
        "Crap, out of Dearchive IO buffers for FIOS"
    );
    private static final String OUT_PATH = "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/dearchiver_report.txt";

    private Address findFirst(String s) throws Exception {
        return currentProgram.getMemory().findBytes(currentProgram.getMinAddress(), s.getBytes("US-ASCII"), null, true, monitor);
    }

    @Override
    protected void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(OUT_PATH));
        ReferenceManager refMgr = currentProgram.getReferenceManager();
        LinkedHashSet<Function> fns = new LinkedHashSet<>();
        for (String s : TARGETS) {
            Address a = findFirst(s);
            out.println("==== " + s);
            if (a == null) { out.println("  not found"); continue; }
            out.println("  addr " + a);
            ReferenceIterator refs = refMgr.getReferencesTo(a);
            while (refs.hasNext()) {
                Reference r = refs.next();
                Function fn = getFunctionContaining(r.getFromAddress());
                out.println("  ref from " + r.getFromAddress() + " in " + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                if (fn != null) fns.add(fn);
            }
        }
        out.println();
        out.println("Functions found: " + fns.size());
        for (Function f : fns) out.println("  " + f.getName() + " @ " + f.getEntryPoint());
        out.close();
        println("done");
    }
}
