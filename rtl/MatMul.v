/* Matrix-Vector multiply with memory of Matrix,
 * sequential loading in unit of `writeWidth` INT8s
 */
module MatVecMulWithMem #(parameter N=8, writeWidth = 4, bank = 16) (
input reset,
input memSet,
input bankSelSet,
input clk,
input [$clog2(bank)-1:0] bankSelIn,
//input [8*N*N-1:0] matIn,
input [8*writeWidth-1:0] matIn,
input [8*N-1:0] vIn,
output [(16+$clog2(N))*N-1:0] vOut
);

    reg [8*N*N-1:0] matMemBanks [bank-1:0];
    reg writing;
    reg [$clog2(N*N/writeWidth)-1:0] writeCounter;
    reg [$clog2(bank)-1:0] bankSel;
    wire [8*N*N-1:0] matMem;

    assign matMem = matMemBanks[bankSel];

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            writing <= 0;
            bankSel <= 0;
        end else begin
            if (bankSelSet && !writing) begin
                bankSel <= bankSelIn;
            end

            case(writing)
                0: begin
                    if (memSet == 1) begin
                        writing <= 1;
                        writeCounter <= 0;
                    end
                end

                1: begin
                    writeCounter <= writeCounter + 1;
                    matMemBanks[bankSel][{writeCounter, {$clog2(8*writeWidth){1'b0}}} +: 8*writeWidth]  <= matIn;
                    if (writeCounter == N*N/writeWidth-1) begin
                        writing <= 0;
                    end
                end


                default: begin

                end

            endcase
        end
    end

    MatVecProduct8Bits #(
	.N(N)
     ) matVecProduct8Bits (
	.matIn(matMem),
	.vIn  (vIn),
	.vOut (vOut)
    );

endmodule

// Basic Matrix-Vector multiplier, with dim N*N matrix as input, dim N vector input and output, INT8 number format
module MatVecProduct8Bits #(parameter N=8) (
input [8*N*N-1:0] matIn,
input [8*N-1:0] vIn,
output [(16+$clog2(N))*N-1:0] vOut
);
    genvar i;

    generate
        for (i = 0; i < N; i = i + 1) begin : gen_row
            wire signed [16+$clog2(N)-1:0] y;

            DotProduct8Bits #(
                .N(N)
            ) rowDot (
                .a(matIn[(8*N)*i +: 8*N]),
                .b(vIn),
                .y(y)
            );

            assign vOut[(16+$clog2(N))*i +: 16+$clog2(N)] = $unsigned(y);
        end
    endgenerate

endmodule

// Dot product of 2 dim 8 INT8 vectors
module DotProduct8Bits #(parameter N=8) (
input [8*N-1:0] a,
input [8*N-1:0] b,
output signed [16+$clog2(N)-1:0] y
);
    integer i;
    reg signed [16+$clog2(N)-1:0] acc;

    always @* begin
        acc = 0;
        for (i = 0; i < N; i = i + 1)
            acc += $signed(a[8*i +: 8]) * $signed(b[8*i +: 8]);
    end

    assign y = acc;

endmodule
