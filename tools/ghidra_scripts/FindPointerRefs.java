// Search all of memory for 4-byte big-endian occurrences of a target address value
// (i.e. find where that address is stored AS DATA - a pointer table entry - rather
// than looking for code xrefs, which Ghidra's own reference manager misses for
// TOC-relative loads in this binary). Once found, decompile whatever function(s)
// reference the CONTAINING TABLE via a normal data xref (tables are more often
// directly referenced than individual string literals in this codebase).
// Args: outPath targetAddrHex
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

public class FindPointerRefs extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long targetVal = Long.parseLong(args[0].startsWith("0x") ? args[0].substring(2) : args[0], 16);
        String outPath = args.length > 1 ? args[1] : "/tmp/find_pointer_refs.txt";
        // allow either (target, out) or (out, target) calling order safety
        try { Long.parseLong(args[1].startsWith("0x") ? args[1].substring(2) : args[1], 16);
              // both parse as hex - args[0] is target, args[1] could be out path fallback, keep default
        } catch (Exception ignore) {}

        Memory mem = currentProgram.getMemory();
        byte[] pattern = new byte[] {
            (byte) ((targetVal >> 24) & 0xff),
            (byte) ((targetVal >> 16) & 0xff),
            (byte) ((targetVal >> 8) & 0xff),
            (byte) (targetVal & 0xff)
        };

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            out.println("Searching for 4-byte BE occurrences of 0x" + Long.toHexString(targetVal));
            Address start = currentProgram.getMinAddress();
            Address found = mem.findBytes(start, pattern, null, true, monitor);
            Set<Function> seen = new LinkedHashSet<>();
            ReferenceManager refMgr = currentProgram.getReferenceManager();
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);

            int count = 0;
            while (found != null && count < 20) {
                count++;
                out.println("---- occurrence " + count + " at " + found + " ----");
                // Now find what references THIS location (the table slot)
                ReferenceIterator refs = refMgr.getReferencesTo(found);
                boolean any = false;
                while (refs.hasNext()) {
                    any = true;
                    Reference ref = refs.next();
                    Address fromAddr = ref.getFromAddress();
                    Function fn = getFunctionContaining(fromAddr);
                    out.println("  ref from " + fromAddr + " in " + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                    if (fn != null) seen.add(fn);
                }
                if (!any) out.println("  (no code refs to this exact slot)");

                Address next = found.add(1);
                if (next.compareTo(currentProgram.getMaxAddress()) >= 0) break;
                found = mem.findBytes(next, pattern, null, true, monitor);
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
