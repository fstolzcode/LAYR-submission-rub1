// AES-128 Top-level Module
// Round-based masked implementation with:
// - 2 x 2-byte S-box instances for round function
// - 1 x 2-byte S-box instance for key schedule (inside aes_key_schedule)
// - ShiftRows folded into address generation
// - Column-at-a-time processing

module aes_top (
    input wire clk,
    input wire rst,  // Active-high synchronous reset

    // Control
    input  wire start,      // Start encryption/decryption
    input  wire enc_mode,   // 1 = encrypt, 0 = decrypt
    output wire busy,       // Operation in progress
    output wire done,       // Operation complete (output valid)

    // Data I/O (2 shares each)
    input  wire [127:0] data_in_0,
    input  wire [127:0] data_in_1,
    output wire [127:0] data_out_0,
    output wire [127:0] data_out_1,

    // Key input (2 shares)
    input wire [127:0] key_0,
    input wire [127:0] key_1,

    // Randomness input
    // Per-cycle randomness for S-boxes: 2 × 68 bits = 136 bits
    // Key schedule: 68 bits
    input wire [135:0] random_round,   // S-boxes (136 bits) for round datapath
    input wire [67:0] random_ks        // Key schedule randomness (68 bits for S-box)
);

    // =========================================================================
    // State Machine States (simplified: 6 states instead of 8)
    // =========================================================================
    localparam IDLE           = 3'd0;
    localparam KEY_EXPAND_FWD = 3'd1;   // Expand to k10 for decryption
    localparam INIT_ADDKEY    = 3'd2;   // Initial AddRoundKey
    localparam ROUND_PROCESS  = 3'd3;   // Process columns (SubBytes→MixColumns)
    localparam ROUND_ADDKEY   = 3'd4;   // Apply AddRoundKey
    localparam DONE_STATE     = 3'd5;

    reg [2:0] state;

    // =========================================================================
    // Counters
    // =========================================================================
    reg [3:0] round_ctr;      // Round counter (0-9)
    reg [1:0] col_ctr;        // Column counter (0-3)
    reg [3:0] key_expand_ctr; // Key expansion counter for decrypt init
    reg       col_phase;      // Column processing phase: 0=reset, 1=process
    reg       dp_rdy_seen_low; // Track if dp_rdy has gone low after reset
    reg       ks_rdy_prev;    // Previous ks_rdy for edge detection

    // =========================================================================
    // Mode Register
    // =========================================================================
    reg enc_mode_reg;

    // =========================================================================
    // State Registers (2 shares)
    // =========================================================================
    reg [127:0] state_0, state_1;

    // Working column buffer for collecting S-box outputs
    reg [127:0] next_state_0, next_state_1;

    // =========================================================================
    // Round Key Registers (2 shares)
    // =========================================================================
    reg [127:0] rkey_0, rkey_1;

    // =========================================================================
    // RCON values (packed localparams, MSB-first: index 0 at high bits)
    // Access pattern: RCON_xxx[79 - idx*8 -: 8] for index idx
    // =========================================================================
    localparam [79:0] RCON_FWD = {8'h01, 8'h02, 8'h04, 8'h08, 8'h10,
                                  8'h20, 8'h40, 8'h80, 8'h1B, 8'h36};
    localparam [79:0] RCON_REV = {8'h36, 8'h1B, 8'h80, 8'h40, 8'h20,
                                  8'h10, 8'h08, 8'h04, 8'h02, 8'h01};

    // =========================================================================
    // Key Schedule Interface
    // =========================================================================
    reg        ks_start;
    reg  [7:0] ks_rcon;
    reg        ks_reverse;
    wire       ks_rdy;
    wire       ks_busy;
    wire [127:0] ks_next_key_0, ks_next_key_1;

    aes_key_schedule u_key_schedule (
        .clk(clk),
        .rst(rst),
        .start(ks_start),
        .rcon(ks_rcon),
        .reverse(ks_reverse),
        .rdy(ks_rdy),
        .busy(ks_busy),
        .prev_key_0(rkey_0),
        .prev_key_1(rkey_1),
        .next_key_0(ks_next_key_0),
        .next_key_1(ks_next_key_1),
        .random_ks(random_ks)
    );

    // =========================================================================
    // Round Datapath Interface
    // =========================================================================
    reg         dp_rst;
    wire [31:0] dp_col_in_0, dp_col_in_1;
    wire [31:0] dp_col_out_0, dp_col_out_1;
    wire        dp_rdy;

    aes_round_datapath u_round_datapath (
        .clk(clk),
        .rst(dp_rst),
        .col_in_0(dp_col_in_0),
        .col_in_1(dp_col_in_1),
        .enc_mode(enc_mode_reg),
        .random_sbox_0(random_round[67:0]),
        .random_sbox_1(random_round[135:68]),
        .col_out_0(dp_col_out_0),
        .col_out_1(dp_col_out_1),
        .rdy(dp_rdy)
    );

    // =========================================================================
    // ShiftRows (applied to full state before column processing)
    // =========================================================================
    wire [127:0] shifted_state_0, shifted_state_1;
    aes_shift_rows u_shift_rows_0 (
        .istate(state_0),
        .decrypt(!enc_mode_reg),  // encrypt→ShiftRows, decrypt→InvShiftRows
        .ostate(shifted_state_0)
    );
    aes_shift_rows u_shift_rows_1 (
        .istate(state_1),
        .decrypt(!enc_mode_reg),
        .ostate(shifted_state_1)
    );

    // Extract current column from shifted state
    assign dp_col_in_0 = shifted_state_0[127 - col_ctr*32 -: 32];
    assign dp_col_in_1 = shifted_state_1[127 - col_ctr*32 -: 32];

    // =========================================================================
    // MixColumns for key preprocessing (decryption intermediate keys)
    // Apply InvMixColumns to each key share independently (linear operation)
    // =========================================================================

    // Apply InvMixColumns to next round key shares (from key schedule)
    // decrypt=1 computes InvMixColumns(MixColumns(x))
    wire [127:0] ks_next_key_imc_0;
    wire [127:0] ks_next_key_imc_1;
    aes_mix_columns u_ks_imc_0 (
        .istate(ks_next_key_0),
        .decrypt(1'b1),
        .ostate(ks_next_key_imc_0)
    );
    aes_mix_columns u_ks_imc_1 (
        .istate(ks_next_key_1),
        .decrypt(1'b1),
        .ostate(ks_next_key_imc_1)
    );

    // Use InvMC-processed key for decryption rounds 0-8
    // (These rounds apply keys k9-k1 which need InvMixColumns)
    // Round 9 applies k0 without InvMixColumns
    wire use_imc = !enc_mode_reg && (round_ctr <= 4'd8);

    // =========================================================================
    // MixColumns for round data (applied to full state after all 4 columns collected)
    // Apply to each share independently (MixColumns is linear)
    // =========================================================================
    wire [127:0] mc_round_0, mc_round_1;
    aes_mix_columns u_mc_round_0 (
        .istate(next_state_0),
        .decrypt(!enc_mode_reg),  // encrypt→MC, decrypt→InvMC
        .ostate(mc_round_0)
    );
    aes_mix_columns u_mc_round_1 (
        .istate(next_state_1),
        .decrypt(!enc_mode_reg),
        .ostate(mc_round_1)
    );

    // Bypass MixColumns in final round (round 9)
    wire [127:0] mc_or_bypass_0 = (round_ctr == 4'd9) ? next_state_0 : mc_round_0;
    wire [127:0] mc_or_bypass_1 = (round_ctr == 4'd9) ? next_state_1 : mc_round_1;

    // =========================================================================
    // Main State Machine
    // =========================================================================
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            round_ctr <= 4'd0;
            col_ctr <= 2'd0;
            key_expand_ctr <= 4'd0;
            col_phase <= 1'b0;
            dp_rdy_seen_low <= 1'b0;
            ks_rdy_prev <= 1'b0;
            enc_mode_reg <= 1'b1;
            state_0 <= 128'd0;
            state_1 <= 128'd0;
            next_state_0 <= 128'd0;
            next_state_1 <= 128'd0;
            rkey_0 <= 128'd0;
            rkey_1 <= 128'd0;
            dp_rst <= 1'b1;
            ks_start <= 1'b0;
            ks_rcon <= 8'h00;
            ks_reverse <= 1'b0;
        end else begin
            // Default: deassert one-shot signals
            ks_start <= 1'b0;

            // Track ks_rdy for edge detection
            ks_rdy_prev <= ks_rdy;

            case (state)
                // =============================================================
                IDLE: begin
                    dp_rst <= 1'b1;
                    if (start) begin
                        enc_mode_reg <= enc_mode;
                        rkey_0 <= key_0;
                        rkey_1 <= key_1;
                        state_0 <= data_in_0;
                        state_1 <= data_in_1;
                        round_ctr <= 4'd0;
                        key_expand_ctr <= 4'd0;

                        if (enc_mode) begin
                            // Encryption: go directly to initial AddRoundKey
                            state <= INIT_ADDKEY;
                        end else begin
                            // Decryption: first expand key to k10
                            ks_start <= 1'b1;
                            ks_rcon <= RCON_FWD[79 -: 8];
                            ks_reverse <= 1'b0;
                            ks_rdy_prev <= 1'b0;  // Reset for edge detection
                            state <= KEY_EXPAND_FWD;
                        end
                    end
                end

                // =============================================================
                KEY_EXPAND_FWD: begin
                    // Expand key forward to get k10 for decryption
                    // Use rising edge detection to avoid processing twice
                    if (ks_rdy && !ks_rdy_prev) begin
                        rkey_0 <= ks_next_key_0;
                        rkey_1 <= ks_next_key_1;
                        key_expand_ctr <= key_expand_ctr + 1;

                        if (key_expand_ctr == 4'd9) begin
                            // Have k10, proceed to initial AddRoundKey
                            state <= INIT_ADDKEY;
                        end else begin
                            // Continue expanding
                            ks_start <= 1'b1;
                            ks_rcon <= RCON_FWD[79 - ({3'b0, key_expand_ctr} + 7'd1)*8 -: 8];
                            ks_reverse <= 1'b0;
                        end
                    end
                end

                // =============================================================
                INIT_ADDKEY: begin
                    // Apply initial AddRoundKey to each share independently
                    // No demasking needed - XOR is linear
                    state_0 <= state_0 ^ rkey_0;
                    state_1 <= state_1 ^ rkey_1;
                    round_ctr <= 4'd0;

                    // Start first key schedule iteration
                    if (enc_mode_reg) begin
                        ks_start <= 1'b1;
                        ks_rcon <= RCON_FWD[79 -: 8];
                        ks_reverse <= 1'b0;
                    end else begin
                        ks_start <= 1'b1;
                        ks_rcon <= RCON_REV[79 -: 8];
                        ks_reverse <= 1'b1;
                    end

                    col_ctr <= 2'd0;
                    col_phase <= 1'b0;
                    next_state_0 <= 128'd0;
                    next_state_1 <= 128'd0;
                    state <= ROUND_PROCESS;
                end

                // =============================================================
                ROUND_PROCESS: begin
                    // Process columns using col_phase sub-counter
                    // Phase 0: Reset datapath (1 cycle)
                    // Phase 1: Process and collect output
                    case (col_phase)
                        1'b0: begin  // Reset phase
                            dp_rst <= 1'b1;
                            dp_rdy_seen_low <= 1'b0;
                            col_phase <= 1'b1;
                        end
                        1'b1: begin  // Process phase
                            dp_rst <= 1'b0;  // S-box captures input on first cycle

                            // Track when dp_rdy goes low after reset
                            if (!dp_rdy) begin
                                dp_rdy_seen_low <= 1'b1;
                            end

                            // Collect output when rdy and we've seen the S-box reset
                            if (dp_rdy && dp_rdy_seen_low) begin
                                // Store output to correct column position
                                case (col_ctr)
                                    2'd0: begin
                                        next_state_0[127:96] <= dp_col_out_0;
                                        next_state_1[127:96] <= dp_col_out_1;
                                    end
                                    2'd1: begin
                                        next_state_0[95:64] <= dp_col_out_0;
                                        next_state_1[95:64] <= dp_col_out_1;
                                    end
                                    2'd2: begin
                                        next_state_0[63:32] <= dp_col_out_0;
                                        next_state_1[63:32] <= dp_col_out_1;
                                    end
                                    2'd3: begin
                                        next_state_0[31:0] <= dp_col_out_0;
                                        next_state_1[31:0] <= dp_col_out_1;
                                    end
                                endcase

                                if (col_ctr == 2'd3) begin
                                    ks_rdy_prev <= 1'b0;  // Reset for edge detection
                                    state <= ROUND_ADDKEY;
                                end else begin
                                    col_ctr <= col_ctr + 1;
                                    col_phase <= 1'b0;  // Go back to reset phase
                                end
                            end
                        end
                    endcase
                end

                // =============================================================
                ROUND_ADDKEY: begin
                    // Wait for key schedule - always need the next key
                    // Key schedule was started in INIT_ADDKEY or previous round
                    // Use rising edge detection to avoid processing twice
                    if (ks_rdy && !ks_rdy_prev) begin
                        // Update round key register for future reference
                        rkey_0 <= ks_next_key_0;
                        rkey_1 <= ks_next_key_1;

                        // Apply MixColumns (or bypass for round 9) then AddRoundKey
                        // For decryption rounds 0-8, apply InvMixColumns to the key shares
                        if (use_imc) begin
                            state_0 <= mc_or_bypass_0 ^ ks_next_key_imc_0;
                            state_1 <= mc_or_bypass_1 ^ ks_next_key_imc_1;
                        end else begin
                            state_0 <= mc_or_bypass_0 ^ ks_next_key_0;
                            state_1 <= mc_or_bypass_1 ^ ks_next_key_1;
                        end

                        round_ctr <= round_ctr + 1;

                        if (round_ctr == 4'd9) begin
                            // Done with all rounds
                            state <= DONE_STATE;
                        end else begin
                            // Start next key schedule
                            ks_start <= 1'b1;
                            if (enc_mode_reg) begin
                                ks_rcon <= RCON_FWD[79 - ({3'b0, round_ctr} + 7'd1)*8 -: 8];
                                ks_reverse <= 1'b0;
                            end else begin
                                ks_rcon <= RCON_REV[79 - ({3'b0, round_ctr} + 7'd1)*8 -: 8];
                                ks_reverse <= 1'b1;
                            end
                            col_ctr <= 2'd0;
                            col_phase <= 1'b0;
                            next_state_0 <= 128'd0;
                            next_state_1 <= 128'd0;
                            state <= ROUND_PROCESS;
                        end
                    end
                end

                // =============================================================
                DONE_STATE: begin
                    dp_rst <= 1'b1;
                    // Stay in done until new start
                    if (start) begin
                        enc_mode_reg <= enc_mode;
                        rkey_0 <= key_0;
                        rkey_1 <= key_1;
                        state_0 <= data_in_0;
                        state_1 <= data_in_1;
                        round_ctr <= 4'd0;
                        key_expand_ctr <= 4'd0;

                        if (enc_mode) begin
                            state <= INIT_ADDKEY;
                        end else begin
                            ks_start <= 1'b1;
                            ks_rcon <= RCON_FWD[79 -: 8];
                            ks_reverse <= 1'b0;
                            state <= KEY_EXPAND_FWD;
                        end
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

    // =========================================================================
    // Output Assignments
    // =========================================================================
    assign busy = (state != IDLE) && (state != DONE_STATE);
    assign done = (state == DONE_STATE);
    assign data_out_0 = state_0;
    assign data_out_1 = state_1;

endmodule
