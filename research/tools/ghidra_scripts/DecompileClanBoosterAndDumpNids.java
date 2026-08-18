// 1) Decompile all net-clan-manager.cpp / net-booster-manager.cpp / net-buff-manager.cpp
//    referencing functions found in the prior pass.
// 2) Dump raw NIDs for the sceNp2 import table (29 funcs) to check whether sceNpTus is
//    actually imported/resolved, since a name-substring search came up empty.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.List;

public class DecompileClanBoosterAndDumpNids extends GhidraScript {

    private static final List<Long> CLAN_FUNCS = Arrays.asList(
        0x0037b2ccL, 0x0037b770L, 0x0037a28cL, 0x0037a494L, 0x00378e38L,
        0x0037839cL, 0x00378780L, 0x0037ed64L, 0x0037d6f0L, 0x0037cf90L
    );

    private static final List<Long> BOOSTER_FUNCS = Arrays.asList(
        0x0036708cL, 0x00367360L, 0x00366884L, 0x00366bf4L, 0x00366f3cL,
        0x0036583cL, 0x00365c6cL, 0x00365e20L, 0x00365f64L, 0x00365088L,
        0x003651a4L, 0x003652c0L, 0x00365620L, 0x00364ca4L, 0x00364d88L,
        0x00364e64L, 0x00364f3cL
    );

    private static final List<Long> BUFF_FUNCS = Arrays.asList(0x00368550L);

    private static final long SCENP2_NID_TABLE = 0xE594C8L;
    private static final long SCENP2_FUNC_TABLE = 0x12530E4L;
    private static final int SCENP2_NUM_FUNC = 29;

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/clan_booster_decompile_report.txt";

    private void decompileGroup(PrintWriter out, DecompInterface decomp, String label, List<Long> addrs)
            throws Exception {
        out.println("==== " + label + " (" + addrs.size() + " functions) ====");
        for (long a : addrs) {
            Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(a);
            Function fn = getFunctionAt(addr);
            if (fn == null) fn = getFunctionContaining(addr);
            out.println("---- " + addr + " (" + (fn == null ? "no function" : fn.getName()) + ") ----");
            if (fn == null) { out.println("(no function at this address)\n"); continue; }
            DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
            if (res.decompileCompleted() && res.getDecompiledFunction() != null) {
                out.println(res.getDecompiledFunction().getC());
            } else {
                out.println("(decompilation failed: " + res.getErrorMessage() + ")");
            }
            out.println();
        }
    }

    @Override
    protected void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(OUT_PATH));
        try {
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);

            decompileGroup(out, decomp, "net-clan-manager.cpp", CLAN_FUNCS);
            decompileGroup(out, decomp, "net-booster-manager.cpp", BOOSTER_FUNCS);
            decompileGroup(out, decomp, "net-buff-manager.cpp", BUFF_FUNCS);

            decomp.dispose();

            out.println("==== sceNp2 RAW NID TABLE (checking for sceNpTus) ====");
            SymbolTable symTab = currentProgram.getSymbolTable();
            for (int i = 0; i < SCENP2_NUM_FUNC; i++) {
                Address nidSlot = currentProgram.getAddressFactory().getDefaultAddressSpace()
                    .getAddress(SCENP2_NID_TABLE + (long) i * 4);
                Address funcSlot = currentProgram.getAddressFactory().getDefaultAddressSpace()
                    .getAddress(SCENP2_FUNC_TABLE + (long) i * 4);
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
        println("Wrote report to " + OUT_PATH);
    }
}
