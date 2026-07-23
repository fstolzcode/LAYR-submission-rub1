module spi_master (
    input wire clk,        // 10 MHz clock
    input wire rst,
    input wire start_tx,
    input wire open_cs0,   // active low
    input wire open_cs1,   // active low

    input wire spi_miso,
    input wire [7:0] tx_data,

    output wire busy,
    output reg spi_sclk,
    output reg spi_mosi,
    output wire spi_cs_0,   // active-low
    output wire spi_cs_1,   // active-low
    output reg [7:0] rx_data
);

    // Half-period count for 2.5 MHz from 10 MHz
    localparam [2:0] HALF_TICKS = 3'd2;

    reg [2:0] div_cnt;

    reg running;       // internal busy
    reg [7:0] shift_reg;     // TX shift
    reg [7:0] rx_shift;      // RX shift
    reg [2:0] bit_cnt;       // counts remaining bits (7..0)

    assign busy = running;
    assign spi_cs_0 = ~open_cs0; // active-low on the pins
    assign spi_cs_1 = ~open_cs1; // active-low on the pins

    always @(posedge clk) begin
        if (rst) begin
            spi_sclk <= 1'b0;       // idle low (CPOL=0)
            spi_mosi <= 1'b0;
            rx_data <= 8'h00;

            div_cnt <= 3'd0;
            running <= 1'b0;

            shift_reg <= 8'h00;
            rx_shift <= 8'h00;
            bit_cnt <= 3'd0;
        end else begin
            if (!running) begin
                // ----- IDLE -----
                spi_sclk <= 1'b0;
                div_cnt <= 3'd0;

                // Start only if a open_cs is high
                if (start_tx && (open_cs0 || open_cs1)) begin
                    running <= 1'b1;
                    shift_reg <= tx_data;
                    rx_shift <= 8'h00;
                    bit_cnt <= 3'd7;

                    // Present MSB before the first rising edge
                    spi_mosi <= tx_data[7];
                end
            end else begin
                // generate SCLK and move data
                if (div_cnt == HALF_TICKS - 1'b1) begin
                    div_cnt <= 3'd0;
                    spi_sclk <= ~spi_sclk;

                    if (spi_sclk == 1'b0) begin
                        // 0 -> 1 : RISING EDGE (sample MISO)
                        rx_shift <= {rx_shift[6:0], spi_miso};

                        if (bit_cnt == 3'd0) begin
                            // Completed 8 samples -> latch and stop
                            rx_data <= {rx_shift[6:0], spi_miso};
                            //running <= 1'b0;
                        end
                    end else begin
                        // 1 -> 0 : FALLING EDGE (update MOSI to next bit)
                        shift_reg <= {shift_reg[6:0], 1'b0};
                        spi_mosi <= shift_reg[6];   // next bit held while SCLK is high
                        if (bit_cnt != 3'd0)
                            bit_cnt <= bit_cnt - 3'd1;
                        else running <= 1'b0;
                    end
                end else begin
                    div_cnt <= div_cnt + 3'd1;
                end
            end
        end
    end

endmodule
