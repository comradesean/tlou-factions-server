// Dump raw bytes at one or more addresses. Args: outPath addrHex len [addrHex len ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpBytesAt extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        PrintWriter out = new PrintWriter(new FileWriter(outPath, true));
        try {
            Memory mem = currentProgram.getMemory();
            for (int i = 1; i + 1 < args.length; i += 2) {
                long a = Long.parseLong(args[i], 16);
                int len = Integer.parseInt(args[i + 1]);
                Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
                try {
                    byte[] b = new byte[len];
                    mem.getBytes(addr, b);
                    StringBuilder sb = new StringBuilder();
                    for (byte x : b) sb.append(String.format("%02x ", x));
                    out.println(addr + ": " + sb.toString());
                } catch (Exception e) {
                    out.println(addr + ": read failed: " + e);
                }
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
