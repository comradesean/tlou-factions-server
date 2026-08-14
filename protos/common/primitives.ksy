meta:
  id: primitives
  endian: be
  license: CC0-1.0
doc: |
  Shared reusable types for TLOU Factions packet definitions. STATUS: placeholder.
  Wire endianness is assumed big-endian (matching the PS3/Cell PPU host) but this
  is NOT confirmed — many games explicitly pick an endianness independent of host
  CPU. Treat every type below as a hypothesis until confirmed against a real capture
  or decompiled serialization code.
doc-ref: ../../docs/protocol/README.md
types:
  vec3:
    doc: "Hypothesis: 3x IEEE-754 float32, common for a position/direction vector. Not yet confirmed."
    seq:
      - id: x
        type: f4
      - id: y
        type: f4
      - id: z
        type: f4
