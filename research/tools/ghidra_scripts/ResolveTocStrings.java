// Resolve TOC-relative "PTR_DAT_xxxx + offset" chains used throughout this binary's
// generated code (sprintf-style calls referencing global pointer tables) down to the
// actual referenced string, so we can read the real path-template text instead of
// guessing from decompiled offsets.
//
// Args: outPath baseAddrHex offset1Hex offset2Hex ...
// offsets may be negative (prefixed with '-'), matching how Ghidra prints them,
// e.g. "-7fa4" for `puVar1 + -0x7fa4`.
//
// For each offset:
//   ptrTableAddr = baseAddr            (the location whose *value* is loaded into puVar1)
//   base = readInt(ptrTableAddr)       (this is what "puVar1 = PTR_DAT_xxx" actually holds)
//   slotAddr = base + offset
//   strPtr = readInt(slotAddr)         (what "*(undefined4*)(puVar1+off)" reads)
//   Then try reading a C string at strPtr. If that fails / isn't printable, also
//   print strPtr itself and try reading a string directly at slotAddr (in case the
//   compiler inlined a short string in place rather than indirecting).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ResolveTocStrings extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        long baseAddrVal = Long.parseLong(args[0], 16);
        String outPath = args[1];
        Memory mem = currentProgram.getMemory();
        Address baseAddr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(baseAddrVal);

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            int base = mem.getInt(baseAddr);
            out.println("base ptr table value (what puVar1 = " + baseAddr + " loads) = 0x" + Integer.toHexString(base));
            out.println();
            for (int i = 2; i < args.length; i++) {
                String offArg = args[i];
                long off = Long.parseLong(offArg, 16);
                long slot = (base + off) & 0xffffffffL;
                Address slotAddr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(slot);
                out.println("---- offset " + offArg + " -> slot " + slotAddr + " ----");
                try {
                    int strPtr = mem.getInt(slotAddr);
                    Address strAddr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(strPtr & 0xffffffffL);
                    out.println("  slot value (pointer) = " + strAddr);
                    try {
                        String s = readCString(mem, strAddr);
                        out.println("  string @ ptr: " + escape(s));
                    } catch (Exception e) {
                        out.println("  (failed to read string at pointer: " + e + ")");
                    }
                } catch (Exception e) {
                    out.println("  (failed to read slot: " + e + ")");
                }
                try {
                    String s2 = readCString(mem, slotAddr);
                    out.println("  string @ slot directly: " + escape(s2));
                } catch (Exception e) {
                    out.println("  (failed to read string directly at slot: " + e + ")");
                }
                out.println();
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }

    private String readCString(Memory mem, Address addr) throws Exception {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 256; i++) {
            byte b = mem.getByte(addr.add(i));
            if (b == 0) break;
            sb.append((char) (b & 0xff));
        }
        return sb.toString();
    }

    private String escape(String s) {
        StringBuilder sb = new StringBuilder();
        for (char c : s.toCharArray()) {
            if (c >= 0x20 && c < 0x7f) sb.append(c);
            else sb.append(String.format("\\x%02x", (int) c));
        }
        return sb.toString();
    }
}
