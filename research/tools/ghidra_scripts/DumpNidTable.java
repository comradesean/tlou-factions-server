// Generic: dump a library's raw NID table (NID -> resolved symbol name if any).
// Args: nidTableAddrHex funcTableAddrHex numFuncDecimal outPath
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpNidTable extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long nidTable = Long.parseLong(args[0], 16);
        long funcTable = Long.parseLong(args[1], 16);
        int numFunc = Integer.parseInt(args[2]);
        String outPath = args[3];

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            SymbolTable symTab = currentProgram.getSymbolTable();
            for (int i = 0; i < numFunc; i++) {
                Address nidSlot = currentProgram.getAddressFactory().getDefaultAddressSpace()
                    .getAddress(nidTable + (long) i * 4);
                Address funcSlot = currentProgram.getAddressFactory().getDefaultAddressSpace()
                    .getAddress(funcTable + (long) i * 4);
                long nid = currentProgram.getMemory().getInt(nidSlot) & 0xFFFFFFFFL;
                long funcPtrRaw = currentProgram.getMemory().getInt(funcSlot) & 0xFFFFFFFFL;
                Address funcPtrAddr = currentProgram.getAddressFactory().getDefaultAddressSpace()
                    .getAddress(funcPtrRaw);
                Symbol sym = symTab.getPrimarySymbol(funcPtrAddr);
                out.println(String.format("  [%2d] NID=0x%08X -> %s (%s)", i, nid,
                    funcPtrAddr, sym == null ? "<unnamed>" : sym.getName()));
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
