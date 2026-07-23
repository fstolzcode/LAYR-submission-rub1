// This module executed a fault protected AES encryption/decryption.
// We run the AES three times with the same input and key sharing, but new input masking. 
// Then we perform a masked majority vote on the three outputs to correct any single bit faults and return the unmasked ciphertext/plaintext.
// The module needs fresh randomness for each cycle. 
module fault_protected_aes(
    input wire clk,
    input wire rst,  // Active-high synchronous reset

    // Plain/Ciphertext input
    input  wire [127:0] data_in,

    // Key input (2 shares)
    input wire [127:0] key_in_0,
    input wire [127:0] key_in_1,

    // Randomness input (needs to be provided with new randomness each cycle)
    // 204 for AES + 128 for masking plain or ciphertext = 332 bits
    input wire [331:0] randomness,

    // Control
    input  wire start,      // Start fault protected AES operation
    input  wire enc_mode,   // 1 = encrypt, 0 = decrypt
    output reg [127:0] fault_protect_aes_out, // corrected AES output 
    output wire busy,       
    output wire done       // Operation complete (output valid)
);


    // State machine states
    localparam IDLE     = 3'd0;
    localparam RUN_AES  = 3'd1;
    localparam WAIT_DONE = 3'd2;
    localparam MAJORITY_VOTE = 3'd3;
    localparam DONE_STATE = 3'd4;
    localparam WAIT_START    = 3'd5; // <--- NEW STATE

    reg [2:0] state;
    reg [1:0] run_count;

    // Internal signals for AES instantiation
    reg aes_start;
    wire aes_busy;
    wire aes_done;
    reg enc_mode_reg;
    wire [127:0] aes_data_out_s0;
    wire [127:0] aes_data_out_s1;
    reg [127:0] data_in_s0;
    reg [127:0] data_in_s1;
    reg [127:0] key_0;
    reg [127:0] key_1;
    reg [127:0] data;

    // Storage for outputs from each run
    reg [1:0] [127:0] aes_out_0_reg;
    reg [1:0] [127:0] aes_out_1_reg;
    reg [1:0] [127:0] aes_out_2_reg;

    // Fault detection: compare outputs from all 3 runs
    assign busy = (state != IDLE);
    assign done = (state == DONE_STATE);
    wire [127:0] mux_random = randomness[127:0]; 
    wire mux_done;
    reg mux_enable;
    reg rst_mux;

    // result from majority vote
    wire [127:0] result_s0;
    wire [127:0] result_s1;


    // Module to make a masked majority vote for all three AES outputs. Returns the unmasked corrected result. 
    fault_mux fault_detector (
        // Control signals
        .clk(clk),
        .reset(rst_mux),
        .enable(mux_enable),

        // Inputs from three AES runs
        .a0(aes_out_0_reg[0]),
        .a1(aes_out_0_reg[1]),
        .b0(aes_out_1_reg[0]),
        .b1(aes_out_1_reg[1]),
        .c0(aes_out_2_reg[0]),
        .c1(aes_out_2_reg[1]),
        // Randomness
        .random(mux_random),
        
        // Outputs
        .done(mux_done),
        .result0(result_s0),
        .result1(result_s1)
    );


    aes_top aes (
        // Control signals
        .clk(clk),
        .rst(rst),  // Active-high synchronous reset
        .start(aes_start),     
        .busy(aes_busy),       
        .done(aes_done),   
        .enc_mode(enc_mode_reg),   

        // Plain/Ciphertext input
        .data_in_0(data_in_s0),
        .data_in_1(data_in_s1),
        .data_out_0(aes_data_out_s0),
        .data_out_1(aes_data_out_s1),

        // Key input
        .key_0(key_0),
        .key_1(key_1),

        // Randomness input
        .random_round(randomness[263:128]),   // S-boxes (136 bits) for round datapath
        .random_ks(randomness[331:264])      // Key schedule randomness (68 bits)
    );


    // State machine
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            run_count <= 2'd0;
            mux_enable <= 1'b0;
            fault_protect_aes_out <= 128'd0;
            aes_start <= 1'b0;
            rst_mux <= 1'b1;
            enc_mode_reg <= 1'b1;
        end else begin
            case (state)
                IDLE: begin
                    if (start) begin
                        state <= RUN_AES;
                        key_0 <= key_in_0;
                        key_1 <= key_in_1;
                        data <= data_in;
                        enc_mode_reg <= enc_mode;
                        run_count <= 2'd0;
                    end
                    mux_enable <= 1'b0;
                    rst_mux <= 1'b1;
                end

                // Initial AES
                RUN_AES: begin
                    aes_start <= 1'b1;
                    // Mask input data
                    data_in_s0 <= data_in[127:0] ^ randomness[127:0];
                    data_in_s1 <= randomness[127:0];
                    

                    state <= WAIT_START;
                end

                WAIT_START: begin
                    aes_start <= 1'b0; // Clear start signal 
                    
                    // Wait until aes_top leaves DONE_STATE.
                    // When it leaves DONE, aes_done goes LOW and aes_busy goes HIGH.
                    if (aes_done == 1'b0) begin
                        state <= WAIT_DONE;
                    end
                end

                WAIT_DONE: begin
                    aes_start <= 1'b0;
                    if (aes_done) begin
                        // Store the results based on which run just completed
                        case (run_count)
                            2'd0: begin
                                aes_out_0_reg[0] <= aes_data_out_s0;
                                aes_out_0_reg[1] <= aes_data_out_s1;
                            end
                            2'd1: begin
                                aes_out_1_reg[0] <= aes_data_out_s0;
                                aes_out_1_reg[1] <= aes_data_out_s1;
                            end
                            2'd2: begin
                                aes_out_2_reg[0] <= aes_data_out_s0;
                                aes_out_2_reg[1] <= aes_data_out_s1;
                            end
                            default: begin
                                // Unreachable state, but required for complete case coverage
                            end
                        endcase

                        // Check if we've completed all 3 runs
                        if (run_count == 2'd2) begin
                            state <= MAJORITY_VOTE;
                            rst_mux <= 1'b0;
                            mux_enable <= 1'b1;
                        end else begin
                            state <= RUN_AES;
                            run_count <= run_count + 1;
                        end
                    end
                end
                // Output final unmasked result from majority vote
                MAJORITY_VOTE: begin
                    if (mux_done) begin
                        mux_enable <= 1'b1;
                        state <= DONE_STATE;
                        fault_protect_aes_out <= result_s0 ^ result_s1;
                    end
                end

                DONE_STATE: begin
                    state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end





endmodule
