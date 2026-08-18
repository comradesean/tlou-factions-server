// Dump raw disassembly (mnemonic + operands + raw bytes) for a function, to see
// register usage the decompiler's parameter-recovery may have dropped.
// Args: addrHex outPath [extraBytes]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpRawDisasm extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long a = Long.parseLong(args[0], 16);
        String outPath = args[1];
        Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
        Function fn = getFunctionAt(addr);
        if (fn == null) fn = getFunctionContaining(addr);

        PrintWriter out = new PrintWriter(new FileWriter(outPath, true));
        try {
            if (fn == null) { out.println("(no function at " + addr + ")"); return; }
            out.println("==== " + fn.getName() + " @ " + fn.getEntryPoint() + " body=" + fn.getBody() + " ====");
            InstructionIterator it = currentProgram.getListing().getInstructions(fn.getBody(), true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                out.printf("%s  %-10s %s%n", ins.getAddress(), ins.getMnemonicString(), ins.toString());
            }
            out.println();
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
