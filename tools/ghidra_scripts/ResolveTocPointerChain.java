// Resolve a TOC-relative load instruction's actual referenced address, then
// follow one more level of pointer indirection, and dump bytes at the final
// location. Args: insnAddrHex outPath [dumpLen]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ResolveTocPointerChain extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long insnAddr = Long.parseLong(args[0], 16);
        String outPath = args[1];
        int dumpLen = args.length > 2 ? Integer.parseInt(args[2]) : 32;

        Address a = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(insnAddr);
        PrintWriter out = new PrintWriter(new FileWriter(outPath, true));
        try {
            Instruction ins = getInstructionAt(a);
            out.println("Instruction at " + a + ": " + (ins == null ? "<none>" : ins.toString()));
            if (ins != null) {
                Reference[] refs = ins.getReferencesFrom();
                for (Reference r : refs) {
                    Address to = r.getToAddress();
                    out.println("  -> ref to " + to + " (" + r.getReferenceType() + ")");
                    dumpBytes(out, to, dumpLen, "level0");
                    try {
                        Memory mem = currentProgram.getMemory();
                        byte[] ptrBytes = new byte[4];
                        mem.getBytes(to, ptrBytes);
                        long ptrVal = ((long)(ptrBytes[0] & 0xff) << 24) | ((ptrBytes[1] & 0xff) << 16)
                                | ((ptrBytes[2] & 0xff) << 8) | (ptrBytes[3] & 0xff);
                        Address deref = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(ptrVal);
                        out.println("  level0 as big-endian u32 pointer = " + deref);
                        dumpBytes(out, deref, dumpLen, "level1(deref-as-ptr)");
                    } catch (Exception e) {
                        out.println("  (deref failed: " + e + ")");
                    }
                }
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }

    private void dumpBytes(PrintWriter out, Address addr, int len, String label) {
        try {
            Memory mem = currentProgram.getMemory();
            byte[] b = new byte[len];
            mem.getBytes(addr, b);
            StringBuilder sb = new StringBuilder();
            for (byte x : b) sb.append(String.format("%02x ", x));
            out.println("  [" + label + "] bytes at " + addr + ": " + sb.toString());
        } catch (Exception e) {
            out.println("  [" + label + "] read failed at " + addr + ": " + e);
        }
    }
}
