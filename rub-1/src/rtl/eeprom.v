/*
 Control module for ATMEL AT250xxB series SPI EEPROMs
 Currently supports read operation only*/

module eeprom(
    input wire clk,

    /* Synchronous reset.
     * There is no special procedure taken for resetting the actual EEPROM
     * except for bringing the CS line high, which will abort the current transaction
     * The following parts of chip state are unaffected by the reset
     * - Write enable / disable state
     * - Write operations, there may still be an ongoing operation
     *
     * This should not be of concern to users of the module, as both only apply to writes
     * which are not currently implemented
     */
    input wire rst,

    /* If the module was in idle state previously, will start a new transaction,
       reading a byte from the specified address.
       If a byte read in a transaction has just finished, setting enable to high
       will continue the transfer of the next byte from the memory, using the internal
       address counter of the chip.

       Because of this, it is recommended to pulse this signal for 1 clock cycle from the CPU side
    */
    input wire enable,

    
    /* The byte address to read from */
    input wire [ADDR_BITS-1:0] address,


    output reg [7:0] data_out,
    
    output reg finished,

    // SPI lines to EEPROM, driven by SPI mod
    output reg [7:0] spi_transmit_buffer,
    input wire [7:0] spi_rx_data,
    output reg spi_start_tx,
    input wire spi_busy,
    output reg spi_cs
);

    localparam ADDR_BITS = 7;

    // we don't have address bit A8, set it to zero in the read insn
    localparam EEPROM_INSN_READ = 8'b00000011;

    // our state machine
    // it's a moore machine, so the output depends only on the current state
    // 
    // this means that we have two states for every SPI transaction that we want to do
    // one state that we're in only for 1 cycle, which is responsible for setting up the SPI module
    // and another wait state that we are in while we're waiting for the SPI module to do it's work
    //
    // if we used a mealy machine (whose output can depend on current input as well),
    // we could use only one state per type of SPI transaction, and abuse the input-dependence of the previous state
    // to write the command to the SPI module as we are transitioning into the SPI TXN state
    // (for example, when we are transitioning from the idle state into the SPI insn state)
    // that would make things a bit complicated and annoying to debug though.
    // After all, the EEPROM module is not used too often and therefore not time critical.
    localparam 
        // Reset state of the module. The chip is not active (_CS high)
        STATE_IDLE = 0,

        // The STATE_SPITXN_* states all work in a similar manner
        // - Upon first reaching the state, the internal `spi_wait` reg is set to 0, and the 
        STATE_SPITXN_INSN = 1,
        STATE_SPITXNW_INSN = 2,
        STATE_SPITXN_ADDR = 3,
        STATE_SPITXNW_ADDR = 4,
        STATE_SPITXN_DATA = 5,
        STATE_SPITXNW_DATA = 6,
        STATE_FINISHED = 7;

    
    // state machine state
    reg [3:0] state;

    // address and data registers
    reg [ADDR_BITS-1:0] addr;
    reg [7:0] data;

    // the data we want to transmit. 'buffer' is a bit of a misnomer, it's only a wire
    // and not a register.
    //reg [7:0] spi_transmit_buffer;

    //wire [7:0] spi_rx_data;


    // Starts an SPI transaction
    //reg spi_start_tx;
    //wire spi_busy;

    // the SPI module internally inverts CS, so this one is active high
    //reg spi_cs;

    // the verilator doesn't allow unused signals, give an explicit wire although we dont' need it
    //wire spi_cs_1;

    // our SPI module
    // - Uses SPI mode 0,0 
    // - shifts MSB first
    /*
    spi_master eeprom_spi(
        .clk(clk),
        .rst(rst),
        .start_tx(spi_start_tx),
        .open_cs0(spi_cs),
        
        // we don't have two SPI eeproms at the same time
        .open_cs1(0),

        .spi_miso(eeprom_spi_miso),
        .tx_data(spi_transmit_buffer),

        .busy(spi_busy),
        .spi_sclk(eeprom_spi_sclk),
        .spi_mosi(eeprom_spi_mosi),

        .spi_cs_0(eeprom_spi_cs),

        // we don't need it
        .spi_cs_1(spi_cs_1),

        .rx_data(spi_rx_data)
    );
    */

    // next-state logic, handle state transitions as well as actions on transition
    always @ (posedge clk)
        if (rst) begin
            state <= STATE_IDLE;
            addr <= 0;
            data <= 8'b0;
        end
        else case (state)
            // initiate instruction transfer if we have enable signal
            // read in the data now, so that the module user only has to provide valid data on the clock edge
            // where enable was high first
            STATE_IDLE: if (enable) begin
                state <= STATE_SPITXN_INSN;
                addr <= address;
            end

            // SPI transfer states work the same; immediately transition after we have made transfer,
            // (since all our constant-sized transfers are 1 byte), then stay in wait state
            // the output logic below is responsible for setting up the arguments to the SPI module
            // (i.e. raising enable and providing a word to write) in the execution state
            STATE_SPITXN_INSN : state <=                                      STATE_SPITXNW_INSN;
            STATE_SPITXNW_INSN: state <= !spi_busy ?    STATE_SPITXN_ADDR :   STATE_SPITXNW_INSN;
            STATE_SPITXN_ADDR:  state <=                                      STATE_SPITXNW_ADDR;
            STATE_SPITXNW_ADDR: state <= !spi_busy ?    STATE_SPITXN_DATA :   STATE_SPITXNW_ADDR;
            STATE_SPITXN_DATA:  state <=                                      STATE_SPITXNW_DATA;
            STATE_SPITXNW_DATA: if ( !spi_busy ) begin
                // data must be valid now, read it out
                data <= spi_rx_data;
                state <= STATE_FINISHED;
            end   
            STATE_FINISHED:           if (enable) begin
                // if we raise enable again in the finished state we start another data transfer from the next address
                // we can go immediately to STATE_SPITXN_DATA, which will start another 8-bit SPI read transfer into our internal data reg
                // no need to put insn / addr again
                state <= STATE_SPITXN_DATA;
            end
            // If we don't see enable immediately we stay in the "finished" state. The EEPROM doesn't have any constraints
            // on clock period length, so we can keep the SPI "transaction" open as long as we want,
            // so the main controller can do whatever and request a next byte at any time
            // To start a new transaction, a reset pulse is required to go into idle state, which will finish the txn
            // by pulling _CS high
            else state <= STATE_IDLE;
            default: state <= STATE_IDLE;
        endcase
    
    // i/o logic
    always_comb begin
        // assign default values that make sense in most states and override in the case blocks
        finished = state == STATE_FINISHED;
        data_out = data;
        spi_transmit_buffer = 8'b0;
        spi_start_tx = 1'b0;

        // the chip has to be selected in all except for idle states
        spi_cs = 1'b1;
        case (state)
            STATE_IDLE: spi_cs =1'b0;
            STATE_SPITXN_INSN: begin
                spi_transmit_buffer = EEPROM_INSN_READ;
                spi_start_tx=1'b1;
            end
            STATE_SPITXN_ADDR: begin
                spi_transmit_buffer = {1'b0,addr};
                spi_start_tx=1'b1;
            end
            STATE_SPITXN_DATA: begin
                spi_start_tx = 1'b1;
            end

        endcase
    end
endmodule
