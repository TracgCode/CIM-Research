/* ---------------------------------------------------------------------------
 * MatVecMulWithMem
 *
 * Matrix-vector multiplier with an on-chip bank of INT8 matrices.
 *
 *   vOut = M[bankSel] * vIn      (M is N x N INT8, vIn is N INT8, vOut is N values)
 *
 * Matrices are stored in `bank` banks of N*N INT8 elements each. A matrix is
 * written sequentially, `writeWidth` INT8 elements per clock, so one full
 * matrix takes N*N/writeWidth cycles. The multiply itself is fully
 * combinational: vOut follows (bankSel, vIn) in the same cycle, there is no
 * output register.
 *
 * Parameters
 *   N          matrix dimension (N x N matrix, length-N vectors)
 *   writeWidth INT8 elements accepted on matIn per write cycle (must divide N*N)
 *   bank       number of matrix banks (power of two keeps bankSel decode simple)
 *
 * Write protocol
 *   1. (optional) pulse bankSelSet with bankSelIn to choose the target bank.
 *      bankSel is ignored while a write is in progress.
 *   2. pulse memSet for one cycle; the following N*N/writeWidth cycles each
 *      store matIn into the next slice of the selected bank. matIn must be
 *      valid on every one of those cycles, slice 0 first.
 *   3. `writing` returns to 0 after the last slice. Starting a new write
 *      while `writing` is 1 is ignored.
 *   bankSel also selects the bank that feeds the multiplier, so vOut is only
 *   meaningful for a bank that is fully written and not currently being written.
 *
 * Element layout: element k of a flat vector occupies bits [8*k +: 8].
 * Matrix element (row r, col c) is element r*N + c of the flat matrix, so
 * row r occupies bits [8*N*r +: 8*N].
 * ------------------------------------------------------------------------- */
module MatVecMulWithMem #(parameter N=8, writeWidth = 4, bank = 16) (
input reset,                                // asynchronous, active-high; clears control state only (not matrix storage)
input memSet,                               // start a matrix write into the selected bank (ignored while writing)
input bankSelSet,                           // latch bankSelIn into bankSel (ignored while writing)
input clk,
input [$clog2(bank)-1:0] bankSelIn,         // bank index to latch when bankSelSet is high
//input [8*N*N-1:0] matIn,
input [8*writeWidth-1:0] matIn,             // one write slice: writeWidth INT8 elements
input [8*N-1:0] vIn,                        // input vector, N INT8
output [(16+$clog2(N))*N-1:0] vOut          // N results, each (16+log2(N)) bits wide, element 0 in the low bits
);

    // Matrix storage: `bank` entries, each one flattened N x N INT8 matrix.
    // Not reset; contents are undefined until a bank has been written.
    reg [8*N*N-1:0] matMemBanks [bank-1:0];
    reg writing;                                        // 1 while a matrix write is in progress
    reg [$clog2(N*N/writeWidth)-1:0] writeCounter;      // index of the slice written this cycle
    reg [$clog2(bank)-1:0] bankSel;                     // bank used for both read (multiply) and write
    wire [8*N*N-1:0] matMem;                            // matrix currently feeding the multiplier

    // Combinational read of the selected bank.
    assign matMem = matMemBanks[bankSel];

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            writing <= 0;
            bankSel <= 0;
            // writeCounter is not reset: it is always loaded with 0 when a write starts.
        end else begin
            // The bank can only be changed while idle, so an in-flight write
            // cannot be redirected to a different bank halfway through.
            if (bankSelSet && !writing) begin
                bankSel <= bankSelIn;
            end

            case(writing)
                // Idle: wait for a write request.
                0: begin
                    if (memSet == 1) begin
                        writing <= 1;
                        writeCounter <= 0;
                    end
                end

                // Writing: store one slice per cycle, lowest slice first.
                1: begin
                    writeCounter <= writeCounter + 1;
                    // Slice index selects bits [writeCounter*8*writeWidth +: 8*writeWidth];
                    // the concatenation below is that index shifted left by log2(8*writeWidth)
                    // (this relies on writeWidth being a power of two).
                    matMemBanks[bankSel][{writeCounter, {$clog2(8*writeWidth){1'b0}}} +: 8*writeWidth]  <= matIn;
                    // Last slice stored: go back to idle.
                    if (writeCounter == N*N/writeWidth-1) begin
                        writing <= 0;
                    end
                end


                default: begin
                    // Unreachable: `writing` is a single bit.
                end

            endcase
        end
    end

    // Combinational multiplier fed by the selected bank.
    MatVecProduct8Bits #(
	.N(N)
     ) matVecProduct8Bits (
	.matIn(matMem),
	.vIn  (vIn),
	.vOut (vOut)
    );

endmodule

/* ---------------------------------------------------------------------------
 * MatVecProduct8Bits
 *
 * Basic matrix-vector multiplier, INT8 inputs, fully combinational.
 *   vOut[r] = sum_c matIn[r][c] * vIn[c]     for r = 0..N-1
 *
 * One DotProduct8Bits instance per matrix row; all rows share vIn.
 * Each result is a signed (16+log2(N))-bit value (see DotProduct8Bits for why)
 * and is packed into vOut as its two's-complement bit pattern, row 0 in the
 * lowest bits.
 * ------------------------------------------------------------------------- */
module MatVecProduct8Bits #(parameter N=8) (
input [8*N*N-1:0] matIn,                    // N x N INT8 matrix, row-major; row r at [8*N*r +: 8*N]
input [8*N-1:0] vIn,                        // N INT8 elements
output [(16+$clog2(N))*N-1:0] vOut          // N results, row r at [(16+log2(N))*r +: 16+log2(N)]
);
    genvar i;

    generate
        for (i = 0; i < N; i = i + 1) begin : gen_row
            wire signed [16+$clog2(N)-1:0] y;   // dot product of row i with vIn

            DotProduct8Bits #(
                .N(N)
            ) rowDot (
                .a(matIn[(8*N)*i +: 8*N]),
                .b(vIn),
                .y(y)
            );

            // Pack the signed result as raw bits; consumers must treat each
            // field as signed.
            assign vOut[(16+$clog2(N))*i +: 16+$clog2(N)] = $unsigned(y);
        end
    endgenerate

endmodule

/* ---------------------------------------------------------------------------
 * DotProduct8Bits
 *
 * Dot product of two length-N signed INT8 vectors, fully combinational.
 *   y = sum_{i=0}^{N-1} a[i] * b[i]
 *
 * Result width: each product fits in 16 bits (max magnitude (-128)*(-128) =
 * 2^14, so 16 bits signed is ample), and summing N of them needs log2(N)
 * extra bits, hence 16 + log2(N). This is exact for every input, so the
 * accumulator can never overflow.
 * ------------------------------------------------------------------------- */
module DotProduct8Bits #(parameter N=8) (
input [8*N-1:0] a,                          // element i at [8*i +: 8], treated as signed
input [8*N-1:0] b,                          // element i at [8*i +: 8], treated as signed
output signed [16+$clog2(N)-1:0] y
);
    integer i;
    reg signed [16+$clog2(N)-1:0] acc;

    // Re-evaluated whenever a or b changes; acc is rebuilt from zero each time.
    always @* begin
        acc = 0;
        for (i = 0; i < N; i = i + 1)
            acc += $signed(a[8*i +: 8]) * $signed(b[8*i +: 8]);
    end

    assign y = acc;

endmodule
