// Scan all defined memory for ASCII substrings matching a literal needle (case
// sensitive) and report the address + surrounding printable run. Useful for
// finding SDK identifier literals (NPWR..., NPXS..., service ids) that were
// never turned into defined Data by auto-analysis.
// Args: outPath needle [needle ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

import java.io.FileWriter;
import java.io.PrintWriter;

public class FindStringsMatching extends GhidraScript {
    private static boolean printable(byte b) {
        return b >= 0x20 && b < 0x7f;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            Memory mem = currentProgram.getMemory();
            for (MemoryBlock block : mem.getBlocks()) {
                if (!block.isInitialized()) continue;
                int len = (int) Math.min(block.getSize(), Integer.MAX_VALUE);
                byte[] buf = new byte[len];
                try {
                    block.getBytes(block.getStart(), buf);
                } catch (Exception e) {
                    out.println("(failed to read block " + block.getName() + ": " + e + ")");
                    continue;
                }
                for (int n = 1; n < args.length; n++) {
                    byte[] needle = args[n].getBytes("US-ASCII");
                    for (int i = 0; i + needle.length <= len; i++) {
                        boolean hit = true;
                        for (int j = 0; j < needle.length; j++) {
                            if (buf[i + j] != needle[j]) { hit = false; break; }
                        }
                        if (!hit) continue;
                        int s = i;
                        while (s > 0 && printable(buf[s - 1])) s--;
                        int e = i + needle.length;
                        while (e < len && printable(buf[e])) e++;
                        Address addr = block.getStart().add(i);
                        Function fn = getFunctionContaining(addr);
                        out.println("needle=" + args[n] + " at " + addr + " block=" + block.getName()
                                + (fn == null ? "" : " in " + fn.getName())
                                + " run=[" + new String(buf, s, e - s, "US-ASCII") + "] runStart=" + block.getStart().add(s));
                    }
                }
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
