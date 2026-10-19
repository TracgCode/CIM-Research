/* ---------------------------------------------------------------------------
 * CIM8Bits (top level, placeholder)
 *
 * Intended to hold the controller, instruction cache and the compute tiles
 * (MatVecMulWithMem + ReLU8Bits) connected by a programmable switch fabric.
 * Not implemented yet: the ports below are only the host-facing interface.
 *
 * Parameters
 *   N          vector / matrix dimension, passed down to the compute tiles
 *   writeWidth INT8 elements per host transfer on dataIn / dataOut
 * ------------------------------------------------------------------------- */
module CIM8Bits #(parameter N=8, writeWidth=4) (
input cmdInSet,                             // host strobe: dataIn carries a new command/data word
input [8*writeWidth-1:0] dataIn,            // host -> chip: instructions, matrix slices, input vectors
output [8*writeWidth-1:0] dataOut           // chip -> host: results
);

endmodule
