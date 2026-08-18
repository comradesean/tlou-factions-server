// List all memory blocks Ghidra has for the program, plus whether a given
// address is contained in any of them. Args: outPath [addrHex ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ListMemoryBlocks extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
                out.printf("%-20s start=%s end=%s size=%#x initialized=%b type=%s perms=%s%s%s%n",
                        b.getName(), b.getStart(), b.getEnd(), b.getSize(), b.isInitialized(),
                        b.getType(), b.isRead() ? "r" : "-", b.isWrite() ? "w" : "-", b.isExecute() ? "x" : "-");
            }
            out.println();
            for (int i = 1; i < args.length; i++) {
                long a = Long.parseLong(args[i].startsWith("0x") ? args[i].substring(2) : args[i], 16);
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
                MemoryBlock b = currentProgram.getMemory().getBlock(addr);
                out.println(addr + " is in block: " + (b == null ? "<none>" : b.getName()));
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
