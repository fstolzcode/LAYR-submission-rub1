module aes_shift_rows
    (
        input  [127:0] istate,
        input wire decrypt,   // 0: ShiftRows (encrypt), 1: InvShiftRows (decrypt)
        output [127:0] ostate
    );

    wire [7:0] istate_matrix [0:3][0:3]; // [row][col]
    wire [7:0] ostate_matrix [0:3][0:3]; // [row][col]
    genvar r, c;

    // pack/unpack (column-major)
    generate
        for (c = 0; c < 4; c = c + 1) begin : gen_pack_cols
            for (r = 0; r < 4; r = r + 1) begin : gen_pack_rows
                assign istate_matrix[r][c] = istate[127-(c*4+r)*8 : 120-(c*4+r)*8];
                assign ostate[127-(c*4+r)*8 : 120-(c*4+r)*8] = ostate_matrix[r][c];
            end
        end
    endgenerate

    // shiftrows / invshiftrows
    generate
        for (r = 0; r < 4; r = r + 1) begin : gen_rows
            for (c = 0; c < 4; c = c + 1) begin : gen_cols
                localparam int SRC_ENC = (c + r >= 4) ? (c + r - 4) : (c + r);
                localparam int SRC_DEC = (c - r < 0)  ? (c - r + 4) : (c - r);

                assign ostate_matrix[r][c] =
                    decrypt ? istate_matrix[r][SRC_DEC[1:0]]
                            : istate_matrix[r][SRC_ENC[1:0]];
            end
        end
    endgenerate

endmodule
