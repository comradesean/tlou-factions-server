// Resolve derived-class vtables for net_event_type opcodes constructed via a
// dedicated external constructor function (as opposed to the inline-construction
// opcodes handled by ResolveNetEventVtables.java).
//
// Each such constructor loads its own derived vtable pointer via a TOC-relative
// load off a per-compilation-unit anchor global (decompiled by Ghidra as e.g.
// "PTR_DAT_012fdfa4" / "PTR_PTR_012fdfa0" - a global memory cell, at the address
// embedded in its own symbol name, holding the raw TOC base pointer value used by
// that function's code). This script takes that anchor address directly (read
// from the constructor's own decompile output - see research/ghidra/batch*_
// constructors_decomp.txt) plus the derived-vtable offset (the "uVar1 = *(...)"
// line, NOT the "-0x8000"/"-0x7ffc"-style base-vtable line that gets overwritten),
// resolves: anchorVal = *anchorAddr; vtableAddr = *(anchorVal + offset); then
// double-dereferences vtable+0x8 (Deserialize) and vtable+0xc (Serialize) through
// the PPC32 .opd descriptor indirection (same gotcha as ResolveNetEventVtables.java)
// to get real function addresses, and decompiles both.
//
// Args: outPath name1 anchorAddrHex1 offsetHex1 name2 anchorAddrHex2 offsetHex2 ...
// offsetHex may be negative, e.g. "-7ffc".
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ResolveExternalCtorVtables extends GhidraScript {
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
            for (int i = 1; i < args.length; i += 3) {
                String name = args[i];
                long anchorAddrL = Long.parseLong(args[i + 1], 16);
                long off = Long.parseLong(args[i + 2], 16);
                Address anchorAddr = space.getAddress(anchorAddrL);
                int anchorVal;
                try {
                    anchorVal = mem.getInt(anchorAddr);
                } catch (Exception e) {
                    out.println("==== " + name + " anchor " + anchorAddr + " FAILED: " + e + " ====\n");
                    continue;
                }
                long slot = (anchorVal + off) & 0xffffffffL;
                Address slotAddr = space.getAddress(slot);
                int vtableAddrRaw;
                try {
                    vtableAddrRaw = mem.getInt(slotAddr);
                } catch (Exception e) {
                    out.println("==== " + name + " anchor=" + anchorAddr + " (val=0x" + Integer.toHexString(anchorVal) +
                        ") off=" + args[i+2] + " -> slot " + slotAddr + " FAILED: " + e + " ====\n");
                    continue;
                }
                Address vtable = space.getAddress(vtableAddrRaw & 0xffffffffL);
                out.println("==== " + name + ": anchor " + anchorAddr + " (=0x" + Integer.toHexString(anchorVal) +
                    ") + " + args[i+2] + " -> slot " + slotAddr + " -> vtable " + vtable + " ====");
                for (int s : SLOTS) {
                    Address slotPtrAddr = vtable.add(s);
                    int opdPtr;
                    try {
                        opdPtr = mem.getInt(slotPtrAddr);
                    } catch (Exception e) {
                        out.println("  [vtable+0x" + Integer.toHexString(s) + "] (unreadable)");
                        continue;
                    }
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

            out.println("\n\n==== DECOMPILED DESERIALIZE/SERIALIZE (vtable+0x8 / +0xc) ====\n");
            java.util.LinkedHashSet<Long> seen = new java.util.LinkedHashSet<>();
            for (int i = 1; i < args.length; i += 3) {
                String name = args[i];
                long anchorAddrL = Long.parseLong(args[i + 1], 16);
                long off = Long.parseLong(args[i + 2], 16);
                Address anchorAddr = space.getAddress(anchorAddrL);
                int anchorVal;
                try { anchorVal = mem.getInt(anchorAddr); } catch (Exception e) { continue; }
                long slot = (anchorVal + off) & 0xffffffffL;
                int vtableAddrRaw;
                try { vtableAddrRaw = mem.getInt(space.getAddress(slot)); } catch (Exception e) { continue; }
                Address vtable = space.getAddress(vtableAddrRaw & 0xffffffffL);
                for (int s : new int[]{0x8, 0xc}) {
                    int opdPtr;
                    try { opdPtr = mem.getInt(vtable.add(s)); } catch (Exception e) { continue; }
                    int codeAddrRaw;
                    try { codeAddrRaw = mem.getInt(space.getAddress(opdPtr & 0xffffffffL)); } catch (Exception e) { continue; }
                    long fa = codeAddrRaw & 0xffffffffL;
                    if (fa == 0) continue;
                    Address fnAddr = space.getAddress(fa);
                    Function fn = getFunctionAt(fnAddr);
                    if (fn == null) {
                        try {
                            disassemble(fnAddr);
                            fn = createFunction(fnAddr, "vfn_" + fnAddr);
                        } catch (Exception e) {
                            out.println("---- " + name + " vtable+0x" + Integer.toHexString(s) + " @ " + fnAddr + ": could not create function (" + e + ") ----\n");
                            continue;
                        }
                    }
                    if (fn == null) continue;
                    String tag = (s == 0x8) ? "Deserialize" : "Serialize";
                    out.println("---- " + name + " " + tag + " = " + fn.getName() + " @ " + fnAddr +
                        (seen.contains(fa) ? " (dup, already decompiled above)" : "") + " ----");
                    if (!seen.contains(fa)) {
                        seen.add(fa);
                        DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
                        if (res.decompileCompleted() && res.getDecompiledFunction() != null) {
                            out.println(res.getDecompiledFunction().getC());
                        } else {
                            out.println("(decompilation failed: " + res.getErrorMessage() + ")");
                        }
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
