"""Cocotb Testbench for CIM (Computation-In-Memory) INT8 Arithmetic Modules.

This testbench provides verification test suites for:
  - DotProduct8Bits: 8-bit signed vector dot product with signed accumulator.
  - MatVecProduct8Bits: Combinational matrix-vector multiplier (INT8).
  - ALUWithMem: Matrix-vector multiplier with single-bank memory latching.
  - MatVecMulWithMem: Multi-bank matrix-vector multiplier with sequential write loading.
  - ReLU8Bits: Element-wise Rectified Linear Unit activation function for INT8 vectors.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer


# ==============================================================================
# Helper Utilities: Packing and Unpacking
# ==============================================================================

def pack(vec):
    """Packs a sequence of signed 8-bit integers into a single concatenated integer.

    The first element (vec[0]) occupies the lowest 8 bits [7:0], vec[1] occupies
    [15:8], and so forth in little-endian byte ordering.

    Args:
        vec: List of signed 8-bit integers in the range [-128, 127].

    Returns:
        int: Packed integer representing the bit-vector.
    """
    return sum((x & 0xFF) << (8 * i) for i, x in enumerate(vec))


def unpack_signed(value, width, count):
    """Unpacks a bit-concatenated integer into a list of signed integers.

    Extracts `count` elements, each of bit-width `width`, treating bit [width-1]
    as the two's complement sign bit. Element 0 is extracted from the least
    significant slice [width-1:0].

    Args:
        value: Packed integer containing all concatenated elements.
        width: Bit-width of each individual element.
        count: Number of elements to unpack.

    Returns:
        List of decoded signed integers.
    """
    out = []
    for i in range(count):
        v = (value >> (width * i)) & ((1 << width) - 1)
        # Sign-extend if the MSB of the width-bit slice is set (negative number)
        out.append(v - (1 << width) if v >> (width - 1) else v)
    return out


# ==============================================================================
# Unit Tests for Standalone Combinational / Single-Bank Modules
# ==============================================================================

#@cocotb.test()
async def mainTest(dut):
    """Verifies DotProduct8Bits with random signed 8-bit input vectors."""
    if not hasattr(dut, "a"):
        dut._log.info("TOPLEVEL is not DotProduct8Bits, skipping.")
        return
    n = len(dut.a) // 8
    for _ in range(100):
        va = [random.randint(-128, 127) for _ in range(n)]
        vb = [random.randint(-128, 127) for _ in range(n)]
        dut.a.value, dut.b.value = pack(va), pack(vb)
        await Timer(1, "ns")
        expected = sum(x * y for x, y in zip(va, vb))
        assert dut.y.value.to_signed() == expected, f"Mismatch: a={va} b={vb}"


#@cocotb.test()
async def overflowTest(dut):
    """Verifies DotProduct8Bits dynamic range and corner cases without accumulator overflow."""
    if not hasattr(dut, "a"):
        dut._log.info("TOPLEVEL is not DotProduct8Bits, skipping.")
        return
    n = len(dut.a) // 8
    # Test cases: maximum positive, maximum negative, and alternating bounds
    cases = [
        (-128, -128),  # Max positive: (-128) * (-128) = +16384 per element -> N * 16384
        (-128, 127),   # Max negative: (-128) * (+127) = -16256 per element
        (127, 127),    # Positive square: (+127) * (+127) = +16129 per element
        (127, -128),   # Symmetrical negative product
    ]
    for x, y in cases:
        dut.a.value, dut.b.value = pack([x] * n), pack([y] * n)
        await Timer(1, "ns")
        assert dut.y.value.to_signed() == n * x * y, f"Overflow failure: x={x} y={y}"


#@cocotb.test()
async def matVecTest(dut):
    """Verifies MatVecProduct8Bits combinational matrix-vector multiplier."""
    if not hasattr(dut, "matIn"):
        dut._log.info("TOPLEVEL is not MatVecProduct8Bits, skipping.")
        return
    n = len(dut.vIn) // 8
    w = len(dut.vOut) // n
    for _ in range(100):
        mat = [[random.randint(-128, 127) for _ in range(n)] for _ in range(n)]
        vec = [random.randint(-128, 127) for _ in range(n)]
        # Matrix is laid out in row-major order: row i occupies [8*n*i +: 8*n]
        dut.matIn.value = pack([x for row in mat for x in row])
        dut.vIn.value = pack(vec)
        await Timer(1, "ns")
        expected = [sum(x * y for x, y in zip(row, vec)) for row in mat]
        got = unpack_signed(int(dut.vOut.value), w, n)
        assert got == expected, f"mat={mat} vec={vec}\ngot={got}\nexp={expected}"


#@cocotb.test()
async def matVecOverflowTest(dut):
    """Verifies extreme corner cases for MatVecProduct8Bits."""
    if not hasattr(dut, "matIn"):
        return
    n = len(dut.vIn) // 8
    w = len(dut.vOut) // n
    for x, y in [(-128, -128), (-128, 127), (127, 127), (127, -128)]:
        dut.matIn.value = pack([x] * (n * n))
        dut.vIn.value = pack([y] * n)
        await Timer(1, "ns")
        got = unpack_signed(int(dut.vOut.value), w, n)
        assert got == [n * x * y] * n, f"x={x} y={y} got={got}"


#@cocotb.test()
async def ALUWithMemTest(dut):
    """Verifies ALUWithMem single-bank matrix storage latch and multiplication."""
    if not hasattr(dut, "matIn"):
        dut._log.info("TOPLEVEL is not ALUWithMem, skipping.")
        return
    n = len(dut.vIn) // 8
    w = len(dut.vOut) // n
    dut.set.value = 0
    await Timer(1, "ns")

    for _ in range(10):
        mat = [[random.randint(-128, 127) for _ in range(n)] for _ in range(n)]

        # Latch matrix into memory on `set` pulse
        dut.matIn.value = pack([x for row in mat for x in row])
        dut.set.value = 1
        await Timer(1, "ns")
        dut.set.value = 0
        await Timer(1, "ns")

        # Test multiple vectors against the stored matrix
        for __ in range(10):
            vec = [random.randint(-128, 127) for _ in range(n)]
            dut.vIn.value = pack(vec)
            await Timer(1, "ns")
            expected = [sum(x * y for x, y in zip(row, vec)) for row in mat]
            got = unpack_signed(int(dut.vOut.value), w, n)
            assert got == expected, f"mat={mat} vec={vec}\ngot={got}\nexp={expected}"


# ==============================================================================
# Helper Routines for MatVecMulWithMem Verification
# ==============================================================================

async def select_bank(dut, bank_idx):
    """Synchronously selects the active memory bank for read/compute and write operations.

    Drives `bankSelIn` and asserts `bankSelSet` on a falling clock edge to guarantee
    setup time before the next rising edge, where `bankSel` is sampled by the DUT.

    Args:
        dut: Device under test handle.
        bank_idx: Target bank index [0 .. bank-1].
    """
    dut.bankSelIn.value = bank_idx
    await FallingEdge(dut.clk)
    dut.bankSelSet.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.bankSelSet.value = 0


async def write_bank(dut, bank_idx, mat_flatten, n):
    """Sequentially loads a flattened N*N matrix into a designated memory bank.

    Protocol Sequence:
      1. Select target bank via `select_bank`.
      2. Pulse `memSet` high for 1 clock cycle to trigger the internal FSM (`writing <= 1`).
      3. Sequentially feed `matIn` in 4-byte (writeWidth) chunks per clock cycle.
      4. Verify `writing` de-asserts upon counter completion and bank memory content matches.

    Args:
        dut: Device under test handle.
        bank_idx: Target bank index to write into.
        mat_flatten: 1D list containing N*N signed 8-bit integers (row-major).
        n: Matrix dimension N (N rows, N columns).
    """
    await select_bank(dut, bank_idx)
    assert int(dut.bankSel.value) == bank_idx, f"Bank selection failed: bankSel={dut.bankSel.value}"

    # Pulse memSet to initiate sequential write FSM
    await FallingEdge(dut.clk)
    dut.memSet.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.memSet.value = 0

    assert int(dut.writing.value) == 1, "DUT failed to enter writing state (writing != 1)"

    # Stream 4-byte chunks per clock cycle for (N*N / writeWidth) cycles
    for i in range(0, len(mat_flatten) + 1, 4):
        dut.matIn.value = pack(mat_flatten[i : i + 4])
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)

    # Verify write cycle completion and state register resets
    assert int(dut.writing.value) == 0, f"Writing state did not terminate: writing={dut.writing.value}"
    assert int(dut.writeCounter.value) == 0, f"writeCounter did not reset: writeCounter={dut.writeCounter.value}"

    # Verify that the bank memory contents perfectly match the packed input matrix
    assert int(dut.matMemBanks[bank_idx].value) == int(pack(mat_flatten)), (
        f"Memory content mismatch at Bank {bank_idx}:\n"
        f"  Got:      {unpack_signed(int(dut.matMemBanks[bank_idx].value), n, n ** 2)}\n"
        f"  Expected: {mat_flatten}"
    )


async def check_mat_vec_mult(dut, mat, vec, n, w):
    """Applies an input vector vIn and validates combinational vOut against software model.

    Computes expected output:
      vOut[i] = sum(mat[i][j] * vec[j] for j in 0..N-1)

    Args:
        dut: Device under test handle.
        mat: 2D matrix (N x N) of signed 8-bit integers.
        vec: 1D vector (length N) of signed 8-bit integers.
        n: Dimension N.
        w: Bit-width of each output element (16 + ceil(log2(N))).
    """
    dut.vIn.value = pack(vec)
    await Timer(1, "ns")  # Allow combinational multiplier logic to settle

    expected = [sum(x * y for x, y in zip(row, vec)) for row in mat]
    got = unpack_signed(int(dut.vOut.value), w, n)
    assert got == expected, (
        f"Matrix-vector multiplication mismatch:\n"
        f"  vIn:      {vec}\n"
        f"  Got:      {got}\n"
        f"  Expected: {expected}\n"
        f"  Matrix:   {mat}"
    )


# ==============================================================================
# Main Verification Suite: MatVecMulWithMem
# ==============================================================================

@cocotb.test()
async def MatVecMulWithMemTest(dut):
    """Comprehensive verification suite for MatVecMulWithMem.

    Test Structure:
      - Phase 1: Clock startup, asynchronous/synchronous reset, and initial state checks.
      - Phase 2: Sequential write loading into all 16 memory banks with immediate smoke checks.
      - Phase 3: Exhaustive multiplication verification for each individual bank (0 to 15),
                 testing zero vectors, unit basis vectors, dynamic range bounds, and random data.
      - Phase 4: Dynamic random bank-switching stress test (evaluates non-sequential bank reads).
      - Phase 5: Hardware safety and control edge cases (write-lock bankSelSet protection and reset).
    """
    if not hasattr(dut, "bankSelSet"):
        dut._log.info("TOPLEVEL is not MatVecMulWithMem, skipping.")
        return

    n = len(dut.vIn) // 8
    w = len(dut.vOut) // n
    num_banks = len(dut.matMemBanks) if hasattr(dut, "matMemBanks") else 16

    dut._log.info(f"=== Starting MatVecMulWithMem test suite: N={n}, output_width={w}-bit, banks={num_banks} ===")

    # --------------------------------------------------------------------------
    # Phase 1: Clock Generation and Reset Verification
    # --------------------------------------------------------------------------
    dut.bankSelSet.value = 0
    dut.memSet.value = 0
    dut.vIn.value = 0
    dut.matIn.value = 0

    # Start 1 GHz free-running clock (1 ns period)
    cocotb.start_soon(Clock(dut.clk, 1, unit="ns").start())
    await ClockCycles(dut.clk, 2)

    # Initialize all banks to zero prior to reset
    for i in range(num_banks):
        dut.matMemBanks[i].value = 0

    # Assert and release reset
    dut.reset.value = 1
    await RisingEdge(dut.clk)
    dut.reset.value = 0
    await FallingEdge(dut.clk)

    assert int(dut.writing.value) == 0, f"writing flag not 0 after reset: {dut.writing.value}"
    assert int(dut.bankSel.value) == 0, f"bankSel not 0 after reset: {dut.bankSel.value}"
    dut._log.info("Phase 1 Passed: Reset asserted and verified successfully.")

    # --------------------------------------------------------------------------
    # Phase 2: Sequential Write Loading into All 16 Banks
    # --------------------------------------------------------------------------
    bank_matrices = []
    dut._log.info(f"Phase 2: Programming {num_banks} memory banks with unique random matrices...")

    for bank_idx in range(num_banks):
        # Generate random N x N matrix with signed INT8 elements
        mat = [[random.randint(-128, 127) for _ in range(n)] for _ in range(n)]
        bank_matrices.append(mat)
        mat_flatten = [x for row in mat for x in row]

        # Sequentially write the matrix into bank_idx
        await write_bank(dut, bank_idx, mat_flatten, n)

        # Immediate smoke verification for current bank
        for _ in range(3):
            vec = [random.randint(-128, 127) for _ in range(n)]
            await check_mat_vec_mult(dut, mat, vec, n, w)

    dut._log.info(f"Phase 2 Passed: All {num_banks} memory banks programmed and verified.")

    # --------------------------------------------------------------------------
    # Phase 3: Exhaustive Multiplication Testing on Each Individual Bank
    # --------------------------------------------------------------------------
    dut._log.info("Phase 3: Running exhaustive multiplication tests on each bank (0 to 15)...")

    for bank_idx in range(num_banks):
        dut._log.info(f"  Verifying Bank {bank_idx} arithmetic accuracy...")
        await select_bank(dut, bank_idx)
        assert int(dut.bankSel.value) == bank_idx, f"Bank selection failed for Bank {bank_idx}"
        mat = bank_matrices[bank_idx]

        # 1. Zero vector test: A * 0 = 0
        await check_mat_vec_mult(dut, mat, [0] * n, n, w)

        # 2. All-ones vector test: A * 1 = column sum / row reduction
        await check_mat_vec_mult(dut, mat, [1] * n, n, w)

        # 3. Canonical unit basis vectors (e_k): extracts individual column k of matrix A
        for col in range(n):
            unit_vec = [1 if j == col else 0 for j in range(n)]
            await check_mat_vec_mult(dut, mat, unit_vec, n, w)

        # 4. Extreme dynamic range vectors (checking sign extension and overflow protection)
        extreme_vectors = [
            [127] * n,                                        # Maximum positive saturation
            [-128] * n,                                       # Maximum negative saturation
            [127 if j % 2 == 0 else -128 for j in range(n)],  # Alternating extrema (+127, -128)
            [-128 if j % 2 == 0 else 127 for j in range(n)],  # Alternating extrema (-128, +127)
        ]
        for vec in extreme_vectors:
            await check_mat_vec_mult(dut, mat, vec, n, w)

        # 5. Randomized signed 8-bit vector tests (15 random vectors per bank)
        for _ in range(15):
            vec = [random.randint(-128, 127) for _ in range(n)]
            await check_mat_vec_mult(dut, mat, vec, n, w)

    dut._log.info("Phase 3 Passed: All 16 banks passed exhaustive matrix-vector multiplication tests.")

    # --------------------------------------------------------------------------
    # Phase 4: Dynamic Random Bank-Switching Stress Test
    # --------------------------------------------------------------------------
    dut._log.info("Phase 4: Running dynamic random bank-switching stress tests (50 iterations)...")

    for _ in range(50):
        target_bank = random.randint(0, num_banks - 1)
        await select_bank(dut, target_bank)
        assert int(dut.bankSel.value) == target_bank, f"Bank selection mismatch: expected {target_bank}"

        mat = bank_matrices[target_bank]
        vec = [random.randint(-128, 127) for _ in range(n)]
        await check_mat_vec_mult(dut, mat, vec, n, w)

    dut._log.info("Phase 4 Passed: Random dynamic bank-switching tests verified without data contamination.")

    # --------------------------------------------------------------------------
    # Phase 5: Hardware Safety and Control Edge Case Verification
    # --------------------------------------------------------------------------
    dut._log.info("Phase 5: Verifying hardware control protection and reset edge cases...")

    # Case A: Ensure bankSel cannot be altered while writing == 1 (if (bankSelSet && !writing))
    current_bank = 2
    await select_bank(dut, current_bank)
    await FallingEdge(dut.clk)
    dut.memSet.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.memSet.value = 0
    assert int(dut.writing.value) == 1, "DUT failed to enter writing state."

    # Attempt illegal bank selection change during active writing
    dut.bankSelIn.value = 9
    dut.bankSelSet.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.bankSel.value) == current_bank, (
        f"Security fault: bankSel was modified during active write cycle! Got {dut.bankSel.value}, expected {current_bank}"
    )
    dut.bankSelSet.value = 0

    # Complete the remainder of this write cycle to leave the DUT in clean state
    for _ in range(n * n // 4 - 1):
        dut.matIn.value = 0
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.writing.value) == 0, "DUT failed to return to idle after write cycle completion."

    # Case B: Ensure synchronous/asynchronous reset resets bankSel to 0
    await select_bank(dut, 7)
    assert int(dut.bankSel.value) == 7, "Failed to switch to bank 7 before reset test."
    dut.reset.value = 1
    await RisingEdge(dut.clk)
    dut.reset.value = 0
    await FallingEdge(dut.clk)
    assert int(dut.bankSel.value) == 0, f"bankSel did not reset to 0 upon reset: {dut.bankSel.value}"

    dut._log.info("Phase 5 Passed: Control protection and reset behavior fully verified.")
    dut._log.info("=== MatVecMulWithMem test suite completed successfully! ===")


# ==============================================================================
# Unit Test for ReLU Activation
# ==============================================================================

#@cocotb.test()
async def ReLU8BitsTest(dut):
    """Verifies ReLU8Bits element-wise rectification for INT8 vectors."""
    for _ in range(10):
        n = len(dut.vIn) // 8
        vIn = [random.randint(-128, 127) for _ in range(n)]
        dut.vIn.value = pack(vIn)
        await Timer(1, "ns")

        vInReLU = [max(0, x) for x in vIn]
        expected_packed = pack(vInReLU)
        assert int(dut.vOut.value) == expected_packed, (
            f"ReLU mismatch:\n"
            f"  vIn:      {vIn}\n"
            f"  Expected: {vInReLU}\n"
            f"  Got:      {unpack_signed(dut.vOut.value, 8, n)}"
        )
