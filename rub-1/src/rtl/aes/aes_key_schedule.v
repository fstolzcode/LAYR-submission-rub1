module aes_key_schedule (
    input wire clk,
    input wire rst,  // Active-high synchronous reset

    input  wire       start,   // Start round key computation
    input  wire [7:0] rcon,    // Round constant (managed by controller)
    input  wire       reverse, // 0 = forward (K_{i-1} → K_i), 1 = reverse (K_i → K_{i-1})
    output wire       rdy,
    output wire       busy,    // Computation in progress

    // Previous round key input K_{i-1} (2 shares)
    input wire [127:0] prev_key_0,
    input wire [127:0] prev_key_1,

    // Next round key output K_i (2 shares)
    output wire [127:0] next_key_0,
    output wire [127:0] next_key_1,

    // Randomness: 68 bits for S-box (wired directly, fresh each cycle)
    input wire [67:0] random_ks
);

    // States
    localparam IDLE    = 3'd0;
    localparam SETUP   = 3'd1;  // Load key, prepare first 2 bytes
    localparam FEED    = 3'd2;  // Feed bytes 0-1, prepare bytes 2-3
    localparam WAIT    = 3'd3;  // Wait for sbox_rdy, collect bytes 0-1
    localparam COMPUTE = 3'd4;  // Collect bytes 2-3 and compute new round key
    localparam READY   = 3'd5;  // Output valid

    reg [2:0] state;

    // Working variables
    reg [127:0] key_reg_0, key_reg_1;
    reg  [ 7:0] rcon_reg;
    reg         reverse_reg;

    // S-box output storage (only need bytes 0-1, bytes 2-3 read directly from sbox_out)
    reg [7:0] sbox_out_bytes_s0 [0:1];
    reg [7:0] sbox_out_bytes_s1 [0:1];

    // S-box interface (2-byte pipelined S-box)
    reg  [15:0] sbox_in_reg_s0;
    reg  [15:0] sbox_in_reg_s1;

    wire [15:0] sbox_out_s0;
    wire [15:0] sbox_out_s1;
    wire        sbox_rdy;
    reg         sbox_rst;

    aes_sbox u_sbox (
        .clk(clk),
        .rst(sbox_rst),
        .random(random_ks),
        .masked_share_0(sbox_in_reg_s0),
        .masked_share_1(sbox_in_reg_s1),
        .enc_mode(1'b1),
        .share_out_0(sbox_out_s0),
        .share_out_1(sbox_out_s1),
        .rdy(sbox_rdy)
    );
    wire [7:0] sbox_test_in1 = sbox_in_reg_s0[7:0] ^ sbox_in_reg_s1[7:0];
    wire [7:0] sbox_test_in2 = sbox_in_reg_s0[15:8] ^ sbox_in_reg_s1[15:8];
    wire [7:0] sbox_test_0 = sbox_out_s0[7:0] ^ sbox_out_s1[7:0];
    wire [7:0] sbox_test_1 = sbox_out_s0[15:8] ^ sbox_out_s1[15:8];
    // =========================================================================
    // g-function input: W3 with RotWord applied
    // W3 = key[31:0] = [b3, b2, b1, b0] (MSB to LSB)
    // RotWord(W3) = [b2, b1, b0, b3]
    // =========================================================================

    // Forward mode: use W3 directly from key_reg
    
    //wire [31:0] w3_combined = key_reg_0[31:0] ^ key_reg_1[31:0];
    wire [31:0] w3_s0 = key_reg_0[31:0];
    wire [31:0] w3_s1 = key_reg_1[31:0];
    //wire [31:0] w3_rotated = {w3_combined[23:0], w3_combined[31:24]};
    wire [31:0] w3_rotated_s0 = {w3_s0[23:0], w3_s0[31:24]};
    wire [31:0] w3_rotated_s1 = {w3_s1[23:0], w3_s1[31:24]};

    // Reverse mode: reconstruct original W3 = W3' ^ W2'
    // (W3' and W2' are the words from K_i that we want to invert)

    //wire [31:0] w2_combined = key_reg_0[63:32] ^ key_reg_1[63:32];
    wire [31:0] w2_s0 = key_reg_0[63:32];
    wire [31:0] w2_s1 = key_reg_1[63:32];
    //  wire [31:0] w3_reverse = w3_combined ^ w2_combined;
    wire [31:0] w3_reverse_s0 = w3_s0 ^ w2_s0;
    wire [31:0] w3_reverse_s1 = w3_s1 ^ w2_s1;

    //wire [31:0] w3_rotated_reverse = {w3_reverse[23:0], w3_reverse[31:24]};
    wire [31:0] w3_rotated_reverse_s0 = {w3_reverse_s0[23:0], w3_reverse_s0[31:24]};
    wire [31:0] w3_rotated_reverse_s1 = {w3_reverse_s1[23:0], w3_reverse_s1[31:24]};

    // Select based on mode
    wire [31:0] w3_rot_sel_s0 = reverse_reg ? w3_rotated_reverse_s0 : w3_rotated_s0;
    wire [31:0] w3_rot_sel_s1 = reverse_reg ? w3_rotated_reverse_s1 : w3_rotated_s1;
    

    // Extract byte pairs for 2-byte S-box

    //wire [7:0] rot_byte_0 = w3_rot_sel[31:24];  // First byte to process
    //wire [7:0] rot_byte_1 = w3_rot_sel[23:16];
    //wire [7:0] rot_byte_2 = w3_rot_sel[15:8];
    //wire [7:0] rot_byte_3 = w3_rot_sel[7:0];    // Last byte to process

    wire [7:0] rot_byte_0_s0 = w3_rot_sel_s0[31:24];  // First byte to process
    wire [7:0] rot_byte_0_s1 = w3_rot_sel_s1[31:24];
    wire [7:0] rot_byte_1_s0 = w3_rot_sel_s0[23:16];
    wire [7:0] rot_byte_1_s1 = w3_rot_sel_s1[23:16];
    wire [7:0] rot_byte_2_s0 = w3_rot_sel_s0[15:8];
    wire [7:0] rot_byte_2_s1 = w3_rot_sel_s1[15:8];
    wire [7:0] rot_byte_3_s0 = w3_rot_sel_s0[7:0];    // Last byte to process
    wire [7:0] rot_byte_3_s1 = w3_rot_sel_s1[7:0];   


    // =========================================================================
    // State Machine
    //
    // Timeline:
    //   IDLE->SETUP: Load key_reg
    //   SETUP: key_reg valid, load bytes 0-1 into S-box
    //   FEED: S-box captures bytes 0-1, load bytes 2-3
    //   WAIT: S-box captures bytes 2-3, wait for sbox_rdy, collect bytes 0-1
    //   COMPUTE: Collect bytes 2-3 from sbox_out, calculate new round key
    //   READY: Output valid
    // =========================================================================
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            sbox_rst <= 1'b1;
            sbox_in_reg_s0 <= 16'd0;
            sbox_in_reg_s1 <= 16'd0;

            key_reg_0 <= 128'd0;
            key_reg_1 <= 128'd0;
            rcon_reg <= 8'h00;
            reverse_reg <= 1'b0;
            sbox_out_bytes_s0[0] <= 8'd0;
            sbox_out_bytes_s1[0] <= 8'd0;
            sbox_out_bytes_s0[1] <= 8'd0;
            sbox_out_bytes_s1[1] <= 8'd0;
        end else begin
            case (state)
                // =========================================================
                IDLE: begin
                    sbox_rst <= 1'b1;
                    if (start) begin
                        key_reg_0 <= prev_key_0;
                        key_reg_1 <= prev_key_1;
                        rcon_reg <= rcon;
                        reverse_reg <= reverse;
                        state <= SETUP;
                    end
                end

                // =========================================================
                SETUP: begin
                    // key_reg is now valid, prepare first 2 bytes
                    sbox_rst <= 1'b0;
                    sbox_in_reg_s0 <= {rot_byte_1_s0, rot_byte_0_s0};
                    sbox_in_reg_s1 <= {rot_byte_1_s1, rot_byte_0_s1};

                    state <= FEED;
                end

                // =========================================================
                FEED: begin
                    // Bytes 0-1 captured this cycle, prepare bytes 2-3
                    sbox_in_reg_s0 <= {rot_byte_3_s0, rot_byte_2_s0};
                    sbox_in_reg_s1 <= {rot_byte_3_s1, rot_byte_2_s1};

                    state <= WAIT;
                end

                // =========================================================
                WAIT: begin
                    // Bytes 2-3 captured on entry, wait for pipeline
                    if (sbox_rdy) begin
                        // Bytes 0-1 ready, collect them
                        sbox_out_bytes_s0[0] <= sbox_out_s0[7:0];
                        sbox_out_bytes_s1[0] <= sbox_out_s1[7:0];
                        sbox_out_bytes_s0[1] <= sbox_out_s0[15:8];
                        sbox_out_bytes_s1[1] <= sbox_out_s1[15:8];
                        state <= COMPUTE;
                    end
                end

                // =========================================================
                COMPUTE: begin
                    // Bytes 2-3 now on sbox_out, bytes 0-1 in registers
                    // g(W3) = SubWord(RotWord(W3)) XOR Rcon
                    // Masking: g is split as (g ^ remask, remask)

                    if (reverse_reg) begin
                        // =======================================================
                        // REVERSE key expansion: K_i → K_{i-1}
                        //   W0 = W0' ^ g(W3)     where W3 = W3' ^ W2' (reconstructed)
                        //   W1 = W1' ^ W0'       (simple XOR, no cascade)
                        //   W2 = W2' ^ W1'       (simple XOR, no cascade)
                        //   W3 = W3' ^ W2'       (simple XOR, no cascade)
                        // =======================================================

                        // Share 0: W0 gets (g ^ remask), others are simple XORs
                        key_reg_0[127:96] <= key_reg_0[127:96] ^
                                             {sbox_out_bytes_s0[0] ^ rcon_reg,
                                              sbox_out_bytes_s0[1],
                                              sbox_out_s0[7:0],
                                              sbox_out_s0[15:8]};
                        key_reg_0[95:64]  <= key_reg_0[95:64] ^ key_reg_0[127:96];
                        key_reg_0[63:32]  <= key_reg_0[63:32] ^ key_reg_0[95:64];
                        key_reg_0[31:0]   <= key_reg_0[31:0] ^ key_reg_0[63:32];

                        // Share 1: W0 gets remask, others are simple XORs
                        key_reg_1[127:96] <= key_reg_1[127:96] ^
                                            {sbox_out_bytes_s1[0],
                                             sbox_out_bytes_s1[1],
                                             sbox_out_s1[7:0],
                                             sbox_out_s1[15:8]};
                        key_reg_1[95:64]  <= key_reg_1[95:64] ^ key_reg_1[127:96];
                        key_reg_1[63:32]  <= key_reg_1[63:32] ^ key_reg_1[95:64];
                        key_reg_1[31:0]   <= key_reg_1[31:0] ^ key_reg_1[63:32];

                    end else begin
                        // =======================================================
                        // FORWARD key expansion: K_{i-1} → K_i
                        //   W0' = W0 ^ g(W3)
                        //   W1' = W1 ^ W0'
                        //   W2' = W2 ^ W1'
                        //   W3' = W3 ^ W2'
                        // =======================================================

                        // Share 0: gets (g ^ remask)
                        key_reg_0[127:96] <= key_reg_0[127:96] ^
                                             {sbox_out_bytes_s0[0] ^ rcon_reg,
                                              sbox_out_bytes_s0[1],
                                              sbox_out_s0[7:0],
                                              sbox_out_s0[15:8]};

                        key_reg_0[95:64] <= key_reg_0[127:96] ^ key_reg_0[95:64] ^
                                            {sbox_out_bytes_s0[0] ^ rcon_reg,
                                             sbox_out_bytes_s0[1],
                                             sbox_out_s0[7:0],
                                             sbox_out_s0[15:8]};

                        key_reg_0[63:32] <= key_reg_0[127:96] ^ key_reg_0[95:64] ^ key_reg_0[63:32] ^
                                            {sbox_out_bytes_s0[0] ^ rcon_reg,
                                             sbox_out_bytes_s0[1],
                                             sbox_out_s0[7:0],
                                             sbox_out_s0[15:8]};

                        key_reg_0[31:0] <= key_reg_0[127:96] ^ key_reg_0[95:64] ^ key_reg_0[63:32] ^ key_reg_0[31:0] ^
                                           {sbox_out_bytes_s0[0] ^ rcon_reg,
                                            sbox_out_bytes_s0[1],
                                            sbox_out_s0[7:0],
                                            sbox_out_s0[15:8]};
                        
                        // Share 1: gets remask
                        key_reg_1[127:96] <= key_reg_1[127:96] ^
                                             {sbox_out_bytes_s1[0],
                                              sbox_out_bytes_s1[1],
                                              sbox_out_s1[7:0],
                                              sbox_out_s1[15:8]};

                        key_reg_1[95:64] <= key_reg_1[127:96] ^ key_reg_1[95:64] ^
                                            {sbox_out_bytes_s1[0],
                                             sbox_out_bytes_s1[1],
                                             sbox_out_s1[7:0],
                                             sbox_out_s1[15:8]};

                        key_reg_1[63:32] <= key_reg_1[127:96] ^ key_reg_1[95:64] ^ key_reg_1[63:32] ^
                                            {sbox_out_bytes_s1[0] ,
                                             sbox_out_bytes_s1[1],
                                             sbox_out_s1[7:0],
                                             sbox_out_s1[15:8]};

                        key_reg_1[31:0] <= key_reg_1[127:96] ^ key_reg_1[95:64] ^ key_reg_1[63:32] ^ key_reg_1[31:0] ^
                                           {sbox_out_bytes_s1[0],
                                            sbox_out_bytes_s1[1],
                                            sbox_out_s1[7:0],
                                            sbox_out_s1[15:8]};
                    end

                    sbox_rst <= 1'b1;
                    state <= READY;
                end

                // =========================================================
                READY: begin
                    sbox_rst <= 1'b1;
                    if (start) begin
                        key_reg_0 <= prev_key_0;
                        key_reg_1 <= prev_key_1;
                        rcon_reg <= rcon;
                        reverse_reg <= reverse;
                        state <= SETUP;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

    // =========================================================================
    // Outputs
    // =========================================================================
    assign rdy = (state == READY);
    assign busy = (state != IDLE) && (state != READY);
    assign next_key_0 = key_reg_0;
    assign next_key_1 = key_reg_1;

endmodule
