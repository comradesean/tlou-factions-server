// Like GetReferencesTo but WITHOUT decompiling - just lists the referencing
// address + containing function for each target. Use this first when a target
// may have dozens of referrers and a full decompile dump would be unusable.
// Args: outPath addrHex [addrHex ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ListReferencesTo extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            ReferenceManager refMgr = currentProgram.getReferenceManager();
            for (int i = 1; i < args.length; i++) {
                long a = Long.parseLong(args[i].startsWith("0x") ? args[i].substring(2) : args[i], 16);
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
                out.println("==== references to " + addr + " ====");
                ReferenceIterator refs = refMgr.getReferencesTo(addr);
                boolean any = false;
                int n = 0;
                while (refs.hasNext()) {
                    any = true;
                    Reference ref = refs.next();
                    Address fromAddr = ref.getFromAddress();
                    Function fn = getFunctionContaining(fromAddr);
                    out.println("  " + ref.getReferenceType() + " from " + fromAddr + " in "
                            + (fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint()));
                    n++;
                }
                if (!any) out.println("  (no references found)");
                out.println("  total: " + n);
                out.println();
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
