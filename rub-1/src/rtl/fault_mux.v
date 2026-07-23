// This module implements a fault correction, by checking 3 inputs a,b,c and selecting the majority value bitwise.
// For each bit we calculate
// 1. s = ~(a XOR b) for our multiplexer
// 2. s as MUX select and x = MUX(a,c) 
//      MUX(a0, a1, b0, b1, s0, s1):
//      a_plus_c = XOR(a0, a1, b0, b1)
//      acs = AND(a_plus_c0, a_plus_c1, s0, s1)
//      x = acs XOR a  
// 3. return x
module fault_mux (
    input  wire      clk,
    input  wire      reset,
    input wire      enable,
    
    input  wire [127:0] a0,
    input  wire [127:0] a1,
    input  wire [127:0] b0,
    input  wire [127:0] b1,
    input  wire [127:0] c0,
    input  wire [127:0] c1,
    input  wire [127:0] random,

    output wire done,
    output wire[127:0] result0,
    output wire[127:0] result1
);
    wire[127:0] [1:0] s;
    wire[127:0] [1:0] a_plus_c;
    wire[127:0] [1:0] acs;
    reg [1:0] counter;


   for (genvar i = 0; i < 128; i++) begin : gen_fault_mux
        // Step 1: s = ~(a XOR b)
        HPC2Xor #(.d(1)) a_xor_b (.control_clk(clk), .control_reset(reset), .io_x({a0[i], a1[i]}), .io_y({b0[i], b1[i]}), .io_z(s[i]));

        // Step 2 MUX: 
        // 2.1: a_plus_c = XOR(a0, a1, c0, c1)
        HPC2Xor #(.d(1)) xor_a_plus_b (.control_clk(clk), .control_reset(reset), .io_x({a0[i], a1[i]}), .io_y({c0[i], c1[i]}), .io_z(a_plus_c[i]));

        // 2.2: acs = AND(a_plus_c0, a_plus_c1, s0, s1)
        HPC2And #(.d(1)) and_acs (.control_clk(clk), .control_reset(reset), .io_x(a_plus_c[i]), .io_y(s[i]), .io_r(random[i]), .io_z(acs[i]));

        // 2:3 result = acs XOR a  (unmask)
        wire [1:0] xor_out;
        HPC2Xor #(.d(1)) xor_result (.control_clk(clk), .control_reset(reset), .io_x(acs[i]), .io_y({a0[i], a1[i]}), .io_z(xor_out));
        
        assign result0[i] = enable ? xor_out[0] : 1'b0;
        assign result1[i] = enable ? xor_out[1] : 1'b0;
        
    end
    
    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            counter <= 0;
        end else begin
            counter <= counter + 1;
        end
    end

    assign done = enable ? (counter == 2) : 1'b0;


endmodule
