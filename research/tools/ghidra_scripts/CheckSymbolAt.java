// Check what symbol/data Ghidra has defined at a given address post-analysis.
// Args: outPath addrHex [addrHex ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;

import java.io.FileWriter;
import java.io.PrintWriter;

public class CheckSymbolAt extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            SymbolTable symTable = currentProgram.getSymbolTable();
            for (int i = 1; i < args.length; i++) {
                long a = Long.parseLong(args[i].startsWith("0x") ? args[i].substring(2) : args[i], 16);
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
                out.println("==== " + addr + " ====");
                Symbol[] syms = symTable.getSymbols(addr);
                for (Symbol s : syms) {
                    out.println("  symbol: " + s.getName() + " type=" + s.getSymbolType());
                }
                Data d = getDataAt(addr);
                out.println("  data: " + (d == null ? "<none>" : d.toString() + " type=" + d.getDataType()));
                out.println("  references FROM here: ");
                for (var ref : currentProgram.getReferenceManager().getReferencesFrom(addr)) {
                    out.println("    -> " + ref.getToAddress());
                }
                out.println();
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
