// Combined probe: for each target string address given, do BOTH
//  (a) code-xref lookup via ReferenceManager.getReferencesTo(target) directly on the string addr
//  (b) flat 4-byte-BE data search across all of memory for the address value (pointer table entries)
// and decompile whatever functions either technique surfaces. One process launch covers many
// addresses, saving the ~30s Ghidra headless project-open overhead per address.
// Args: outPath addr1Hex addr2Hex ...
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class ProbeNetSmLeads extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        Memory mem = currentProgram.getMemory();
        ReferenceManager refMgr = currentProgram.getReferenceManager();
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        Set<Function> allFns = new LinkedHashSet<>();

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            for (int ai = 1; ai < args.length; ai++) {
                long targetVal = Long.parseLong(args[ai], 16);
                Address target = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(targetVal);
                out.println("======== target 0x" + Long.toHexString(targetVal) + " (" + target + ") ========");

                out.println("-- direct code xrefs to this exact address --");
                ReferenceIterator refs = refMgr.getReferencesTo(target);
                boolean any = false;
                while (refs.hasNext()) {
                    any = true;
                    Reference ref = refs.next();
                    Address fromAddr = ref.getFromAddress();
                    Function fn = getFunctionContaining(fromAddr);
                    out.println("  ref from " + fromAddr + " in " + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()) + " (" + ref.getReferenceType() + ")");
                    if (fn != null) allFns.add(fn);
                }
                if (!any) out.println("  (none)");

                out.println("-- flat 4-byte BE data search for this address value as a pointer table entry --");
                byte[] pattern = new byte[] {
                    (byte) ((targetVal >> 24) & 0xff),
                    (byte) ((targetVal >> 16) & 0xff),
                    (byte) ((targetVal >> 8) & 0xff),
                    (byte) (targetVal & 0xff)
                };
                Address start = currentProgram.getMinAddress();
                Address found = mem.findBytes(start, pattern, null, true, monitor);
                int count = 0;
                while (found != null && count < 10) {
                    count++;
                    out.println("  occurrence at " + found);
                    ReferenceIterator refs2 = refMgr.getReferencesTo(found);
                    boolean any2 = false;
                    while (refs2.hasNext()) {
                        any2 = true;
                        Reference ref2 = refs2.next();
                        Address fromAddr2 = ref2.getFromAddress();
                        Function fn2 = getFunctionContaining(fromAddr2);
                        out.println("    ref from " + fromAddr2 + " in " + (fn2 == null ? "<none>" : fn2.getName() + " @ " + fn2.getEntryPoint()));
                        if (fn2 != null) allFns.add(fn2);
                    }
                    if (!any2) out.println("    (no code refs to this slot)");
                    Address next = found.add(1);
                    if (next.compareTo(currentProgram.getMaxAddress()) >= 0) break;
                    found = mem.findBytes(next, pattern, null, true, monitor);
                }
                if (count == 0) out.println("  (no data occurrences found anywhere in memory)");
                out.println();
            }

            out.println();
            out.println("==== DECOMPILED (" + allFns.size() + " functions) ====");
            for (Function fn : allFns) {
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
