module gadget (
    input wire clk,
    input wire rst,  // Active-high reset
    input wire a,  // 68 bits of randomness for 34 AND gates with d=1
    input wire b,
    input wire c,
    input wire [2:0] mask,  // 2 bytes: [15:8] = byte1, [7:0] = byte0
    input wire random,  // 2 bytes input masked
    output data_out,  // 2 bytes output masked
    output wire rdy
);

wire [1:0] masked_a, maked_b, masked_c;

assign masked_a[0] = a ^ mask[0];
assign masked_a[1] = mask[0];
assign maked_b[0] = b ^ mask[1];
assign maked_b[1] = mask[1];
assign masked_c[0] = c ^ mask[2];
assign masked_c[1] = mask[2];


// Wait 6 cycles to for the result due to masked AND gates
reg [3:0] rdy_count;
always @(posedge clk) begin
    if (rst) begin
        rdy_count <= 4'b000;
    end else begin
        rdy_count <= rdy_count + 1;
    end
end
assign rdy = (rdy_count >= 4'b1110 ) ? 1'b1 : 1'b0; 
wire [1:0] tmp;
wire [1:0] result;
HPC2And #(.d(1)) xor_m3 (.control_clk(clk), .control_reset(rst), .io_x(masked_a), .io_y(maked_b),.io_r(random), .io_z(tmp));
    
HPC2And #(.d(1)) and_inst_0 (.control_clk(clk), .control_reset(rst), .io_x(tmp), .io_y(masked_c), .io_r(random), .io_z(result));

assign data_out = result[0] ^ result[1];

endmodule