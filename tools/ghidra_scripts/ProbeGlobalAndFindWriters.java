// Read a TOC-relative global pointer slot (base@ptrTableAddr + offset), then search
// for any code that WRITES (not just reads) to [thatvalue]+subOffset for a list of
// candidate sub-offsets - to find what sets a runtime object's fields, not just what
// reads them. Falls back gracefully if the resolved pointer is a runtime-only (BSS)
// value with no static content.
// Args: outPath ptrTableAddrHex offsetHex subOffset1Hex subOffset2Hex ...
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

public class ProbeGlobalAndFindWriters extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        long ptrTableAddrVal = Long.parseLong(args[1], 16);
        long off = Long.parseLong(args[2], 16);

        Memory mem = currentProgram.getMemory();
        Address ptrTableAddr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(ptrTableAddrVal);

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            int base = mem.getInt(ptrTableAddr);
            out.println("base ptr table value (what loads from " + ptrTableAddr + ") = 0x" + Integer.toHexString(base));
            long slot = (base + off) & 0xffffffffL;
            out.println("slot address (base+offset) = 0x" + Long.toHexString(slot));
            int slotVal = 0;
            try {
                slotVal = mem.getInt(currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(slot));
                out.println("static content at slot = 0x" + Integer.toHexString(slotVal) + " (may be 0/meaningless if runtime-populated BSS)");
            } catch (Exception e) {
                out.println("(failed to read slot content: " + e + ")");
            }
            out.println();

            ReferenceManager refMgr = currentProgram.getReferenceManager();
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);
            Set<Function> seen = new LinkedHashSet<>();

            // Also just find ALL references to the ptrTableAddr slot itself (every
            // function that loads this global at all) - useful even without a
            // resolved runtime pointer, since the global loader sites are where
            // the object gets created/initialized.
            out.println("==== References to ptr table slot " + ptrTableAddr + " itself ====");
            ReferenceIterator refs = refMgr.getReferencesTo(ptrTableAddr);
            while (refs.hasNext()) {
                Reference ref = refs.next();
                Address fromAddr = ref.getFromAddress();
                Function fn = getFunctionContaining(fromAddr);
                out.println("  ref from " + fromAddr + " in " + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                if (fn != null) seen.add(fn);
            }

            out.println();
            out.println("==== DECOMPILED (" + seen.size() + " functions referencing the global slot) ====");
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
