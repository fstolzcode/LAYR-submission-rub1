module uart_tx
    (
        input wire clk,
        input wire en,
        input wire rst,

        input wire clk_in,
        input wire [7:0] tx_in,

        output wire ready,
        output wire tx_out
    );

    localparam CLOCK_DIVIDER = 16;
    localparam NUM_BITS = 11;

    // Treat idle bit as data. This results in a tiny performance loss,
    // but simplifies the code a lot.
    wire [NUM_BITS - 1:0] actual_data = {1'b1, tx_in, 1'b0, 1'b1};

    reg clk_in_ff[2:0];
    wire clk_in_pulse = (clk_in_ff[1] && !clk_in_ff[2]);

    always @(posedge clk) begin
        if (rst) begin
            clk_in_ff[0] <= 1'b1;
            clk_in_ff[1] <= 1'b1;
            clk_in_ff[2] <= 1'b1;
        end else begin 
            clk_in_ff[0] <= clk_in;
            clk_in_ff[1] <= clk_in_ff[0];
            clk_in_ff[2] <= clk_in_ff[1];
        end
    end

    reg [$clog2(NUM_BITS * CLOCK_DIVIDER) - 1:0] clk_count;

    assign tx_out = (actual_data[clk_count / CLOCK_DIVIDER]);
    assign ready = (clk_count == 0);

    always @(posedge clk) begin
        if (!rst && clk_in_pulse && en && clk_count < NUM_BITS * CLOCK_DIVIDER - 1) begin
            clk_count <= clk_count + 1;
        end else if (rst || clk_in_pulse) begin
            clk_count <= 0;
        end
    end

endmodule
