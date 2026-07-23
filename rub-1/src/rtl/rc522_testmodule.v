module rc522_testmodule (
    input wire clk,
    input wire rst,

    input wire setup_transaction,
    input wire start_transaction,
    input wire read_next_byte,

    input wire [511:0] data_in,      // Data to transmit (max 64 bytes)
    input wire [5:0] num_bytes,      // Number of bytes to transmit
    input wire [2:0] len_last_byte,  // Number of valid bits in last byte (1-8, 0=8)
    output wire data_rdy,             // High when receive data is ready
    output wire [511:0] data_out,     // Received data from RC522

    // Status Signals
    output wire busy,                 // High when transaction in progress
    output wire ready_for_transaction,// High when ready to accept new transaction
    output wire ready_for_reading,    // (Currently unused)
    output wire byte_ready,           // (Currently unused)

    // Debug Interface
    output wire [1:0] main_state,     // Current main state for debugging
    output wire [7:0] init_state,     // Current init state for debugging

    // SPI interface to RC522
    output wire       spi_sclk,      // SPI clock
    output wire       spi_mosi,      // SPI MOSI
    input  wire       spi_miso,      // SPI MISO
    output wire       spi_cs_0,      // SPI chip select (active low)
    output wire       spi_cs_1      // SPI chip select (active low)

);

wire spi_busy;
wire spi_start_tx;
wire spi_open_cs0;
wire [7:0] spi_transmit_buffer;
wire [7:0] spi_rx_data;

spi_master spi_inst(
        .clk(clk),
        .rst(rst),
        .start_tx(spi_start_tx),
        .open_cs0(spi_open_cs0),
        
        // we don't have two SPI slaves at the same time
        .open_cs1(0),

        .spi_miso(spi_miso),
        .tx_data(spi_transmit_buffer),

        .busy(spi_busy),
        .spi_sclk(spi_sclk),
        .spi_mosi(spi_mosi),

        .spi_cs_0(spi_cs_0),

        // we don't need it
        .spi_cs_1(spi_cs_1),

        .rx_data(spi_rx_data)
    );


rc522 rc522_inst (
    // Clock and Reset
    .clk(clk),
    .rst(rst),

    // Transaction Control
    .setup_transaction(setup_transaction),    // Setup new transaction with data_in
    .start_transaction(start_transaction),    // (Currently unused - auto-starts after setup)
    .read_next_byte(read_next_byte),       // (Currently unused - reads all at once)

    // Data Interface
    .data_in(data_in),      // Data to transmit (max 64 bytes)
    .num_bytes(num_bytes),      // Number of bytes to transmit
    .len_last_byte(len_last_byte),  // Number of valid bits in last byte (1-8, 0=8)
    .data_rdy(data_rdy),             // High when receive data is ready
    .data_out(data_out),     // Received data from RC522

    // Status Signals
    .busy(busy),                 // High when transaction in progress
    .ready_for_transaction(ready_for_transaction),// High when ready to accept new transaction
    .ready_for_reading(ready_for_reading),    // (Currently unused)
    .byte_ready(byte_ready),           // (Currently unused)

    // Debug Interface
    .main_state(main_state),         // Current main state for debugging
    .init_state(init_state),          // Current init state for debugging

    .spi_start_tx(spi_start_tx),
    .spi_open_cs1(spi_open_cs0),
    .spi_tx_data(spi_transmit_buffer),
    .spi_busy(spi_busy),
    .spi_rx_data(spi_rx_data)
);

endmodule