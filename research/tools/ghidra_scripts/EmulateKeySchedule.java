// Ground-truth checkpointed emulation of FUN_00db5ec0 specifically, dumping
// state at each internal call boundary, to find exactly where a Python
// reimplementation diverges. Args: outPath keyAddrHex counterDec
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.mem.MemoryBlock;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.math.BigInteger;
import java.util.LinkedHashMap;
import java.util.Map;

public class EmulateKeySchedule extends GhidraScript {
    private PrintWriter out;

    private void log(String s) {
        out.println(s);
        println(s);
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
            EmulatorHelper emu = new EmulatorHelper(currentProgram);
            try {
                long scratchBase = 0x60000000L;
                Address scratchStart = space.getAddress(scratchBase);
                if (currentProgram.getMemory().getBlock(scratchStart) == null) {
                    int txId = currentProgram.startTransaction("scratch");
                    try {
                        currentProgram.getMemory().createInitializedBlock(
                            "EMU_SCRATCH", scratchStart, 0x20000, (byte) 0, monitor, false);
                    } finally {
                        currentProgram.endTransaction(txId, false);
                    }
                }

                long stackTop = scratchBase + 0x10000;
                long outStateAddr = scratchBase + 0x11000;
                long sentinelRet = scratchBase + 0x1000;

                emu.writeRegister(emu.getPCRegister(), BigInteger.valueOf(0x00db5ec0L));
                emu.writeRegister("r1", BigInteger.valueOf(stackTop));
                emu.writeRegister("r3", BigInteger.valueOf(keyAddrVal));
                emu.writeRegister("r4", BigInteger.valueOf(counter));
                emu.writeRegister("r5", BigInteger.valueOf(outStateAddr));
                emu.writeRegister("LR", BigInteger.valueOf(sentinelRet));

                // Checkpoints: address -> label. r1 at entry = stackTop, so all
                // frame-relative offsets below are stackTop - 0xb0 (post stdu) + offset.
                long frame = stackTop - 0xb0; // r1 value INSIDE the function after stdu
                Map<Long, String> checkpoints = new LinkedHashMap<>();
                checkpoints.put(0x00db5f8cL, "after 1st FUN_00db7c80 (byte-swap raw key) -> out_state[0:16]");
                checkpoints.put(0x00db5fa4L, "after FUN_00db7f88 (mix counter, 1 word) -> out_state[0:16]");
                checkpoints.put(0x00db5fd4L, "BEFORE 2nd FUN_00db7c80 (scratch2 @ r1+0x74, pre-swap, 16 bytes)");
                checkpoints.put(0x00db5fd8L, "AFTER 2nd FUN_00db7c80 (scratch2 @ r1+0x74, post-swap, 16 bytes) = reversed_words");
                checkpoints.put(0x00db5fecL, "after FUN_00db7cb0 (finalize round) -> out_state[0:16] FINAL");

                Address stopAddr = space.getAddress(sentinelRet);
                int steps = 0, maxSteps = 50000;
                while (steps < maxSteps) {
                    BigInteger pcVal = emu.readRegister(emu.getPCRegister());
                    if (pcVal == null) break;
                    long pcLong = pcVal.longValue();
                    if (pcLong == sentinelRet) break;
                    String label = checkpoints.get(pcLong);
                    if (label != null) {
                        log(String.format("[pc=%08x] %s", pcLong, label));
                        log("  out_state[0:16] = " + hex(emu, space.getAddress(outStateAddr), 16));
                        log("  scratch2 r1+0x74 (16B) = " + hex(emu, space.getAddress(frame + 0x74), 16));
                        log("  r16..r19 = " + regHex(emu, "r16") + " " + regHex(emu, "r17") + " " + regHex(emu, "r18") + " " + regHex(emu, "r19"));
                    }
                    boolean ok = emu.step(monitor);
                    if (!ok) {
                        log("step failed at " + Long.toHexString(pcLong) + ": " + emu.getLastError());
                        break;
                    }
                    steps++;
                }
                log("done, " + steps + " steps");
                log("FINAL out_state[0:16] = " + hex(emu, space.getAddress(outStateAddr), 16));
            } finally {
                emu.dispose();
            }
        } finally {
            out.close();
        }
        println("Wrote report to " + outPath);
    }

    private String hex(EmulatorHelper emu, Address a, int len) {
        try {
            byte[] b = emu.readMemory(a, len);
            StringBuilder sb = new StringBuilder();
            for (byte x : b) sb.append(String.format("%02x ", x));
            return sb.toString();
        } catch (Exception e) {
            return "(read failed: " + e + ")";
        }
    }

    private String regHex(EmulatorHelper emu, String reg) {
        BigInteger v = emu.readRegister(reg);
        return v == null ? "null" : String.format("%08x", v.longValue() & 0xffffffffL);
    }
}
