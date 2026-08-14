// Two things:
// 1) List (not decompile - too many callsites) every function that references the
//    game/net/net-event.cpp and game/net/net.cpp source-path strings, to inventory
//    what functions actually live in those translation units.
// 2) Try to recover the NetEvent name lookup table: find where "NetEventPlayerMove" is
//    referenced from, then scan outward from that pointer slot in 4-byte steps looking
//    for a contiguous run of pointers to printable strings - if it's an enum-to-name
//    array, its element order directly reveals numeric opcode IDs.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.List;
import java.util.TreeMap;

public class ExploreNetEventStructure extends GhidraScript {

    private static final List<String> SOURCE_FILE_STRINGS = Arrays.asList(
        "game/net/net-event.cpp",
        "game/net/net.cpp",
        "game/net/net-snapshot.cpp"
    );

    private static final String ANCHOR_STRING = "NetEventPlayerMove";
    private static final int SCAN_RADIUS_ENTRIES = 200;

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/netevent_structure_report.txt";

    private Address findFirst(String s) throws Exception {
        return currentProgram.getMemory().findBytes(
            currentProgram.getMinAddress(), s.getBytes("US-ASCII"), null, true, monitor);
    }

    private boolean looksLikeString(Address addr, StringBuilder out) {
        Memory mem = currentProgram.getMemory();
        StringBuilder sb = new StringBuilder();
        try {
            for (int i = 0; i < 80; i++) {
                byte b = mem.getByte(addr.add(i));
                if (b == 0) break;
                int c = b & 0xFF;
                if (c < 0x20 || c > 0x7E) return false;
                sb.append((char) c);
            }
        } catch (Exception e) {
            return false;
        }
        if (sb.length() < 3) return false;
        out.append(sb);
        return true;
    }

    @Override
    protected void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(OUT_PATH));
        try {
            ReferenceManager refMgr = currentProgram.getReferenceManager();

            out.println("==== SOURCE FILE STRING REFERENCING FUNCTIONS ====");
            for (String s : SOURCE_FILE_STRINGS) {
                Address strAddr = findFirst(s);
                out.println("-- " + s + " --");
                if (strAddr == null) {
                    out.println("   not found");
                    continue;
                }
                out.println("   address: " + strAddr);
                ReferenceIterator refs = refMgr.getReferencesTo(strAddr);
                java.util.LinkedHashSet<String> fns = new java.util.LinkedHashSet<>();
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function fn = getFunctionContaining(ref.getFromAddress());
                    if (fn != null) {
                        fns.add(fn.getName() + " @ " + fn.getEntryPoint());
                    } else {
                        fns.add("<no function> @ " + ref.getFromAddress());
                    }
                }
                out.println("   " + fns.size() + " referencing site(s):");
                for (String f : fns) out.println("     " + f);
            }
            out.println();

            out.println("==== NETEVENT NAME TABLE RECOVERY ATTEMPT ====");
            Address anchorStr = findFirst(ANCHOR_STRING);
            if (anchorStr == null) {
                out.println("Anchor string '" + ANCHOR_STRING + "' not found.");
            } else {
                out.println("Anchor string '" + ANCHOR_STRING + "' at " + anchorStr);
                ReferenceIterator refs = refMgr.getReferencesTo(anchorStr);
                if (!refs.hasNext()) {
                    out.println("No references to anchor string found - cannot locate table.");
                } else {
                    Reference ref = refs.next();
                    Address tableSlot = ref.getFromAddress();
                    out.println("First xref from: " + tableSlot
                        + " in function " + describeFn(tableSlot));
                    out.println();

                    for (int ptrSize : new int[]{4, 8}) {
                        out.println("---- scanning as " + (ptrSize * 8) + "-bit pointer table around "
                            + tableSlot + " ----");
                        TreeMap<Integer, String> found = new TreeMap<>();
                        for (int dir = -1; dir <= 1; dir += 2) {
                            for (int i = 0; i <= SCAN_RADIUS_ENTRIES; i++) {
                                int idx = dir * i;
                                if (idx == 0 && dir == -1) continue;
                                Address slot = tableSlot.add((long) idx * ptrSize);
                                try {
                                    long raw = ptrSize == 4
                                        ? (currentProgram.getMemory().getInt(slot) & 0xFFFFFFFFL)
                                        : currentProgram.getMemory().getLong(slot);
                                    if (raw == 0) { if (i > 0) break; else continue; }
                                    Address target = currentProgram.getAddressFactory()
                                        .getDefaultAddressSpace().getAddress(raw);
                                    StringBuilder sval = new StringBuilder();
                                    if (looksLikeString(target, sval)) {
                                        found.put(idx, sval.toString());
                                    } else if (i > 0) {
                                        break;
                                    }
                                } catch (Exception e) {
                                    if (i > 0) break;
                                }
                            }
                        }
                        out.println("Recovered " + found.size() + " entries (index relative to anchor slot):");
                        for (java.util.Map.Entry<Integer, String> e : found.entrySet()) {
                            out.println("  [" + e.getKey() + "] " + e.getValue());
                        }
                        out.println();
                    }
                }
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + OUT_PATH);
    }

    private String describeFn(Address addr) {
        Function fn = getFunctionContaining(addr);
        return fn == null ? "<none>" : fn.getName() + " @ " + fn.getEntryPoint();
    }
}
