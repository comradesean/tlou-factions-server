// 1) List functions referencing net-tus-variable.cpp / net-clan-manager.cpp source strings.
// 2) Search all named symbols for "Tus"/"Clan" substrings (NID-resolved SDK functions land
//    here with real names, e.g. sceNpTusGetData) and list their callers - much more useful
//    than blind decompilation of unnamed FUN_ functions.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;

public class DigIntoTusAndClan extends GhidraScript {

    private static final List<String> SOURCE_FILE_STRINGS = Arrays.asList(
        "game/net/net-tus-variable.cpp",
        "game/net/net-clan-manager.cpp",
        "game/net/net-booster-manager.cpp",
        "game/net/net-buff-manager.cpp",
        "game/net/in-game-commerce.cpp"
    );

    private static final List<String> SYMBOL_SUBSTRINGS = Arrays.asList(
        "tus", "clan", "commerce", "booster"
    );

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/tus_clan_dig_report.txt";

    private Address findFirst(String s) throws Exception {
        return currentProgram.getMemory().findBytes(
            currentProgram.getMinAddress(), s.getBytes("US-ASCII"), null, true, monitor);
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
                LinkedHashSet<String> fns = new LinkedHashSet<>();
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function fn = getFunctionContaining(ref.getFromAddress());
                    fns.add(fn != null ? fn.getName() + " @ " + fn.getEntryPoint()
                                        : "<no function> @ " + ref.getFromAddress());
                }
                out.println("   " + fns.size() + " referencing site(s):");
                for (String f : fns) out.println("     " + f);
            }
            out.println();

            out.println("==== NAMED SYMBOLS MATCHING (case-insensitive) " + SYMBOL_SUBSTRINGS + " ====");
            SymbolTable symTab = currentProgram.getSymbolTable();
            SymbolIterator symIt = symTab.getSymbolIterator();
            while (symIt.hasNext()) {
                Symbol sym = symIt.next();
                String name = sym.getName();
                String lname = name.toLowerCase();
                boolean match = false;
                for (String sub : SYMBOL_SUBSTRINGS) {
                    if (lname.contains(sub)) { match = true; break; }
                }
                if (!match) continue;
                out.println("-- " + name + " @ " + sym.getAddress() + " (" + sym.getSymbolType() + ") --");
                ReferenceIterator refs = refMgr.getReferencesTo(sym.getAddress());
                LinkedHashSet<String> callers = new LinkedHashSet<>();
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function fn = getFunctionContaining(ref.getFromAddress());
                    callers.add(fn != null ? fn.getName() + " @ " + fn.getEntryPoint()
                                            : "<no function> @ " + ref.getFromAddress());
                }
                out.println("   " + callers.size() + " caller site(s):");
                for (String c : callers) out.println("     " + c);
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + OUT_PATH);
    }
}
