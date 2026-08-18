// Finds functions that reference known opcode-dispatch/assert strings and dumps their
// decompiled pseudocode, so the real numeric opcode range/dispatch mechanism can be read
// off without opening the Ghidra GUI. Run as a -postScript against an already-analyzed
// project (see docs/ghidra-setup.md).
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class DumpOpcodeDispatchEvidence extends GhidraScript {

    private static final List<String> TARGET_STRINGS = Arrays.asList(
        "%p:%3u - UNKNOWN OPCODE",
        "%s(%d) : Out of range Opcode type of 0x%X.",
        "%s(%d) : Unimplemented Opcode type of 0x%X.",
        "notify->packetSequenceNumber == m_highestAckedSequence + i + 1",
        "The buffer passed in to read the string from the packet is too small to fit the string in the packet"
    );

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/opcode_dispatch_report.txt";

    @Override
    protected void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(OUT_PATH));
        try {
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);

            ReferenceManager refMgr = currentProgram.getReferenceManager();
            Set<Function> seenFunctions = new LinkedHashSet<>();
            Set<String> remaining = new HashSet<>();

            for (String s : TARGET_STRINGS) {
                byte[] needle = s.getBytes("US-ASCII");
                Address searchFrom = currentProgram.getMinAddress();
                boolean foundAny = false;

                while (true) {
                    Address strAddr = currentProgram.getMemory()
                        .findBytes(searchFrom, needle, null, true, monitor);
                    if (strAddr == null) break;
                    foundAny = true;

                    out.println("==== STRING: " + s);
                    out.println("     address: " + strAddr);

                    ReferenceIterator refs = refMgr.getReferencesTo(strAddr);
                    int refCount = 0;
                    while (refs.hasNext()) {
                        Reference ref = refs.next();
                        Address fromAddr = ref.getFromAddress();
                        Function fn = getFunctionContaining(fromAddr);
                        out.println("     ref from " + fromAddr + " in function "
                            + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                        refCount++;
                        if (fn != null) seenFunctions.add(fn);
                    }
                    if (refCount == 0) out.println("     (no references found)");
                    out.println();

                    searchFrom = strAddr.add(1);
                }
                if (!foundAny) remaining.add(s);
            }

            if (!remaining.isEmpty()) {
                out.println("==== STRINGS NOT FOUND VIA RAW BYTE SEARCH: " + remaining);
                out.println();
            }

            out.println("==== DECOMPILED FUNCTIONS (" + seenFunctions.size() + ") ====");
            out.println();
            for (Function fn : seenFunctions) {
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
