// Resolve NetEvent-derived class vtable pointers from their TOC slot offsets
// (relative to the same TOC base used by FUN_0038ec00's factory table, confirmed
// as the pointer value stored at address 0x012fdef4), then dump + decompile the
// virtual function slots at several candidate offsets (0x4, 0x8, 0xc, 0x10, 0x14,
// 0x18, 0x1c, 0x20) for each vtable, since those are the ones observed being
// invoked polymorphically in FUN_00ace694 / FUN_00acecd0 (the confirmed
// event-queue processing functions).
//
// Args: outPath name1 offset1Hex name2 offset2Hex ...   (offsets may be negative,
// e.g. "-7ee0", matching Ghidra's decompiler output style)
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ResolveNetEventVtables extends GhidraScript {
    static final long TOC_BASE = 0x1271330L;
    static final int[] SLOTS = {0x0, 0x4, 0x8, 0xc, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24};

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        Memory mem = currentProgram.getMemory();
        var space = currentProgram.getAddressFactory().getDefaultAddressSpace();

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        PrintWriter out = new PrintWriter(new FileWriter(outPath));
        try {
            for (int i = 1; i < args.length; i += 2) {
                String name = args[i];
                long off = Long.parseLong(args[i + 1], 16);
                long slot = (TOC_BASE + off) & 0xffffffffL;
                Address slotAddr = space.getAddress(slot);
                int vtableAddr;
                try {
                    vtableAddr = mem.getInt(slotAddr);
                } catch (Exception e) {
                    out.println("==== " + name + " (offset " + args[i+1] + ", slot " + slotAddr + ") FAILED: " + e + " ====\n");
                    continue;
                }
                Address vtable = space.getAddress(vtableAddr & 0xffffffffL);
                out.println("==== " + name + ": offset " + args[i+1] + " -> slot " + slotAddr + " -> vtable " + vtable + " ====");
                for (int s : SLOTS) {
                    Address slotPtrAddr = vtable.add(s);
                    int opdPtr;
                    try {
                        opdPtr = mem.getInt(slotPtrAddr);
                    } catch (Exception e) {
                        out.println("  [vtable+0x" + Integer.toHexString(s) + "] (unreadable)");
                        continue;
                    }
                    // PPC32 ABI: vtable slot holds a pointer to an .opd descriptor
                    // {code_addr, toc_addr}; dereference once more to get real code addr.
                    Address opdAddr = space.getAddress(opdPtr & 0xffffffffL);
                    int codeAddrRaw;
                    try {
                        codeAddrRaw = mem.getInt(opdAddr);
                    } catch (Exception e) {
                        out.println("  [vtable+0x" + Integer.toHexString(s) + "] -> opd " + opdAddr + " (unreadable code word)");
                        continue;
                    }
                    Address fnAddr = space.getAddress(codeAddrRaw & 0xffffffffL);
                    Function fn = getFunctionAt(fnAddr);
                    String fname = (fn != null) ? fn.getName() : "(no function at " + fnAddr + ")";
                    out.println("  [vtable+0x" + Integer.toHexString(s) + "] -> opd " + opdAddr + " -> " + fnAddr + " " + fname);
                }
                out.println();
            }

            out.println("\n\n==== DECOMPILED TARGETS ====\n");
            // Second pass: decompile every unique function we found (excluding null/invalid)
            java.util.LinkedHashSet<Long> seen = new java.util.LinkedHashSet<>();
            for (int i = 1; i < args.length; i += 2) {
                long off = Long.parseLong(args[i + 1], 16);
                long slot = (TOC_BASE + off) & 0xffffffffL;
                Address slotAddr = space.getAddress(slot);
                int vtableAddr;
                try { vtableAddr = mem.getInt(slotAddr); } catch (Exception e) { continue; }
                Address vtable = space.getAddress(vtableAddr & 0xffffffffL);
                for (int s : SLOTS) {
                    int opdPtr;
                    try { opdPtr = mem.getInt(vtable.add(s)); } catch (Exception e) { continue; }
                    int codeAddrRaw;
                    try { codeAddrRaw = mem.getInt(space.getAddress(opdPtr & 0xffffffffL)); } catch (Exception e) { continue; }
                    long fa = codeAddrRaw & 0xffffffffL;
                    if (fa == 0 || seen.contains(fa)) continue;
                    seen.add(fa);
                    Address fnAddr = space.getAddress(fa);
                    Function fn = getFunctionAt(fnAddr);
                    if (fn == null) {
                        try {
                            disassemble(fnAddr);
                            fn = createFunction(fnAddr, "vfn_" + fnAddr);
                        } catch (Exception e) {
                            out.println("---- " + args[i] + " vtable slot @ " + fnAddr + ": could not create function (" + e + ") ----\n");
                            continue;
                        }
                    }
                    if (fn == null) continue; // still failed
                    out.println("---- " + args[i] + " vtable+0x" + Integer.toHexString(s) + " = " + fn.getName() + " @ " + fnAddr + " ----");
                    DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
                    if (res.decompileCompleted() && res.getDecompiledFunction() != null) {
                        out.println(res.getDecompiledFunction().getC());
                    } else {
                        out.println("(decompilation failed: " + res.getErrorMessage() + ")");
                    }
                    out.println();
                }
            }
            decomp.dispose();
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }
}
