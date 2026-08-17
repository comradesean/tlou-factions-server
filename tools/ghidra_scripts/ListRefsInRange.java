// List every reference whose destination falls inside [start, end) — used to map
// out an entire global struct's field accesses at once (readers AND writers),
// rather than probing one address at a time.
// Args: outPath startHex endHex
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ListRefsInRange extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        long start = Long.parseLong(args[1], 16);
        long end = Long.parseLong(args[2], 16);
        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            ReferenceManager rm = currentProgram.getReferenceManager();
            for (long a = start; a < end; a++) {
                Address addr = currentProgram.getAddressFactory()
                        .getDefaultAddressSpace().getAddress(a);
                ReferenceIterator it = rm.getReferencesTo(addr);
                while (it.hasNext()) {
                    Reference r = it.next();
                    Address from = r.getFromAddress();
                    Function fn = getFunctionContaining(from);
                    out.printf("%08x  %-10s from %s  in %s%n",
                            a, r.getReferenceType().getName(), from,
                            fn == null ? "<none>" : (fn.getName() + " @ " + fn.getEntryPoint()));
                }
            }
            println("Wrote report to " + outPath);
        } finally {
            out.close();
        }
    }
}
