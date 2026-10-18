module ALUWithMem #(parameter N=8, WriteWidth = 4) (
input set,
input clk,
//input [8*N*N-1:0] matIn,
input [WriteWidth-1:0] matIn,
input [8*N-1:0] vIn,
output [(16+$clog2(N))*N-1:0] vOut
);

    reg [8*N*N-1:0] matMem;
    reg writing;

    always @(posedge clk) begin
        case(writing)
            0: begin

            end


            default: begin

            end

        endcase
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
