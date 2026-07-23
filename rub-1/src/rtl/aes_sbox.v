// This file implements the AES S-box and its inverse with masking proposed in https://inria.hal.science/hal-01518214/file/978-3-642-30436-1_24_Chapter.pdf.

// The implementation implements a pipeline, which has an initial waiting time of 8 cycles indicated by the rdy signal.
// As inputs we need 68 bits of randomness for the AND gates.
// Currently the SBox masks the inputs and then outputs the unmasked SBox results.

module aes_sbox (
    input wire clk,
    input wire rst,  // Active-high reset
    input wire [67:0] random,  
    input wire [15:0] masked_share_0,  //data ^ mask  for both bytes share_0_byte0 | share_0_byte1
    input wire [15:0] masked_share_1,  //mask for both bytes share_1_byte0 | share_1_byte1
    input wire enc_mode,  // 1 for encryption 0 for decryption
    output [15:0] share_out_0,
    output [15:0] share_out_1, 
    output wire rdy
);

// Each signal is [byte][share]
wire [1:0] [1:0] t_enc1, t_enc2, t_enc3, t_enc4, t_enc5, t_enc6,
     t_enc7, t_enc8, t_enc9, t_enc10, t_enc11, t_enc12,
     t_enc13, t_enc14, t_enc15, t_enc16, t_enc17, t_enc18,
     t_enc19, t_enc20, t_enc21, t_enc22, t_enc23, t_enc24,
     t_enc25, t_enc26, t_enc27;

wire [1:0] [1:0] t_dec1, t_dec2, t_dec3, t_dec4, t_dec6, t_dec8,
     t_dec9, t_dec10, t_dec13, t_dec14, t_dec15, t_dec16,
     t_dec17, t_dec19, t_dec20, t_dec22, t_dec23, t_dec24,
     t_dec25, t_dec26, t_dec27;

wire [1:0] [1:0] t1, t2, t3, t4, t5, t6, t7, t8, t9, t10,
     t11, t12, t13, t14, t15, t16, t17, t18, t19, t20,
     t21, t22, t23, t24, t25, t26, t27;

wire [1:0] [1:0] m0, m1, m2, m3, m4, m5, m6, m7, m8, m9, m10,
     m11, m12, m13, m14, m15, m16, m17, m18, m19, m20,
     m21, m22, m23, m24, m25, m26, m27, m28, m29, m30,
     m31, m32, m33, m34, m35, m36, m37, m38, m39, m40,
     m41, m42, m43, m44, m45, m46, m47, m48, m49, m50,
     m51, m52, m53, m54, m55, m56, m57, m58, m59, m60,
     m61, m62, m63;

wire [1:0] [1:0] l0, l1, l2, l3, l4, l5, l6, l7, l8, l9, l10,
     l11, l12, l13, l14, l15, l16, l17, l18, l19, l20,
     l21, l22, l23, l24, l25, l26, l27, l28, l29;

wire [1:0] [1:0] p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10,
     p11, p12, p13, p14, p15, p16, p17, p18, p19, p20,
     p22, p23, p24, p25, p26, p27, p28, p29;

wire [1:0] [1:0] s0, s1, s2, s3, s4, s5, s6, s7;
wire [1:0] [1:0] s0_xor, s1_xor, s5_xor, s6_xor;

wire [1:0] [1:0] w0, w1, w2, w3, w4, w5, w6, w7;

wire [1:0] [1:0] r0, r1, r2, r3, r4;
wire [1:0] [1:0] r2_temp, r3_temp, r4_temp;
wire [1:0] [1:0] dec2_temp, dec5_temp , dec8_temp, dec9_temp, dec17_temp,  dec22_temp, dec24_temp, dec25_temp;
wire [1:0] [1:0] y;
wire [1:0] [1:0] d;


// Registers for pipelining: [Pipeline stage] [byte] [share]
reg [1:0] [1:0] [1:0] t14_pipe, t24_pipe, m24_pipe, m27_pipe, m33_pipe, m36_pipe;

reg [3:0][1:0][1:0]  m21_pipe, m23_pipe;

reg [5:0] [1:0] [1:0] d_pipe, t1_pipe, t2_pipe, t3_pipe, t4_pipe, 
    t6_pipe, t8_pipe, t9_pipe, t10_pipe,
    t13_pipe, t15_pipe, t16_pipe, t17_pipe, t19_pipe, t20_pipe,
    t22_pipe, t23_pipe, t25_pipe, t26_pipe, t27_pipe;



// The following code implements the AES circuit using only XOR, NOT and AND gates to make masking possible.
// Each operation described in the paper is implemented step by step below 
// + -> XOR
// # -> XNOR (a # b = NOT(a XOR b))
// Note, that the bit ordering is inversed to the paper's notation (i.e., U0 is indicated by index 7).



// Encryption path 
// Byte 0 (bits [7:0])

// T1 = U0 + U3
HPC2Xor #(.d(1)) xor_enc1_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[7], masked_share_1[7]}), .io_y({masked_share_0[4], masked_share_1[4]}), .io_z(t_enc1[0]));
// T2 = U0 + U5
HPC2Xor #(.d(1)) xor_enc2_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[7], masked_share_1[7]}), .io_y({masked_share_0[2], masked_share_1[2]}), .io_z(t_enc2[0]));
// T3 = U0 + U6
HPC2Xor #(.d(1)) xor_enc3_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[7], masked_share_1[7]}), .io_y({masked_share_0[1], masked_share_1[1]}), .io_z(t_enc3[0]));
// T4 = U3 + U5
HPC2Xor #(.d(1)) xor_enc4_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[4], masked_share_1[4]}), .io_y({masked_share_0[2], masked_share_1[2]}), .io_z(t_enc4[0]));
// T5 = U4 + U6
HPC2Xor #(.d(1)) xor_enc5_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[3], masked_share_1[3]}), .io_y({masked_share_0[1], masked_share_1[1]}), .io_z(t_enc5[0]));
// T6 = T1 + T5
HPC2Xor #(.d(1)) xor_enc6_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc1[0]), .io_y(t_enc5[0]), .io_z(t_enc6[0]));
// T7 = U1 + U2
HPC2Xor #(.d(1)) xor_enc7_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[6], masked_share_1[6]}), .io_y({masked_share_0[5], masked_share_1[5]}), .io_z(t_enc7[0]));
// T8 = U7 + T6
HPC2Xor #(.d(1)) xor_enc8_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[0], masked_share_1[0]}), .io_y(t_enc6[0]), .io_z(t_enc8[0]));
// T9 = U7 + T7
HPC2Xor #(.d(1)) xor_enc9_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[0], masked_share_1[0]}), .io_y(t_enc7[0]), .io_z(t_enc9[0]));
// T10 = T6 + T7
HPC2Xor #(.d(1)) xor_enc10_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc6[0]), .io_y(t_enc7[0]), .io_z(t_enc10[0]));
// T11 = U1 + U5
HPC2Xor #(.d(1)) xor_enc11_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[6], masked_share_1[6]}), .io_y({masked_share_0[2], masked_share_1[2]}), .io_z(t_enc11[0]));
// T12 = U2 + U5
HPC2Xor #(.d(1)) xor_enc12_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[5], masked_share_1[5]}), .io_y({masked_share_0[2], masked_share_1[2]}), .io_z(t_enc12[0]));
// T13 = T3 + T4
HPC2Xor #(.d(1)) xor_enc13_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc3[0]), .io_y(t_enc4[0]), .io_z(t_enc13[0]));
// T14 = T6 + T11
HPC2Xor #(.d(1)) xor_enc14_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc6[0]), .io_y(t_enc11[0]), .io_z(t_enc14[0]));
// T15 = T5 + T11
HPC2Xor #(.d(1)) xor_enc15_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc5[0]), .io_y(t_enc11[0]), .io_z(t_enc15[0]));
// T16 = T5 + T12
HPC2Xor #(.d(1)) xor_enc16_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc5[0]), .io_y(t_enc12[0]), .io_z(t_enc16[0]));
// T17 = T9 + T16
HPC2Xor #(.d(1)) xor_enc17_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc9[0]), .io_y(t_enc16[0]), .io_z(t_enc17[0]));
// T18 = U3 + U7
HPC2Xor #(.d(1)) xor_enc18_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[4], masked_share_1[4]}), .io_y({masked_share_0[0], masked_share_1[0]}), .io_z(t_enc18[0]));
// T19 = T7 + T18
HPC2Xor #(.d(1)) xor_enc19_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc7[0]), .io_y(t_enc18[0]), .io_z(t_enc19[0]));
// T20 = T1 + T19
HPC2Xor #(.d(1)) xor_enc20_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc1[0]), .io_y(t_enc19[0]), .io_z(t_enc20[0]));
// T21 = U6 + U7
HPC2Xor #(.d(1)) xor_enc21_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[1], masked_share_1[1]}), .io_y({masked_share_0[0], masked_share_1[0]}), .io_z(t_enc21[0]));
// T22 = T7 + T21
HPC2Xor #(.d(1)) xor_enc22_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc7[0]), .io_y(t_enc21[0]), .io_z(t_enc22[0]));
// T23 = T2 + T22
HPC2Xor #(.d(1)) xor_enc23_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc2[0]), .io_y(t_enc22[0]), .io_z(t_enc23[0]));
// T24 = T2 + T10
HPC2Xor #(.d(1)) xor_enc24_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc2[0]), .io_y(t_enc10[0]), .io_z(t_enc24[0]));
// T25 = T20 + T17
HPC2Xor #(.d(1)) xor_enc25_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc20[0]), .io_y(t_enc17[0]), .io_z(t_enc25[0]));
// T26 = T3 + T16
HPC2Xor #(.d(1)) xor_enc26_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc3[0]), .io_y(t_enc16[0]), .io_z(t_enc26[0]));
// T27 = T1 + T12
HPC2Xor #(.d(1)) xor_enc27_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_enc1[0]), .io_y(t_enc12[0]), .io_z(t_enc27[0]));

// Byte 1 (bits [15:8]): Same operations for the second byte as shown above
HPC2Xor #(.d(1)) xor_enc1_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[15], masked_share_1[15]}), .io_y({masked_share_0[12], masked_share_1[12]}), .io_z(t_enc1[1]));
HPC2Xor #(.d(1)) xor_enc2_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[15], masked_share_1[15]}), .io_y({masked_share_0[10], masked_share_1[10]}), .io_z(t_enc2[1]));
HPC2Xor #(.d(1)) xor_enc3_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[15], masked_share_1[15]}), .io_y({masked_share_0[9], masked_share_1[9]}), .io_z(t_enc3[1]));
HPC2Xor #(.d(1)) xor_enc4_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[12], masked_share_1[12]}), .io_y({masked_share_0[10], masked_share_1[10]}), .io_z(t_enc4[1]));
HPC2Xor #(.d(1)) xor_enc5_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[11], masked_share_1[11]}), .io_y({masked_share_0[9], masked_share_1[9]}), .io_z(t_enc5[1]));
HPC2Xor #(.d(1)) xor_enc6_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc1[1]), .io_y(t_enc5[1]), .io_z(t_enc6[1]));
HPC2Xor #(.d(1)) xor_enc7_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[14], masked_share_1[14]}), .io_y({masked_share_0[13], masked_share_1[13]}), .io_z(t_enc7[1]));
HPC2Xor #(.d(1)) xor_enc8_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[8], masked_share_1[8]}), .io_y(t_enc6[1]), .io_z(t_enc8[1]));
HPC2Xor #(.d(1)) xor_enc9_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[8], masked_share_1[8]}), .io_y(t_enc7[1]), .io_z(t_enc9[1]));
HPC2Xor #(.d(1)) xor_enc10_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc6[1]), .io_y(t_enc7[1]), .io_z(t_enc10[1]));
HPC2Xor #(.d(1)) xor_enc11_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[14], masked_share_1[14]}), .io_y({masked_share_0[10], masked_share_1[10]}), .io_z(t_enc11[1]));
HPC2Xor #(.d(1)) xor_enc12_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[13], masked_share_1[13]}), .io_y({masked_share_0[10], masked_share_1[10]}), .io_z(t_enc12[1]));
HPC2Xor #(.d(1)) xor_enc13_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc3[1]), .io_y(t_enc4[1]), .io_z(t_enc13[1]));
HPC2Xor #(.d(1)) xor_enc14_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc6[1]), .io_y(t_enc11[1]), .io_z(t_enc14[1]));
HPC2Xor #(.d(1)) xor_enc15_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc5[1]), .io_y(t_enc11[1]), .io_z(t_enc15[1]));
HPC2Xor #(.d(1)) xor_enc16_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc5[1]), .io_y(t_enc12[1]), .io_z(t_enc16[1]));
HPC2Xor #(.d(1)) xor_enc17_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc9[1]), .io_y(t_enc16[1]), .io_z(t_enc17[1]));
HPC2Xor #(.d(1)) xor_enc18_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[12], masked_share_1[12]}), .io_y({masked_share_0[8], masked_share_1[8]}), .io_z(t_enc18[1]));
HPC2Xor #(.d(1)) xor_enc19_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc7[1]), .io_y(t_enc18[1]), .io_z(t_enc19[1]));
HPC2Xor #(.d(1)) xor_enc20_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc1[1]), .io_y(t_enc19[1]), .io_z(t_enc20[1]));
HPC2Xor #(.d(1)) xor_enc21_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[9], masked_share_1[9]}), .io_y({masked_share_0[8], masked_share_1[8]}), .io_z(t_enc21[1]));
HPC2Xor #(.d(1)) xor_enc22_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc7[1]), .io_y(t_enc21[1]), .io_z(t_enc22[1]));
HPC2Xor #(.d(1)) xor_enc23_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc2[1]), .io_y(t_enc22[1]), .io_z(t_enc23[1]));
HPC2Xor #(.d(1)) xor_enc24_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc2[1]), .io_y(t_enc10[1]), .io_z(t_enc24[1]));
HPC2Xor #(.d(1)) xor_enc25_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc20[1]), .io_y(t_enc17[1]), .io_z(t_enc25[1]));
HPC2Xor #(.d(1)) xor_enc26_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc3[1]), .io_y(t_enc16[1]), .io_z(t_enc26[1]));
HPC2Xor #(.d(1)) xor_enc27_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_enc1[1]), .io_y(t_enc12[1]), .io_z(t_enc27[1]));


// Calculation for Decryption T 
// Byte 0
// T23 = U0 + U3
HPC2Xor #(.d(1)) xor_dec23_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[7], masked_share_1[7]}), .io_y({masked_share_0[4], masked_share_1[4]}), .io_z(t_dec23[0]));
// T22 = U1 # U3
HPC2Xor #(.d(1)) xor_dec22_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[6], masked_share_1[6]}), .io_y({masked_share_0[4], masked_share_1[4]}), .io_z(dec22_temp[0]));
HPC2Not #(.d(1)) not_dec22_b0 (.control_clk(clk), .control_reset(rst), .io_x(dec22_temp[0]), .io_z(t_dec22[0]));
// T2 = U0 # U1
HPC2Xor #(.d(1)) xor_dec2_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[7], masked_share_1[7]}), .io_y({masked_share_0[6], masked_share_1[6]}), .io_z(dec2_temp[0]));
HPC2Not #(.d(1)) not_dec2_b0 (.control_clk(clk), .control_reset(rst), .io_x(dec2_temp[0]), .io_z(t_dec2[0]));
// T1 = U3 + U4
HPC2Xor #(.d(1)) xor_dec1_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[4], masked_share_1[4]}), .io_y({masked_share_0[3], masked_share_1[3]}), .io_z(t_dec1[0]));
// T24 = U4 # U7
HPC2Xor #(.d(1)) xor_dec24_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[3], masked_share_1[3]}), .io_y({masked_share_0[0], masked_share_1[0]}), .io_z(dec24_temp[0]));
HPC2Not #(.d(1)) not_dec24_b0 (.control_clk(clk), .control_reset(rst), .io_x(dec24_temp[0]), .io_z(t_dec24[0]));
// R5 = U6 + U7
HPC2Xor #(.d(1)) xor_r0_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[1], masked_share_1[1]}), .io_y({masked_share_0[0], masked_share_1[0]}), .io_z(r0[0]));
// T8 = U1 # T23
HPC2Xor #(.d(1)) xor_dec8_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[6], masked_share_1[6]}), .io_y(t_dec23[0]), .io_z(dec8_temp[0]));
HPC2Not #(.d(1)) not_dec8_b0 (.control_clk(clk), .control_reset(rst), .io_x(dec8_temp[0]), .io_z(t_dec8[0]));
// T19 = T22 + R5
HPC2Xor #(.d(1)) xor_dec19_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec22[0]), .io_y(r0[0]), .io_z(t_dec19[0]));
// T9 = U7 # T1
HPC2Xor #(.d(1)) xor_dec9_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[0], masked_share_1[0]}), .io_y(t_dec1[0]), .io_z(dec9_temp[0]));
HPC2Not #(.d(1)) not_dec9_b0 (.control_clk(clk), .control_reset(rst), .io_x(dec9_temp[0]), .io_z(t_dec9[0]));
// T10 = T2 + T24
HPC2Xor #(.d(1)) xor_dec10_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec2[0]), .io_y(t_dec24[0]), .io_z(t_dec10[0]));
// T13 = T2 + R5
HPC2Xor #(.d(1)) xor_dec13_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec2[0]), .io_y(r0[0]), .io_z(t_dec13[0]));
// T3 = T1 + R5
HPC2Xor #(.d(1)) xor_dec3_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec1[0]), .io_y(r0[0]), .io_z(t_dec3[0]));
// T25 = U2 # T1
HPC2Xor #(.d(1)) xor_dec25_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[5], masked_share_1[5]}), .io_y(t_dec1[0]), .io_z(dec25_temp[0]));
HPC2Not #(.d(1)) not_dec25_b0 (.control_clk(clk), .control_reset(rst), .io_x(dec25_temp[0]), .io_z(t_dec25[0]));
// R13 = U1 + U6
HPC2Xor #(.d(1)) xor_r1_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[6], masked_share_1[6]}), .io_y({masked_share_0[1], masked_share_1[1]}), .io_z(r1[0]));
// T17 = U2 # T19
HPC2Xor #(.d(1)) xor_dec17_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[5], masked_share_1[5]}), .io_y(t_dec19[0]), .io_z(dec17_temp[0]));
HPC2Not #(.d(1)) not_dec17_b0 (.control_clk(clk), .control_reset(rst), .io_x(dec17_temp[0]), .io_z(t_dec17[0]));
// T20 = T24 + R13
HPC2Xor #(.d(1)) xor_dec20_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec24[0]), .io_y(r1[0]), .io_z(t_dec20[0]));
// T4 = U4 + T8
HPC2Xor #(.d(1)) xor_dec4_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[3], masked_share_1[3]}), .io_y(t_dec8[0]), .io_z(t_dec4[0]));
// R17 = U2 # U5
HPC2Xor #(.d(1)) xor_r2_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[5], masked_share_1[5]}), .io_y({masked_share_0[2], masked_share_1[2]}), .io_z(r2_temp[0]));
HPC2Not #(.d(1)) not_r2_b0 (.control_clk(clk), .control_reset(rst), .io_x(r2_temp[0]), .io_z(r2[0]));
// R18 = U5 # U6
HPC2Xor #(.d(1)) xor_r3_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[2], masked_share_1[2]}), .io_y({masked_share_0[1], masked_share_1[1]}), .io_z(r3_temp[0]));
HPC2Not #(.d(1)) not_r3_b0 (.control_clk(clk), .control_reset(rst), .io_x(r3_temp[0]), .io_z(r3[0]));
// R19 = U2 # U4
HPC2Xor #(.d(1)) xor_r4_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[5], masked_share_1[5]}), .io_y({masked_share_0[3], masked_share_1[3]}), .io_z(r4_temp[0]));
HPC2Not #(.d(1)) not_r4_b0 (.control_clk(clk), .control_reset(rst), .io_x(r4_temp[0]), .io_z(r4[0]));
// Y5 = U0 + R17
HPC2Xor #(.d(1)) xor_y_b0 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[7], masked_share_1[7]}), .io_y(r2[0]), .io_z(y[0]));
// T6 = T22 + R17
HPC2Xor #(.d(1)) xor_dec6_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec22[0]), .io_y(r2[0]), .io_z(t_dec6[0]));
// T16 = R13 + R19
HPC2Xor #(.d(1)) xor_dec16_b0 (.control_clk(clk), .control_reset(rst), .io_x(r1[0]), .io_y(r4[0]), .io_z(t_dec16[0]));
// T27 = T1 + R18
HPC2Xor #(.d(1)) xor_dec27_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec1[0]), .io_y(r3[0]), .io_z(t_dec27[0]));
// T15 = T10 + T27
HPC2Xor #(.d(1)) xor_dec15_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec10[0]), .io_y(t_dec27[0]), .io_z(t_dec15[0]));
// T14 = T10 + R18
HPC2Xor #(.d(1)) xor_dec14_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec10[0]), .io_y(r3[0]), .io_z(t_dec14[0]));
// T26 = T3 + T16
HPC2Xor #(.d(1)) xor_dec26_b0 (.control_clk(clk), .control_reset(rst), .io_x(t_dec3[0]), .io_y(t_dec16[0]), .io_z(t_dec26[0]));



// Byte 1 (bits [15:8]): Same operations for the second byte as shown above
HPC2Xor #(.d(1)) xor_dec25_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[13], masked_share_1[13]}), .io_y(t_dec1[1]), .io_z(dec25_temp[1]));
HPC2Xor #(.d(1)) xor_dec2_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[15], masked_share_1[15]}), .io_y({masked_share_0[14], masked_share_1[14]}), .io_z(dec2_temp[1]));
HPC2Xor #(.d(1)) xor_dec22_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[14], masked_share_1[14]}), .io_y({masked_share_0[12], masked_share_1[12]}), .io_z(dec22_temp[1]));
HPC2Xor #(.d(1)) xor_dec24_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[11], masked_share_1[11]}), .io_y({masked_share_0[8], masked_share_1[8]}), .io_z(dec24_temp[1]));
HPC2Xor #(.d(1)) xor_dec8_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[14], masked_share_1[14]}), .io_y(t_dec23[1]), .io_z(dec8_temp[1]));
HPC2Xor #(.d(1)) xor_dec9_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[8], masked_share_1[8]}), .io_y(t_dec1[1]), .io_z(dec9_temp[1]));
HPC2Xor #(.d(1)) xor_dec17_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[13], masked_share_1[13]}), .io_y(t_dec19[1]), .io_z(dec17_temp[1]));
HPC2Not #(.d(1)) not_dec25_b1 (.control_clk(clk), .control_reset(rst), .io_x(dec25_temp[1]), .io_z(t_dec25[1]));
HPC2Not #(.d(1)) not_dec2_b1 (.control_clk(clk), .control_reset(rst), .io_x(dec2_temp[1]), .io_z(t_dec2[1]));
HPC2Not #(.d(1)) not_dec22_b1 (.control_clk(clk), .control_reset(rst), .io_x(dec22_temp[1]), .io_z(t_dec22[1]));
HPC2Not #(.d(1)) not_dec24_b1 (.control_clk(clk), .control_reset(rst), .io_x(dec24_temp[1]), .io_z(t_dec24[1]));
HPC2Not #(.d(1)) not_dec8_b1 (.control_clk(clk), .control_reset(rst), .io_x(dec8_temp[1]), .io_z(t_dec8[1]));
HPC2Not #(.d(1)) not_dec9_b1 (.control_clk(clk), .control_reset(rst), .io_x(dec9_temp[1]), .io_z(t_dec9[1]));
HPC2Not #(.d(1)) not_dec17_b1 (.control_clk(clk), .control_reset(rst), .io_x(dec17_temp[1]), .io_z(t_dec17[1]));
HPC2Xor #(.d(1)) xor_dec23_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[15], masked_share_1[15]}), .io_y({masked_share_0[12], masked_share_1[12]}), .io_z(t_dec23[1]));
HPC2Xor #(.d(1)) xor_dec1_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[12], masked_share_1[12]}), .io_y({masked_share_0[11], masked_share_1[11]}), .io_z(t_dec1[1]));
HPC2Xor #(.d(1)) xor_dec3_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec1[1]), .io_y(r0[1]), .io_z(t_dec3[1]));
HPC2Xor #(.d(1)) xor_dec4_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[11], masked_share_1[11]}), .io_y(t_dec8[1]), .io_z(t_dec4[1]));
HPC2Xor #(.d(1)) xor_dec6_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec22[1]), .io_y(r2[1]), .io_z(t_dec6[1]));
HPC2Xor #(.d(1)) xor_dec10_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec2[1]), .io_y(t_dec24[1]), .io_z(t_dec10[1]));
HPC2Xor #(.d(1)) xor_dec13_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec2[1]), .io_y(r0[1]), .io_z(t_dec13[1]));
HPC2Xor #(.d(1)) xor_dec14_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec10[1]), .io_y(r3[1]), .io_z(t_dec14[1]));
HPC2Xor #(.d(1)) xor_dec15_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec10[1]), .io_y(t_dec27[1]), .io_z(t_dec15[1]));
HPC2Xor #(.d(1)) xor_dec16_b1 (.control_clk(clk), .control_reset(rst), .io_x(r1[1]), .io_y(r4[1]), .io_z(t_dec16[1]));
HPC2Xor #(.d(1)) xor_dec19_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec22[1]), .io_y(r0[1]), .io_z(t_dec19[1]));
HPC2Xor #(.d(1)) xor_dec20_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec24[1]), .io_y(r1[1]), .io_z(t_dec20[1]));
HPC2Xor #(.d(1)) xor_dec26_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec3[1]), .io_y(t_dec16[1]), .io_z(t_dec26[1]));
HPC2Xor #(.d(1)) xor_dec27_b1 (.control_clk(clk), .control_reset(rst), .io_x(t_dec1[1]), .io_y(r3[1]), .io_z(t_dec27[1]));

HPC2Xor #(.d(1)) xor_r0_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[9], masked_share_1[9]}), .io_y({masked_share_0[8], masked_share_1[8]}), .io_z(r0[1]));
HPC2Xor #(.d(1)) xor_r1_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[14], masked_share_1[14]}), .io_y({masked_share_0[9], masked_share_1[9]}), .io_z(r1[1]));
HPC2Xor #(.d(1)) xor_r2_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[13], masked_share_1[13]}), .io_y({masked_share_0[10], masked_share_1[10]}), .io_z(r2_temp[1]));
HPC2Not #(.d(1)) not_r2_b1 (.control_clk(clk), .control_reset(rst), .io_x(r2_temp[1]), .io_z(r2[1]));
HPC2Xor #(.d(1)) xor_r3_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[10], masked_share_1[10]}), .io_y({masked_share_0[9], masked_share_1[9]}), .io_z(r3_temp[1]));
HPC2Not #(.d(1)) not_r3_b1 (.control_clk(clk), .control_reset(rst), .io_x(r3_temp[1]), .io_z(r3[1]));
HPC2Xor #(.d(1)) xor_r4_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[13], masked_share_1[13]}), .io_y({masked_share_0[11], masked_share_1[11]}), .io_z(r4_temp[1]));
HPC2Not #(.d(1)) not_r4_b1 (.control_clk(clk), .control_reset(rst), .io_x(r4_temp[1]), .io_z(r4[1]));
HPC2Xor #(.d(1)) xor_y_b1 (.control_clk(clk), .control_reset(rst), .io_x({masked_share_0[15], masked_share_1[15]}), .io_y(r2[1]), .io_z(y[1]));

// Mode multiplexing to calculate either encryption or decryption
// Byte 0
assign d[0] = enc_mode ? {masked_share_0[0], masked_share_1[0]} : y[0];
assign t1[0] = enc_mode ? t_enc1[0] : t_dec1[0];
assign t2[0] = enc_mode ? t_enc2[0] : t_dec2[0];
assign t3[0] = enc_mode ? t_enc3[0] : t_dec3[0];
assign t4[0] = enc_mode ? t_enc4[0] : t_dec4[0];
assign t5[0] = enc_mode ? t_enc5[0] : 2'b00;
assign t6[0] = enc_mode ? t_enc6[0] : t_dec6[0];
assign t7[0] = enc_mode ? t_enc7[0] : 2'b00;
assign t8[0] = enc_mode ? t_enc8[0] : t_dec8[0];
assign t9[0] = enc_mode ? t_enc9[0] : t_dec9[0];
assign t10[0] = enc_mode ? t_enc10[0] : t_dec10[0];
assign t11[0] = enc_mode ? t_enc11[0] : 2'b00;
assign t12[0] = enc_mode ? t_enc12[0] : 2'b00;
assign t13[0] = enc_mode ? t_enc13[0] : t_dec13[0];
assign t14[0] = enc_mode ? t_enc14[0] : t_dec14[0];
assign t15[0] = enc_mode ? t_enc15[0] : t_dec15[0];
assign t16[0] = enc_mode ? t_enc16[0] : t_dec16[0];
assign t17[0] = enc_mode ? t_enc17[0] : t_dec17[0];
assign t18[0] = enc_mode ? t_enc18[0] : 2'b00;
assign t19[0] = enc_mode ? t_enc19[0] : t_dec19[0];
assign t20[0] = enc_mode ? t_enc20[0] : t_dec20[0];
assign t21[0] = enc_mode ? t_enc21[0] : 2'b00;
assign t22[0] = enc_mode ? t_enc22[0] : t_dec22[0];
assign t23[0] = enc_mode ? t_enc23[0] : t_dec23[0];
assign t24[0] = enc_mode ? t_enc24[0] : t_dec24[0];
assign t25[0] = enc_mode ? t_enc25[0] : t_dec25[0];
assign t26[0] = enc_mode ? t_enc26[0] : t_dec26[0];
assign t27[0] = enc_mode ? t_enc27[0] : t_dec27[0];

// Byte 1
assign d[1] = enc_mode ? {masked_share_0[8], masked_share_1[8]} : y[1];
assign t1[1] = enc_mode ? t_enc1[1] : t_dec1[1];
assign t2[1] = enc_mode ? t_enc2[1] : t_dec2[1];
assign t3[1] = enc_mode ? t_enc3[1] : t_dec3[1];
assign t4[1] = enc_mode ? t_enc4[1] : t_dec4[1];
assign t5[1] = enc_mode ? t_enc5[1] : 2'b00;
assign t6[1] = enc_mode ? t_enc6[1] : t_dec6[1];
assign t7[1] = enc_mode ? t_enc7[1] : 2'b00;
assign t8[1] = enc_mode ? t_enc8[1] : t_dec8[1];
assign t9[1] = enc_mode ? t_enc9[1] : t_dec9[1];
assign t10[1] = enc_mode ? t_enc10[1] : t_dec10[1];
assign t11[1] = enc_mode ? t_enc11[1] : 2'b00;
assign t12[1] = enc_mode ? t_enc12[1] : 2'b00;
assign t13[1] = enc_mode ? t_enc13[1] : t_dec13[1];
assign t14[1] = enc_mode ? t_enc14[1] : t_dec14[1];
assign t15[1] = enc_mode ? t_enc15[1] : t_dec15[1];
assign t16[1] = enc_mode ? t_enc16[1] : t_dec16[1];
assign t17[1] = enc_mode ? t_enc17[1] : t_dec17[1];
assign t18[1] = enc_mode ? t_enc18[1] : 2'b00;
assign t19[1] = enc_mode ? t_enc19[1] : t_dec19[1];
assign t20[1] = enc_mode ? t_enc20[1] : t_dec20[1];
assign t21[1] = enc_mode ? t_enc21[1] : 2'b00;
assign t22[1] = enc_mode ? t_enc22[1] : t_dec22[1];
assign t23[1] = enc_mode ? t_enc23[1] : t_dec23[1];
assign t24[1] = enc_mode ? t_enc24[1] : t_dec24[1];
assign t25[1] = enc_mode ? t_enc25[1] : t_dec25[1];
assign t26[1] = enc_mode ? t_enc26[1] : t_dec26[1];
assign t27[1] = enc_mode ? t_enc27[1] : t_dec27[1];

always @(posedge clk) begin

    // Save m's for pipeline
    m21_pipe[0][0] <= m21[0];
    m21_pipe[1][0] <= m21_pipe[0][0];
    m21_pipe[2][0] <= m21_pipe[1][0];
    m21_pipe[3][0] <= m21_pipe[2][0];
    m23_pipe[0][0] <= m23[0];
    m23_pipe[1][0] <= m23_pipe[0][0];
    m23_pipe[2][0] <= m23_pipe[1][0];
    m23_pipe[3][0] <= m23_pipe[2][0];
    m24_pipe[0][0] <= m24[0];
    m24_pipe[1][0] <= m24_pipe[0][0];
    m27_pipe[0][0] <= m27[0];
    m27_pipe[1][0] <= m27_pipe[0][0];
    m33_pipe[0][0] <= m33[0];
    m33_pipe[1][0] <= m33_pipe[0][0];
    m36_pipe[0][0] <= m36[0];
    m36_pipe[1][0] <= m36_pipe[0][0];


    // Save t values for pipeline
    d_pipe[0][0] <= d[0];
    d_pipe[1][0] <= d_pipe[0][0];
    d_pipe[2][0] <= d_pipe[1][0];
    d_pipe[3][0] <= d_pipe[2][0];
    d_pipe[4][0] <= d_pipe[3][0];
    d_pipe[5][0] <= d_pipe[4][0];
    t1_pipe[0][0] <= t1[0];
    t1_pipe[1][0] <= t1_pipe[0][0];
    t1_pipe[2][0] <= t1_pipe[1][0];
    t1_pipe[3][0] <= t1_pipe[2][0];
    t1_pipe[4][0] <= t1_pipe[3][0];
    t1_pipe[5][0] <= t1_pipe[4][0];
    t2_pipe[0][0] <= t2[0];
    t2_pipe[1][0] <= t2_pipe[0][0];
    t2_pipe[2][0] <= t2_pipe[1][0];
    t2_pipe[3][0] <= t2_pipe[2][0];
    t2_pipe[4][0] <= t2_pipe[3][0];
    t2_pipe[5][0] <= t2_pipe[4][0];
    t3_pipe[0][0] <= t3[0];
    t3_pipe[1][0] <= t3_pipe[0][0];
    t3_pipe[2][0] <= t3_pipe[1][0];
    t3_pipe[3][0] <= t3_pipe[2][0];
    t3_pipe[4][0] <= t3_pipe[3][0];
    t3_pipe[5][0] <= t3_pipe[4][0];
    t4_pipe[0][0] <= t4[0];
    t4_pipe[1][0] <= t4_pipe[0][0];
    t4_pipe[2][0] <= t4_pipe[1][0];
    t4_pipe[3][0] <= t4_pipe[2][0];
    t4_pipe[4][0] <= t4_pipe[3][0];
    t4_pipe[5][0] <= t4_pipe[4][0];
    t6_pipe[0][0] <= t6[0];
    t6_pipe[1][0] <= t6_pipe[0][0];
    t6_pipe[2][0] <= t6_pipe[1][0];
    t6_pipe[3][0] <= t6_pipe[2][0];
    t6_pipe[4][0] <= t6_pipe[3][0];
    t6_pipe[5][0] <= t6_pipe[4][0];
    t8_pipe[0][0] <= t8[0];
    t8_pipe[1][0] <= t8_pipe[0][0];
    t8_pipe[2][0] <= t8_pipe[1][0];
    t8_pipe[3][0] <= t8_pipe[2][0];
    t8_pipe[4][0] <= t8_pipe[3][0];
    t8_pipe[5][0] <= t8_pipe[4][0];
    t9_pipe[0][0] <= t9[0];
    t9_pipe[1][0] <= t9_pipe[0][0];
    t9_pipe[2][0] <= t9_pipe[1][0];
    t9_pipe[3][0] <= t9_pipe[2][0];
    t9_pipe[4][0] <= t9_pipe[3][0];
    t9_pipe[5][0] <= t9_pipe[4][0];
    t10_pipe[0][0] <= t10[0];
    t10_pipe[1][0] <= t10_pipe[0][0];
    t10_pipe[2][0] <= t10_pipe[1][0];
    t10_pipe[3][0] <= t10_pipe[2][0];
    t10_pipe[4][0] <= t10_pipe[3][0];
    t10_pipe[5][0] <= t10_pipe[4][0];
    t13_pipe[0][0] <= t13[0];
    t13_pipe[1][0] <= t13_pipe[0][0];
    t13_pipe[2][0] <= t13_pipe[1][0];
    t13_pipe[3][0] <= t13_pipe[2][0];
    t13_pipe[4][0] <= t13_pipe[3][0];
    t13_pipe[5][0] <= t13_pipe[4][0];
    t14_pipe[0][0] <= t14[0];
    t14_pipe[1][0] <= t14_pipe[0][0];
    t15_pipe[0][0] <= t15[0];
    t15_pipe[1][0] <= t15_pipe[0][0];
    t15_pipe[2][0] <= t15_pipe[1][0];
    t15_pipe[3][0] <= t15_pipe[2][0];
    t15_pipe[4][0] <= t15_pipe[3][0];
    t15_pipe[5][0] <= t15_pipe[4][0];
    t16_pipe[0][0] <= t16[0];
    t16_pipe[1][0] <= t16_pipe[0][0];
    t16_pipe[2][0] <= t16_pipe[1][0];
    t16_pipe[3][0] <= t16_pipe[2][0];
    t16_pipe[4][0] <= t16_pipe[3][0];
    t16_pipe[5][0] <= t16_pipe[4][0];
    t17_pipe[0][0] <= t17[0];
    t17_pipe[1][0] <= t17_pipe[0][0];
    t17_pipe[2][0] <= t17_pipe[1][0];
    t17_pipe[3][0] <= t17_pipe[2][0];
    t17_pipe[4][0] <= t17_pipe[3][0];
    t17_pipe[5][0] <= t17_pipe[4][0];
    t19_pipe[0][0] <= t19[0];
    t19_pipe[1][0] <= t19_pipe[0][0];
    t19_pipe[2][0] <= t19_pipe[1][0];
    t19_pipe[3][0] <= t19_pipe[2][0];
    t19_pipe[4][0] <= t19_pipe[3][0];
    t19_pipe[5][0] <= t19_pipe[4][0];
    t20_pipe[0][0] <= t20[0];
    t20_pipe[1][0] <= t20_pipe[0][0];
    t20_pipe[2][0] <= t20_pipe[1][0];
    t20_pipe[3][0] <= t20_pipe[2][0];
    t20_pipe[4][0] <= t20_pipe[3][0];
    t20_pipe[5][0] <= t20_pipe[4][0];
    t22_pipe[0][0] <= t22[0];
    t22_pipe[1][0] <= t22_pipe[0][0];
    t22_pipe[2][0] <= t22_pipe[1][0];
    t22_pipe[3][0] <= t22_pipe[2][0];
    t22_pipe[4][0] <= t22_pipe[3][0];
    t22_pipe[5][0] <= t22_pipe[4][0];
    t23_pipe[0][0] <= t23[0];
    t23_pipe[1][0] <= t23_pipe[0][0];
    t23_pipe[2][0] <= t23_pipe[1][0];
    t23_pipe[3][0] <= t23_pipe[2][0];
    t23_pipe[4][0] <= t23_pipe[3][0];
    t23_pipe[5][0] <= t23_pipe[4][0];
    t24_pipe[0][0] <= t24[0];
    t24_pipe[1][0] <= t24_pipe[0][0];
    t25_pipe[0][0] <= t25[0];
    t25_pipe[1][0] <= t25_pipe[0][0];
    t26_pipe[0][0] <= t26[0];
    t26_pipe[1][0] <= t26_pipe[0][0];
    t27_pipe[0][0] <= t27[0];
    t27_pipe[1][0] <= t27_pipe[0][0];
    t27_pipe[2][0] <= t27_pipe[1][0];
    t27_pipe[3][0] <= t27_pipe[2][0];
    t27_pipe[4][0] <= t27_pipe[3][0];
    t27_pipe[5][0] <= t27_pipe[4][0];

    //do the same for second byte
    m21_pipe[0][1] <= m21[1];
    m21_pipe[1][1] <= m21_pipe[0][1];
    m21_pipe[2][1] <= m21_pipe[1][1];
    m21_pipe[3][1] <= m21_pipe[2][1];
    m23_pipe[0][1] <= m23[1];
    m23_pipe[1][1] <= m23_pipe[0][1];
    m23_pipe[2][1] <= m23_pipe[1][1];
    m23_pipe[3][1] <= m23_pipe[2][1];
    m24_pipe[0][1] <= m24[1];
    m24_pipe[1][1] <= m24_pipe[0][1];
    m27_pipe[0][1] <= m27[1];
    m27_pipe[1][1] <= m27_pipe[0][1];
    m33_pipe[0][1] <= m33[1];
    m33_pipe[1][1] <= m33_pipe[0][1];
    m36_pipe[0][1] <= m36[1];
    m36_pipe[1][1] <= m36_pipe[0][1];

    d_pipe[0][1] <= d[1];
    d_pipe[1][1] <= d_pipe[0][1];
    d_pipe[2][1] <= d_pipe[1][1];
    d_pipe[3][1] <= d_pipe[2][1];
    d_pipe[4][1] <= d_pipe[3][1];
    d_pipe[5][1] <= d_pipe[4][1];
    t1_pipe[0][1] <= t1[1];
    t1_pipe[1][1] <= t1_pipe[0][1];
    t1_pipe[2][1] <= t1_pipe[1][1];
    t1_pipe[3][1] <= t1_pipe[2][1];
    t1_pipe[4][1] <= t1_pipe[3][1];
    t1_pipe[5][1] <= t1_pipe[4][1];
    t2_pipe[0][1] <= t2[1];
    t2_pipe[1][1] <= t2_pipe[0][1];
    t2_pipe[2][1] <= t2_pipe[1][1];
    t2_pipe[3][1] <= t2_pipe[2][1];
    t2_pipe[4][1] <= t2_pipe[3][1];
    t2_pipe[5][1] <= t2_pipe[4][1];
    t3_pipe[0][1] <= t3[1];
    t3_pipe[1][1] <= t3_pipe[0][1];
    t3_pipe[2][1] <= t3_pipe[1][1];
    t3_pipe[3][1] <= t3_pipe[2][1];
    t3_pipe[4][1] <= t3_pipe[3][1];
    t3_pipe[5][1] <= t3_pipe[4][1];
    t4_pipe[0][1] <= t4[1];
    t4_pipe[1][1] <= t4_pipe[0][1];
    t4_pipe[2][1] <= t4_pipe[1][1];
    t4_pipe[3][1] <= t4_pipe[2][1];
    t4_pipe[4][1] <= t4_pipe[3][1];
    t4_pipe[5][1] <= t4_pipe[4][1];
    t6_pipe[0][1] <= t6[1];
    t6_pipe[1][1] <= t6_pipe[0][1];
    t6_pipe[2][1] <= t6_pipe[1][1];
    t6_pipe[3][1] <= t6_pipe[2][1];
    t6_pipe[4][1] <= t6_pipe[3][1];
    t6_pipe[5][1] <= t6_pipe[4][1];
    t8_pipe[0][1] <= t8[1];
    t8_pipe[1][1] <= t8_pipe[0][1];
    t8_pipe[2][1] <= t8_pipe[1][1];
    t8_pipe[3][1] <= t8_pipe[2][1];
    t8_pipe[4][1] <= t8_pipe[3][1];
    t8_pipe[5][1] <= t8_pipe[4][1];
    t9_pipe[0][1] <= t9[1];
    t9_pipe[1][1] <= t9_pipe[0][1];
    t9_pipe[2][1] <= t9_pipe[1][1];
    t9_pipe[3][1] <= t9_pipe[2][1];
    t9_pipe[4][1] <= t9_pipe[3][1];
    t9_pipe[5][1] <= t9_pipe[4][1];
    t10_pipe[0][1] <= t10[1];
    t10_pipe[1][1] <= t10_pipe[0][1];
    t10_pipe[2][1] <= t10_pipe[1][1];
    t10_pipe[3][1] <= t10_pipe[2][1];
    t10_pipe[4][1] <= t10_pipe[3][1];
    t10_pipe[5][1] <= t10_pipe[4][1];
    t13_pipe[0][1] <= t13[1];
    t13_pipe[1][1] <= t13_pipe[0][1];
    t13_pipe[2][1] <= t13_pipe[1][1];
    t13_pipe[3][1] <= t13_pipe[2][1];
    t13_pipe[4][1] <= t13_pipe[3][1];
    t13_pipe[5][1] <= t13_pipe[4][1];
    t14_pipe[0][1] <= t14[1];
    t14_pipe[1][1] <= t14_pipe[0][1];
    t15_pipe[0][1] <= t15[1];
    t15_pipe[1][1] <= t15_pipe[0][1];
    t15_pipe[2][1] <= t15_pipe[1][1];
    t15_pipe[3][1] <= t15_pipe[2][1];
    t15_pipe[4][1] <= t15_pipe[3][1];
    t15_pipe[5][1] <= t15_pipe[4][1];
    t16_pipe[0][1] <= t16[1];
    t16_pipe[1][1] <= t16_pipe[0][1];
    t16_pipe[2][1] <= t16_pipe[1][1];
    t16_pipe[3][1] <= t16_pipe[2][1];
    t16_pipe[4][1] <= t16_pipe[3][1];
    t16_pipe[5][1] <= t16_pipe[4][1];
    t17_pipe[0][1] <= t17[1];
    t17_pipe[1][1] <= t17_pipe[0][1];
    t17_pipe[2][1] <= t17_pipe[1][1];
    t17_pipe[3][1] <= t17_pipe[2][1];
    t17_pipe[4][1] <= t17_pipe[3][1];
    t17_pipe[5][1] <= t17_pipe[4][1];
    t19_pipe[0][1] <= t19[1];
    t19_pipe[1][1] <= t19_pipe[0][1];
    t19_pipe[2][1] <= t19_pipe[1][1];
    t19_pipe[3][1] <= t19_pipe[2][1];
    t19_pipe[4][1] <= t19_pipe[3][1];
    t19_pipe[5][1] <= t19_pipe[4][1];
    t20_pipe[0][1] <= t20[1];
    t20_pipe[1][1] <= t20_pipe[0][1];
    t20_pipe[2][1] <= t20_pipe[1][1];
    t20_pipe[3][1] <= t20_pipe[2][1];
    t20_pipe[4][1] <= t20_pipe[3][1];
    t20_pipe[5][1] <= t20_pipe[4][1];
    t22_pipe[0][1] <= t22[1];
    t22_pipe[1][1] <= t22_pipe[0][1];
    t22_pipe[2][1] <= t22_pipe[1][1];
    t22_pipe[3][1] <= t22_pipe[2][1];
    t22_pipe[4][1] <= t22_pipe[3][1];
    t22_pipe[5][1] <= t22_pipe[4][1];
    t23_pipe[0][1] <= t23[1];
    t23_pipe[1][1] <= t23_pipe[0][1];
    t23_pipe[2][1] <= t23_pipe[1][1];
    t23_pipe[3][1] <= t23_pipe[2][1];
    t23_pipe[4][1] <= t23_pipe[3][1];
    t23_pipe[5][1] <= t23_pipe[4][1];
    t24_pipe[0][1] <= t24[1];
    t24_pipe[1][1] <= t24_pipe[0][1];
    t25_pipe[0][1] <= t25[1];
    t25_pipe[1][1] <= t25_pipe[0][1];
    t26_pipe[0][1] <= t26[1];
    t26_pipe[1][1] <= t26_pipe[0][1];
    t27_pipe[0][1] <= t27[1];
    t27_pipe[1][1] <= t27_pipe[0][1];
    t27_pipe[2][1] <= t27_pipe[1][1];
    t27_pipe[3][1] <= t27_pipe[2][1];
    t27_pipe[4][1] <= t27_pipe[3][1];
    t27_pipe[5][1] <= t27_pipe[4][1];
end

// M1 = T13 x T6
HPC2And #(.d(1)) and_inst_0_b0 (.control_clk(clk), .control_reset(rst), .io_x(t13[0]), .io_y(t6[0]), .io_r(random[0]), .io_z(m1[0]));
// M2 = T23 x T8
HPC2And #(.d(1)) and_inst_1_b0 (.control_clk(clk), .control_reset(rst), .io_x(t23[0]), .io_y(t8[0]), .io_r(random[1]), .io_z(m2[0]));
// M3 = T14 + M1
HPC2Xor #(.d(1)) xor_m3_b0 (.control_clk(clk), .control_reset(rst), .io_x(t14_pipe[1][0]), .io_y(m1[0]), .io_z(m3[0]));
// M4 = T19 x D
HPC2And #(.d(1)) and_inst_2_b0 (.control_clk(clk), .control_reset(rst), .io_x(t19[0]), .io_y(d[0]), .io_r(random[2]), .io_z(m4[0]));
// M5 = M4 + M1
HPC2Xor #(.d(1)) xor_m5_b0 (.control_clk(clk), .control_reset(rst), .io_x(m4[0]), .io_y(m1[0]), .io_z(m5[0]));
// M6 = T3 x T16
HPC2And #(.d(1)) and_inst_3_b0 (.control_clk(clk), .control_reset(rst), .io_x(t3[0]), .io_y(t16[0]), .io_r(random[3]), .io_z(m6[0]));
// M7 = T22 x T9
HPC2And #(.d(1)) and_inst_4_b0 (.control_clk(clk), .control_reset(rst), .io_x(t22[0]), .io_y(t9[0]), .io_r(random[4]), .io_z(m7[0]));
// M8 = T26 + M6
HPC2Xor #(.d(1)) xor_m8_b0 (.control_clk(clk), .control_reset(rst), .io_x(t26_pipe[1][0]), .io_y(m6[0]), .io_z(m8[0]));
// M9 = T20 x T17
HPC2And #(.d(1)) and_inst_5_b0 (.control_clk(clk), .control_reset(rst), .io_x(t20[0]), .io_y(t17[0]), .io_r(random[5]), .io_z(m9[0]));
// M10 = M9 + M6
HPC2Xor #(.d(1)) xor_m10_b0 (.control_clk(clk), .control_reset(rst), .io_x(m9[0]), .io_y(m6[0]), .io_z(m10[0]));
// M11 = T1 x T15
HPC2And #(.d(1)) and_inst_6_b0 (.control_clk(clk), .control_reset(rst), .io_x(t1[0]), .io_y(t15[0]), .io_r(random[6]), .io_z(m11[0]));
// M12 = T4 x T27
HPC2And #(.d(1)) and_inst_7_b0 (.control_clk(clk), .control_reset(rst), .io_x(t4[0]), .io_y(t27[0]), .io_r(random[7]), .io_z(m12[0]));
// M13 = M12 + M11
HPC2Xor #(.d(1)) xor_m13_b0 (.control_clk(clk), .control_reset(rst), .io_x(m12[0]), .io_y(m11[0]), .io_z(m13[0]));
// M14 = T2 x T10
HPC2And #(.d(1)) and_inst_8_b0 (.control_clk(clk), .control_reset(rst), .io_x(t2[0]), .io_y(t10[0]), .io_r(random[8]), .io_z(m14[0]));
// M15 = M14 + M11
HPC2Xor #(.d(1)) xor_m15_b0 (.control_clk(clk), .control_reset(rst), .io_x(m14[0]), .io_y(m11[0]), .io_z(m15[0]));
// M16 = M3 + M2
HPC2Xor #(.d(1)) xor_m16_b0 (.control_clk(clk), .control_reset(rst), .io_x(m3[0]), .io_y(m2[0]), .io_z(m16[0]));
// M17 = M5 + T24
HPC2Xor #(.d(1)) xor_m17_b0 (.control_clk(clk), .control_reset(rst), .io_x(m5[0]), .io_y(t24_pipe[1][0]), .io_z(m17[0]));
// M18 = M8 + M7
HPC2Xor #(.d(1)) xor_m18_b0 (.control_clk(clk), .control_reset(rst), .io_x(m8[0]), .io_y(m7[0]), .io_z(m18[0]));
// M19 = M10 + M15
HPC2Xor #(.d(1)) xor_m19_b0 (.control_clk(clk), .control_reset(rst), .io_x(m10[0]), .io_y(m15[0]), .io_z(m19[0]));
// M20 = M16 + M13
HPC2Xor #(.d(1)) xor_m20_b0 (.control_clk(clk), .control_reset(rst), .io_x(m16[0]), .io_y(m13[0]), .io_z(m20[0]));
// M21 = M17 + M15
HPC2Xor #(.d(1)) xor_m21_b0 (.control_clk(clk), .control_reset(rst), .io_x(m17[0]), .io_y(m15[0]), .io_z(m21[0]));
// M22 = M18 + M13
HPC2Xor #(.d(1)) xor_m22_b0 (.control_clk(clk), .control_reset(rst), .io_x(m18[0]), .io_y(m13[0]), .io_z(m22[0]));
// M23 = M19 + T25
HPC2Xor #(.d(1)) xor_m23_b0 (.control_clk(clk), .control_reset(rst), .io_x(m19[0]), .io_y(t25_pipe[1][0]), .io_z(m23[0]));
// M24 = M22 + M23
HPC2Xor #(.d(1)) xor_m24_b0 (.control_clk(clk), .control_reset(rst), .io_x(m22[0]), .io_y(m23[0]), .io_z(m24[0]));
// M27 = M20 + M21
HPC2Xor #(.d(1)) xor_m27_b0 (.control_clk(clk), .control_reset(rst), .io_x(m20[0]), .io_y(m21[0]), .io_z(m27[0]));

// Stage 2:
// M25 = M22 x M20
HPC2And #(.d(1)) and_inst_9_b0 (.control_clk(clk), .control_reset(rst), .io_x(m22[0]), .io_y(m20[0]), .io_r(random[9]), .io_z(m25[0]));
// M26 = M21 + M25
HPC2Xor #(.d(1)) xor_m26_b0 (.control_clk(clk), .control_reset(rst), .io_x(m21_pipe[1][0]), .io_y(m25[0]), .io_z(m26[0]));
// M28 = M23 + M25
HPC2Xor #(.d(1)) xor_m28_b0 (.control_clk(clk), .control_reset(rst), .io_x(m23_pipe[1][0]), .io_y(m25[0]), .io_z(m28[0]));
// M31 = M20 x M23
HPC2And #(.d(1)) and_inst_12_b0 (.control_clk(clk), .control_reset(rst), .io_x(m20[0]), .io_y(m23[0]), .io_r(random[10]), .io_z(m31[0]));
// M33 = M27 + M25
HPC2Xor #(.d(1)) xor_m33_b0 (.control_clk(clk), .control_reset(rst), .io_x(m27_pipe[1][0]), .io_y(m25[0]), .io_z(m33[0]));
// M34 = M21 x M22
HPC2And #(.d(1)) and_inst_14_b0 (.control_clk(clk), .control_reset(rst), .io_x(m21[0]), .io_y(m22[0]), .io_r(random[11]), .io_z(m34[0]));
// M36 = M24 + M25
HPC2Xor #(.d(1)) xor_m36_b0 (.control_clk(clk), .control_reset(rst), .io_x(m24_pipe[1][0]), .io_y(m25[0]), .io_z(m36[0]));

// Stage 3:
// M29 = M28 x M27
HPC2And #(.d(1)) and_inst_10_b0 (.control_clk(clk), .control_reset(rst), .io_x(m28[0]), .io_y(m27_pipe[1][0]), .io_r(random[12]), .io_z(m29[0]));
// M30 = M26 x M24
HPC2And #(.d(1)) and_inst_11_b0 (.control_clk(clk), .control_reset(rst), .io_x(m26[0]), .io_y(m24_pipe[1][0]), .io_r(random[13]), .io_z(m30[0]));
// M32 = M27 x M31
HPC2And #(.d(1)) and_inst_13_b0 (.control_clk(clk), .control_reset(rst), .io_x(m27_pipe[1][0]), .io_y(m31[0]), .io_r(random[14]), .io_z(m32[0]));
// M35 = M24 x M34
HPC2And #(.d(1)) and_inst_15_b0 (.control_clk(clk), .control_reset(rst), .io_x(m24_pipe[1][0]), .io_y(m34[0]), .io_r(random[15]), .io_z(m35[0]));
// M37 = M21 + M29
HPC2Xor #(.d(1)) xor_m37_b0 (.control_clk(clk), .control_reset(rst), .io_x(m21_pipe[3][0]), .io_y(m29[0]), .io_z(m37[0]));
// M38 = M32 + M33
HPC2Xor #(.d(1)) xor_m38_b0 (.control_clk(clk), .control_reset(rst), .io_x(m32[0]), .io_y(m33_pipe[1][0]), .io_z(m38[0]));
// M39 = M23 + M30
HPC2Xor #(.d(1)) xor_m39_b0 (.control_clk(clk), .control_reset(rst), .io_x(m23_pipe[3][0]), .io_y(m30[0]), .io_z(m39[0]));
// M40 = M35 + M36
HPC2Xor #(.d(1)) xor_m40_b0 (.control_clk(clk), .control_reset(rst), .io_x(m35[0]), .io_y(m36_pipe[1][0]), .io_z(m40[0]));
// M41 = M38 + M40
HPC2Xor #(.d(1)) xor_m41_b0 (.control_clk(clk), .control_reset(rst), .io_x(m38[0]), .io_y(m40[0]), .io_z(m41[0]));
// M42 = M37 + M39
HPC2Xor #(.d(1)) xor_m42_b0 (.control_clk(clk), .control_reset(rst), .io_x(m37[0]), .io_y(m39[0]), .io_z(m42[0]));
// M43 = M37 + M38
HPC2Xor #(.d(1)) xor_m43_b0 (.control_clk(clk), .control_reset(rst), .io_x(m37[0]), .io_y(m38[0]), .io_z(m43[0]));
// M44 = M39 + M40
HPC2Xor #(.d(1)) xor_m44_b0 (.control_clk(clk), .control_reset(rst), .io_x(m39[0]), .io_y(m40[0]), .io_z(m44[0]));
// M45 = M42 + M41
HPC2Xor #(.d(1)) xor_m45_b0 (.control_clk(clk), .control_reset(rst), .io_x(m42[0]), .io_y(m41[0]), .io_z(m45[0]));

//Stage 4:
// M46 = M44 x T6
HPC2And #(.d(1)) and_inst_16_b0 (.control_clk(clk), .control_reset(rst), .io_x(m44[0]), .io_y(t6_pipe[5][0]), .io_r(random[16]), .io_z(m46[0]));
// M47 = M40 x T8
HPC2And #(.d(1)) and_inst_17_b0 (.control_clk(clk), .control_reset(rst), .io_x(m40[0]), .io_y(t8_pipe[5][0]), .io_r(random[17]), .io_z(m47[0]));
// M48 = M39 x D
HPC2And #(.d(1)) and_inst_18_b0 (.control_clk(clk), .control_reset(rst), .io_x(m39[0]), .io_y(d_pipe[5][0]), .io_r(random[18]), .io_z(m48[0]));
// M49 = M43 x T16
HPC2And #(.d(1)) and_inst_19_b0 (.control_clk(clk), .control_reset(rst), .io_x(m43[0]), .io_y(t16_pipe[5][0]), .io_r(random[19]), .io_z(m49[0]));
// M50 = M38 x T9
HPC2And #(.d(1)) and_inst_20_b0 (.control_clk(clk), .control_reset(rst), .io_x(m38[0]), .io_y(t9_pipe[5][0]), .io_r(random[20]), .io_z(m50[0]));
// M51 = M37 x T17
HPC2And #(.d(1)) and_inst_21_b0 (.control_clk(clk), .control_reset(rst), .io_x(m37[0]), .io_y(t17_pipe[5][0]), .io_r(random[21]), .io_z(m51[0]));
// M52 = M42 x T15
HPC2And #(.d(1)) and_inst_22_b0 (.control_clk(clk), .control_reset(rst), .io_x(m42[0]), .io_y(t15_pipe[5][0]), .io_r(random[22]), .io_z(m52[0]));
// M53 = M45 x T27
HPC2And #(.d(1)) and_inst_23_b0 (.control_clk(clk), .control_reset(rst), .io_x(m45[0]), .io_y(t27_pipe[5][0]), .io_r(random[23]), .io_z(m53[0]));
// M54 = M41 x T10
HPC2And #(.d(1)) and_inst_24_b0 (.control_clk(clk), .control_reset(rst), .io_x(m41[0]), .io_y(t10_pipe[5][0]), .io_r(random[24]), .io_z(m54[0]));
// M55 = M44 x T13
HPC2And #(.d(1)) and_inst_25_b0 (.control_clk(clk), .control_reset(rst), .io_x(m44[0]), .io_y(t13_pipe[5][0]), .io_r(random[25]), .io_z(m55[0]));
// M56 = M40 x T23
HPC2And #(.d(1)) and_inst_26_b0 (.control_clk(clk), .control_reset(rst), .io_x(m40[0]), .io_y(t23_pipe[5][0]), .io_r(random[26]), .io_z(m56[0]));
// M57 = M39 x T19
HPC2And #(.d(1)) and_inst_27_b0 (.control_clk(clk), .control_reset(rst), .io_x(m39[0]), .io_y(t19_pipe[5][0]), .io_r(random[27]), .io_z(m57[0]));
// M58 = M43 x T3
HPC2And #(.d(1)) and_inst_28_b0 (.control_clk(clk), .control_reset(rst), .io_x(m43[0]), .io_y(t3_pipe[5][0]), .io_r(random[28]), .io_z(m58[0]));
// M59 = M38 x T22
HPC2And #(.d(1)) and_inst_29_b0 (.control_clk(clk), .control_reset(rst), .io_x(m38[0]), .io_y(t22_pipe[5][0]), .io_r(random[29]), .io_z(m59[0]));
// M60 = M37 x T20
HPC2And #(.d(1)) and_inst_30_b0 (.control_clk(clk), .control_reset(rst), .io_x(m37[0]), .io_y(t20_pipe[5][0]), .io_r(random[30]), .io_z(m60[0]));
// M61 = M42 x T1
HPC2And #(.d(1)) and_inst_31_b0 (.control_clk(clk), .control_reset(rst), .io_x(m42[0]), .io_y(t1_pipe[5][0]), .io_r(random[31]), .io_z(m61[0]));
// M62 = M45 x T4
HPC2And #(.d(1)) and_inst_32_b0 (.control_clk(clk), .control_reset(rst), .io_x(m45[0]), .io_y(t4_pipe[5][0]), .io_r(random[32]), .io_z(m62[0]));
// M63 = M41 x T2
HPC2And #(.d(1)) and_inst_33_b0 (.control_clk(clk), .control_reset(rst), .io_x(m41[0]), .io_y(t2_pipe[5][0]), .io_r(random[33]), .io_z(m63[0]));
 
// Byte 1 : Same operations as above
// M1 = T13 x T6
HPC2And #(.d(1)) and_inst_0_b1 (.control_clk(clk), .control_reset(rst), .io_x(t13[1]), .io_y(t6[1]), .io_r(random[34]), .io_z(m1[1]));
// M2 = T23 x T8
HPC2And #(.d(1)) and_inst_1_b1 (.control_clk(clk), .control_reset(rst), .io_x(t23[1]), .io_y(t8[1]), .io_r(random[35]), .io_z(m2[1]));
// M3 = T14 + M1
HPC2Xor #(.d(1)) xor_m3_b1 (.control_clk(clk), .control_reset(rst), .io_x(t14_pipe[1][1]), .io_y(m1[1]), .io_z(m3[1]));
// M4 = T19 x D
HPC2And #(.d(1)) and_inst_2_b1 (.control_clk(clk), .control_reset(rst), .io_x(t19[1]), .io_y(d[1]), .io_r(random[36]), .io_z(m4[1]));
// M5 = M4 + M1
HPC2Xor #(.d(1)) xor_m5_b1 (.control_clk(clk), .control_reset(rst), .io_x(m4[1]), .io_y(m1[1]), .io_z(m5[1]));
// M6 = T3 x T16
HPC2And #(.d(1)) and_inst_3_b1 (.control_clk(clk), .control_reset(rst), .io_x(t3[1]), .io_y(t16[1]), .io_r(random[37]), .io_z(m6[1]));
// M7 = T22 x T9
HPC2And #(.d(1)) and_inst_4_b1 (.control_clk(clk), .control_reset(rst), .io_x(t22[1]), .io_y(t9[1]), .io_r(random[38]), .io_z(m7[1]));
// M8 = T26 + M6
HPC2Xor #(.d(1)) xor_m8_b1 (.control_clk(clk), .control_reset(rst), .io_x(t26_pipe[1][1]), .io_y(m6[1]), .io_z(m8[1]));
// M9 = T20 x T17
HPC2And #(.d(1)) and_inst_5_b1 (.control_clk(clk), .control_reset(rst), .io_x(t20[1]), .io_y(t17[1]), .io_r(random[39]), .io_z(m9[1]));
// M10 = M9 + M6
HPC2Xor #(.d(1)) xor_m10_b1 (.control_clk(clk), .control_reset(rst), .io_x(m9[1]), .io_y(m6[1]), .io_z(m10[1]));
// M11 = T1 x T15
HPC2And #(.d(1)) and_inst_6_b1 (.control_clk(clk), .control_reset(rst), .io_x(t1[1]), .io_y(t15[1]), .io_r(random[40]), .io_z(m11[1]));
// M12 = T4 x T27
HPC2And #(.d(1)) and_inst_7_b1 (.control_clk(clk), .control_reset(rst), .io_x(t4[1]), .io_y(t27[1]), .io_r(random[41]), .io_z(m12[1]));
// M13 = M12 + M11
HPC2Xor #(.d(1)) xor_m13_b1 (.control_clk(clk), .control_reset(rst), .io_x(m12[1]), .io_y(m11[1]), .io_z(m13[1]));
// M14 = T2 x T10
HPC2And #(.d(1)) and_inst_8_b1 (.control_clk(clk), .control_reset(rst), .io_x(t2[1]), .io_y(t10[1]), .io_r(random[42]), .io_z(m14[1]));
// M15 = M14 + M11
HPC2Xor #(.d(1)) xor_m15_b1 (.control_clk(clk), .control_reset(rst), .io_x(m14[1]), .io_y(m11[1]), .io_z(m15[1]));
// M16 = M3 + M2
HPC2Xor #(.d(1)) xor_m16_b1 (.control_clk(clk), .control_reset(rst), .io_x(m3[1]), .io_y(m2[1]), .io_z(m16[1]));
// M17 = M5 + T24
HPC2Xor #(.d(1)) xor_m17_b1 (.control_clk(clk), .control_reset(rst), .io_x(m5[1]), .io_y(t24_pipe[1][1]), .io_z(m17[1]));
// M18 = M8 + M7
HPC2Xor #(.d(1)) xor_m18_b1 (.control_clk(clk), .control_reset(rst), .io_x(m8[1]), .io_y(m7[1]), .io_z(m18[1]));
// M19 = M10 + M15
HPC2Xor #(.d(1)) xor_m19_b1 (.control_clk(clk), .control_reset(rst), .io_x(m10[1]), .io_y(m15[1]), .io_z(m19[1]));
// M20 = M16 + M13
HPC2Xor #(.d(1)) xor_m20_b1 (.control_clk(clk), .control_reset(rst), .io_x(m16[1]), .io_y(m13[1]), .io_z(m20[1]));
// M21 = M17 + M15
HPC2Xor #(.d(1)) xor_m21_b1 (.control_clk(clk), .control_reset(rst), .io_x(m17[1]), .io_y(m15[1]), .io_z(m21[1]));
// M22 = M18 + M13
HPC2Xor #(.d(1)) xor_m22_b1 (.control_clk(clk), .control_reset(rst), .io_x(m18[1]), .io_y(m13[1]), .io_z(m22[1]));
// M23 = M19 + T25
HPC2Xor #(.d(1)) xor_m23_b1 (.control_clk(clk), .control_reset(rst), .io_x(m19[1]), .io_y(t25_pipe[1][1]), .io_z(m23[1]));
// M24 = M22 + M23
HPC2Xor #(.d(1)) xor_m24_b1 (.control_clk(clk), .control_reset(rst), .io_x(m22[1]), .io_y(m23[1]), .io_z(m24[1]));
// M27 = M20 + M21
HPC2Xor #(.d(1)) xor_m27_b1 (.control_clk(clk), .control_reset(rst), .io_x(m20[1]), .io_y(m21[1]), .io_z(m27[1]));

// Stage 2:
// M25 = M22 x M20
HPC2And #(.d(1)) and_inst_9_b1 (.control_clk(clk), .control_reset(rst), .io_x(m22[1]), .io_y(m20[1]), .io_r(random[43]), .io_z(m25[1]));
// M26 = M21 + M25
HPC2Xor #(.d(1)) xor_m26_b1 (.control_clk(clk), .control_reset(rst), .io_x(m21_pipe[1][1]), .io_y(m25[1]), .io_z(m26[1]));
// M28 = M23 + M25
HPC2Xor #(.d(1)) xor_m28_b1 (.control_clk(clk), .control_reset(rst), .io_x(m23_pipe[1][1]), .io_y(m25[1]), .io_z(m28[1]));
// M31 = M20 x M23
HPC2And #(.d(1)) and_inst_12_b1 (.control_clk(clk), .control_reset(rst), .io_x(m20[1]), .io_y(m23[1]), .io_r(random[44]), .io_z(m31[1]));
// M33 = M27 + M25
HPC2Xor #(.d(1)) xor_m33_b1 (.control_clk(clk), .control_reset(rst), .io_x(m27_pipe[1][1]), .io_y(m25[1]), .io_z(m33[1]));
// M34 = M21 x M22
HPC2And #(.d(1)) and_inst_14_b1 (.control_clk(clk), .control_reset(rst), .io_x(m21[1]), .io_y(m22[1]), .io_r(random[45]), .io_z(m34[1]));
// M36 = M24 + M25
HPC2Xor #(.d(1)) xor_m36_b1 (.control_clk(clk), .control_reset(rst), .io_x(m24_pipe[1][1]), .io_y(m25[1]), .io_z(m36[1]));

// Stage 3:
// M29 = M28 x M27
HPC2And #(.d(1)) and_inst_10_b1 (.control_clk(clk), .control_reset(rst), .io_x(m28[1]), .io_y(m27_pipe[1][1]), .io_r(random[46]), .io_z(m29[1]));
// M30 = M26 x M24
HPC2And #(.d(1)) and_inst_11_b1 (.control_clk(clk), .control_reset(rst), .io_x(m26[1]), .io_y(m24_pipe[1][1]), .io_r(random[47]), .io_z(m30[1]));
// M32 = M27 x M31
HPC2And #(.d(1)) and_inst_13_b1 (.control_clk(clk), .control_reset(rst), .io_x(m27_pipe[1][1]), .io_y(m31[1]), .io_r(random[48]), .io_z(m32[1]));
// M35 = M24 x M34
HPC2And #(.d(1)) and_inst_15_b1 (.control_clk(clk), .control_reset(rst), .io_x(m24_pipe[1][1]), .io_y(m34[1]), .io_r(random[49]), .io_z(m35[1]));
// M37 = M21 + M29
HPC2Xor #(.d(1)) xor_m37_b1 (.control_clk(clk), .control_reset(rst), .io_x(m21_pipe[3][1]), .io_y(m29[1]), .io_z(m37[1]));
// M38 = M32 + M33
HPC2Xor #(.d(1)) xor_m38_b1 (.control_clk(clk), .control_reset(rst), .io_x(m32[1]), .io_y(m33_pipe[1][1]), .io_z(m38[1]));
// M39 = M23 + M30
HPC2Xor #(.d(1)) xor_m39_b1 (.control_clk(clk), .control_reset(rst), .io_x(m23_pipe[3][1]), .io_y(m30[1]), .io_z(m39[1]));
// M40 = M35 + M36
HPC2Xor #(.d(1)) xor_m40_b1 (.control_clk(clk), .control_reset(rst), .io_x(m35[1]), .io_y(m36_pipe[1][1]), .io_z(m40[1]));
// M41 = M38 + M40
HPC2Xor #(.d(1)) xor_m41_b1 (.control_clk(clk), .control_reset(rst), .io_x(m38[1]), .io_y(m40[1]), .io_z(m41[1]));
// M42 = M37 + M39
HPC2Xor #(.d(1)) xor_m42_b1 (.control_clk(clk), .control_reset(rst), .io_x(m37[1]), .io_y(m39[1]), .io_z(m42[1]));
// M43 = M37 + M38
HPC2Xor #(.d(1)) xor_m43_b1 (.control_clk(clk), .control_reset(rst), .io_x(m37[1]), .io_y(m38[1]), .io_z(m43[1]));
// M44 = M39 + M40
HPC2Xor #(.d(1)) xor_m44_b1 (.control_clk(clk), .control_reset(rst), .io_x(m39[1]), .io_y(m40[1]), .io_z(m44[1]));
// M45 = M42 + M41
HPC2Xor #(.d(1)) xor_m45_b1 (.control_clk(clk), .control_reset(rst), .io_x(m42[1]), .io_y(m41[1]), .io_z(m45[1]));

//Stage 4:
// M46 = M44 x T6
HPC2And #(.d(1)) and_inst_16_b1 (.control_clk(clk), .control_reset(rst), .io_x(m44[1]), .io_y(t6_pipe[5][1]), .io_r(random[50]), .io_z(m46[1]));
// M47 = M40 x T8
HPC2And #(.d(1)) and_inst_17_b1 (.control_clk(clk), .control_reset(rst), .io_x(m40[1]), .io_y(t8_pipe[5][1]), .io_r(random[51]), .io_z(m47[1]));
// M48 = M39 x D
HPC2And #(.d(1)) and_inst_18_b1 (.control_clk(clk), .control_reset(rst), .io_x(m39[1]), .io_y(d_pipe[5][1]), .io_r(random[52]), .io_z(m48[1]));
// M49 = M43 x T16
HPC2And #(.d(1)) and_inst_19_b1 (.control_clk(clk), .control_reset(rst), .io_x(m43[1]), .io_y(t16_pipe[5][1]), .io_r(random[53]), .io_z(m49[1]));
// M50 = M38 x T9
HPC2And #(.d(1)) and_inst_20_b1 (.control_clk(clk), .control_reset(rst), .io_x(m38[1]), .io_y(t9_pipe[5][1]), .io_r(random[54]), .io_z(m50[1]));
// M51 = M37 x T17
HPC2And #(.d(1)) and_inst_21_b1 (.control_clk(clk), .control_reset(rst), .io_x(m37[1]), .io_y(t17_pipe[5][1]), .io_r(random[55]), .io_z(m51[1]));
// M52 = M42 x T15
HPC2And #(.d(1)) and_inst_22_b1 (.control_clk(clk), .control_reset(rst), .io_x(m42[1]), .io_y(t15_pipe[5][1]), .io_r(random[56]), .io_z(m52[1]));
// M53 = M45 x T27
HPC2And #(.d(1)) and_inst_23_b1 (.control_clk(clk), .control_reset(rst), .io_x(m45[1]), .io_y(t27_pipe[5][1]), .io_r(random[57]), .io_z(m53[1]));
// M54 = M41 x T10
HPC2And #(.d(1)) and_inst_24_b1 (.control_clk(clk), .control_reset(rst), .io_x(m41[1]), .io_y(t10_pipe[5][1]), .io_r(random[58]), .io_z(m54[1]));
// M55 = M44 x T13
HPC2And #(.d(1)) and_inst_25_b1 (.control_clk(clk), .control_reset(rst), .io_x(m44[1]), .io_y(t13_pipe[5][1]), .io_r(random[59]), .io_z(m55[1]));
// M56 = M40 x T23
HPC2And #(.d(1)) and_inst_26_b1 (.control_clk(clk), .control_reset(rst), .io_x(m40[1]), .io_y(t23_pipe[5][1]), .io_r(random[60]), .io_z(m56[1]));
// M57 = M39 x T19
HPC2And #(.d(1)) and_inst_27_b1 (.control_clk(clk), .control_reset(rst), .io_x(m39[1]), .io_y(t19_pipe[5][1]), .io_r(random[61]), .io_z(m57[1]));
// M58 = M43 x T3
HPC2And #(.d(1)) and_inst_28_b1 (.control_clk(clk), .control_reset(rst), .io_x(m43[1]), .io_y(t3_pipe[5][1]), .io_r(random[62]), .io_z(m58[1]));
// M59 = M38 x T22
HPC2And #(.d(1)) and_inst_29_b1 (.control_clk(clk), .control_reset(rst), .io_x(m38[1]), .io_y(t22_pipe[5][1]), .io_r(random[63]), .io_z(m59[1]));
// M60 = M37 x T20
HPC2And #(.d(1)) and_inst_30_b1 (.control_clk(clk), .control_reset(rst), .io_x(m37[1]), .io_y(t20_pipe[5][1]), .io_r(random[64]), .io_z(m60[1]));
// M61 = M42 x T1
HPC2And #(.d(1)) and_inst_31_b1 (.control_clk(clk), .control_reset(rst), .io_x(m42[1]), .io_y(t1_pipe[5][1]), .io_r(random[65]), .io_z(m61[1]));
// M62 = M45 x T4
HPC2And #(.d(1)) and_inst_32_b1 (.control_clk(clk), .control_reset(rst), .io_x(m45[1]), .io_y(t4_pipe[5][1]), .io_r(random[66]), .io_z(m62[1]));
// M63 = M41 x T2
HPC2And #(.d(1)) and_inst_33_b1 (.control_clk(clk), .control_reset(rst), .io_x(m41[1]), .io_y(t2_pipe[5][1]), .io_r(random[67]), .io_z(m63[1]));

// L intermediate XOR operations using gadgets
// L0 = M61 + M62
HPC2Xor #(.d(1)) xor_l0_b0 (.control_clk(clk), .control_reset(rst), .io_x(m61[0]), .io_y(m62[0]), .io_z(l0[0]));
// L1 = M50 + M56
HPC2Xor #(.d(1)) xor_l1_b0 (.control_clk(clk), .control_reset(rst), .io_x(m50[0]), .io_y(m56[0]), .io_z(l1[0]));
// L2 = M46 + M48
HPC2Xor #(.d(1)) xor_l2_b0 (.control_clk(clk), .control_reset(rst), .io_x(m46[0]), .io_y(m48[0]), .io_z(l2[0]));
// L3 = M47 + M55
HPC2Xor #(.d(1)) xor_l3_b0 (.control_clk(clk), .control_reset(rst), .io_x(m47[0]), .io_y(m55[0]), .io_z(l3[0]));
// L4 = M54 + M58
HPC2Xor #(.d(1)) xor_l4_b0 (.control_clk(clk), .control_reset(rst), .io_x(m54[0]), .io_y(m58[0]), .io_z(l4[0]));
// L5 = M49 + M61
HPC2Xor #(.d(1)) xor_l5_b0 (.control_clk(clk), .control_reset(rst), .io_x(m49[0]), .io_y(m61[0]), .io_z(l5[0]));
// L6 = M62 + L5
HPC2Xor #(.d(1)) xor_l6_b0 (.control_clk(clk), .control_reset(rst), .io_x(m62[0]), .io_y(l5[0]), .io_z(l6[0]));
// L7 = M46 + L3
HPC2Xor #(.d(1)) xor_l7_b0 (.control_clk(clk), .control_reset(rst), .io_x(m46[0]), .io_y(l3[0]), .io_z(l7[0]));
// L8 = M51 + M59
HPC2Xor #(.d(1)) xor_l8_b0 (.control_clk(clk), .control_reset(rst), .io_x(m51[0]), .io_y(m59[0]), .io_z(l8[0]));
// L9 = M52 + M53
HPC2Xor #(.d(1)) xor_l9_b0 (.control_clk(clk), .control_reset(rst), .io_x(m52[0]), .io_y(m53[0]), .io_z(l9[0]));
// L10 = M53 + L4
HPC2Xor #(.d(1)) xor_l10_b0 (.control_clk(clk), .control_reset(rst), .io_x(m53[0]), .io_y(l4[0]), .io_z(l10[0]));
// L11 = M60 + L2
HPC2Xor #(.d(1)) xor_l11_b0 (.control_clk(clk), .control_reset(rst), .io_x(m60[0]), .io_y(l2[0]), .io_z(l11[0]));
// L12 = M48 + M51
HPC2Xor #(.d(1)) xor_l12_b0 (.control_clk(clk), .control_reset(rst), .io_x(m48[0]), .io_y(m51[0]), .io_z(l12[0]));
// L13 = M50 + L0
HPC2Xor #(.d(1)) xor_l13_b0 (.control_clk(clk), .control_reset(rst), .io_x(m50[0]), .io_y(l0[0]), .io_z(l13[0]));
// L14 = M52 + M61
HPC2Xor #(.d(1)) xor_l14_b0 (.control_clk(clk), .control_reset(rst), .io_x(m52[0]), .io_y(m61[0]), .io_z(l14[0]));
// L15 = M55 + L1
HPC2Xor #(.d(1)) xor_l15_b0 (.control_clk(clk), .control_reset(rst), .io_x(m55[0]), .io_y(l1[0]), .io_z(l15[0]));
// L16 = M56 + L0
HPC2Xor #(.d(1)) xor_l16_b0 (.control_clk(clk), .control_reset(rst), .io_x(m56[0]), .io_y(l0[0]), .io_z(l16[0]));
// L17 = M57 + L1
HPC2Xor #(.d(1)) xor_l17_b0 (.control_clk(clk), .control_reset(rst), .io_x(m57[0]), .io_y(l1[0]), .io_z(l17[0]));
// L18 = M58 + L8
HPC2Xor #(.d(1)) xor_l18_b0 (.control_clk(clk), .control_reset(rst), .io_x(m58[0]), .io_y(l8[0]), .io_z(l18[0]));
// L19 = M63 + L4
HPC2Xor #(.d(1)) xor_l19_b0 (.control_clk(clk), .control_reset(rst), .io_x(m63[0]), .io_y(l4[0]), .io_z(l19[0]));
// L20 = L0 + L1
HPC2Xor #(.d(1)) xor_l20_b0 (.control_clk(clk), .control_reset(rst), .io_x(l0[0]), .io_y(l1[0]), .io_z(l20[0]));
// L21 = L1 + L7
HPC2Xor #(.d(1)) xor_l21_b0 (.control_clk(clk), .control_reset(rst), .io_x(l1[0]), .io_y(l7[0]), .io_z(l21[0]));
// L22 = L3 + L12
HPC2Xor #(.d(1)) xor_l22_b0 (.control_clk(clk), .control_reset(rst), .io_x(l3[0]), .io_y(l12[0]), .io_z(l22[0]));
// L23 = L18 + L2
HPC2Xor #(.d(1)) xor_l23_b0 (.control_clk(clk), .control_reset(rst), .io_x(l18[0]), .io_y(l2[0]), .io_z(l23[0]));
// L24 = L15 + L9
HPC2Xor #(.d(1)) xor_l24_b0 (.control_clk(clk), .control_reset(rst), .io_x(l15[0]), .io_y(l9[0]), .io_z(l24[0]));
// L25 = L6 + L10
HPC2Xor #(.d(1)) xor_l25_b0 (.control_clk(clk), .control_reset(rst), .io_x(l6[0]), .io_y(l10[0]), .io_z(l25[0]));
// L26 = L7 + L9
HPC2Xor #(.d(1)) xor_l26_b0 (.control_clk(clk), .control_reset(rst), .io_x(l7[0]), .io_y(l9[0]), .io_z(l26[0]));
// L27 = L8 + L10
HPC2Xor #(.d(1)) xor_l27_b0 (.control_clk(clk), .control_reset(rst), .io_x(l8[0]), .io_y(l10[0]), .io_z(l27[0]));
// L28 = L11 + L14
HPC2Xor #(.d(1)) xor_l28_b0 (.control_clk(clk), .control_reset(rst), .io_x(l11[0]), .io_y(l14[0]), .io_z(l28[0]));
// L29 = L11 + L17
HPC2Xor #(.d(1)) xor_l29_b0 (.control_clk(clk), .control_reset(rst), .io_x(l11[0]), .io_y(l17[0]), .io_z(l29[0]));


// Get encryption output bits using gadgets
// S0 = L6 + L24
HPC2Xor #(.d(1)) xor_s7_b0 (.control_clk(clk), .control_reset(rst), .io_x(l6[0]), .io_y(l24[0]), .io_z(s7[0]));
// S1 = L16 # L26
HPC2Xor #(.d(1)) xor_s6_pre_b0 (.control_clk(clk), .control_reset(rst), .io_x(l16[0]), .io_y(l26[0]), .io_z(s6_xor[0]));
HPC2Not #(.d(1)) not_s6_b0 (.control_clk(clk), .control_reset(rst), .io_x(s6_xor[0]), .io_z(s6[0]));
// S2 = L19 # L28
HPC2Xor #(.d(1)) xor_s5_pre_b0 (.control_clk(clk), .control_reset(rst), .io_x(l19[0]), .io_y(l28[0]), .io_z(s5_xor[0]));
HPC2Not #(.d(1)) not_s5_b0 (.control_clk(clk), .control_reset(rst), .io_x(s5_xor[0]), .io_z(s5[0]));
// S3 = L6 + L21
HPC2Xor #(.d(1)) xor_s4_b0 (.control_clk(clk), .control_reset(rst), .io_x(l6[0]), .io_y(l21[0]), .io_z(s4[0]));
// S4 = L20 + L22
HPC2Xor #(.d(1)) xor_s3_b0 (.control_clk(clk), .control_reset(rst), .io_x(l20[0]), .io_y(l22[0]), .io_z(s3[0]));
// S5 = L25 + L29
HPC2Xor #(.d(1)) xor_s2_b0 (.control_clk(clk), .control_reset(rst), .io_x(l25[0]), .io_y(l29[0]), .io_z(s2[0]));
// S6 = L13 # L27
HPC2Xor #(.d(1)) xor_s1_pre_b0 (.control_clk(clk), .control_reset(rst), .io_x(l13[0]), .io_y(l27[0]), .io_z(s1_xor[0]));
HPC2Not #(.d(1)) not_s1_b0 (.control_clk(clk), .control_reset(rst), .io_x(s1_xor[0]), .io_z(s1[0]));
// S7 = L6 # L23
HPC2Xor #(.d(1)) xor_s0_pre_b0 (.control_clk(clk), .control_reset(rst), .io_x(l6[0]), .io_y(l23[0]), .io_z(s0_xor[0]));
HPC2Not #(.d(1)) not_s0_b0 (.control_clk(clk), .control_reset(rst), .io_x(s0_xor[0]), .io_z(s0[0]));





// Byte 1 L operations
HPC2Xor #(.d(1)) xor_l0_b1 (.control_clk(clk), .control_reset(rst), .io_x(m61[1]), .io_y(m62[1]), .io_z(l0[1]));
HPC2Xor #(.d(1)) xor_l1_b1 (.control_clk(clk), .control_reset(rst), .io_x(m50[1]), .io_y(m56[1]), .io_z(l1[1]));
HPC2Xor #(.d(1)) xor_l2_b1 (.control_clk(clk), .control_reset(rst), .io_x(m46[1]), .io_y(m48[1]), .io_z(l2[1]));
HPC2Xor #(.d(1)) xor_l3_b1 (.control_clk(clk), .control_reset(rst), .io_x(m47[1]), .io_y(m55[1]), .io_z(l3[1]));
HPC2Xor #(.d(1)) xor_l4_b1 (.control_clk(clk), .control_reset(rst), .io_x(m54[1]), .io_y(m58[1]), .io_z(l4[1]));
HPC2Xor #(.d(1)) xor_l5_b1 (.control_clk(clk), .control_reset(rst), .io_x(m49[1]), .io_y(m61[1]), .io_z(l5[1]));
HPC2Xor #(.d(1)) xor_l6_b1 (.control_clk(clk), .control_reset(rst), .io_x(m62[1]), .io_y(l5[1]), .io_z(l6[1]));
HPC2Xor #(.d(1)) xor_l7_b1 (.control_clk(clk), .control_reset(rst), .io_x(m46[1]), .io_y(l3[1]), .io_z(l7[1]));
HPC2Xor #(.d(1)) xor_l8_b1 (.control_clk(clk), .control_reset(rst), .io_x(m51[1]), .io_y(m59[1]), .io_z(l8[1]));
HPC2Xor #(.d(1)) xor_l9_b1 (.control_clk(clk), .control_reset(rst), .io_x(m52[1]), .io_y(m53[1]), .io_z(l9[1]));
HPC2Xor #(.d(1)) xor_l10_b1 (.control_clk(clk), .control_reset(rst), .io_x(m53[1]), .io_y(l4[1]), .io_z(l10[1]));
HPC2Xor #(.d(1)) xor_l11_b1 (.control_clk(clk), .control_reset(rst), .io_x(m60[1]), .io_y(l2[1]), .io_z(l11[1]));
HPC2Xor #(.d(1)) xor_l12_b1 (.control_clk(clk), .control_reset(rst), .io_x(m48[1]), .io_y(m51[1]), .io_z(l12[1]));
HPC2Xor #(.d(1)) xor_l13_b1 (.control_clk(clk), .control_reset(rst), .io_x(m50[1]), .io_y(l0[1]), .io_z(l13[1]));
HPC2Xor #(.d(1)) xor_l14_b1 (.control_clk(clk), .control_reset(rst), .io_x(m52[1]), .io_y(m61[1]), .io_z(l14[1]));
HPC2Xor #(.d(1)) xor_l15_b1 (.control_clk(clk), .control_reset(rst), .io_x(m55[1]), .io_y(l1[1]), .io_z(l15[1]));
HPC2Xor #(.d(1)) xor_l16_b1 (.control_clk(clk), .control_reset(rst), .io_x(m56[1]), .io_y(l0[1]), .io_z(l16[1]));
HPC2Xor #(.d(1)) xor_l17_b1 (.control_clk(clk), .control_reset(rst), .io_x(m57[1]), .io_y(l1[1]), .io_z(l17[1]));
HPC2Xor #(.d(1)) xor_l18_b1 (.control_clk(clk), .control_reset(rst), .io_x(m58[1]), .io_y(l8[1]), .io_z(l18[1]));
HPC2Xor #(.d(1)) xor_l19_b1 (.control_clk(clk), .control_reset(rst), .io_x(m63[1]), .io_y(l4[1]), .io_z(l19[1]));
HPC2Xor #(.d(1)) xor_l20_b1 (.control_clk(clk), .control_reset(rst), .io_x(l0[1]), .io_y(l1[1]), .io_z(l20[1]));
HPC2Xor #(.d(1)) xor_l21_b1 (.control_clk(clk), .control_reset(rst), .io_x(l1[1]), .io_y(l7[1]), .io_z(l21[1]));
HPC2Xor #(.d(1)) xor_l22_b1 (.control_clk(clk), .control_reset(rst), .io_x(l3[1]), .io_y(l12[1]), .io_z(l22[1]));
HPC2Xor #(.d(1)) xor_l23_b1 (.control_clk(clk), .control_reset(rst), .io_x(l18[1]), .io_y(l2[1]), .io_z(l23[1]));
HPC2Xor #(.d(1)) xor_l24_b1 (.control_clk(clk), .control_reset(rst), .io_x(l15[1]), .io_y(l9[1]), .io_z(l24[1]));
HPC2Xor #(.d(1)) xor_l25_b1 (.control_clk(clk), .control_reset(rst), .io_x(l6[1]), .io_y(l10[1]), .io_z(l25[1]));
HPC2Xor #(.d(1)) xor_l26_b1 (.control_clk(clk), .control_reset(rst), .io_x(l7[1]), .io_y(l9[1]), .io_z(l26[1]));
HPC2Xor #(.d(1)) xor_l27_b1 (.control_clk(clk), .control_reset(rst), .io_x(l8[1]), .io_y(l10[1]), .io_z(l27[1]));
HPC2Xor #(.d(1)) xor_l28_b1 (.control_clk(clk), .control_reset(rst), .io_x(l11[1]), .io_y(l14[1]), .io_z(l28[1]));
HPC2Xor #(.d(1)) xor_l29_b1 (.control_clk(clk), .control_reset(rst), .io_x(l11[1]), .io_y(l17[1]), .io_z(l29[1]));


HPC2Xor #(.d(1)) xor_s7_b1 (.control_clk(clk), .control_reset(rst), .io_x(l6[1]), .io_y(l24[1]), .io_z(s7[1]));
HPC2Xor #(.d(1)) xor_s6_pre_b1 (.control_clk(clk), .control_reset(rst), .io_x(l16[1]), .io_y(l26[1]), .io_z(s6_xor[1]));
HPC2Not #(.d(1)) not_s6_b1 (.control_clk(clk), .control_reset(rst), .io_x(s6_xor[1]), .io_z(s6[1]));
HPC2Xor #(.d(1)) xor_s5_pre_b1 (.control_clk(clk), .control_reset(rst), .io_x(l19[1]), .io_y(l28[1]), .io_z(s5_xor[1]));
HPC2Not #(.d(1)) not_s5_b1 (.control_clk(clk), .control_reset(rst), .io_x(s5_xor[1]), .io_z(s5[1]));
HPC2Xor #(.d(1)) xor_s4_b1 (.control_clk(clk), .control_reset(rst), .io_x(l6[1]), .io_y(l21[1]), .io_z(s4[1]));
HPC2Xor #(.d(1)) xor_s3_b1 (.control_clk(clk), .control_reset(rst), .io_x(l20[1]), .io_y(l22[1]), .io_z(s3[1]));
HPC2Xor #(.d(1)) xor_s2_b1 (.control_clk(clk), .control_reset(rst), .io_x(l25[1]), .io_y(l29[1]), .io_z(s2[1]));
HPC2Xor #(.d(1)) xor_s1_pre_b1 (.control_clk(clk), .control_reset(rst), .io_x(l13[1]), .io_y(l27[1]), .io_z(s1_xor[1]));
HPC2Not #(.d(1)) not_s1_b1 (.control_clk(clk), .control_reset(rst), .io_x(s1_xor[1]), .io_z(s1[1]));
HPC2Xor #(.d(1)) xor_s0_pre_b1 (.control_clk(clk), .control_reset(rst), .io_x(l6[1]), .io_y(l23[1]), .io_z(s0_xor[1]));
HPC2Not #(.d(1)) not_s0_b1 (.control_clk(clk), .control_reset(rst), .io_x(s0_xor[1]), .io_z(s0[1]));


// P intermediate XOR operations using gadgets (for decryption)
// P0 = M52 + M61
HPC2Xor #(.d(1)) xor_p0_b0 (.control_clk(clk), .control_reset(rst), .io_x(m52[0]), .io_y(m61[0]), .io_z(p0[0]));
// P1 = M58 + M59
HPC2Xor #(.d(1)) xor_p1_b0 (.control_clk(clk), .control_reset(rst), .io_x(m58[0]), .io_y(m59[0]), .io_z(p1[0]));
// P2 = M54 + M62
HPC2Xor #(.d(1)) xor_p2_b0 (.control_clk(clk), .control_reset(rst), .io_x(m54[0]), .io_y(m62[0]), .io_z(p2[0]));
// P3 = M47 + M50
HPC2Xor #(.d(1)) xor_p3_b0 (.control_clk(clk), .control_reset(rst), .io_x(m47[0]), .io_y(m50[0]), .io_z(p3[0]));
// P4 = M48 + M56
HPC2Xor #(.d(1)) xor_p4_b0 (.control_clk(clk), .control_reset(rst), .io_x(m48[0]), .io_y(m56[0]), .io_z(p4[0]));
// P5 = M46 + M51
HPC2Xor #(.d(1)) xor_p5_b0 (.control_clk(clk), .control_reset(rst), .io_x(m46[0]), .io_y(m51[0]), .io_z(p5[0]));
// P6 = M49 + M60
HPC2Xor #(.d(1)) xor_p6_b0 (.control_clk(clk), .control_reset(rst), .io_x(m49[0]), .io_y(m60[0]), .io_z(p6[0]));
// P7 = P0 + P1
HPC2Xor #(.d(1)) xor_p7_b0 (.control_clk(clk), .control_reset(rst), .io_x(p0[0]), .io_y(p1[0]), .io_z(p7[0]));
// P8 = M50 + M53
HPC2Xor #(.d(1)) xor_p8_b0 (.control_clk(clk), .control_reset(rst), .io_x(m50[0]), .io_y(m53[0]), .io_z(p8[0]));
// P9 = M55 + M63
HPC2Xor #(.d(1)) xor_p9_b0 (.control_clk(clk), .control_reset(rst), .io_x(m55[0]), .io_y(m63[0]), .io_z(p9[0]));
// P10 = M57 + P4
HPC2Xor #(.d(1)) xor_p10_b0 (.control_clk(clk), .control_reset(rst), .io_x(m57[0]), .io_y(p4[0]), .io_z(p10[0]));
// P11 = P0 + P3
HPC2Xor #(.d(1)) xor_p11_b0 (.control_clk(clk), .control_reset(rst), .io_x(p0[0]), .io_y(p3[0]), .io_z(p11[0]));
// P12 = M46 + M48
HPC2Xor #(.d(1)) xor_p12_b0 (.control_clk(clk), .control_reset(rst), .io_x(m46[0]), .io_y(m48[0]), .io_z(p12[0]));
// P13 = M49 + M51
HPC2Xor #(.d(1)) xor_p13_b0 (.control_clk(clk), .control_reset(rst), .io_x(m49[0]), .io_y(m51[0]), .io_z(p13[0]));
// P14 = M49 + M62
HPC2Xor #(.d(1)) xor_p14_b0 (.control_clk(clk), .control_reset(rst), .io_x(m49[0]), .io_y(m62[0]), .io_z(p14[0]));
// P15 = M54 + M59
HPC2Xor #(.d(1)) xor_p15_b0 (.control_clk(clk), .control_reset(rst), .io_x(m54[0]), .io_y(m59[0]), .io_z(p15[0]));
// P16 = M57 + M61
HPC2Xor #(.d(1)) xor_p16_b0 (.control_clk(clk), .control_reset(rst), .io_x(m57[0]), .io_y(m61[0]), .io_z(p16[0]));
// P17 = M58 + P2
HPC2Xor #(.d(1)) xor_p17_b0 (.control_clk(clk), .control_reset(rst), .io_x(m58[0]), .io_y(p2[0]), .io_z(p17[0]));
// P18 = M63 + P5
HPC2Xor #(.d(1)) xor_p18_b0 (.control_clk(clk), .control_reset(rst), .io_x(m63[0]), .io_y(p5[0]), .io_z(p18[0]));
// P19 = P2 + P3
HPC2Xor #(.d(1)) xor_p19_b0 (.control_clk(clk), .control_reset(rst), .io_x(p2[0]), .io_y(p3[0]), .io_z(p19[0]));
// P20 = P4 + P6
HPC2Xor #(.d(1)) xor_p20_b0 (.control_clk(clk), .control_reset(rst), .io_x(p4[0]), .io_y(p6[0]), .io_z(p20[0]));
// P22 = P2 + P7
HPC2Xor #(.d(1)) xor_p22_b0 (.control_clk(clk), .control_reset(rst), .io_x(p2[0]), .io_y(p7[0]), .io_z(p22[0]));
// P23 = P7 + P8
HPC2Xor #(.d(1)) xor_p23_b0 (.control_clk(clk), .control_reset(rst), .io_x(p7[0]), .io_y(p8[0]), .io_z(p23[0]));
// P24 = P5 + P7
HPC2Xor #(.d(1)) xor_p24_b0 (.control_clk(clk), .control_reset(rst), .io_x(p5[0]), .io_y(p7[0]), .io_z(p24[0]));
// P25 = P6 + P10
HPC2Xor #(.d(1)) xor_p25_b0 (.control_clk(clk), .control_reset(rst), .io_x(p6[0]), .io_y(p10[0]), .io_z(p25[0]));
// P26 = P9 + P11
HPC2Xor #(.d(1)) xor_p26_b0 (.control_clk(clk), .control_reset(rst), .io_x(p9[0]), .io_y(p11[0]), .io_z(p26[0]));
// P27 = P10 + P18
HPC2Xor #(.d(1)) xor_p27_b0 (.control_clk(clk), .control_reset(rst), .io_x(p10[0]), .io_y(p18[0]), .io_z(p27[0]));
// P28 = P11 + P25
HPC2Xor #(.d(1)) xor_p28_b0 (.control_clk(clk), .control_reset(rst), .io_x(p11[0]), .io_y(p25[0]), .io_z(p28[0]));
// P29 = P15 + P20
HPC2Xor #(.d(1)) xor_p29_b0 (.control_clk(clk), .control_reset(rst), .io_x(p15[0]), .io_y(p20[0]), .io_z(p29[0]));

// P intermediate XOR operations (for decryption) - byte 1
HPC2Xor #(.d(1)) xor_p0_b1 (.control_clk(clk), .control_reset(rst), .io_x(m52[1]), .io_y(m61[1]), .io_z(p0[1]));
HPC2Xor #(.d(1)) xor_p1_b1 (.control_clk(clk), .control_reset(rst), .io_x(m58[1]), .io_y(m59[1]), .io_z(p1[1]));
HPC2Xor #(.d(1)) xor_p2_b1 (.control_clk(clk), .control_reset(rst), .io_x(m54[1]), .io_y(m62[1]), .io_z(p2[1]));
HPC2Xor #(.d(1)) xor_p3_b1 (.control_clk(clk), .control_reset(rst), .io_x(m47[1]), .io_y(m50[1]), .io_z(p3[1]));
HPC2Xor #(.d(1)) xor_p4_b1 (.control_clk(clk), .control_reset(rst), .io_x(m48[1]), .io_y(m56[1]), .io_z(p4[1]));
HPC2Xor #(.d(1)) xor_p5_b1 (.control_clk(clk), .control_reset(rst), .io_x(m46[1]), .io_y(m51[1]), .io_z(p5[1]));
HPC2Xor #(.d(1)) xor_p6_b1 (.control_clk(clk), .control_reset(rst), .io_x(m49[1]), .io_y(m60[1]), .io_z(p6[1]));
HPC2Xor #(.d(1)) xor_p7_b1 (.control_clk(clk), .control_reset(rst), .io_x(p0[1]), .io_y(p1[1]), .io_z(p7[1]));
HPC2Xor #(.d(1)) xor_p8_b1 (.control_clk(clk), .control_reset(rst), .io_x(m50[1]), .io_y(m53[1]), .io_z(p8[1]));
HPC2Xor #(.d(1)) xor_p9_b1 (.control_clk(clk), .control_reset(rst), .io_x(m55[1]), .io_y(m63[1]), .io_z(p9[1]));
HPC2Xor #(.d(1)) xor_p10_b1 (.control_clk(clk), .control_reset(rst), .io_x(m57[1]), .io_y(p4[1]), .io_z(p10[1]));
HPC2Xor #(.d(1)) xor_p11_b1 (.control_clk(clk), .control_reset(rst), .io_x(p0[1]), .io_y(p3[1]), .io_z(p11[1]));
HPC2Xor #(.d(1)) xor_p12_b1 (.control_clk(clk), .control_reset(rst), .io_x(m46[1]), .io_y(m48[1]), .io_z(p12[1]));
HPC2Xor #(.d(1)) xor_p13_b1 (.control_clk(clk), .control_reset(rst), .io_x(m49[1]), .io_y(m51[1]), .io_z(p13[1]));
HPC2Xor #(.d(1)) xor_p14_b1 (.control_clk(clk), .control_reset(rst), .io_x(m49[1]), .io_y(m62[1]), .io_z(p14[1]));
HPC2Xor #(.d(1)) xor_p15_b1 (.control_clk(clk), .control_reset(rst), .io_x(m54[1]), .io_y(m59[1]), .io_z(p15[1]));
HPC2Xor #(.d(1)) xor_p16_b1 (.control_clk(clk), .control_reset(rst), .io_x(m57[1]), .io_y(m61[1]), .io_z(p16[1]));
HPC2Xor #(.d(1)) xor_p17_b1 (.control_clk(clk), .control_reset(rst), .io_x(m58[1]), .io_y(p2[1]), .io_z(p17[1]));
HPC2Xor #(.d(1)) xor_p18_b1 (.control_clk(clk), .control_reset(rst), .io_x(m63[1]), .io_y(p5[1]), .io_z(p18[1]));
HPC2Xor #(.d(1)) xor_p19_b1 (.control_clk(clk), .control_reset(rst), .io_x(p2[1]), .io_y(p3[1]), .io_z(p19[1]));
HPC2Xor #(.d(1)) xor_p20_b1 (.control_clk(clk), .control_reset(rst), .io_x(p4[1]), .io_y(p6[1]), .io_z(p20[1]));
HPC2Xor #(.d(1)) xor_p22_b1 (.control_clk(clk), .control_reset(rst), .io_x(p2[1]), .io_y(p7[1]), .io_z(p22[1]));
HPC2Xor #(.d(1)) xor_p23_b1 (.control_clk(clk), .control_reset(rst), .io_x(p7[1]), .io_y(p8[1]), .io_z(p23[1]));
HPC2Xor #(.d(1)) xor_p24_b1 (.control_clk(clk), .control_reset(rst), .io_x(p5[1]), .io_y(p7[1]), .io_z(p24[1]));
HPC2Xor #(.d(1)) xor_p25_b1 (.control_clk(clk), .control_reset(rst), .io_x(p6[1]), .io_y(p10[1]), .io_z(p25[1]));
HPC2Xor #(.d(1)) xor_p26_b1 (.control_clk(clk), .control_reset(rst), .io_x(p9[1]), .io_y(p11[1]), .io_z(p26[1]));
HPC2Xor #(.d(1)) xor_p27_b1 (.control_clk(clk), .control_reset(rst), .io_x(p10[1]), .io_y(p18[1]), .io_z(p27[1]));
HPC2Xor #(.d(1)) xor_p28_b1 (.control_clk(clk), .control_reset(rst), .io_x(p11[1]), .io_y(p25[1]), .io_z(p28[1]));
HPC2Xor #(.d(1)) xor_p29_b1 (.control_clk(clk), .control_reset(rst), .io_x(p15[1]), .io_y(p20[1]), .io_z(p29[1]));

// Get decryption output bits

// W0 = P13 + P22
HPC2Xor #(.d(1)) xor_w7_b0 (.control_clk(clk), .control_reset(rst), .io_x(p13[0]), .io_y(p22[0]), .io_z(w7[0]));
// W1 = P26 + P29
HPC2Xor #(.d(1)) xor_w6_b0 (.control_clk(clk), .control_reset(rst), .io_x(p26[0]), .io_y(p29[0]), .io_z(w6[0]));
// W2 = P17 + P28
HPC2Xor #(.d(1)) xor_w5_b0 (.control_clk(clk), .control_reset(rst), .io_x(p17[0]), .io_y(p28[0]), .io_z(w5[0]));
// W3 = P12 + P22
HPC2Xor #(.d(1)) xor_w4_b0 (.control_clk(clk), .control_reset(rst), .io_x(p12[0]), .io_y(p22[0]), .io_z(w4[0]));
// W4 = P23 + P27
HPC2Xor #(.d(1)) xor_w3_b0 (.control_clk(clk), .control_reset(rst), .io_x(p23[0]), .io_y(p27[0]), .io_z(w3[0]));
// W5 = P19 + P24
HPC2Xor #(.d(1)) xor_w2_b0 (.control_clk(clk), .control_reset(rst), .io_x(p19[0]), .io_y(p24[0]), .io_z(w2[0]));
// W6 = P14 + P23
HPC2Xor #(.d(1)) xor_w1_b0 (.control_clk(clk), .control_reset(rst), .io_x(p14[0]), .io_y(p23[0]), .io_z(w1[0]));
// W7 = P9 + P16
HPC2Xor #(.d(1)) xor_w0_b0 (.control_clk(clk), .control_reset(rst), .io_x(p9[0]), .io_y(p16[0]), .io_z(w0[0]));

// Decryptopion output bits - byte 1
HPC2Xor #(.d(1)) xor_w7_b1 (.control_clk(clk), .control_reset(rst), .io_x(p13[1]), .io_y(p22[1]), .io_z(w7[1]));
HPC2Xor #(.d(1)) xor_w6_b1 (.control_clk(clk), .control_reset(rst), .io_x(p26[1]), .io_y(p29[1]), .io_z(w6[1]));
HPC2Xor #(.d(1)) xor_w5_b1 (.control_clk(clk), .control_reset(rst), .io_x(p17[1]), .io_y(p28[1]), .io_z(w5[1]));
HPC2Xor #(.d(1)) xor_w4_b1 (.control_clk(clk), .control_reset(rst), .io_x(p12[1]), .io_y(p22[1]), .io_z(w4[1]));
HPC2Xor #(.d(1)) xor_w3_b1 (.control_clk(clk), .control_reset(rst), .io_x(p23[1]), .io_y(p27[1]), .io_z(w3[1]));
HPC2Xor #(.d(1)) xor_w2_b1 (.control_clk(clk), .control_reset(rst), .io_x(p19[1]), .io_y(p24[1]), .io_z(w2[1]));
HPC2Xor #(.d(1)) xor_w1_b1 (.control_clk(clk), .control_reset(rst), .io_x(p14[1]), .io_y(p23[1]), .io_z(w1[1]));
HPC2Xor #(.d(1)) xor_w0_b1 (.control_clk(clk), .control_reset(rst), .io_x(p9[1]), .io_y(p16[1]), .io_z(w0[1]));



// Output data - 2 byte shares
assign share_out_0 = enc_mode ? { s7[1][0], s6[1][0], s5[1][0], s4[1][0], s3[1][0], s2[1][0], s1[1][0], s0[1][0], s7[0][0], s6[0][0], s5[0][0], s4[0][0], s3[0][0], s2[0][0], s1[0][0], s0[0][0]} 
                             : {w7[1][0], w6[1][0], w5[1][0], w4[1][0], w3[1][0], w2[1][0], w1[1][0], w0[1][0], w7[0][0], w6[0][0], w5[0][0], w4[0][0], w3[0][0], w2[0][0], w1[0][0], w0[0][0]};
assign share_out_1 = enc_mode ? { s7[1][1], s6[1][1], s5[1][1], s4[1][1], s3[1][1], s2[1][1], s1[1][1], s0[1][1], s7[0][1], s6[0][1], s5[0][1], s4[0][1], s3[0][1], s2[0][1], s1[0][1], s0[0][1]}
                                : { w7[1][1], w6[1][1], w5[1][1], w4[1][1], w3[1][1], w2[1][1], w1[1][1], w0[1][1],w7[0][1], w6[0][1], w5[0][1], w4[0][1], w3[0][1], w2[0][1], w1[0][1], w0[0][1]};
// Wait 8 cycles to for the result due to masked AND gates
reg [3:0] rdy_count;
always @(posedge clk) begin
    if (rst) begin
        rdy_count <= 4'b0000;
    end else if (rdy_count != 4'b1000) begin
        rdy_count <= rdy_count + 1;
    end
end
assign rdy = (rdy_count >= 4'b1000 ) ? 1'b1 : 1'b0; 
endmodule

