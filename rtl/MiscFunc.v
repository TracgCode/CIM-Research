module ReLU8Bits #(parameter N=8) (
input [8*N-1:0] vIn,
output [8*N-1:0] vOut
);
    /*
    integer i;
    always @(*) begin
        for (i = 0; i < N; i = i + 1) begin
            if (vIn[8*i+7] == 1) begin
                vOut[8*i +: 8] = 8'b0;
            end else begin
                vOut[8*i +: 8] = vIn[8*i +: 8];
            end
        end
    end
    */

    genvar j;
    generate
        for (j = 0; j < N; j = j + 1) begin: ReLUGen
            assign vOut[8*j +: 8] = (vIn[8*j+7] == 1) ? 0 : vIn[8*j +: 8];
        end
    endgenerate

endmodule
