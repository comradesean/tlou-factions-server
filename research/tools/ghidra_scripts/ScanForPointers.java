// Scan all defined memory for raw 4-byte big-endian words matching any of the
// given target addresses (catches pointer-table / TOC-slot references that
// Ghidra's own ReferenceManager didn't resolve into Reference objects - e.g.
// data tables of format-string pointers indexed by an enum, rather than a
// direct instruction operand reference). Args: outPath addrHex [addrHex ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class ScanForPointers extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        Set<Long> targets = new HashSet<>();
        Map<Long, String> targetHex = new HashMap<>();
        for (int i = 1; i < args.length; i++) {
            String s = args[i].startsWith("0x") ? args[i].substring(2) : args[i];
            long v = Long.parseLong(s, 16);
            targets.add(v);
            targetHex.put(v, args[i]);
        }

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            Memory mem = currentProgram.getMemory();
            for (MemoryBlock block : mem.getBlocks()) {
                if (!block.isInitialized() || !block.isLoaded()) continue;
                if (block.getSize() > 64 * 1024 * 1024) continue; // skip huge blocks
                byte[] data;
                try {
                    data = new byte[(int) block.getSize()];
                    block.getBytes(block.getStart(), data);
                } catch (Exception e) {
                    continue;
                }
                for (int off = 0; off + 4 <= data.length; off += 4) {
                    long val = ((long)(data[off] & 0xff) << 24) |
                               ((long)(data[off+1] & 0xff) << 16) |
                               ((long)(data[off+2] & 0xff) << 8) |
                               ((long)(data[off+3] & 0xff));
                    if (targets.contains(val)) {
                        Address hitAddr = block.getStart().add(off);
                        Function fn = getFunctionContaining(hitAddr);
                        out.println("target " + targetHex.get(val) + " found as raw pointer at " + hitAddr +
                                " (block " + block.getName() + ") in " +
                                (fn == null ? "<no function>" : fn.getName() + " @ " + fn.getEntryPoint()));
                    }
                }
                monitor.checkCancelled();
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
