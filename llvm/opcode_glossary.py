#!/usr/bin/env python3
"""opcode_glossary.py -- best-effort human-readable meanings for LLVM opcodes.

LLVM's AArch64/X86 backends emit machine-instruction mnemonics that encode a
lot of information in a compact, non-obvious way (e.g. ``ADDSWrs`` = "add,
setting flags, 32-bit register, shifted-register operand"). Exhaustively
cataloguing every variant (~1000+ across both targets) isn't practical, so
this module instead:

  1. Looks up the "base" mnemonic (e.g. ``ADD``, ``LDR``, ``MOVSX``) in a
     table of plain-English meanings.
  2. Decodes the systematic suffix that follows it (register width,
     addressing mode, operand kinds) using known naming conventions.
  3. Falls back to a loose keyword-based guess for anything unrecognized,
     rather than silently showing nothing.

Nothing here is guaranteed 100% accurate for every possible opcode --
it is a readability aid for the energy report, not an ISA reference.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Cross-target pseudo/meta instructions (same names on both backends)
# ---------------------------------------------------------------------------

_PSEUDO: dict[str, str] = {
    "NOP": "No operation",
    "COPY": "Register copy (pseudo-instruction)",
    "PHI": "SSA phi node (pseudo-instruction, resolved during register allocation)",
    "IMPLICIT_DEF": "Implicit/undefined register definition (pseudo-instruction)",
    "KILL": "Marks a register as dead (pseudo-instruction, no code emitted)",
    "DBG_VALUE": "Debug metadata: variable location (no code emitted)",
    "DBG_LABEL": "Debug metadata: source label (no code emitted)",
    "CFI_INSTRUCTION": "Call frame information directive (unwind metadata)",
    "EH_LABEL": "Exception-handling label (no code emitted)",
    "BUNDLE": "Instruction bundle marker (VLIW/packet grouping)",
    "ADJCALLSTACKDOWN": "Reserve stack space for an upcoming call's arguments",
    "ADJCALLSTACKUP": "Release stack space after a call returns",
}

# ---------------------------------------------------------------------------
# AArch64 base mnemonics
# ---------------------------------------------------------------------------

_AARCH64_BASES: dict[str, str] = {
    # arithmetic
    "ADD": "Add", "ADDS": "Add, setting flags",
    "SUB": "Subtract", "SUBS": "Subtract, setting flags",
    "ADC": "Add with carry", "ADCS": "Add with carry, setting flags",
    "SBC": "Subtract with carry (borrow)", "SBCS": "Subtract with carry, setting flags",
    "NEG": "Negate", "NEGS": "Negate, setting flags",
    "MUL": "Multiply", "MADD": "Multiply-add", "MSUB": "Multiply-subtract", "MNEG": "Multiply-negate",
    "SMULL": "Signed multiply (32x32 to 64-bit)", "UMULL": "Unsigned multiply (32x32 to 64-bit)",
    "SMADDL": "Signed multiply-add (32x32 to 64-bit)", "UMADDL": "Unsigned multiply-add (32x32 to 64-bit)",
    "SMSUBL": "Signed multiply-subtract (32x32 to 64-bit)", "UMSUBL": "Unsigned multiply-subtract (32x32 to 64-bit)",
    "MULH": "Multiply, high half of result",
    "SMULH": "Signed multiply, high 64 bits of 128-bit result",
    "UMULH": "Unsigned multiply, high 64 bits of 128-bit result",
    "SDIV": "Signed divide", "UDIV": "Unsigned divide",
    # logical
    "AND": "Bitwise AND", "ANDS": "Bitwise AND, setting flags",
    "ORR": "Bitwise OR", "ORN": "Bitwise OR NOT",
    "EOR": "Bitwise XOR", "EON": "Bitwise XOR NOT",
    "BIC": "Bitwise AND NOT (bit clear)", "BICS": "Bitwise AND NOT, setting flags",
    "MVN": "Bitwise NOT (move-not)",
    # move
    "MOV": "Move register/immediate",
    "MOVZ": "Move immediate, zeroing other bits",
    "MOVK": "Move immediate into one 16-bit slot, keeping the rest",
    "MOVN": "Move inverted (bitwise-NOT) immediate",
    # compare/test
    "CMP": "Compare (subtract, discard result, set flags)",
    "CMN": "Compare negative (add, discard result, set flags)",
    "TST": "Test bits (AND, discard result, set flags)",
    "CCMP": "Conditional compare", "CCMN": "Conditional compare negative",
    # shifts / bitfield
    "LSL": "Logical shift left", "LSR": "Logical shift right", "ASR": "Arithmetic shift right",
    "ROR": "Rotate right", "EXTR": "Extract register (bitfield from a register pair)",
    "RORV": "Rotate right by register", "LSLV": "Logical shift left by register",
    "LSRV": "Logical shift right by register", "ASRV": "Arithmetic shift right by register",
    "UBFM": "Unsigned bitfield move", "SBFM": "Signed bitfield move", "BFM": "Bitfield move",
    "UBFX": "Unsigned bitfield extract", "SBFX": "Signed bitfield extract", "BFXIL": "Bitfield insert, low",
    "BFI": "Bitfield insert", "BFC": "Bitfield clear",
    "CLZ": "Count leading zeros", "CLS": "Count leading sign bits",
    "RBIT": "Reverse bit order",
    "REV": "Reverse byte order", "REV16": "Reverse bytes within 16-bit halfwords",
    "REV32": "Reverse bytes within 32-bit words", "REV64": "Reverse bytes within 64-bit doubleword",
    "SXTB": "Sign-extend byte", "SXTH": "Sign-extend halfword", "SXTW": "Sign-extend word",
    "UXTB": "Zero-extend byte", "UXTH": "Zero-extend halfword",
    # load/store
    "LDR": "Load register", "LDUR": "Load register, unscaled offset",
    "LDRB": "Load byte, zero-extend", "LDRH": "Load halfword, zero-extend",
    "LDRSB": "Load byte, sign-extend", "LDRSH": "Load halfword, sign-extend", "LDRSW": "Load word, sign-extend",
    "LDP": "Load pair of registers", "LDNP": "Load pair, non-temporal (skip cache hint)",
    "LDXR": "Load exclusive register", "LDXRB": "Load exclusive byte", "LDXRH": "Load exclusive halfword",
    "LDAR": "Load-acquire register", "LDARB": "Load-acquire byte", "LDARH": "Load-acquire halfword",
    "STR": "Store register", "STUR": "Store register, unscaled offset",
    "STRB": "Store byte", "STRH": "Store halfword",
    "STP": "Store pair of registers", "STNP": "Store pair, non-temporal (skip cache hint)",
    "STXR": "Store exclusive register", "STXRB": "Store exclusive byte", "STXRH": "Store exclusive halfword",
    "STLR": "Store-release register", "STLRB": "Store-release byte", "STLRH": "Store-release halfword",
    "PRFM": "Prefetch memory",
    "ADR": "Form PC-relative address", "ADRP": "Form PC-relative address of a 4KB page",
    # branch / control
    "B": "Unconditional branch", "Bcc": "Conditional branch",
    "BL": "Branch with link (call)", "BLR": "Branch with link to register (indirect call)",
    "BR": "Branch to register (indirect jump)", "RET": "Return from subroutine",
    "CBZ": "Compare and branch if zero", "CBNZ": "Compare and branch if nonzero",
    "TBZ": "Test bit and branch if zero", "TBNZ": "Test bit and branch if nonzero",
    "CSEL": "Conditional select", "CSINC": "Conditional select and increment",
    "CSINV": "Conditional select and invert", "CSNEG": "Conditional select and negate",
    "CSET": "Conditional set to 1/0", "CSETM": "Conditional set to all-1s/0",
    "CINC": "Conditional increment", "CINV": "Conditional invert", "CNEG": "Conditional negate",
    # system
    "DSB": "Data synchronization barrier", "DMB": "Data memory barrier", "ISB": "Instruction synchronization barrier",
    "WFI": "Wait for interrupt", "WFE": "Wait for event", "SEV": "Send event", "SEVL": "Send event local",
    "HINT": "Hint instruction (no-op with micro-architectural hint)",
    "MSR": "Move to system register", "MRS": "Move from system register",
    "SYS": "System instruction", "SYSL": "System instruction with register result",
    "SVC": "Supervisor call (syscall)", "BRK": "Breakpoint trap", "HLT": "Halt", "ERET": "Exception return",
    # scalar float
    "FADD": "Floating-point add", "FSUB": "Floating-point subtract",
    "FMUL": "Floating-point multiply", "FDIV": "Floating-point divide",
    "FSQRT": "Floating-point square root",
    "FABS": "Floating-point absolute value", "FNEG": "Floating-point negate",
    "FMADD": "Floating-point fused multiply-add", "FMSUB": "Floating-point fused multiply-subtract",
    "FNMADD": "Floating-point negated fused multiply-add", "FNMSUB": "Floating-point negated fused multiply-subtract",
    "FMOV": "Floating-point/integer register move", "FCMP": "Floating-point compare",
    "FCCMP": "Floating-point conditional compare",
    "FSEL": "Floating-point conditional select", "FCSEL": "Floating-point conditional select",
    "FCVT": "Floating-point precision convert (single<->double)",
    "FCVTZS": "Floating-point to signed integer, round toward zero",
    "FCVTZU": "Floating-point to unsigned integer, round toward zero",
    "SCVTF": "Signed integer to floating-point convert", "UCVTF": "Unsigned integer to floating-point convert",
    "FMAX": "Floating-point maximum", "FMIN": "Floating-point minimum",
    "FMAXNM": "Floating-point maximum, propagating numbers over NaN",
    "FMINNM": "Floating-point minimum, propagating numbers over NaN",
    "FRINTA": "Round to integral, ties away from zero", "FRINTI": "Round to integral (current rounding mode)",
    "FRINTM": "Round to integral toward -infinity", "FRINTN": "Round to integral, ties to even",
    "FRINTP": "Round to integral toward +infinity", "FRINTX": "Round to integral, exact (raises inexact)",
    "FRINTZ": "Round to integral toward zero",
    # vector / SIMD
    "MLA": "Vector multiply-accumulate", "MLS": "Vector multiply-subtract",
    "FMLA": "Vector floating-point multiply-accumulate", "FMLS": "Vector floating-point multiply-subtract",
    "ZIP1": "Vector interleave, low halves", "ZIP2": "Vector interleave, high halves",
    "UZP1": "Vector de-interleave, even elements", "UZP2": "Vector de-interleave, odd elements",
    "TRN1": "Vector transpose, even elements", "TRN2": "Vector transpose, odd elements",
    "EXT": "Vector extract (concatenate and slice)", "DUP": "Vector duplicate/broadcast lane",
    "INS": "Vector insert lane", "CNT": "Vector population count per lane",
    "LD1": "Load 1 vector register (structure load)",
    "LD2": "Load 2 vector registers, de-interleaved",
    "LD3": "Load 3 vector registers, de-interleaved",
    "LD4": "Load 4 vector registers, de-interleaved",
    "ST1": "Store 1 vector register (structure store)",
    "ST2": "Store 2 vector registers, interleaved",
    "ST3": "Store 3 vector registers, interleaved",
    "ST4": "Store 4 vector registers, interleaved",
    "PMULL": "Vector polynomial multiply (long)",
    # crypto / checksum
    "CRC32": "CRC-32 checksum step", "CRC32C": "CRC-32C (Castagnoli) checksum step",
    "AESE": "AES single-round encryption", "AESD": "AES single-round decryption",
    "AESIMC": "AES inverse mix columns", "AESMC": "AES mix columns",
    "SHA1C": "SHA-1 hash update (choose)", "SHA1H": "SHA-1 fixed rotate",
    "SHA1M": "SHA-1 hash update (majority)", "SHA1P": "SHA-1 hash update (parity)",
    "SHA1SU0": "SHA-1 schedule update 0", "SHA1SU1": "SHA-1 schedule update 1",
    "SHA256H": "SHA-256 hash update", "SHA256H2": "SHA-256 hash update (2)",
    "SHA256SU0": "SHA-256 schedule update 0", "SHA256SU1": "SHA-256 schedule update 1",
}

# ---------------------------------------------------------------------------
# x86-64 base mnemonics
# ---------------------------------------------------------------------------

_X86_BASES: dict[str, str] = {
    "ADD": "Add", "SUB": "Subtract", "AND": "Bitwise AND", "OR": "Bitwise OR", "XOR": "Bitwise XOR",
    "MOV": "Move/copy data", "MOVSX": "Move with sign-extension", "MOVZX": "Move with zero-extension",
    "CMP": "Compare (subtract, discard result, set flags)", "TEST": "Test bits (AND, discard result, set flags)",
    "SHL": "Shift left", "SHR": "Shift right, logical", "SAR": "Shift right, arithmetic",
    "ROL": "Rotate left", "ROR": "Rotate right",
    "NOT": "Bitwise NOT", "NEG": "Negate (two's complement)",
    "IMUL": "Signed multiply", "MUL": "Unsigned multiply",
    "IDIV": "Signed divide", "DIV": "Unsigned divide",
    "LEA": "Load effective address (address computation, no memory access)",
    "BSF": "Bit scan forward (find lowest set bit)", "BSR": "Bit scan reverse (find highest set bit)",
    "BSWAP": "Byte swap (endianness reverse)", "POPCNT": "Population count (count set bits)",
    "CTLZ": "Count leading zeros", "CTTZ": "Count trailing zeros",
    "PUSH": "Push onto the stack", "POP": "Pop from the stack",
    "XCHG": "Exchange two operands", "LEAVE": "Tear down stack frame (mov rsp,rbp; pop rbp)",
    "JMP": "Unconditional jump",
    "JE": "Jump if equal", "JNE": "Jump if not equal",
    "JL": "Jump if less (signed)", "JLE": "Jump if less-or-equal (signed)",
    "JG": "Jump if greater (signed)", "JGE": "Jump if greater-or-equal (signed)",
    "JB": "Jump if below (unsigned)", "JBE": "Jump if below-or-equal (unsigned)",
    "JA": "Jump if above (unsigned)", "JAE": "Jump if above-or-equal (unsigned)",
    "JO": "Jump if overflow", "JNO": "Jump if no overflow",
    "JS": "Jump if sign (negative)", "JNS": "Jump if not sign (non-negative)",
    "JP": "Jump if parity even", "JNP": "Jump if parity odd",
    "CALL": "Call subroutine", "RET": "Return from subroutine", "RETQ": "Return from subroutine (64-bit)",
    "CMOVA": "Move if above (unsigned)", "CMOVAE": "Move if above-or-equal (unsigned)",
    "CMOVB": "Move if below (unsigned)", "CMOVBE": "Move if below-or-equal (unsigned)",
    "CMOVE": "Move if equal", "CMOVG": "Move if greater (signed)", "CMOVGE": "Move if greater-or-equal (signed)",
    "CMOVL": "Move if less (signed)", "CMOVLE": "Move if less-or-equal (signed)",
    "CMOVNE": "Move if not equal", "CMOVNO": "Move if no overflow", "CMOVNP": "Move if parity odd",
    "CMOVNS": "Move if not sign (non-negative)", "CMOVO": "Move if overflow",
    "CMOVP": "Move if parity even", "CMOVS": "Move if sign (negative)",
    "SETA": "Set byte to 1 if above (unsigned), else 0", "SETAE": "Set byte to 1 if above-or-equal, else 0",
    "SETB": "Set byte to 1 if below (unsigned), else 0", "SETBE": "Set byte to 1 if below-or-equal, else 0",
    "SETE": "Set byte to 1 if equal, else 0", "SETG": "Set byte to 1 if greater (signed), else 0",
    "SETGE": "Set byte to 1 if greater-or-equal, else 0", "SETL": "Set byte to 1 if less (signed), else 0",
    "SETLE": "Set byte to 1 if less-or-equal, else 0", "SETNE": "Set byte to 1 if not equal, else 0",
    "SETNO": "Set byte to 1 if no overflow, else 0", "SETNP": "Set byte to 1 if parity odd, else 0",
    "SETNS": "Set byte to 1 if not sign, else 0", "SETO": "Set byte to 1 if overflow, else 0",
    "SETP": "Set byte to 1 if parity even, else 0", "SETS": "Set byte to 1 if sign (negative), else 0",
    "SET": "Set byte to 1 if condition met, else 0",
    "CPUID": "CPU identification query", "RDTSC": "Read timestamp counter",
    "MFENCE": "Full memory fence", "SFENCE": "Store fence", "LFENCE": "Load fence",
    "PAUSE": "Spin-loop hint", "HLT": "Halt processor",
    "FADDrST0": "x87 add to ST0", "FADD": "x87 floating-point add", "FSUB": "x87 floating-point subtract",
    "FMUL": "x87 floating-point multiply", "FDIV": "x87 floating-point divide",
    "FCOM": "x87 compare", "FICOMP": "x87 integer compare and pop",
    "X87": "Legacy x87 floating-point instruction",
    "FLDr": "x87 load onto FP stack", "FSTr": "x87 store from FP stack",
    "FILDrm": "x87 load integer from memory", "FISTrm": "x87 store integer to memory",
    "ADDSS": "Add, scalar single-precision float", "ADDSD": "Add, scalar double-precision float",
    "SUBSS": "Subtract, scalar single-precision float", "SUBSD": "Subtract, scalar double-precision float",
    "MULSS": "Multiply, scalar single-precision float", "MULSD": "Multiply, scalar double-precision float",
    "DIVSS": "Divide, scalar single-precision float", "DIVSD": "Divide, scalar double-precision float",
    "SQRTSS": "Square root, scalar single-precision float", "SQRTSD": "Square root, scalar double-precision float",
    "ADDPS": "Add, packed single-precision floats", "ADDPD": "Add, packed double-precision floats",
    "SUBPS": "Subtract, packed single-precision floats", "SUBPD": "Subtract, packed double-precision floats",
    "MULPS": "Multiply, packed single-precision floats", "MULPD": "Multiply, packed double-precision floats",
    "DIVPS": "Divide, packed single-precision floats", "DIVPD": "Divide, packed double-precision floats",
    "SQRTPS": "Square root, packed single-precision floats", "SQRTPD": "Square root, packed double-precision floats",
    "FMA": "Fused multiply-add (generic)",
    "VFMADDPS": "Fused multiply-add, packed single-precision (AVX)",
    "VFMADDSS": "Fused multiply-add, scalar single-precision (AVX)",
    "VFMADDPD": "Fused multiply-add, packed double-precision (AVX)",
    "VFMADDSD": "Fused multiply-add, scalar double-precision (AVX)",
    "VFMSUBPS": "Fused multiply-subtract, packed single-precision (AVX)",
    "VFMSUBPD": "Fused multiply-subtract, packed double-precision (AVX)",
    "VFMADDSUBPS": "Fused multiply-add/subtract, alternating lanes, packed single-precision (AVX)",
    "VFMSUBADDPS": "Fused multiply-subtract/add, alternating lanes, packed single-precision (AVX)",
    "MOVAPS": "Move aligned packed single-precision floats", "MOVUPS": "Move unaligned packed single-precision floats",
    "MOVSS": "Move scalar single-precision float", "MOVSD": "Move scalar double-precision float",
    "MOVD": "Move 32-bit value between GPR and XMM", "MOVQ": "Move 64-bit value between GPR and XMM",
    "CVTSI2SS": "Convert integer to scalar single-precision float",
    "CVTSI2SD": "Convert integer to scalar double-precision float",
    "CVTSS2SI": "Convert scalar single-precision float to integer (round)",
    "CVTSD2SI": "Convert scalar double-precision float to integer (round)",
    "CVTTSS2SI": "Convert scalar single-precision float to integer (truncate)",
    "CVTTSD2SI": "Convert scalar double-precision float to integer (truncate)",
    "CVTPS2PD": "Convert packed single-precision floats to double-precision",
    "CVTPD2PS": "Convert packed double-precision floats to single-precision",
    "CVTDQ2PS": "Convert packed 32-bit integers to single-precision floats",
    "CVTPS2DQ": "Convert packed single-precision floats to 32-bit integers (round)",
    "CVTTPS2DQ": "Convert packed single-precision floats to 32-bit integers (truncate)",
    "UCOMISS": "Unordered compare scalar single-precision floats, set flags",
    "UCOMISD": "Unordered compare scalar double-precision floats, set flags",
    "COMISS": "Ordered compare scalar single-precision floats, set flags",
    "COMISD": "Ordered compare scalar double-precision floats, set flags",
    "PADDB": "Packed add, 8-bit lanes", "PADDW": "Packed add, 16-bit lanes",
    "PADDD": "Packed add, 32-bit lanes", "PADDQ": "Packed add, 64-bit lanes",
    "PSUBB": "Packed subtract, 8-bit lanes", "PSUBW": "Packed subtract, 16-bit lanes",
    "PSUBD": "Packed subtract, 32-bit lanes", "PSUBQ": "Packed subtract, 64-bit lanes",
    "PMULLD": "Packed multiply, 32-bit lanes, low half of result",
    "PMULHW": "Packed multiply, 16-bit lanes, high half (signed)",
    "PMULHUW": "Packed multiply, 16-bit lanes, high half (unsigned)",
    "PMULUDQ": "Packed unsigned multiply, 32x32 to 64-bit lanes",
    "PAND": "Packed bitwise AND", "POR": "Packed bitwise OR", "PXOR": "Packed bitwise XOR",
    "PANDN": "Packed bitwise AND-NOT",
    "PSHUFD": "Shuffle packed 32-bit lanes (immediate control)",
    "PSHUFB": "Shuffle bytes using a control mask",
    "PSHUFHW": "Shuffle high 16-bit lanes", "PSHUFLW": "Shuffle low 16-bit lanes",
    "PSLLD": "Packed shift left, 32-bit lanes", "PSLLQ": "Packed shift left, 64-bit lanes",
    "PSRLD": "Packed shift right (logical), 32-bit lanes", "PSRLQ": "Packed shift right (logical), 64-bit lanes",
    "PSRAD": "Packed shift right (arithmetic), 32-bit lanes",
    "PCMPEQD": "Packed compare equal, 32-bit lanes", "PCMPEQW": "Packed compare equal, 16-bit lanes",
    "PCMPEQB": "Packed compare equal, 8-bit lanes",
    "PCMPGTD": "Packed compare greater-than, 32-bit lanes", "PCMPGTB": "Packed compare greater-than, 8-bit lanes",
    "PMAXSB": "Packed signed maximum, 8-bit lanes", "PMAXSW": "Packed signed maximum, 16-bit lanes",
    "PMAXSD": "Packed signed maximum, 32-bit lanes",
    "PMINSB": "Packed signed minimum, 8-bit lanes", "PMINSW": "Packed signed minimum, 16-bit lanes",
    "PMINSD": "Packed signed minimum, 32-bit lanes",
    "PACKSSDW": "Pack 32-bit to 16-bit lanes, signed saturation",
    "PACKUSWB": "Pack 16-bit to 8-bit lanes, unsigned saturation",
    "PUNPCKLDQ": "Unpack/interleave low 32-bit lanes", "PUNPCKHDQ": "Unpack/interleave high 32-bit lanes",
    "PUNPCKLBW": "Unpack/interleave low 8-bit lanes to 16-bit", "PUNPCKHWD": "Unpack/interleave high 16-bit lanes to 32-bit",
    "PUNPCKLQDQ": "Unpack/interleave low 64-bit lanes", "PUNPCKHQDQ": "Unpack/interleave high 64-bit lanes",
    "PHADD": "Packed horizontal add", "PHSUBD": "Packed horizontal subtract, 32-bit lanes",
    "PMADDUBSW": "Multiply unsigned bytes by signed bytes and add adjacent pairs",
    "PMADDWD": "Multiply signed 16-bit lanes and add adjacent pairs to 32-bit",
    "PALIGNR": "Packed byte-align concatenation of two registers",
    "PABSB": "Packed absolute value, 8-bit lanes", "PABSW": "Packed absolute value, 16-bit lanes",
    "PABSD": "Packed absolute value, 32-bit lanes",
    "SHUFPS": "Shuffle packed single-precision floats (immediate control)",
    "SHUFPD": "Shuffle packed double-precision floats (immediate control)",
    "UNPCKLPS": "Unpack/interleave low single-precision floats", "UNPCKHPS": "Unpack/interleave high single-precision floats",
    "UNPCKLPD": "Unpack/interleave low double-precision floats", "UNPCKHPD": "Unpack/interleave high double-precision floats",
    "PMOVMSKB": "Move packed byte sign-mask bits into a GPR",
    "MOVMSKPS": "Move packed single-precision sign-mask bits into a GPR",
    "MOVMSKPD": "Move packed double-precision sign-mask bits into a GPR",
    "MASKMOVDQU": "Masked store of packed bytes to memory",
    "ANDNPS": "Bitwise AND-NOT on packed single-precision bits", "ANDPS": "Bitwise AND on packed single-precision bits",
    "ORPS": "Bitwise OR on packed single-precision bits", "XORPS": "Bitwise XOR on packed single-precision bits",
    "ANDNPD": "Bitwise AND-NOT on packed double-precision bits", "ANDPD": "Bitwise AND on packed double-precision bits",
    "ORPD": "Bitwise OR on packed double-precision bits", "XORPD": "Bitwise XOR on packed double-precision bits",
    "BLENDPS": "Blend packed single-precision floats (immediate mask)",
    "BLENDPD": "Blend packed double-precision floats (immediate mask)",
    "BLENDVPS": "Blend packed single-precision floats (variable mask register)",
    "BLENDVPD": "Blend packed double-precision floats (variable mask register)",
    "DPPS": "Dot product of packed single-precision floats", "DPPD": "Dot product of packed double-precision floats",
    "ROUNDPS": "Round packed single-precision floats to integer",
    "ROUNDPD": "Round packed double-precision floats to integer",
    "ROUNDSS": "Round scalar single-precision float to integer",
    "ROUNDSD": "Round scalar double-precision float to integer",
    "EXTRACTPS": "Extract a single-precision float lane to GPR/memory",
    "INSERTPS": "Insert a single-precision float lane",
    "default": "Unmodelled/uncategorized instruction (model default cost)",
}

# ---------------------------------------------------------------------------
# Suffix decoding
# ---------------------------------------------------------------------------


def _match_base(opcode: str, bases: dict[str, str]) -> tuple[str, str] | None:
    """Return (base, remaining_suffix) for the longest matching base prefix."""
    for base in sorted(bases.keys(), key=len, reverse=True):
        if opcode == base:
            return base, ""
        if opcode.startswith(base) and len(opcode) > len(base):
            return base, opcode[len(base):]
    return None


def _dedupe_join(fragments: list[str]) -> str:
    deduped: list[str] = []
    for f in fragments:
        if not deduped or deduped[-1] != f:
            deduped.append(f)
    return ", ".join(deduped)


def _decode_aarch64_suffix(suffix: str) -> str:
    if not suffix:
        return ""

    # Vector lane pattern, e.g. "2i32", "v2i32", "4f32", "8i8gpr", "2i32lane"
    m = re.match(r"^v?(\d+)(i|f)(\d+)(lane|gpr)?$", suffix)
    if m:
        n, kind, width, extra = m.groups()
        kind_str = "integer" if kind == "i" else "floating-point"
        desc = f"{n} x {width}-bit {kind_str} lanes"
        if extra == "lane":
            desc += " (single-lane variant)"
        elif extra == "gpr":
            desc += " (broadcast from general-purpose register)"
        return desc

    # Structure load/store pattern, e.g. "Onev8b", "Twov16b"
    m = re.match(r"^(One|Two|Three|Four)v(\d+)(b|h|s|d)$", suffix)
    if m:
        count_word, n, elem = m.groups()
        elem_bits = {"b": 8, "h": 16, "s": 32, "d": 64}[elem]
        count_num = {"One": 1, "Two": 2, "Three": 3, "Four": 4}[count_word]
        return f"{count_num} register(s), {n} x {elem_bits}-bit lanes"

    tokens = [
        ("post", "post-indexed addressing"),
        ("lane", "single lane"),
        ("roX", "64-bit register-offset addressing"),
        ("roW", "32-bit register-offset addressing"),
        ("pre", "pre-indexed addressing"),
        ("gpr", "general-purpose register operand"),
        ("rrr", "three register operands"),
        ("rri", "two register operands + immediate"),
        ("cc", "conditional"),
        ("ro", "register-offset addressing"),
        ("rs", "shifted register operand"),
        ("rx", "extended register operand"),
        ("rr", "two register operands"),
        ("ui", "unsigned immediate offset"),
        ("ri", "register + immediate operand"),
        ("W", "32-bit register"),
        ("X", "64-bit register"),
        ("S", "single-precision"),
        ("D", "double-precision"),
        ("i", "immediate operand"),
        ("l", "PC-relative literal"),
        ("r", "register operand"),
    ]
    fragments: list[str] = []
    i = 0
    while i < len(suffix):
        for tok, desc in tokens:
            if suffix.startswith(tok, i):
                fragments.append(desc)
                i += len(tok)
                break
        else:
            i += 1  # skip unrecognised character silently
    return _dedupe_join(fragments) if fragments else suffix


def _decode_x86_suffix(suffix: str) -> str:
    if not suffix:
        return ""

    m = re.match(r"^_(\d+)$", suffix)
    if m:
        return f"{m.group(1)}-byte relative displacement"

    fragments: list[str] = []
    rest = suffix
    width_m = re.match(r"^(8|16|32|64)", rest)
    if width_m:
        w = width_m.group(1)
        fragments.append(f"{w}-bit operand")
        rest = rest[len(w):]

    tokens = [
        ("pcrel32", "PC-relative 32-bit displacement"),
        ("rmr", "register-or-memory operand"),
        ("ri32", "register + 32-bit immediate"),
        ("ri8", "register + 8-bit immediate"),
        ("rCL", "shift count in CL register"),
        ("rm", "register destination, memory source"),
        ("mr", "memory destination, register source"),
        ("mi", "memory destination, immediate source"),
        ("ri", "register + immediate"),
        ("r0", "implicit accumulator register"),
        ("r1", "implicit shift-by-1"),
        ("rr", "register-register"),
        ("i8", "8-bit immediate"),
        ("i32", "32-bit immediate"),
        ("r", "register operand"),
        ("m", "memory operand"),
    ]
    i = 0
    while i < len(rest):
        for tok, desc in tokens:
            if rest.startswith(tok, i):
                fragments.append(desc)
                i += len(tok)
                break
        else:
            i += 1
    return _dedupe_join(fragments) if fragments else suffix


# ---------------------------------------------------------------------------
# Generic last-resort guess for opcodes outside the known tables
# ---------------------------------------------------------------------------

_GUESS_KEYWORDS: list[tuple[str, str]] = [
    ("MOV", "Move/copy data"), ("LEA", "Load effective address"),
    ("CVT", "Convert/cast between numeric types"), ("CMP", "Compare values"),
    ("SHUF", "Shuffle/permute vector lanes"), ("PERM", "Permute vector lanes"),
    ("PACK", "Pack/narrow vector elements"), ("UNPCK", "Unpack/widen and interleave vector elements"),
    ("BLEND", "Blend/select between vector elements"),
    ("ADD", "Add"), ("SUB", "Subtract"), ("MUL", "Multiply"), ("DIV", "Divide"),
    ("AND", "Bitwise AND"), ("XOR", "Bitwise XOR"), ("SHIFT", "Bit shift"),
    ("ABS", "Absolute value"), ("SQRT", "Square root"), ("ROUND", "Round to integer"),
    ("LOAD", "Load from memory"), ("STORE", "Store to memory"),
    ("BR", "Branch"), ("JMP", "Jump"), ("CALL", "Call subroutine"), ("RET", "Return"),
]


def _generic_guess(opcode: str) -> str:
    op = opcode.upper()
    for key, desc in _GUESS_KEYWORDS:
        if key in op:
            return f"{desc} (best-effort guess based on mnemonic)"
    return "Unrecognized opcode -- likely a target-specific or pseudo instruction"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def describe_opcode(opcode: str, arch: str = "") -> str:
    """Return a best-effort, human-readable description of a machine opcode.

    ``arch`` (e.g. the report's "AArch64"/"x86_64" field) picks which base
    table to try first -- several base mnemonics (ADD, MOV, CMP, ...) exist
    in both tables with different suffix conventions, so guessing the wrong
    architecture silently mis-decodes the suffix instead of just failing.
    """
    if not opcode:
        return "—"

    if opcode in _PSEUDO:
        return _PSEUDO[opcode]

    arch_l = arch.lower()
    if any(k in arch_l for k in ("x86", "amd64", "intel", "amd")):
        tables = [(_X86_BASES, _decode_x86_suffix), (_AARCH64_BASES, _decode_aarch64_suffix)]
    else:
        tables = [(_AARCH64_BASES, _decode_aarch64_suffix), (_X86_BASES, _decode_x86_suffix)]

    for bases, decoder in tables:
        match = _match_base(opcode, bases)
        if match:
            base, suffix = match
            desc = bases[base]
            extra = decoder(suffix)
            return f"{desc} — {extra}" if extra else desc

    return _generic_guess(opcode)
