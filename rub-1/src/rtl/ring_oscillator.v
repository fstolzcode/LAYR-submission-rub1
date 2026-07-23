module ring_oscillator #(parameter integer STAGES = 3)(
    input wire enable,
    output wire oscillator_out
);
    // Ensure the number of stages is odd
    // if even, add 1
    localparam integer stages = (STAGES % 2 == 0) ? STAGES+1 : STAGES;

    // We need one wire for each inverter stage
    /* verilator lint_off UNOPTFLAT */
    (* KEEP = "true", DONT_TOUCH = "true" *)
    wire [stages-1:0] inverter_wire;
    /* verilator lint_on UNOPTFLAT */

    // first stage input comes from the inverted last stage when enabled,
    // otherwise the ring is held in a stable low state
    assign inverter_wire[0] = enable ? ~inverter_wire[stages-1] : 1'b0;

    // Generate the inverter chain
    genvar i;
    generate
        for (i = 1; i < stages; i = i + 1) begin : inverter_chain
            assign inverter_wire[i] = ~inverter_wire[i-1];
        end
    endgenerate

    // Oscillator output is taken from the last stage
    assign oscillator_out = inverter_wire[stages-1];

endmodule
