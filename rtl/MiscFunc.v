/* ---------------------------------------------------------------------------
 * ReLU8Bits
 *
 * Element-wise ReLU on a vector of N signed INT8 values, combinational.
 *   vOut[i] = (vIn[i] < 0) ? 0 : vIn[i]
 *
 * A signed INT8 is negative exactly when bit 7 is set, so the sign bit alone
 * decides whether the lane is clamped to zero.
 * Element i occupies bits [8*i +: 8] in both vIn and vOut.
 * ------------------------------------------------------------------------- */
module ReLU8Bits #(parameter N=8) (
input [8*N-1:0] vIn,                        // N packed signed INT8
output [8*N-1:0] vOut                       // N packed INT8, all >= 0
);
    /*
    // Behavioral alternative kept for reference; the generate form below is
    // equivalent. (vOut would need to be declared `output reg` to use this.)
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
        // One clamp per lane: sign bit set -> 0, otherwise pass through.
        for (j = 0; j < N; j = j + 1) begin: ReLUGen
            assign vOut[8*j +: 8] = (vIn[8*j+7] == 1) ? 0 : vIn[8*j +: 8];
        end
    endgenerate

endmodule
