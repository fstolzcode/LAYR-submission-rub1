// AES MixColumns + InvMixColumns based on "InvMixColumn Decomposition and Multilevel Resource Sharing in AES Implementations" by Fischer et al. (2005)

module aes_mix_columns (
    input  wire [127:0] istate,
    input  wire decrypt,
    output wire [127:0] ostate
);

    // multiply by {02} in GF(2^8) with AES polynomial 0x11B
    function [7:0] xtime;
        input [7:0] b;
        begin
            xtime = (b[7] == 1'b1) ? ((b << 1) ^ 8'h1B) : (b << 1);
        end
    endfunction

    function [7:0] mul4;
        input [7:0] b;
        begin
            mul4 = xtime(xtime(b)); 
        end
    endfunction

    // MixColumn
    function [31:0] mixcolumns;
        input [31:0] col_in;
        reg   [7:0] a0,a1,a2,a3;
        reg   [7:0] s;
        reg   [7:0] m0,m1,m2,m3;
        begin
            a0 = col_in[31:24];
            a1 = col_in[23:16];
            a2 = col_in[15:8];
            a3 = col_in[7:0];

            s  = a0 ^ a1 ^ a2 ^ a3;

            m0 = s ^ xtime(a0 ^ a1) ^ a0;
            m1 = s ^ xtime(a1 ^ a2) ^ a1;
            m2 = s ^ xtime(a2 ^ a3) ^ a2;
            m3 = s ^ xtime(a3 ^ a0) ^ a3;

            mixcolumns = {m0,m1,m2,m3};
        end
    endfunction

    // InvMixColumn
    function [31:0] inv_mixcolumns;
        input [31:0] mix_in;
        reg   [7:0] m0,m1,m2,m3;
        reg   [7:0] p0,p1,p2,p3;
        reg   [7:0] t02,t13;
        reg   [7:0] b0,b1,b2,b3;
        begin
            m0 = mix_in[31:24];
            m1 = mix_in[23:16];
            m2 = mix_in[15:8];
            m3 = mix_in[7:0];

            p0 = mul4(m0);
            p1 = mul4(m1);
            p2 = mul4(m2);
            p3 = mul4(m3);

            t02 = p0 ^ p2;
            t13 = p1 ^ p3;

            b0 = t02 ^ m0;
            b1 = t13 ^ m1;
            b2 = t02 ^ m2; 
            b3 = t13 ^ m3;  

            inv_mixcolumns = {b0,b1,b2,b3};
        end
    endfunction

    // Column extraction (column-major AES state)
    wire [31:0] col0_in = istate[127:96];
    wire [31:0] col1_in = istate[95:64];
    wire [31:0] col2_in = istate[63:32];
    wire [31:0] col3_in = istate[31:0];

    wire [31:0] col0_mix = mixcolumns(col0_in);
    wire [31:0] col1_mix = mixcolumns(col1_in);
    wire [31:0] col2_mix = mixcolumns(col2_in);
    wire [31:0] col3_mix = mixcolumns(col3_in);

    wire [31:0] col0_out = decrypt ? inv_mixcolumns(col0_mix) : col0_mix;
    wire [31:0] col1_out = decrypt ? inv_mixcolumns(col1_mix) : col1_mix;
    wire [31:0] col2_out = decrypt ? inv_mixcolumns(col2_mix) : col2_mix;
    wire [31:0] col3_out = decrypt ? inv_mixcolumns(col3_mix) : col3_mix;

    assign ostate = {col0_out, col1_out, col2_out, col3_out};

endmodule
