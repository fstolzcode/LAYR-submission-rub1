/*
    Trivium PRNG implementation
    Based on the Unrolled Trivium design from: https://github.com/uclcrypto/randomness_for_hardware_masking/blob/main/README.md
*/

module trivium #(parameter OUTPUT_BITS = 64)(
    input wire clk,
    input wire rst,
    input wire enable,
    input wire [79:0] key,
    input wire [79:0] iv,
    output wire [OUTPUT_BITS-1:0] stream_out,
    output wire rdy
);
    // Inner state of 288 bits for all output bits
    /* verilator lint_off UNOPTFLAT */
    reg [287:0] init_state;
    wire [287:0] state [0:OUTPUT_BITS];

    // counter for initialization cycles
    reg [10:0] init_counter;

    // Temporary variables for state calculations
    wire [OUTPUT_BITS-1:0] t1;
    wire [OUTPUT_BITS-1:0] t2;
    wire [OUTPUT_BITS-1:0] t3;

    wire invalid_key_iv;
    assign invalid_key_iv = (key == {80{1'b1}}) || (iv == {80{1'b1}});

    // State update on clock edge
    always @(posedge clk) begin
        if (rst) begin
            if (!invalid_key_iv) begin
                init_state <= {3'b111,
                    112'h0000000000000000000000000000,
                    iv,
                    12'h000,
                    1'b0,
                    key
                };
                init_counter <= 'b0;
            end

        end else if (enable) begin
            init_state <= state[OUTPUT_BITS];
            init_counter <= init_counter + 1;
        end
    end

    assign state[0] = init_state;

    // Set ready signal after initialization (1152 steps) and only of the key and iv are valid
    assign rdy = !invalid_key_iv && (init_counter >= 11'd1152 / OUTPUT_BITS);



    // Unrolled combinatorial logic
    genvar i;
    generate
        for (i = 1; i <= OUTPUT_BITS; i = i + 1) begin : gen_trivium_core
            assign t1[i-1] = state[i-1][161] ^ state[i-1][176];
            assign t2[i-1] = state[i-1][65] ^ state[i-1][92];
            assign t3[i-1] = state[i-1][242] ^ state[i-1][287];
            assign state[i] = {
                state[i-1][286:177], (t1[i-1] ^ (state[i-1][174] & state[i-1][175]) ^ state[i-1][263]),
                state[i-1][175: 93], (t2[i-1] ^ (state[i-1][ 90] & state[i-1][ 91]) ^ state[i-1][170]),
                state[i-1][ 91:  0], (t3[i-1] ^ (state[i-1][285] & state[i-1][286]) ^ state[i-1][ 68])
            };
            assign stream_out[i-1] =
                    t1[OUTPUT_BITS-i] ^
                    t2[OUTPUT_BITS-i] ^
                    t3[OUTPUT_BITS-i];
        end
    endgenerate

endmodule
