// Finds functions referencing content-delivery / decrypt-related strings and decompiles them,
// to characterize the *.crypt decryption routine used for net1.bin.psarc.crypt etc.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class FindCryptDecryptRoutine extends GhidraScript {

    private static final List<String> TARGET_STRINGS = Arrays.asList(
        "Content Delivery : %s",
        "Decrypt failed",
        "net1.bin",
        "S3 bucket : %s",
        "http://%s.s3.amazonaws.com",
        "http://%s.naughtydog.com",
        "%s/%s/%s.psarc.crypt",
        "%s/%s.crypt",
        "ERROR NET INIT %x",
        "NetInit Started",
        "NetInit Done"
    );

    private static final String OUT_PATH =
        "/mnt/f/ClaudeHole/tlou_factions/research/ghidra/crypt_decrypt_report.txt";

    private Address findFirst(String s) throws Exception {
        return currentProgram.getMemory().findBytes(
            currentProgram.getMinAddress(), s.getBytes("US-ASCII"), null, true, monitor);
    }

    @Override
    protected void run() throws Exception {
        PrintWriter out = new PrintWriter(new FileWriter(OUT_PATH));
        try {
            DecompInterface decomp = new DecompInterface();
            decomp.openProgram(currentProgram);

            ReferenceManager refMgr = currentProgram.getReferenceManager();
            Set<Function> seenFunctions = new LinkedHashSet<>();

            for (String s : TARGET_STRINGS) {
                Address strAddr = findFirst(s);
                out.println("==== STRING: " + s);
                if (strAddr == null) {
                    out.println("   not found");
                    continue;
                }
                out.println("   address: " + strAddr);
                ReferenceIterator refs = refMgr.getReferencesTo(strAddr);
                LinkedHashSet<String> fns = new LinkedHashSet<>();
                int refCount = 0;
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Address fromAddr = ref.getFromAddress();
                    Function fn = getFunctionContaining(fromAddr);
                    fns.add(fn != null ? fn.getName() + " @ " + fn.getEntryPoint()
                                        : "<no function> @ " + fromAddr);
                    refCount++;
                    if (fn != null) seenFunctions.add(fn);
                }
                out.println("   " + refCount + " reference(s):");
                for (String f : fns) out.println("     " + f);
                out.println();
            }

            out.println("==== DECOMPILED FUNCTIONS (" + seenFunctions.size() + ") ====");
            out.println();
            for (Function fn : seenFunctions) {
                out.println("---- " + fn.getName() + " @ " + fn.getEntryPoint() + " ----");
                DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
                if (res.decompileCompleted() && res.getDecompiledFunction() != null) {
                    out.println(res.getDecompiledFunction().getC());
                } else {
                    out.println("(decompilation failed: " + res.getErrorMessage() + ")");
                }
                out.println();
            }
            decomp.dispose();
        } finally {
            out.close();
        }
        println("Wrote report to " + OUT_PATH);
    }
}
