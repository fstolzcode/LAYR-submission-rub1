module rc522_wrapper(
    input wire clk,
    input wire rst,

    input wire en,
    
    input wire do_reset,
    input wire do_push,
    input wire do_pop,
    input wire do_blen,
    input wire do_trcve,
    input wire do_buffer_rst,
    input wire do_rx_num,

    input wire [7:0] data_input,
    output reg [7:0] data_output,

    output wire module_busy,

    output wire spi_start_tx,
    output wire spi_open_cs1,
    output wire [7:0] spi_transmit_buffer,
    input wire spi_busy,
    input wire [7:0] spi_rx_data
);

reg manual_rst;
reg setup_transaction;
reg start_transaction;
reg [511:0] data_in;
reg [6:0] num_bytes;
reg [6:0] num_shifts;
reg [2:0] len_last_byte;
wire data_rdy;
wire [511:0] data_out;

wire busy;
wire ready_for_transaction;

localparam IDLE           = 4'd0;
localparam RST            = 4'd1;
localparam PUSH           = 4'd2;
localparam POP            = 4'd3;
localparam BLEN           = 4'd4;
localparam TRCVE          = 4'd5;
localparam BUFFERRST      = 4'd6;
localparam TRCVE_SHIFT    = 4'd7;
localparam TRCVE_SETUP    = 4'd8;
localparam RST_WAIT       = 4'd9;
localparam RST_INIT       = 4'd10;
localparam RST_READY_WAIT = 4'd11;
localparam RXNUM          = 4'd12;

reg [3:0] state;
wire cmd_start;
wire [5:0] rx_num;

// Treat RC522 as busy until it reports ready; also assert busy on any command start.
assign module_busy = busy | ~ready_for_transaction | en | (state != IDLE);

always @(posedge clk) begin
    if (rst == 1'b1) begin
        manual_rst <= 0;
        setup_transaction <= 0;
        start_transaction <= 0;
        data_in <= 0;
        num_bytes <= 0;
        len_last_byte <= 0;
        data_output <= 0;
        num_shifts <= 0;
        state <= IDLE;
    end else begin
        case(state)
            IDLE: begin
                manual_rst <= 0;
                start_transaction <= 0;
                if(en == 1'b1) begin
                    if(do_reset) state <= RST;
                    else if(do_push) state <= PUSH;
                    else if(do_pop) state <= POP;
                    else if(do_blen) state <= BLEN;
                    else if(do_trcve) state <= TRCVE;
                    else if(do_buffer_rst) state <= BUFFERRST;
                    else if(do_rx_num) state <= RXNUM;
                end else begin
                    state <= IDLE;
                end
            end

            RST: begin
                manual_rst <= 1;
                state <= RST_WAIT;
            end

            RST_WAIT: begin
                manual_rst <= 0;  // Deassert reset
                state <= RST_INIT;
            end

            RST_INIT: begin
                start_transaction <= 1;  // Trigger RC522 initialization
                state <= RST_READY_WAIT;
            end

            RST_READY_WAIT: begin
                start_transaction <= 0;
                if (ready_for_transaction) begin
                    state <= IDLE;  // RC522 fully initialized
                end
            end
            
            RXNUM: begin
                data_output <= {2'b0, rx_num};
                state <= IDLE;
            end
            
            PUSH: begin
                data_in <= {data_in[503:0],data_input};
                num_bytes <= num_bytes + 1;
                state <= IDLE;
            end

            POP: begin
                data_output <= data_in[511:504];
                data_in <= {data_in[503:0],8'b0};
                state <= IDLE;
            end

            BLEN: begin
                len_last_byte <= data_input[2:0];
                state <= IDLE;
            end

            BUFFERRST: begin
                data_in <= 0;
                num_bytes <= 0;
                len_last_byte <= 0;
                state <= IDLE;
            end

            TRCVE: begin
                num_shifts <= 7'd64 - num_bytes;
                state <= TRCVE_SHIFT;
            end

            TRCVE_SHIFT: begin
                if(num_shifts == 0) begin
                    setup_transaction <= 1;
                    if (busy == 1'b1) state <= TRCVE_SETUP;
                end else begin
                    data_in <= {data_in[503:0],8'b0};
                    num_shifts <= num_shifts - 1;
                end
            end

            TRCVE_SETUP: begin
                setup_transaction <= 0;
                if (data_rdy == 1'b1) begin
                    data_in <= data_out;
                    state <= IDLE;
                end else if (busy == 1'b0) begin
                    // Failure: RC522 finished (Timeout/Error) but no data
                    // Abort and return to IDLE so CPU can continue
                    state <= IDLE;
                end
            end

            default: begin
                state <= IDLE;
            end
        endcase
    end
end

/* verilator lint_off PINCONNECTEMPTY */
rc522 rc522_inst (
    // Clock and Reset
    .clk(clk),
    .rst(rst | manual_rst),

    // Transaction Control
    .setup_transaction(setup_transaction),    // Setup new transaction with data_in
    .start_transaction(start_transaction),    // Trigger RC522 initialization sequence

    // Data Interface
    .data_in(data_in),      // Data to transmit (max 64 bytes)
    .num_bytes(num_bytes[5:0]),      // Number of bytes to transmit
    .len_last_byte(len_last_byte),  // Number of valid bits in last byte (1-8, 0=8)
    .data_rdy(data_rdy),             // High when receive data is ready
    .data_out(data_out),     // Received data from RC522
    .rx_num_bytes(rx_num),         // Number of valid bytes in data_out (unconnected)

    // Status Signals
    .busy(busy),                 // High when transaction in progress
    .ready_for_transaction(ready_for_transaction),// High when ready to accept new transaction

    // Debug Interface
    .main_state(),         // Current main state for debugging
    .init_state(),          // Current init state for debugging

    .spi_start_tx(spi_start_tx),
    .spi_open_cs1(spi_open_cs1),
    .spi_tx_data(spi_transmit_buffer),
    .spi_busy(spi_busy),
    .spi_rx_data(spi_rx_data)
);
endmodule
/* verilator lint_on PINCONNECTEMPTY */
