// Debug: probe a single address to see what's there (bytes, existing data/code,
// disassembly attempt result) when createFunction silently returns null.
// Args: outPath addrHex1 addrHex2 ...
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.mem.Memory;
import ghidra.program.disassemble.Disassembler;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ProbeVtableSlot extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        Memory mem = currentProgram.getMemory();
        var space = currentProgram.getAddressFactory().getDefaultAddressSpace();

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            for (int i = 1; i < args.length; i++) {
                Address a = space.getAddress(Long.parseLong(args[i], 16));
                out.println("==== " + a + " ====");
                out.println("  containing block: " + mem.getBlock(a));
                try {
                    byte[] b = new byte[16];
                    mem.getBytes(a, b);
                    StringBuilder sb = new StringBuilder();
                    for (byte x : b) sb.append(String.format("%02x ", x));
                    out.println("  bytes: " + sb);
                } catch (Exception e) {
                    out.println("  bytes: (failed: " + e + ")");
                }
                CodeUnit cu = currentProgram.getListing().getCodeUnitAt(a);
                out.println("  existing code unit at addr: " + cu);
                Function fnAt = getFunctionAt(a);
                Function fnContaining = getFunctionContaining(a);
                out.println("  getFunctionAt: " + fnAt + "  getFunctionContaining: " + fnContaining);
                try {
                    boolean disasmOk = disassemble(a);
                    out.println("  disassemble() returned: " + disasmOk);
                } catch (Exception e) {
                    out.println("  disassemble() threw: " + e);
                }
                try {
                    Function created = createFunction(a, "probe_" + a);
                    out.println("  createFunction() returned: " + created);
                } catch (Exception e) {
                    out.println("  createFunction() threw: " + e);
                }
                out.println();
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
