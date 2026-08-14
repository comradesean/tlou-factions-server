// Ground-truth emulation of the ticket-server cipher primitives using
// Ghidra's own PPC pcode semantics (not hand-derived logic), to find where
// a hand-reimplementation in Python diverges from real execution.
//
// Sets up a scratch stack + scratch buffers, calls FUN_00db5ec0(key_addr,
// counter, out_state_addr) via emulation, dumps the resulting 16-byte
// state, then also emulates one round of FUN_00db7e08 (decrypt) over the
// first real ciphertext word using that state, dumping every register at
// every step so a human/Python trace can be diffed against it.
//
// Args: outPath keyAddrHex counterDec
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.pcode.emulate.EmulateExecutionState;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.math.BigInteger;

public class EmulateCipherFuncs extends GhidraScript {

    private PrintWriter out;

    private void log(String s) {
        out.println(s);
        println(s);
    }

    private String hex32(long v) {
        return String.format("0x%08x", v & 0xffffffffL);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        long keyAddrVal = Long.parseLong(args[1], 16);
        long counter = Long.parseLong(args[2]);

        out = new PrintWriter(new FileWriter(outPath));
        try {
            AddressSpace space = currentProgram.getAddressFactory().getDefaultAddressSpace();
            Address keyAddr = space.getAddress(keyAddrVal);

            EmulatorHelper emu = new EmulatorHelper(currentProgram);
            try {
                // Scratch memory: create a writable block for stack + output buffers,
                // well away from any real program content.
                long scratchBase = 0x60000000L;
                Address scratchStart = space.getAddress(scratchBase);
                MemoryBlock existing = currentProgram.getMemory().getBlock(scratchStart);
                if (existing == null) {
                    int txId = currentProgram.startTransaction("scratch");
                    boolean txOk = false;
                    try {
                        currentProgram.getMemory().createInitializedBlock(
                            "EMU_SCRATCH", scratchStart, 0x20000, (byte) 0, monitor, false);
                        txOk = true;
                    } finally {
                        currentProgram.endTransaction(txId, false); // never commit - abort so nothing is saved
                    }
                }

                long stackTop = scratchBase + 0x10000;   // stack grows down from here
                long outStateAddr = scratchBase + 0x11000; // 20-byte key-schedule state output
                long dataBufAddr = scratchBase + 0x12000;  // scratch data buffer for round calls
                long sentinelRet = scratchBase + 0x1000;   // fake return address to stop emulation

                emu.writeRegister(emu.getPCRegister(), BigInteger.valueOf(0x00db5ec0L));
                emu.writeRegister("r1", BigInteger.valueOf(stackTop));
                emu.writeRegister("r3", BigInteger.valueOf(keyAddrVal));
                emu.writeRegister("r4", BigInteger.valueOf(counter));
                emu.writeRegister("r5", BigInteger.valueOf(outStateAddr));
                emu.writeRegister("LR", BigInteger.valueOf(sentinelRet));
                // r2 (TOC) - use the value the real function expects; read from its own
                // context if possible, else leave as whatever's already set (the emulator
                // seeds registers from the current program context/analysis by default in
                // some Ghidra versions - explicit to be safe):
                Function fn = getFunctionAt(space.getAddress(0x00db5ec0L));
                if (fn != null) {
                    // best effort - not all Ghidra versions expose per-function TOC directly;
                    // FUN_00db5ec0 doesn't reference the TOC itself (confirmed via disasm -
                    // no lwz ...,(r2) in this function), so this is likely unnecessary, but
                    // set a sane default (0) to avoid stale/garbage TOC use just in case.
                }

                log("==== Emulating FUN_00db5ec0(key=" + keyAddr + ", counter=" + counter + ", out=" + hex32(outStateAddr) + ") ====");
                log("Key bytes at " + keyAddr + ": " + bytesHex(emu, keyAddr, 16));

                int steps = 0;
                int maxSteps = 20000;
                Address stopAddr = space.getAddress(sentinelRet);
                while (steps < maxSteps) {
                    Address pc = emu.readRegister(emu.getPCRegister()) != null
                        ? space.getAddress(emu.readRegister(emu.getPCRegister()).longValue())
                        : null;
                    if (pc == null || pc.equals(stopAddr)) break;
                    boolean ok = emu.step(monitor);
                    if (!ok) {
                        log("emulation step failed at " + pc + ": " + emu.getLastError());
                        break;
                    }
                    steps++;
                }
                log("Stopped after " + steps + " steps at PC=" + emu.readRegister(emu.getPCRegister()));

                log("Output state (20 bytes at " + hex32(outStateAddr) + "): " + bytesHex(emu, space.getAddress(outStateAddr), 20));
                log("Output state as 4 BE words:");
                for (int i = 0; i < 4; i++) {
                    long w = readBEWord(emu, outStateAddr + i * 4);
                    log("  state[" + i + "] = " + hex32(w));
                }

                // ---- Now emulate ONE round of decrypt (FUN_00db7e08) over the real
                // ciphertext word bb 75 ef e6, using the state we just derived ----
                byte[] cipherWordBytes = new byte[] {
                    (byte) 0xbb, (byte) 0x75, (byte) 0xef, (byte) 0xe6
                };
                emu.writeMemory(space.getAddress(dataBufAddr), cipherWordBytes);
                // Also write a second word after it (arbitrary, e08 processes len=4 only
                // so this shouldn't matter, but the function reads data[len] as a sentinel
                // save/restore - give it something defined):
                emu.writeMemory(space.getAddress(dataBufAddr + 4), new byte[] {0,0,0,0});

                emu.writeRegister(emu.getPCRegister(), BigInteger.valueOf(0x00db7e08L));
                emu.writeRegister("r1", BigInteger.valueOf(stackTop));
                emu.writeRegister("r3", BigInteger.valueOf(outStateAddr)); // state ptr
                emu.writeRegister("r4", BigInteger.valueOf(dataBufAddr));  // data ptr
                emu.writeRegister("r5", BigInteger.valueOf(4));            // len = 4 (one word)
                emu.writeRegister("LR", BigInteger.valueOf(sentinelRet));

                log("");
                log("==== Emulating FUN_00db7e08(state, ciphertext_word=bb75efe6, len=4) ====");
                steps = 0;
                while (steps < maxSteps) {
                    Address pc = emu.readRegister(emu.getPCRegister()) != null
                        ? space.getAddress(emu.readRegister(emu.getPCRegister()).longValue())
                        : null;
                    if (pc == null || pc.equals(stopAddr)) break;
                    boolean ok = emu.step(monitor);
                    if (!ok) {
                        log("emulation step failed at " + pc + ": " + emu.getLastError());
                        break;
                    }
                    steps++;
                }
                log("Stopped after " + steps + " steps at PC=" + emu.readRegister(emu.getPCRegister()));
                log("Decrypted word bytes at " + hex32(dataBufAddr) + ": " + bytesHex(space.getAddress(dataBufAddr), 4));
                log("Post-call state (16 bytes at " + hex32(outStateAddr) + "): " + bytesHex(space.getAddress(outStateAddr), 16));

            } finally {
                emu.dispose();
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }

    private long readBEWord(EmulatorHelper emu, long addr) throws Exception {
        byte[] b = emu.readMemory(currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(addr), 4);
        return ((long)(b[0] & 0xff) << 24) | ((b[1] & 0xff) << 16) | ((b[2] & 0xff) << 8) | (b[3] & 0xff);
    }

    private String bytesHex(EmulatorHelper emu, Address a, int len) {
        try {
            byte[] b = emu.readMemory(a, len);
            StringBuilder sb = new StringBuilder();
            for (byte x : b) sb.append(String.format("%02x ", x));
            return sb.toString();
        } catch (Exception e) {
            return "(read failed: " + e + ")";
        }
    }
}
