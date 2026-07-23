// Module definition like it is the top module of the chip, can be changed later
module eeprom_testmodule (
    input  wire       clk,           // 10MHz system clock
    input  wire       rst,           // Active high reset

    input wire [6:0] address,
    input wire enable,
    output wire [7:0] data_out,
    output wire finished,

    
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
        
        // we don't have two SPI eeproms at the same time
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

eeprom eeprom_inst(
    .clk(clk),
    .rst(rst),
    .enable(enable),
    .address(address),
    .data_out(data_out),
    .finished(finished),
    .spi_start_tx(spi_start_tx),
    .spi_transmit_buffer(spi_transmit_buffer),
    .spi_rx_data(spi_rx_data),
    .spi_busy(spi_busy),
    .spi_cs(spi_open_cs0)
);

endmodule
