// Module definition like it is the top module of the chip, can be changed later
module main_controller (
    input  wire       clk,           // 10MHz system clock
    input  wire       uart_clk_in,
    input  wire       rst,           // Active high reset

    input wire        mode,          // Debug switch



    // UART interface
    input  wire       uart_rxd,      // UART receive
    output wire       uart_txd,      // UART transmit

    // SPI interface to RC522
    output wire       spi_sclk,      // SPI clock
    output wire       spi_mosi,      // SPI MOSI
    input  wire       spi_miso,      // SPI MISO
    output wire       spi_cs_0,      // SPI chip select (active low)
    output wire       spi_cs_1,      // SPI chip select (active low)

    output wire       busy,         // we are busy doing something
    output wire       hard_fault,   // error that can not be recovered from
    output wire       unlock        // Unlock the door
);
    /* verilator lint_off UNUSEDPARAM */
    // FSM State encoding
    localparam FETCH        = 4'd0;
    localparam EXECUTE      = 4'd1;
    localparam WRITEBACK    = 4'd2;
    localparam WAIT_CRC     = 4'd3;
    localparam WAIT_EEPROM  = 4'd4;
    localparam WAIT_RC522   = 4'd5;
    localparam WAIT_INSROMRD= 4'd6;
    localparam WAIT_AES     = 4'd7;
    localparam WAIT_RNG		= 4'd8;
    localparam WAIT_UARTTX_1 = 4'd9;
    localparam WAIT_UARTTX_2 = 4'd10;
    localparam WAIT_SPIDBG = 4'd11;
    localparam WAIT_SPIDBG_START = 4'd12;
    localparam WAIT_CRCP  = 4'd13;
    // Instruction Opcodes encoding: 18-bit word
    // [17:12] opcode (6 bit)
    // [11:6]  src    (6 bit RAM address or immediate)
    // [5:0]   dest   (6 bit RAM address)
    //
    // Assigning arbitrary 8-bit values for definition
    localparam [5:0] OP_CRCRST          = 6'd0;  // CRC Reset (no operands)
    localparam [5:0] OP_CRCLD           = 6'd1;  // Load RAM[src] byte into CRC
    localparam [5:0] OP_CRCH            = 6'd2;  // Write CRC HIGH byte to RAM[dest]
    localparam [5:0] OP_CRCL            = 6'd3;  // Write CRC LOW  byte to RAM[dest]
    localparam [5:0] OP_ROMRST          = 6'd4;  // ROM Reset (No operands)
    localparam [5:0] OP_ROMRD           = 6'd5;  // Read from EEPROM ADDR to RAM ADDR (RAM ADDR, RAM ADDR)

    localparam [5:0] OP_RC522RST        = 6'd6;  // RC522 RST
    localparam [5:0] OP_RC522PUSH       = 6'd7;  // Push data to FIFO
    localparam [5:0] OP_RC522POP        = 6'd8;  // Pop data from FIFO
    localparam [5:0] OP_RC522BLEN       = 6'd9;  // Set len of last byte
    localparam [5:0] OP_RC522TRCVE      = 6'd10; // Start Transceive
    localparam [5:0] OP_RC522BUFRST     = 6'd11; // Buffer Reset
    localparam [5:0] OP_RC522WAIT       = 6'd12; // Wait for busy to go low

    localparam [5:0] OP_RNGRST          = 6'd13; // Reset RNG (No operands)
    localparam [5:0] OP_RNGGET          = 6'd14; // Get Randomness into RAM address (RAM ADDR)

    localparam [5:0] OP_CMPEQ           = 6'd15; // Compare two RAM addresses (RAM ADDR, RAM ADDR)
    localparam [5:0] OP_CMPLT           = 6'd16; // Compare two RAM addresses (RAM ADDR, RAM ADDR)
    localparam [5:0] OP_JMPC            = 6'd17; // If CMP flag set jump (JUMP ADDR)
    localparam [5:0] OP_JMPNC           = 6'd24; // If CMP flag is not set jump (JUMP ADDR)
    localparam [5:0] OP_JUMPE           = 6'd18; // If Error flag set jump (JUMP ADDR)
    localparam [5:0] OP_CALL            = 6'd19; // Push return to stack (JUMP ADDR)
    localparam [5:0] OP_RET             = 6'd20; // Pop return from stack
    localparam [5:0] OP_REP             = 6'd28; // FOR BAR in 0..arg2 DO rom[pc:pc+arg1] (any branch will implicitly break the loop)
    localparam [5:0] OP_CRCPW           = 6'd29; // Add explanation here
    localparam [5:0] OP_CRCPC           = 6'd47; // Add explanation here
    localparam [5:0] OP_RPTZ            = 6'd48; // Add explanation here

    localparam [5:0] OP_ADD             = 6'd21; // Add arg1 arg2, overwrite arg2
    localparam [5:0] OP_XOR             = 6'd22; // xor arg1 arg2, overwrite arg2
    localparam [5:0] OP_AND             = 6'd23; // and arg1 arg2, overwrite arg2


    localparam [5:0] OP_INSROMRDL     = 6'd25; // read from relative ROM address low byte into ram[arg2]
    localparam [5:0] OP_INSROMRDH     = 6'd26; // read from relative ROM address high byte into ram[arg2]

    localparam [5:0] OP_MOV           = 6'd27; // mov ram[arg1] to ram[arg2]
    localparam [5:0] OP_IMOV			= 6'd30;

    //localparam [5:0] OP_AESENC        = 6'd28; // AES encrypt: data@arg1, key@arg2 (share1 at +16)
    //localparam [5:0] OP_AESDEC        = 6'd29; // AES decrypt: data@arg1, key@arg2 (share1 at +16)

    localparam [5:0] OP_IMMLD00         = 6'd60; // Load Immediate to RAM (00IIII, RAM ADDR)
    localparam [5:0] OP_IMMLD01         = 6'd61; // Load Immediate to RAM (01IIII, RAM ADDR)
    localparam [5:0] OP_IMMLD10         = 6'd62; // Load Immediate to RAM (10IIII, RAM ADDR)
    localparam [5:0] OP_IMMLD11         = 6'd63; // Load Immediate to RAM (11IIII, RAM ADDR)

    localparam [5:0] OP_AESRST        = 6'd31; //
    localparam [5:0] OP_AESPUSHD      = 6'd32; //
    localparam [5:0] OP_AESPUSHK0     = 6'd33; //
    localparam [5:0] OP_AESPUSHK1     = 6'd34; //
    localparam [5:0] OP_AESPOP        = 6'd35; //
    localparam [5:0] OP_AESMODE       = 6'd36; //
    localparam [5:0] OP_AESSTART      = 6'd37; //
    localparam [5:0] OP_AESBUFRST     = 6'd38; //

    localparam [5:0] OP_RC522RXNUM    = 6'd39;
    localparam [5:0] OP_UARTTX        = 6'd40;
    localparam [5:0] OP_SMOV          = 6'd41;
    localparam [5:0] OP_LOCK          = 6'd42;

    localparam [5:0] OP_SPIDBG        = 6'd43;
    localparam [5:0] OP_SPICS         = 6'd44;
    localparam [5:0] OP_SPITX         = 6'd45;

    localparam [5:0] OP_STACKFLSH     = 6'd46;
    /* verilator lint_on UNUSEDPARAM */

    // Some instructions use relative addressing, which may be changed using
    // a repeat instruction.
    reg [5:0] ram_base_register;
    reg [5:0] repeat_cnt;
    reg [9:0] repeat_pc0;
    reg [9:0] repeat_pcn;

    // Internal signals
    reg [9:0] pc;          // Program Counter (10-bit for 1024 byte ROM)
    reg [9:0] pc_backup;
    reg [3:0] state;       // Current state

    reg [5:0] opcode;      // Current instruction
    reg [5:0] arg1;        // OP argument one (if any)
    reg [5:0] arg2;        // OP argument two (if any)
    reg [7:0] ram_arg1;
    reg [7:0] ram_arg2;
    reg [7:0] result;

    reg       cmp_flag;     // 1-bit Comparator Flag
    reg       err_flag;     // 1-bit Error Flag

    // RAM
    reg [7:0]  ram_data [0:63];     // 64 Bytes, 8-bit data

    // ROM interface
    wire [8:0] rom_addr;
    wire [17:0] rom_data;


    wire [9:0] dbg_rom_addr;
    wire [17:0] dbg_rom_data;
    // Connect PC to ROM address
    assign rom_addr = pc[8:0];

    // Instantiate ROM module
    rom rom_inst (
        .address(rom_addr),
        .data(rom_data),

        .dbg_address(dbg_rom_addr[8:0]),
        .dbg_data(dbg_rom_data)
    );

    // SPI
    wire spi_busy;
    wire spi_start_tx;
    wire [7:0] spi_transmit_buffer;
    wire [7:0] spi_rx_data;
    wire spi_open_cs0;
    wire spi_open_cs1;

    wire [7:0] spi_transmit_buffer_eeprom;
    wire [7:0] spi_transmit_buffer_rc522;

    wire spi_start_tx_eeprom;
    wire spi_start_tx_rc522;

    assign spi_transmit_buffer = (spi_open_cs0 == 1'b1) ? spi_transmit_buffer_eeprom : spi_transmit_buffer_rc522;
    assign spi_start_tx = (spi_open_cs0 == 1'b1) ? spi_start_tx_eeprom : spi_start_tx_rc522;

    // RC522
    reg rc522_en;
    reg rc522_reset;
    reg rc522_push;
    reg rc522_pop;
    reg rc522_blen;
    reg rc522_trcve;
    reg rc522_buffer_rst;
    reg rc522_rx_num;

    reg [7:0] rc522_data_input;
    wire [7:0] rc522_data_output;
    wire rc522_busy;
    rc522_wrapper rc522_wrapper_inst(
        .clk(clk),
        .rst(rst),

        .en(rc522_en),

        .do_reset(rc522_reset),
        .do_push(rc522_push),
        .do_pop(rc522_pop),
        .do_blen(rc522_blen),
        .do_trcve(rc522_trcve),
        .do_buffer_rst(rc522_buffer_rst),
        .do_rx_num(rc522_rx_num),

        .data_input(rc522_data_input),
        .data_output(rc522_data_output),

        .module_busy(rc522_busy),

        .spi_start_tx(spi_start_tx_rc522),
        .spi_open_cs1(spi_open_cs1),
        .spi_transmit_buffer(spi_transmit_buffer_rc522),
        .spi_busy(spi_busy),
        .spi_rx_data(spi_rx_data)
    );

    // EPROM
    reg eeprom_enable;
    reg eeprom_rst;
    reg [6:0] eeprom_address;
    wire [7:0] eeprom_data;
    wire eeprom_done;
    eeprom eeprom_inst(
        .clk(clk),
        .rst(rst | eeprom_rst),
        .enable(eeprom_enable),
        .address(eeprom_address),
        .data_out(eeprom_data),
        .finished(eeprom_done),
        .spi_start_tx(spi_start_tx_eeprom),
        .spi_transmit_buffer(spi_transmit_buffer_eeprom),
        .spi_rx_data(spi_rx_data),
        .spi_busy(spi_busy),
        .spi_cs(spi_open_cs0)
    );

    // SPI
    reg spi_dbg;
    reg [1:0] spi_dbg_cs;
    reg [7:0] spi_dbg_transmit;
    reg spi_dbg_tx_start;
    spi_master spi_inst(
        .clk(clk),
        .rst(rst),
        .start_tx((spi_dbg == 1'b1) ? spi_dbg_tx_start : spi_start_tx),
        .open_cs0((spi_dbg == 1'b1) ? spi_dbg_cs[0] : spi_open_cs0),

        // we don't have two SPI eeproms at the same time
        .open_cs1((spi_dbg == 1'b1) ? spi_dbg_cs[1] : spi_open_cs1),
        .tx_data((spi_dbg == 1'b1) ? spi_dbg_transmit : spi_transmit_buffer),

        .busy(spi_busy),
        .spi_sclk(spi_sclk),
        .spi_mosi(spi_mosi),
        .spi_miso(spi_miso),

        .spi_cs_0(spi_cs_0),

        .spi_cs_1(spi_cs_1),

        .rx_data(spi_rx_data)
    );

    // CRC core interface
    wire [15:0] crc_out;
    wire        crc_busy;
    reg  [7:0]  crc_data_in;
    reg         crc_load_byte;
    reg         crc_rst;

    wire        crc_rst_internal = rst | crc_rst;

    crc crc_inst (
        .clk       (clk),
        .rst       (crc_rst_internal),
        .data_in   (crc_data_in),
        .load_byte (crc_load_byte),
        .crc_out   (crc_out),
        .busy      (crc_busy)
    );

    reg rng_rst;
    wire [339:0] rng_stream_out;
    wire rng_rdy;
    trivium #(.OUTPUT_BITS(340)) rng_inst(
        .clk(clk),
        .rst(rng_rst|rst),
        .enable(1'b1),
        .key(80'hc38f1ab524d9c7e99251), //CHANGE LATER
        .iv(80'h33d38b1cfaf7092c8060), //CHANGE LATER
        .stream_out(rng_stream_out),
        .rdy(rng_rdy)
    );

    reg aes_en;
    reg aes_reset;
    reg aes_push_d;
    reg aes_push_k0;
    reg aes_push_k1;
    reg aes_pop;
    reg aes_set_mode;
    reg aes_start;
    reg aes_buffer_rst;
    reg [7:0] aes_in;
    wire [7:0] aes_out;
    wire aes_busy;

    aes_wrapper aes_wrapper_inst(
        .clk(clk),
        .rst(rst),

        .en(aes_en),

        .do_reset(aes_reset),
        .do_push_data(aes_push_d),
        .do_push_key0(aes_push_k0),
        .do_push_key1(aes_push_k1),
        .do_pop(aes_pop),
        .do_set_mode(aes_set_mode),
        .do_start(aes_start),
        .do_buffer_rst(aes_buffer_rst),

        .data_input(aes_in),
        .data_output(aes_out),

        .randomness(rng_stream_out[331:0]),

        .module_busy(aes_busy)
    );

    // Call stack
    reg [9:0] call_stack [0:3];
    reg [1:0] call_sp;
    reg call_full;

    // UART MULTIPLEX
    reg [7:0] cpu_uarttx_data;
    reg cpu_uarttx_en;
    wire cpu_uarttx_ready;

    // Instruction / immediate data
    // either fetched from acutal ROM or debugger IRAM
    wire [17:0] muxed_rom_data;
    assign muxed_rom_data = pc[9] ? dbg_iram[pc[8:0]] : rom_data; // 8:0 = $clog2(512)-1:0

    // debug controller reset
    `define dbg_reset_fsm \
        begin \
            dbgcr <= 2'b0; \
            dbg_state <= 0; \
            dbg_num_params <= 0; \
            dbg_params_index <= 0; \
            dbg_breakpoints[0] <= 11'h0; \
            dbg_breakpoints[1] <= 11'h0; \
            dbg_breakpoints[2] <= 11'h0; \
            dbg_breakpoints[3] <= 11'h0; \
            dbg_breakpoints[4] <= 11'h0; \
            dbg_breakpoints[5] <= 11'h0; \
            dbg_breakpoints[6] <= 11'h0; \
            dbg_breakpoints[7] <= 11'h0; \
            dbg_insn <= 8'h0; \
            dbg_num_returns <= 5'h0; \
            dbg_params <= 144'h0; \
        end

    reg unlock_reg;
    assign unlock = unlock_reg;
    reg busy_reg;
    assign busy = busy_reg;
    reg hard_fault_reg;
    assign hard_fault = hard_fault_reg;

    // Main FSM - synchronous state machine
    always @(posedge clk) begin
        if (rst || (dbg_initialized && ~mode)) begin
            // Synchronous reset: initialize PC and state
            pc <= 10'b0;
            pc_backup <= 10'b0;
            state <= FETCH;

            // Reset instruction registers
            opcode <= 6'h00;
            arg1 <= 6'h00;
            arg2 <= 6'h00;

            // Reset Flags
            cmp_flag <= 1'b0;
            err_flag <= 1'b0;

            // Reset CRC interface
            crc_data_in   <= 8'h00;
            crc_load_byte <= 1'b0;
            crc_rst  <= 1'b0;

            // Reset internal signals
            ram_arg1 <= 0;
            ram_arg2 <= 0;
            result <= 0;

            // Reset AES interface
            /*
            aes_start <= 1'b0;
            aes_start_pending <= 1'b0;
            aes_enc_mode <= 1'b1;
            aes_data_in_0 <= 128'd0;
            aes_data_in_1 <= 128'd0;
            aes_key_0 <= 128'd0;
            aes_key_1 <= 128'd0;
            aes_out_0 <= 128'd0;
            aes_out_1 <= 128'd0;
            */
            aes_en <= 0;
            aes_reset <= 0;
            aes_push_d <= 0;
            aes_push_k0 <= 0;
            aes_push_k1 <= 0;
            aes_pop <= 0;
            aes_set_mode <= 0;
            aes_start <= 0;
            aes_buffer_rst <= 0;
            aes_in <= 0;

            // RNG
            rng_rst <= 0;

            // RC522
            rc522_en <= 0;
            rc522_reset <= 0;
            rc522_push <= 0;
            rc522_pop <= 0;
            rc522_blen <= 0;
            rc522_trcve <= 0;
            rc522_buffer_rst <= 0;
            rc522_rx_num <= 0;

            rc522_data_input <= 0;

            // Reset RAM
            for (dbg_ram_i = 0; dbg_ram_i < 64; dbg_ram_i = dbg_ram_i + 1) ram_data[dbg_ram_i] <= 8'h00;

            // EEPROM
            eeprom_enable <= 0;
            eeprom_address <= 0;
            eeprom_rst <= 0;

            // Reset call stack
            call_sp <= 0;
            call_full <= 0;
            call_stack[0] <= 10'h0;
            call_stack[1] <= 10'h0;
            call_stack[2] <= 10'h0;
            call_stack[3] <= 10'h0;

            cpu_uarttx_data <= 0;
            cpu_uarttx_en <= 0;

            unlock_reg <= 0;
            busy_reg <= 0;
            hard_fault_reg <= 0;

            spi_dbg <= 0;
            spi_dbg_cs <= 0;
            spi_dbg_transmit <= 0;
            spi_dbg_tx_start <= 0;

            ram_base_register <= 0;
            repeat_cnt <= 0;
            repeat_pc0 <= 10'h0;
            repeat_pcn <= 10'h0;
        end else begin
            busy_reg <= 1;
            case (state)
                FETCH: begin
                    // register-writing for debug engine. has been pulled out of its always block and moved here to avoid multi-driven nets
                    if (mode && dbg_state == DBG_EXECUTE && dbg_insn == DBG_OP_WRREG) begin
                        // note: writes for the CPU-internal registers are implemented in the CPU FETCH state, in its always block
                        // to avoid multi-driven net issues
                        case (dbg_params[15:14])
                            DBG_REGSZ_1:
                                case (dbg_params[13:0])
                                    DBG_REG1_SP: call_sp <= dbg_params[17:16];
                                    // DBG_REG1_DBGCR: < written from debug FSM always block >
                                    DBG_REG1_CALLFULL: call_full <= dbg_params[16];
                                    default:
                                    if ($unsigned(dbg_params[13:0] - DBG_REG1_CPUREG) < 14'd64) ram_data[dbg_params[13:0] - DBG_REG1_CPUREG] <= dbg_params[23:16];
                                endcase
                            DBG_REGSZ_2:
                                case (dbg_params[13:0])
                                    DBG_REG2_PC: pc <= dbg_params[25:16];
                                    default:
                                    if ($unsigned(dbg_params[13:0] - DBG_REG2_STACK) < 14'h4) call_stack[dbg_params[13:0] - DBG_REG2_STACK] <= dbg_params[25:16];
                                endcase
                            default: ;
                        endcase
                    end
                    if (dbg_run_cpu) begin
                        // Fetch instruction fields
                        opcode <= muxed_rom_data[17:12];
                        arg1 <= muxed_rom_data[11:6];
                        arg2 <= muxed_rom_data[5:0];
                        ram_arg1 <= ram_data[ram_base_register + muxed_rom_data[11:6]];
                        ram_arg2 <= ram_data[ram_base_register + muxed_rom_data[5:0]];

                        state <= EXECUTE;
                    end
                end

                WAIT_CRCP: begin
                    // load byte must only be high for one cycle
                    crc_load_byte <= 1'b0;
                    state <= WAIT_CRCP;

                    // crc_busy is delayed two cycles. If we are not busy and
                    // our last request was not to load, then load another
                    // byte.
                    if (!crc_load_byte && !crc_busy) begin
                        if (repeat_cnt > 0) begin
                            crc_load_byte <= 1'b1;

                            // data is buffered internally while not in idle state
                            crc_data_in <= ram_data[ram_base_register];

                            // either first load or done loading, doesn't matter.
                            // Just provide new data after it is done again.
                            ram_base_register <= ram_base_register + 1;
                            repeat_cnt <= repeat_cnt - 1;
                            crc_load_byte <= 1'b1;
                        end else begin
                            state <= WRITEBACK;
                        end
                    end
                end

                EXECUTE: begin
                    // Opcode and Args are ready.
                    // arg1 holds the first operand (e.g., Imm or RAM ADDR)
                    // arg2 holds the second operand (e.g., Imm or RAM ADDR)
                    case (opcode)
                        OP_RPTZ: begin
                            ram_base_register <= 0;
                            repeat_cnt <= 0;
                            state <= WRITEBACK;
                        end
                        OP_STACKFLSH: begin
                            call_sp <= 0;
                            call_full <= 0;
                            state <= WRITEBACK;
                        end
                        OP_CRCPC: begin
                            ram_base_register <= arg1;
                            repeat_cnt <= arg2;
                            state <= WAIT_CRCP;
                        end
                        OP_CRCPW: begin
                            ram_base_register <= arg1;
                            repeat_cnt <= arg2;
                            state <= WAIT_CRCP;
                        end
                        OP_REP: begin
                            repeat_pc0 <= pc + 10'b0000000001;
                            repeat_pcn <= pc + {4'b0000,arg1};
                            ram_base_register <= 0;
                            repeat_cnt <= arg2;
                            state <= WRITEBACK;
                        end

                        OP_SPIDBG: begin
                            spi_dbg <= arg1[0];
                            state <= WRITEBACK;
                        end

                        OP_SPICS: begin
                            spi_dbg_cs <= arg1[1:0];
                            state <= WRITEBACK;
                        end

                        OP_SPITX: begin
                            spi_dbg_transmit <= ram_arg1;
                            spi_dbg_tx_start <= 1'b1;
                            state <= WAIT_SPIDBG_START;
                        end

                        OP_LOCK: begin
                            unlock_reg <= arg1[0];
                            state <= WRITEBACK;
                        end
                        OP_SMOV: begin
                            result <= ram_arg1;
                            state <= WRITEBACK;
                        end
                        OP_UARTTX: begin
                            if(mode) begin
                                // If DBG is on, UARTTX is ignored
                                state <= WRITEBACK;
                            end else begin
                                if (cpu_uarttx_ready == 1'b0) begin
                                    ;
                                end else begin
                                    cpu_uarttx_data <= ram_arg1;
                                    cpu_uarttx_en <= 1;
                                    state <= WAIT_UARTTX_1;
                                end
                            end
                        end
                        OP_AESRST: begin
                            aes_en <= 1;
                            aes_reset <= 1;
                            state <= WAIT_AES;
                        end

                        OP_AESPUSHD: begin
                            aes_en <= 1;
                            aes_push_d <= 1;
                            aes_in <= ram_arg1;
                            state <= WAIT_AES;
                        end

                        OP_AESPUSHK0: begin
                            aes_en <= 1;
                            aes_push_k0 <= 1;
                            aes_in <= ram_arg1;
                            state <= WAIT_AES;
                        end

                        OP_AESPUSHK1: begin
                            aes_en <= 1;
                            aes_push_k1 <= 1;
                            aes_in <= ram_arg1;
                            state <= WAIT_AES;
                        end

                        OP_AESBUFRST: begin
                            aes_en <= 1;
                            aes_buffer_rst <= 1;
                            state <= WAIT_AES;
                        end

                        OP_AESMODE: begin
                            aes_en <= 1;
                            aes_set_mode <= 1;
                            aes_in <= {2'b0,arg1};
                            state <= WAIT_AES;
                        end

                        OP_AESSTART: begin
                            aes_en <= 1;
                            aes_start <= 1;
                            state <= WAIT_AES;
                        end

                        OP_AESPOP: begin
                            aes_en <= 1;
                            aes_pop <= 1;
                            state <= WAIT_AES;
                        end

                        OP_RC522WAIT: begin
                            if(rc522_busy == 1'b0) state <= WRITEBACK;
                            else state <= EXECUTE;  // Keep polling while busy
                        end

                        OP_RC522RST: begin
                            rc522_en <= 1;
                            rc522_reset <= 1;
                            state <= WAIT_RC522;
                        end

                        OP_RC522PUSH: begin
                            rc522_en <= 1;
                            rc522_push <= 1;
                            rc522_data_input <= ram_arg1;
                            state <= WAIT_RC522;
                        end

                        OP_RC522POP: begin
                            rc522_en <= 1;
                            rc522_pop <= 1;
                            state <= WAIT_RC522;
                        end

                        OP_RC522BLEN: begin
                            rc522_en <= 1;
                            rc522_blen <= 1;
                            rc522_data_input <= {2'b0, arg1};
                            state <= WAIT_RC522;
                        end

                        OP_RC522BUFRST: begin
                            rc522_en <= 1;
                            rc522_buffer_rst <= 1;
                            state <= WAIT_RC522;
                        end

                        OP_RC522TRCVE: begin
                            rc522_en <= 1;
                            rc522_trcve <= 1;
                            state <= WAIT_RC522;
                        end

                        OP_RC522RXNUM: begin
                            rc522_en <= 1;
                            rc522_rx_num <= 1;
                            state <= WAIT_RC522;
                        end

                        // CRC Reset: soft reset the CRC core
                        OP_CRCRST: begin
                            crc_rst <= 1'b1;
                            state <= WRITEBACK;
                        end

                        // Load RAM[src] byte into CRC core and wait until done
                        OP_CRCLD: begin
                            // Feed the selected RAM byte into CRC core
                            crc_data_in <= ram_arg1;
                            crc_load_byte <= 1'b1;
                            if (crc_busy) begin
                                state <= WAIT_CRC;
                            end else begin
                                state <= EXECUTE;
                            end
                        end

                        // Write CRC high byte to RAM[dest]
                        OP_CRCH: begin
                            //ram_data[arg1] <= crc_out[15:8];
                            result <= crc_out[15:8];
                            state <= WRITEBACK;
                        end

                        // Write CRC low byte to RAM[dest]
                        OP_CRCL: begin
                            //ram_data[arg1] <= crc_out[7:0];
                            result <= crc_out[7:0];
                            state <= WRITEBACK;
                        end

                        OP_ROMRST: begin
                            eeprom_rst <= 1;
                            state <= WRITEBACK;
                        end

                        OP_ROMRD: begin
                            eeprom_address <= {1'b0, ram_base_register} + {1'b0, arg1};
                            eeprom_enable <= 1;
                            state <= WAIT_EEPROM;
                        end

                        OP_IMMLD00, OP_IMMLD01, OP_IMMLD10, OP_IMMLD11: begin
                            //ram_data[arg2] <= {opcode[1:0], arg1};
                            result <= {opcode[1:0], arg1};
                            state <= WRITEBACK;
                        end

                        OP_CMPEQ: begin
                            cmp_flag <= ram_arg1 == ram_arg2;
                            state <= WRITEBACK;
                        end

                        OP_CMPLT: begin
                            cmp_flag <= ram_arg1 < ram_arg2;
                            state <= WRITEBACK;
                        end

                        OP_ADD: begin
                            result <= ram_arg1 + ram_arg2;
                            state <= WRITEBACK;
                        end

                        OP_XOR: begin
                            result <= ram_arg1 ^ ram_arg2;
                            state <= WRITEBACK;
                        end

                        OP_AND: begin
                            result <= ram_arg1 & ram_arg2;
                            state <= WRITEBACK;
                        end

                        OP_INSROMRDH, OP_INSROMRDL: begin
                            pc_backup <= pc;
                            pc <= pc + {4'b0, arg1};
                            state <= WAIT_INSROMRD;
                        end

                        OP_MOV: begin
                            result <= ram_arg1;
                            state <= WRITEBACK;
                        end

                        /*
                        OP_AESENC, OP_AESDEC: begin
                            aes_enc_mode <= (opcode == OP_AESENC);
                            aes_start_pending <= 1'b1;
                            for (integer i = 0; i < 16; i = i + 1) begin
                                aes_data_in_0[i*8 +: 8] <= ram_data[{26'd0, arg1} + i];
                                aes_data_in_1[i*8 +: 8] <= ram_data[{26'd0, arg1} + 32'd16 + i];
                                aes_key_0[i*8 +: 8] <= ram_data[{26'd0, arg2} + i];
                                aes_key_1[i*8 +: 8] <= ram_data[{26'd0, arg2} + 32'd16 + i];
                            end
                            state <= WAIT_AES;
                        end
                        */
                        OP_IMOV: begin
                            result <= ram_data[ram_base_register + ram_arg1[5:0]];
                            state <= WRITEBACK;
                        end

                        OP_RNGRST: begin
                            rng_rst <= 1;
                            state <= WRITEBACK;
                        end

                        OP_RNGGET: begin
                            if (rng_rdy) begin
                                result <= rng_stream_out[339:332];
                                state <= WRITEBACK;
                            end else begin
                                state <= WAIT_RNG;
                            end
                        end

                        OP_JMPC, OP_JMPNC, OP_CALL, OP_RET, OP_JUMPE: begin
                            state <= WRITEBACK;
                        end

                        // TODO: Add other cases
                        default: begin
                            hard_fault_reg <= 1;
                            // NOP - No operation
                            state <= WRITEBACK;
                        end
                    endcase
                end

                WAIT_UARTTX_1: begin
                    if (cpu_uarttx_ready == 1'b0) begin
                        state <= WAIT_UARTTX_2;
                    end
                end

                WAIT_UARTTX_2: begin
                    if (cpu_uarttx_ready == 1'b1) begin
                        cpu_uarttx_en <= 1'b0;
                        state <= WRITEBACK;
                    end
                end

                WAIT_INSROMRD: begin
                    pc <= pc_backup;
                    case(opcode)
                        OP_INSROMRDL: begin
                            result <= muxed_rom_data[7:0];
                            state <= WRITEBACK;
                        end
                        OP_INSROMRDH: begin
                            result <= muxed_rom_data[15:8];
                            state <= WRITEBACK;
                        end
                        default: begin
                            result <= muxed_rom_data[7:0];
                            state <= WRITEBACK;
                        end
                    endcase
                end

                WAIT_SPIDBG_START: begin
                    spi_dbg_tx_start <= 1'b0;
                    if(spi_busy == 1) begin
                        state <= WAIT_SPIDBG;
                    end
                end
                WAIT_SPIDBG: begin
                    spi_dbg_tx_start <= 1'b0;
                    if(spi_busy == 0) begin
                        result <= spi_rx_data;
                        state <= WRITEBACK;
                    end
                end

                WAIT_RC522: begin
                    rc522_en <= 0;
                    rc522_reset <= 0;
                    rc522_push <= 0;
                    rc522_pop <= 0;
                    rc522_blen <= 0;
                    rc522_trcve <= 0;
                    rc522_buffer_rst <= 0;
                    rc522_rx_num <= 0;
                    if (rc522_busy) begin
                        state <= WAIT_RC522;
                    end else begin
                        result <= rc522_data_output;
                        state <= WRITEBACK;
                    end
                end

                WAIT_EEPROM: begin
                    eeprom_enable <= 0;
                    if(eeprom_done) begin
                        result <= eeprom_data;
                        state <= WRITEBACK;
                    end else begin
                        state <= WAIT_EEPROM;
                    end
                end
                WAIT_AES: begin
                    // Clear all AES control signals immediately upon entering
                    aes_en <= 0;
                    aes_reset <= 0;
                    aes_push_d <= 0;
                    aes_push_k0 <= 0;
                    aes_push_k1 <= 0;
                    aes_pop <= 0;
                    aes_set_mode <= 0;
                    aes_start <= 0;
                    aes_buffer_rst <= 0;

                    // Wait for wrapper to complete operation
                    if (aes_busy) begin
                        state <= WAIT_AES;
                    end else begin
                        // Capture output for POP operations
                        result <= aes_out;
                        state <= WRITEBACK;
                    end
                end

                // Wait for CRC core to finish processing the current byte
                WAIT_CRC: begin
                    crc_load_byte <= 0;

                    // Stay in WAIT_CRC until we see crc_busy == low
                    if (!crc_busy) begin
                        // CRC finished
                        state <= WRITEBACK;
                    end else begin
                        // Still waiting (CRC starting, processing, or not started yet)
                        state <= WAIT_CRC;
                    end
                end

                WAIT_RNG: begin
                    if (rng_rdy) begin
                        result <= rng_stream_out[339:332];
                        state <= WRITEBACK;
                    end else begin
                        state <= WAIT_RNG;
                    end
                end

                WRITEBACK: begin
                    case (opcode)
                        OP_CRCPC: begin
                            cmp_flag <= (ram_data[ram_base_register + 0] == crc_out[ 7: 0]) && (ram_data[ram_base_register + 1] == crc_out[15: 8]);
                            ram_base_register <= 0;
                        end
                        OP_CRCPW: begin
                            ram_data[ram_base_register + 0] <= crc_out[ 7: 0];
                            ram_data[ram_base_register + 1] <= crc_out[15: 8];
                            ram_base_register <= 0;
                        end
                        OP_CRCH, OP_CRCL, OP_RC522POP, OP_AESPOP, OP_RNGGET, OP_RC522RXNUM: begin
                            ram_data[ram_base_register + arg1] <= result;
                        end
                        OP_SPITX, OP_MOV, OP_ROMRD, OP_ADD, OP_XOR, OP_AND, OP_IMMLD00, OP_IMMLD01, OP_IMMLD10, OP_IMMLD11, OP_INSROMRDL, OP_INSROMRDH, OP_IMOV: begin
                            ram_data[ram_base_register + arg2] <= result;
                        end
                        OP_SMOV: begin
                            ram_data[ram_base_register + ram_arg2[5:0]] <= result;
                        end
                        /*
                        OP_AESENC, OP_AESDEC: begin
                            for (integer i = 0; i < 16; i = i + 1) begin
                                ram_data[{26'd0, arg1} + i] <= aes_out_0[i*8 +: 8];
                                ram_data[{26'd0, arg1} + 32'd16 + i] <= aes_out_1[i*8 +: 8];
                            end
                        end
                        */
                        default: begin
                            // No RAM writeback needed for instructions without explicit writeback
                            // Instructions like CRCRST, CRCLD operate on peripherals, not RAM
                        end
                    endcase

                    spi_dbg_tx_start <= 0;
                    spi_dbg_transmit <= 0;
                    //
                    rc522_en <= 0;
                    rc522_reset <= 0;
                    rc522_push <= 0;
                    rc522_pop <= 0;
                    rc522_blen <= 0;
                    rc522_trcve <= 0;
                    rc522_buffer_rst <= 0;
                    rc522_rx_num <= 0;

                    // Clear CRC control signals
                    crc_rst <= 1'b0;
                    crc_load_byte <= 1'b0;

                    // Clear AES control signals
                    aes_en <= 0;
                    aes_reset <= 0;
                    aes_push_d <= 0;
                    aes_push_k0 <= 0;
                    aes_push_k1 <= 0;
                    aes_pop <= 0;
                    aes_set_mode <= 0;
                    aes_start <= 0;
                    aes_buffer_rst <= 0;

                    rng_rst <= 0;

                    cpu_uarttx_data <= 8'h00;
                    cpu_uarttx_en <= 0;

                    // Increment program counter
                    pc <= pc + 10'd1;

                    if (pc == repeat_pcn) begin
                        if (repeat_cnt > 1) begin
                            ram_base_register <= ram_base_register + 1;
                            repeat_cnt <= repeat_cnt - 1;
                            pc <= repeat_pc0;
                        end else begin
                            ram_base_register <= 0;
                        end
                    end

                    case (opcode)
                        OP_JMPC: begin
                            if (cmp_flag) begin
                                repeat_cnt <= 0;
                                ram_base_register <= 0;
                                pc <= {arg2[3:0], arg1};
                            end
                        end

                        OP_JMPNC: begin
                            if (!cmp_flag) begin
                                repeat_cnt <= 0;
                                ram_base_register <= 0;
                                pc <= {arg2[3:0], arg1};
                            end
                        end

                        OP_CALL: begin
                            call_stack[call_sp] <= pc + 10'd1;
                            pc <= {arg2[3:0], arg1};

                            if (call_sp == 2'd3) begin
                                call_full <= 1'd1;
                            end else begin
                                call_sp <= call_sp + 2'd1;
                            end

                            repeat_cnt <= 0;
                            ram_base_register <= 0;
                        end

                        OP_RET: begin
                            if (call_full) begin
                                call_full <= 1'd0;
                                pc <= call_stack[call_sp];
                            end else begin
                                call_sp <= call_sp - 2'd1;
                                pc <= call_stack[call_sp-2'd1];
                            end

                            repeat_cnt <= 0;
                            ram_base_register <= 0;
                        end

                        default: begin
                        end
                    endcase

                    // Clear eeprom reset
                    eeprom_rst <= 0;

                    state <= FETCH;
                end

                default: begin
                    hard_fault_reg <= 1;
                    // Safety: return to FETCH on any invalid state
                    state <= FETCH;
                end
            endcase
        end
    end

    // --- START DEBUG CONTROLLER ---
    // we should consider moving this stuff into its own module

    // Constant / structure definitions to make our life easier

    // debug FSM state
    localparam [2:0]
        // The idle state; FSM goes into this state upon reset. Wait for an instruction to arrive via UART
        DBG_READ_INSN = 0,

        // Some instructions have optional parameters. After parsing the instruction the controller will optionally
        // go into this state to read parameter values into the parameter register array
        // The number of parameters is fixed by the opcode, the dbg_param_len register will be set to the number of values to parse
        // when transitioning from DBG_READ_INSN, and it will decrement with each parameter value read
        DBG_READ_PARAM = 1,

        // The debug controller is executing the operation and will then go to the UART write state if data should be returned, or directly
        // back to DBG_READ_INSN for instructions that don't
        DBG_EXECUTE = 2,


    // UART write states
    // the FSM will alternate between these (waiting for UART to become free / actually writing byte and updating counters)
    // until there is nothing more to be written


    // Start a write of a single byte via UART
    // The enable signal of the UART TX side is enabled, and the Debug controller waits for the UART to start the actual transmission
    // i.e. for its ready signal to come low
    // This state is the entrypoint of UART transmissions. The byte that is currently selected by dbg_params_index will be selected
    DBG_WRITE_UART_START = 3,

    // Wait for the UART to finish transmission
    DBG_WRITE_UART_WAIT = 4;

    // The "instructions"
    localparam [7:0]
        DBG_OP_NULL = 0,
        DBG_OP_RDREG = 1,
        DBG_OP_WRREG = 2,
        DBG_OP_SINGLESTEP = 3,
        DBG_OP_RESET = 4;

    // Parameter counts for the instructions. Opcode is used as an index.
    // (Verilog-2005: replaced unpacked-array localparam with a function)
    // DBG_OP_NULL=0, DBG_OP_RDREG=2, DBG_OP_WRREG=3, DBG_OP_SINGLESTEP=0, DBG_OP_RESET=1

    // Union definition for the parameter block (i.e. all bytes read following the instruction)
    // we have one union member for each instruction with parameters, as well as one member for return values (if instruction have any)
    // This is just to give names to the bit-offsets of individual parameters, making the code more readable
    // note that systemverilog packs structs MSB-first, but the parameters are variable-sized and considered LSB first,
    // that's why there needs to be padding as first member for some of the paramstructs

    // (SV typedef struct/union removed; replaced with reg [143:0] dbg_params below)

    /* verilator lint_off UNUSEDPARAM */
    // 1-byte register indices
    localparam
        /* cmp, err flags packed into a single register*/
        DBG_REG1_FLAGS = 0,
        DBG_REG1_CPUSTATE = 1,
        DBG_REG1_SP = 2,
        DBG_REG1_SPIFLAGS = 3,
        DBG_REG1_SPITX_EEPROM = 4,
        DBG_REG1_SPITX_RC522 = 5,
        DBG_REG1_SPIRX = 6,
        DBG_REG1_RC522_IN = 7,
        DBG_REG1_RC522_OUT = 8,
        DBG_REG1_AESFLAGS = 9,
        DBG_REG1_DBGCR = 10,
        DBG_REG1_CALLFULL = 11,

        // CPU "register RAM" / "Work RAM" is mapped starting from this index
        // i.e. DBG_REG_CPUREG + i corresponds to ram_data[i] for i in [0,64)
        DBG_REG1_CPUREG = 64;

    // 2-byte register indices
    localparam
        DBG_REG2_PC = 0,

        // Call stack. Range [DBG_REG2_STACK; DBG_REG2_STACK+4)
        DBG_REG2_STACK = 1,

        // Hardware breakpoint registers. Range [DBG_REG2_BP; DBG_REG2_BP + DBG_NUM_HARDWARE_BREAKPOINTS)
        DBG_REG2_BP = 8;

    // 3-byte register indices, currently only used for Instruction RAM / ROM
    localparam
        // Instruction ROM, 1024 words
        DBG_REG3_IROM = 0,
        // Instruction RAM
        DBG_REG3_IRAM = 1024;

    // 16-byte registers, for the AES
    localparam
        DBG_REG16_AESKEY0 = 0,
        DBG_REG16_AESKEY1 = 1,
        DBG_REG16_AESIN0 = 2,
        DBG_REG16_AESIN1 = 3,
        DBG_REG16_AESOUT0 = 4,
        DBG_REG16_AESOUT1 = 5;
    /* verilator lint_on UNUSEDPARAM */
    // Register size selectors, this value is written in the two MSBs of the register selector (see its struct)
    localparam
        DBG_REGSZ_1 = 0,
        DBG_REGSZ_2 = 1,
        DBG_REGSZ_3 = 2,
        DBG_REGSZ_16 = 3;

    // Mapping from register size selector to the size in bytes: 0->1, 1->2, 2->3, 3->16
    // (Verilog-2005: replaced with get_dbg_regsz_value function below)

    // (SV typedef BreakpointRegister removed; replaced with reg [10:0] dbg_breakpoints below)



    ////////////////////////////////////////////////////////////
    // Debug controller registers and wires to other hardware //
    ////////////////////////////////////////////////////////////


    // Debug controller registers

    // current state of the debug controller sub-FSM
    reg [2:0] dbg_state;

    // Number of additional parameter bytes coming after the instruction
    reg [4:0] dbg_num_params;

    // Number of "return bytes" that have to be written when the current instruction has executed
    reg [4:0] dbg_num_returns;

    // Current debugger instruction
    reg [7:0] dbg_insn;

    // parameter array. Longest instruction is wrreg with up to 18 parameter bytes (16-byte register value + 2 byte selector)
    // also used for return value
    // Bit-field layout: [15:14]=sel.sizesel, [13:0]=sel.index,
    //   [143:16]=wrreg.value, [127:0]=rdreg_out.value, [i*8+7:i*8]=buffer[i]
    reg [143:0] dbg_params;

    // index of next parameter byte to be written into param array
    // ^= num parameter bytes already read
    reg [4:0] dbg_params_index;


    localparam DBG_NUM_HARDWARE_BREAKPOINTS = 8;

    // Hardware breakpoint registers: bit[10]=enabled, bits[9:0]=match_pc
    reg [10:0] dbg_breakpoints [0:DBG_NUM_HARDWARE_BREAKPOINTS-1];

    localparam DBG_IRAM_SIZE = 512;
    // instruction RAM for debugger
    // CPU can optionally run from this area
    reg [17:0] dbg_iram [DBG_IRAM_SIZE-1:0];


    // The debug control register: [1]=CPURAMSEL, [0]=CPURUN
    reg [1:0] dbgcr;


    // This will be set to 1 after initialization completes, and set to 0 when the mode signal goes low
    // It is required to implement "power-on reset" of the debug controller, i.e. ensuring that we always
    // reinitialize the debug controller when mode goes high
    reg dbg_initialized;
    integer dbg_ram_i; // loop variable for RAM reset (V2005: cannot declare inline in for)





    // Signal that is directly wired into the main CPU to tell it to run or halt
    wire dbg_run_cpu;
    wire dbg_singlestep;


    wire [DBG_NUM_HARDWARE_BREAKPOINTS-1:0] dbg_bp_triggered;

    genvar i;
    generate

        for (i = 0; i < DBG_NUM_HARDWARE_BREAKPOINTS; i = i + 1) begin
            assign dbg_bp_triggered[i] = dbg_breakpoints[i][9:0] == pc && dbg_breakpoints[i][10];
        end
    endgenerate

    assign dbg_singlestep = dbg_state == DBG_EXECUTE & dbg_insn == DBG_OP_SINGLESTEP;

    // CPU run logic
    // - The CPU is never halted when mode is not enabled; so that it will always run normally if the debugger is disabled; whatever the state of the debug controller is
    // - If the debug controller is enabled, there are two means of running the CPU:
    //   - If the dbg_singlestep signal is asserted, the CPU will run unconditionally. This will only happen for a single cycle if the SINGLESTEP debugger instruction is used
    //   - If the CPURUN bit is set in the debug control register, the CPU will run unless one of the enabled hardware breakpoints matches.
    //
    // This gives us breakpoints that behave similar to what we would get with a hardware debugger on a conventional microcontroller:
    // - The breakpoint registers can be set up using the WRREG instruction, and as soon as they are set to enabled, they will break the CPU if it reaches the matching PC and is in FETCH state
    // - When the CPU is in a breakpoint, CPURUN can be left enabled and SINGLESTEP can be used to run until the next breakpoint. In this case, SINGLESTEP behaves like a `continue` command in GDB
    //   Alternatively, CPURUN can be unset, so that SINGLESTEP acts like an actual single-step again
    assign dbg_run_cpu = !mode | ( (dbgcr[0] &  ~ (|dbg_bp_triggered)) | dbg_singlestep);

    // Functions for reading out registers
    // these are all just giant switch statements that should synthesize a large tree-ish structure of MUXes
    // to select a register to read from
    function [7:0] rdreg1 (input [13:0] regidx);
        case (regidx)
            DBG_REG1_FLAGS: rdreg1 = {6'h0, err_flag, cmp_flag};
            DBG_REG1_CPUSTATE: rdreg1 = {4'h0, state};
            DBG_REG1_SP: rdreg1 = {6'h0, call_sp};
            DBG_REG1_SPIFLAGS: rdreg1 = {3'h0,spi_busy,spi_start_tx_rc522,spi_start_tx_eeprom,spi_open_cs1,spi_open_cs0};
            DBG_REG1_SPITX_EEPROM: rdreg1 = spi_transmit_buffer_eeprom;
            DBG_REG1_SPITX_RC522: rdreg1 = spi_transmit_buffer_rc522;
            DBG_REG1_SPIRX: rdreg1 = spi_rx_data;
            DBG_REG1_RC522_IN: rdreg1 = rc522_data_input;
            DBG_REG1_RC522_OUT: rdreg1 = rc522_data_output;
            //DBG_REG1_AESFLAGS: rdreg1 = {3'h0,aes_done,aes_busy,aes_enc_mode,aes_start_pending,aes_start};
            DBG_REG1_CALLFULL: rdreg1 = {7'h0, call_full};
            DBG_REG1_DBGCR: rdreg1 = {6'h0, dbgcr};
            default: begin
                if ($unsigned(regidx - DBG_REG1_CPUREG) < 14'd64) rdreg1 = ram_data[regidx - DBG_REG1_CPUREG];
                else rdreg1 = 0;
            end
        endcase
    endfunction

    function [15:0] rdreg2 (input [13:0] regidx);
        case (regidx)
            DBG_REG2_PC: rdreg2 = {6'h0, pc};
            default: begin
                // check if the regidx is in range [DBG_REG_STACK; DBG_REG_STACK+4)
                // we use unsigned comparison, so if the regidx is smaller, it will roll over to a large value greater than 4 and fail
                // the comparison as well
                if ($unsigned(regidx - DBG_REG2_STACK) < 14'h4) rdreg2 = {6'h0, call_stack[regidx - DBG_REG2_STACK]};
                else if ($unsigned(regidx - DBG_REG2_BP) < DBG_NUM_HARDWARE_BREAKPOINTS) rdreg2 = {5'h0, dbg_breakpoints[regidx- DBG_REG2_BP]};
                else rdreg2 = 0;
            end
        endcase
    endfunction

    function [23:0] rdreg3 (input [13:0] regidx);
        if ($unsigned(regidx - DBG_REG3_IROM) < 14'd1024) rdreg3 = {6'h0, dbg_rom_data};
        else if ($unsigned (regidx - DBG_REG3_IRAM) < DBG_IRAM_SIZE) rdreg3 = {6'h0, dbg_iram[regidx - DBG_REG3_IRAM]};
        else rdreg3 = 24'h0;
    endfunction

    function [127:0] rdreg16 (input [13:0] regidx);
        case (regidx)
            //DBG_REG16_AESKEY0: rdreg16 = aes_key_0;
            //DBG_REG16_AESKEY1: rdreg16 = aes_key_1;
            //DBG_REG16_AESIN0: rdreg16 = aes_data_in_0;
            //DBG_REG16_AESIN1: rdreg16 = aes_data_in_1;
            //DBG_REG16_AESOUT0: rdreg16 = aes_out_0;
            //DBG_REG16_AESOUT1: rdreg16 = aes_out_1;
            default: rdreg16 = 128'h0;
        endcase
    endfunction

    // Parameter-count lookup (replaces SV unpacked-array localparam DBG_OP_PARAMCOUNTS)
    function [4:0] get_dbg_op_paramcounts;
        input [2:0] op;
        case (op)
            3'd0: get_dbg_op_paramcounts = 5'd0; // DBG_OP_NULL
            3'd1: get_dbg_op_paramcounts = 5'd2; // DBG_OP_RDREG
            3'd2: get_dbg_op_paramcounts = 5'd3; // DBG_OP_WRREG
            3'd3: get_dbg_op_paramcounts = 5'd0; // DBG_OP_SINGLESTEP
            3'd4: get_dbg_op_paramcounts = 5'd1; // DBG_OP_RESET
            default: get_dbg_op_paramcounts = 5'd0;
        endcase
    endfunction

    // Register-size lookup (replaces SV unpacked-array localparam DBG_REGSZ_VALUE)
    function [4:0] get_dbg_regsz_value;
        input [1:0] sel;
        case (sel)
            2'd0: get_dbg_regsz_value = 5'd1;
            2'd1: get_dbg_regsz_value = 5'd2;
            2'd2: get_dbg_regsz_value = 5'd3;
            2'd3: get_dbg_regsz_value = 5'd16;
        endcase
    endfunction





    // UART RX interface
    // - dbg_uart_rx_data contains the 8-bit value read from UART
    wire dbg_uart_rx_ready;

    // The debug controller expects the readiness signal for UART RX to last exactly one clock cycle, otherwise it may fetch values too early
    // however, the UART controller may assert the signal for multiple cycles of the main system clock (because it uses another reference clock)
    // easiest solution is to build an edge detector ourselves and only move the debug FSM on the posedge of the uart ready signal
    reg dbg_uart_rx_ready_prev;
    wire dbg_uart_rx_ready_edge;
    assign dbg_uart_rx_ready_edge = dbg_uart_rx_ready && !(dbg_uart_rx_ready_prev);
    always @ (posedge clk) begin
        if (rst) dbg_uart_rx_ready_prev <= 1'b0;
        else dbg_uart_rx_ready_prev <= dbg_uart_rx_ready;
    end

    wire dbg_uart_rx_en;
    wire [7:0] dbg_uart_rx_data;

    wire dbg_uart_tx_en;

    wire [7:0] dbg_uart_tx_data;


    // the UART RX has to be in the enabled state for the entire receive process
    // it is fine to assert the signal the entire time while we're in DBG_READ_{INSN,PARAM} state,
    // the UART module has integrated startbit detection and will stay in idle state until RXD goes low
    // If we read the last byte, we will do the transition out of DBG_READ_INSN
    // in the same clock cycle where the UART does its FINISHED->IDLE transition, so we will not start
    // another transmission accidentally
    //
    // Note: since we transition out of the debug-read state immediately once we have received the last param,
    // it is possible that we deassert enable before the UART RX module has transitioned back into its idle state
    // (the FSM does not transition when enable is deasserted). This shouldn't be a problem, as the internal counter
    // continues to increment even when enable is not asserted. Therefore, once we reach the read state again
    // after doing a full execution cycle of the debug FSM, we should (assuming enough time has passed to make the counter go back to 0)
    // transition to IDLE immediately, and then start the receive cycle for the next byte immediately after.
    // so this should be fine
    assign dbg_uart_rx_en = dbg_state == DBG_READ_INSN || dbg_state == DBG_READ_PARAM;
    /* verilator lint_off PINCONNECTEMPTY */
    uart_rx dbg_uart_rx(
        .clk(clk),
        .en(dbg_uart_rx_en),
        .rst(rst),
        .clk_in(uart_clk_in),

        .rx_in(uart_rxd),
        .rx_out(dbg_uart_rx_data),
        .ready(dbg_uart_rx_ready),
        .frame_error()
    );

    assign dbg_uart_tx_en = dbg_state == DBG_WRITE_UART_WAIT || dbg_state == DBG_WRITE_UART_START;
    uart_tx dbg_uart_tx(
        .clk(clk),
        .en( (mode == 1'b1) ? dbg_uart_tx_en : cpu_uarttx_en),
        .rst(rst),
        .clk_in(uart_clk_in),

        .tx_in((mode == 1'b1) ? dbg_uart_tx_data : cpu_uarttx_data),
        .tx_out(uart_txd),
        .ready(cpu_uarttx_ready)
    );
    /* verilator lint_on PINCONNECTEMPTY */


    // combinational logic bits for the UART transmitter
    assign dbg_uart_tx_data = dbg_params[dbg_params_index*8 +: 8];

    assign dbg_rom_addr = {dbg_params[9:0]};

    // Debugger main FSM

    always @ (posedge clk) begin
        if (rst) begin
            dbg_initialized <= 0;
            dbg_state <= 0;
        end else if (mode) begin
            if (!dbg_initialized) begin
                `dbg_reset_fsm
                dbg_initialized <= 1;
            end
            else begin

                // the main debug controller statemachine
                case (dbg_state)
                    // Read the first instruction byte. This tells us if we have additional parameters to read
                    DBG_READ_INSN: if (dbg_uart_rx_ready_edge) begin
                        // We parse out the instruction itself and determine the number of additional parameters to read,
                        // which depends on the debugger instruction
                        dbg_insn <= dbg_uart_rx_data;
                        dbg_num_params <= get_dbg_op_paramcounts(dbg_uart_rx_data[2:0]);
                        dbg_params_index <= 0;

                        // the default is having no return values, instructions that want to return a value can override this during their EXECUTE phase
                        dbg_num_returns <= 0;

                        // if we have no params, we can skip the param read phase and go straight to execute
                        dbg_state <= get_dbg_op_paramcounts(dbg_uart_rx_data[2:0]) == 0 ? DBG_EXECUTE : DBG_READ_PARAM;
                    end

                    // Read any optional parameters.
                    DBG_READ_PARAM: if (dbg_uart_rx_ready_edge) begin
                        dbg_params[dbg_params_index*8 +: 8] <= dbg_uart_rx_data;
                        dbg_params_index <= dbg_params_index + 1;

                        // we have to special-case WRREG because the data to write is sent after the register selector
                        // the size-selector part is in the two MSBs ([7:6]) of the second byte of the register selector, because it is transmitted little-endian
                        // (as is every other value)
                        if (dbg_insn == DBG_OP_WRREG && dbg_params_index == 1) dbg_num_params <= 2 + get_dbg_regsz_value(dbg_uart_rx_data[7:6]);

                        if (dbg_params_index + 1 == dbg_num_params) begin
                            // reset the params_index at is it also used for transmitting the return values
                            dbg_params_index <= 0;
                            dbg_state <= DBG_EXECUTE;
                        end

                    end

                    DBG_EXECUTE:
                        // note: we treat all multibyte numeric parameters as little-endian
                        case (dbg_insn)
                            DBG_OP_NULL: dbg_state <= DBG_READ_INSN;
                            DBG_OP_RDREG: begin
                                case (dbg_params[15:14])
                                    DBG_REGSZ_1:  dbg_params[7:0]   <= rdreg1(dbg_params[13:0]);
                                    DBG_REGSZ_2:  dbg_params[15:0]  <= rdreg2(dbg_params[13:0]);
                                    DBG_REGSZ_3:  dbg_params[23:0]  <= rdreg3(dbg_params[13:0]);
                                    DBG_REGSZ_16: dbg_params[127:0] <= rdreg16(dbg_params[13:0]);
                                endcase
                                dbg_num_returns <= get_dbg_regsz_value(dbg_params[15:14]);

                                // we will always write at least 1 byte of data, so go to the UART writing part of the FSM
                                dbg_state <= DBG_WRITE_UART_START;
                            end
                            DBG_OP_WRREG: begin
                                // note: writes for the CPU-internal registers are implemented in the CPU FETCH state, in its always block
                                // to avoid multi-driven net issues
                                case (dbg_params[15:14])
                                    DBG_REGSZ_1:
                                        case (dbg_params[13:0])
                                            DBG_REG1_DBGCR: dbgcr <= dbg_params[17:16];
                                            default: ;
                                        endcase
                                    // note: DBG_REG2_PC is handled in the main FSM's FETCH state to avoid multi-driven nets
                                    DBG_REGSZ_2:
                                        if ($unsigned(dbg_params[13:0] - DBG_REG2_BP) < DBG_NUM_HARDWARE_BREAKPOINTS) dbg_breakpoints[dbg_params[13:0] - DBG_REG2_BP] <= dbg_params[26:16];
                                    DBG_REGSZ_3:
                                        if ($unsigned(dbg_params[13:0] - DBG_REG3_IRAM) < DBG_IRAM_SIZE) dbg_iram[dbg_params[13:0] - DBG_REG3_IRAM] <= dbg_params[33:16];
                                    default: ;
                                endcase
                                dbg_state <= DBG_READ_INSN;
                            end

                            // Nothing needs to be done in the sequential part, external combinational logic (implemented above the FSM)
                            // is used to assert the dbg_singlestep signal while we are executing the instruction (i.e. for exactly one clock cycle),
                            // which feeds into the debug-cpu-halt signal and allows the CPU to run for 1 cycle
                            DBG_OP_SINGLESTEP: dbg_state <= DBG_READ_INSN;

                            // TODO: implement submodule reset. Should assert rst for the module indexed by dbg_params.reset.index
                            // for N clock cycles. Needs a counter and additional states.
                            DBG_OP_RESET: dbg_state <= DBG_READ_INSN;

                            // on invalid insn, just go back to idle state
                            default: dbg_state <= DBG_READ_INSN;
                        endcase

                    DBG_WRITE_UART_START: begin
                        // If we want to send back a response, the instruction has written it into the dbg_params buffer and set dbg_num_returns accordingly
                        //
                        // Combinational logic will assert uart_tx_en if we're in DBG_WRITE_UART_{START,WAIT}.
                        // The uart tx side _should_ be in ready state because we are the only user; it will be ready coming out of reset
                        // and we will wait for it to become ready after each transmission. If it isn't ready now, either we or the UART
                        // messed up in a way that we can't recover from anyways.
                        //
                        // The UART TX module will stay in the ready state for a bit until it sees the first clock edge from the UART
                        // clock (while EN is asserted), and only then it will deassert the ready signal. So we have to wait for that to happen,
                        // otherwise we will accidentally increment the TX counter although we haven't sent yet
                        dbg_state <= !cpu_uarttx_ready ? DBG_WRITE_UART_WAIT : DBG_WRITE_UART_START;
                    end

                    DBG_WRITE_UART_WAIT: begin
                        if (cpu_uarttx_ready) begin
                            dbg_params_index <= dbg_params_index + 1;
                            dbg_state <= (dbg_params_index + 1 == dbg_num_returns) ? DBG_READ_INSN : DBG_WRITE_UART_START;
                        end
                    end

                    // should never happen, just go back to idle state
                    default: dbg_state <= DBG_READ_INSN;
                endcase
            end
        end
        else begin
            dbg_initialized <= 0;

            // DBGCR should be reset immediately upon debugger deactivation so that CPU continues to run normally
            dbgcr <= 0;
        end
    end

    // --- END DEBUG CONTROLLER ---

endmodule
