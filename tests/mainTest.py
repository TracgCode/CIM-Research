import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer


def pack(vec):
    """把 signed 8-bit 向量打包成一個整數,vec[0] 放在最低 8 bit。"""
    return sum((x & 0xFF) << (8 * i) for i, x in enumerate(vec))


def unpack_signed(value, width, count):
    """把打包的整數拆成 count 個 width-bit 的 signed 整數,第 0 個在最低位。"""
    out = []
    for i in range(count):
        v = (value >> (width * i)) & ((1 << width) - 1)
        out.append(v - (1 << width) if v >> (width - 1) else v)
    return out


#@cocotb.test()
async def mainTest(dut):
    if not hasattr(dut, "a"):
        dut._log.info("TOPLEVEL 不是 DotProduct8Bits,略過")
        return
    n = len(dut.a) // 8
    for _ in range(100):
        va = [random.randint(-128, 127) for _ in range(n)]
        vb = [random.randint(-128, 127) for _ in range(n)]
        dut.a.value, dut.b.value = pack(va), pack(vb)
        await Timer(1, "ns")
        expected = sum(x * y for x, y in zip(va, vb))
        assert dut.y.value.to_signed() == expected, f"a={va} b={vb}"


#@cocotb.test()
async def overflowTest(dut):
    if not hasattr(dut, "a"):
        dut._log.info("TOPLEVEL 不是 DotProduct8Bits,略過")
        return
    n = len(dut.a) // 8
    cases = [
        (-128, -128),  # 正向最大: N * 16384
        (-128, 127),  # 負向最大
        (127, 127),
        (127, -128),
    ]
    for x, y in cases:
        dut.a.value, dut.b.value = pack([x] * n), pack([y] * n)
        await Timer(1, "ns")
        assert dut.y.value.to_signed() == n * x * y, f"x={x} y={y}"


#@cocotb.test()
async def matVecTest(dut):
    if not hasattr(dut, "matIn"):
        dut._log.info("TOPLEVEL 不是 MatVecProduct8Bits,略過")
        return
    n = len(dut.vIn) // 8
    w = len(dut.vOut) // n
    for _ in range(100):
        mat = [[random.randint(-128, 127) for _ in range(n)] for _ in range(n)]
        vec = [random.randint(-128, 127) for _ in range(n)]
        # 矩陣一列接著一列存放,第 i 列在 [8*n*i +: 8*n]
        dut.matIn.value = pack([x for row in mat for x in row])  # 展平成一維
        dut.vIn.value = pack(vec)
        await Timer(1, "ns")
        expected = [sum(x * y for x, y in zip(row, vec)) for row in mat]
        got = unpack_signed(int(dut.vOut.value), w, n)
        assert got == expected, f"mat={mat} vec={vec}\ngot={got}\nexp={expected}"


#@cocotb.test()
async def matVecOverflowTest(dut):
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
    if not hasattr(dut, "matIn"):
        dut._log.info("TOPLEVEL 不是 ALUWithMem,略過")
        return
    n = len(dut.vIn) // 8
    w = len(dut.vOut) // n
    dut.set.value = 0
    await Timer(1, "ns")

    for _ in range(10):
        mat = [[random.randint(-128, 127) for _ in range(n)] for _ in range(n)]

        # 矩陣一列接著一列存放,第 i 列在 [8*n*i +: 8*n]
        dut.matIn.value = pack([x for row in mat for x in row])  # 展平成一維
        dut.set.value = 1
        await Timer(1, "ns")
        dut.set.value = 0
        await Timer(1, "ns")

        for __ in range(10):
            vec = [random.randint(-128, 127) for _ in range(n)]
            dut.vIn.value = pack(vec)
            await Timer(1, "ns")
            expected = [sum(x * y for x, y in zip(row, vec)) for row in mat]
            got = unpack_signed(int(dut.vOut.value), w, n)
            assert got == expected, f"mat={mat} vec={vec}\ngot={got}\nexp={expected}"

@cocotb.test()
async def MatVecMulWithMemTest(dut):
    if not hasattr(dut, "bankSelSet"):
        dut._log.info("TOPLEVEL 不是 ALUWithMem,略過")
        return
    n = len(dut.vIn) // 8
    w = len(dut.vOut) // n

    dut.bankSelSet.value = 0
    dut.memSet.value = 0
    cocotb.start_soon(Clock(dut.clk, 1, unit="ns").start())
    await ClockCycles(dut.clk, 2)

    for i in range(16):
        dut.matMemBanks[i].value = 0

    await RisingEdge(dut.clk)
    dut._log.info(f"Mem Val: {dut.matMemBanks[0].value}")

    dut.reset.value = 1
    await RisingEdge(dut.clk)
    dut.reset.value = 0
    dut._log.info(f"after reset, writing = {dut.writing.value}")

    for iter in range(16):
        dut._log.info(f"\nIteration {iter}")

        mat = [[random.randint(-128, 127) for _ in range(n)] for _ in range(n)]
        matFlatten = [x for row in mat for x in row]

        dut.bankSelIn.value = iter
        await FallingEdge(dut.clk)
        dut.bankSelSet.value = 1
        await RisingEdge(dut.clk)
        dut.bankSelSet.value = 0

        await FallingEdge(dut.clk)
        dut.memSet.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.memSet.value = 0

        assert dut.writing.value == 1

        dut._log.info(f"writeCounter = {dut.writeCounter.value}, writing = {dut.writing.value}")
        for i in range(0, len(matFlatten) + 1, 4):
            dut.matIn.value = pack(matFlatten[i : i + 4])
            await RisingEdge(dut.clk)
            dut._log.info(f"writeCounter = {dut.writeCounter.value}, writing = {dut.writing.value}")
            dut._log.info(f"matMemBanks[{iter}] = {dut.matMemBanks[iter].value}")
            await FallingEdge(dut.clk)

        assert int(dut.writing.value) == 0, f"writing = {dut.writing.value}"
        assert int(dut.writeCounter.value) == 0, f"writeCounter = {dut.writeCounter.value}"
        assert int(dut.matMemBanks[iter].value) == int(pack(matFlatten)) \
            ,f"matMem = {unpack_signed(int(dut.matMemBanks[iter].value), n, n ** 2)},\nmatFlatten = {matFlatten}"

        '''
        for __ in range(10):
            vec = [random.randint(-128, 127) for _ in range(n)]
            dut.vIn.value = pack(vec)
            await Timer(1, "ns")
            expected = [sum(x * y for x, y in zip(row, vec)) for row in mat]
            got = unpack_signed(int(dut.vOut.value), w, n)
            assert got == expected, f"mat={mat} vec={vec}\ngot={got}\nexp={expected}"
        '''

#@cocotb.test()
async def ReLU8BitsTest(dut):
    for i in range(10):
        n = len(dut.vIn) // 8
        vIn = [random.randint(-128, 127) for _ in range(n)]
        vInPacked = pack(vIn)
        dut.vIn.value = vInPacked
        await Timer(1, "ns")

        vInReLU = [max(0, x) for x in vIn]
        vInReLUPacked = pack(vInReLU)
        assert int(dut.vOut.value) == \
            vInReLUPacked, f"vInRelu = {vInReLU}\nvOut = {unpack_signed(dut.vOut.value, 8, n)}"
