// AES Round Datapath
// Processes one column at a time: SubBytes only (2x 2-byte S-box)
// MixColumns is applied at the top level after all columns are collected

module aes_round_datapath (
    input wire clk,
    input wire rst,  // Active-high synchronous reset (resets S-box pipeline)

    // Column input (2 shares, 4 bytes each)
    input wire [31:0] col_in_0,
    input wire [31:0] col_in_1,

    // Control
    input wire enc_mode,     // 1 = encrypt, 0 = decrypt

    // Randomness for S-boxes (68 bits each)
    input wire [67:0] random_sbox_0,  // For bytes 0-1 (lower 2 bytes)
    input wire [67:0] random_sbox_1,  // For bytes 2-3 (upper 2 bytes)

    // Column output (2 shares)
    output wire [31:0] col_out_0,
    output wire [31:0] col_out_1,

    // Status
    output wire rdy  // Output valid (8 cycles after input)
);

    // =========================================================================
    // S-box instances (2 bytes each)
    // =========================================================================

    // S-box 0: processes bytes 0-1
    wire [15:0] sbox0_out_0;
    wire [15:0] sbox0_out_1;
    wire        sbox0_rdy;

    aes_sbox u_sbox0 (
        .clk(clk),
        .rst(rst),
        .random(random_sbox_0[67:0]),
        .masked_share_0(col_in_0[31:16]),  // bytes 0-1 share 0
        .masked_share_1(col_in_1[31:16]),  // bytes 0-1 share 1
        .enc_mode(enc_mode),
        .share_out_0(sbox0_out_0),
        .share_out_1(sbox0_out_1),
        .rdy(sbox0_rdy)
    );

    // S-box 1: processes bytes 2-3
    wire [15:0] sbox1_out_0;
    wire [15:0] sbox1_out_1;
    wire        sbox1_rdy;

    aes_sbox u_sbox1 (
        .clk(clk),
        .rst(rst),
        .random(random_sbox_1[67:0]),
        .masked_share_0(col_in_0[15:0]),  // bytes 2-3 share 0
        .masked_share_1(col_in_1[15:0]),  // bytes 2-3 share 1
        .enc_mode(enc_mode),
        .share_out_0(sbox1_out_0),
        .share_out_1(sbox1_out_1),
        .rdy(sbox1_rdy)
    );

    // =========================================================================
    // Combine S-box outputs into columns (keep shares separate)
    // S-box 0 processes bytes 0,1 (rows 0,1): sbox0_out[7:0]=S(row0), sbox0_out[15:8]=S(row1)
    // S-box 1 processes bytes 2,3 (rows 2,3): sbox1_out[7:0]=S(row2), sbox1_out[15:8]=S(row3)
    // Output column: {S(row0), S(row1), S(row2), S(row3)} = {[31:24], [23:16], [15:8], [7:0]}
    // =========================================================================
    wire [31:0] sbox_col_0 = {sbox0_out_0[15:8], sbox0_out_0[7:0],
                              sbox1_out_0[15:8], sbox1_out_0[7:0]};
    wire [31:0] sbox_col_1 = {sbox0_out_1[15:8], sbox0_out_1[7:0],
                              sbox1_out_1[15:8], sbox1_out_1[7:0]};

    // Output S-box results directly (MixColumns applied at top level)
    assign col_out_0 = sbox_col_0;
    assign col_out_1 = sbox_col_1;

    // Ready signal (both S-boxes should be ready at the same time)
    assign rdy = sbox0_rdy & sbox1_rdy;

endmodule
