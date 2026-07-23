
module rc522 (
    // Clock and Reset
    input wire clk,
    input wire rst,

    // Transaction Control
    input wire setup_transaction,    // Setup new transaction with data_in
    input wire start_transaction,    // Trigger RC522 initialization sequence

    // Data Interface
    input wire [511:0] data_in,      // Data to transmit (max 64 bytes)
    input wire [5:0] num_bytes,      // Number of bytes to transmit
    input wire [2:0] len_last_byte,  // Number of valid bits in last byte (1-8, 0=8)
    output reg data_rdy,             // High when receive data is ready
    output wire [511:0] data_out,     // Received data from RC522
    output reg [5:0] rx_num_bytes,   // number of valid bytes in data_out

    // Status Signals
    output reg busy,                 // High when transaction in progress
    output reg ready_for_transaction,// High when ready to accept new transaction

    // Debug Interface
    output [7:0] main_state,         // Current main state for debugging
    output [7:0] init_state,          // Current init state for debugging

    output reg spi_start_tx,
    output reg spi_open_cs1,
    output reg [7:0] spi_tx_data,
    input wire spi_busy,
    input wire [7:0] spi_rx_data
);
  //
  //Submodule Wires
  //SPI Wires
  //wire spi_clk;
  //reg spi_rst;
  //reg spi_start_tx;
  //wire spi_busy;
  //reg spi_open_cs0;
  //reg spi_open_cs1;
  //reg spi_miso;
  //reg [7:0] spi_tx_data;
  //reg spi_busy;
  //reg [7:0] spi_rx_data;

  //TODO: clk splitting logic if needed
  //assign spi_clk = clk;
  reg [511:0] buffer;
  assign data_out = buffer;

  //Submodules
  /*
  spi_master spi_master_inst (
      .clk(clk),
      .rst(spi_rst),
      .start_tx(spi_start_tx),
      .open_cs1(spi_open_cs1),
      .tx_data(spi_tx_data),
      .busy(spi_busy),
      .rx_data(spi_rx_data)
  );
  */

  //State Registers
  reg [7:0] main_state_reg;
  reg [7:0] init_state_reg;
  reg [2:0] init_instr_step;
  reg [7:0] read_state_reg;
  reg [7:0] write_state_reg;
  reg [7:0] wait_cnt_reg;
  reg [5:0] bytes_left;
  reg [2:0] len_last;
  reg [7:0] poll_count;  // Counter for polling timeout
  reg [16:0] poll_delay_cnt;  // Delay counter for polling loop (17-bit for 80k cycles)
  reg [5:0] byte_index;  // Index for placing bytes in buffer (0=first byte, 1=second, etc.)

  // Centralized SPI transaction control registers
  reg [6:0] target_reg_addr;   // Target register address for SPI transaction (7 bits)
  reg [7:0] target_reg_data;   // Data to write (for write operations)
  reg [7:0] read_reg_data;     // Data read back (for read operations)
  reg [7:0] main_return_state; // Main state to return to after SPI transaction
  reg [7:0] spi_return_state;  // Sub-state to return to after SPI transaction
  reg [7:0] spi_substate;      // Substate for centralized SPI state machines

  assign main_state = main_state_reg;
  assign init_state = init_state_reg;
  /* verilator lint_off UNUSEDPARAM */
  //Main State Parameters
  localparam STATE_NINIT = 8'h0;
  localparam STATE_READY = 8'h1;
  localparam STATE_WRITE = 8'h2;
  localparam STATE_READ = 8'h3;

  // Centralized SPI transaction states
  localparam SPI_REG_WR_START      = 8'hF0;
  localparam SPI_REG_WR_ADDR_WAIT  = 8'hF1;
  localparam SPI_REG_WR_DATA_START = 8'hF2;
  localparam SPI_REG_WR_DATA_WAIT  = 8'hF3;
  localparam SPI_REG_WR_DONE       = 8'hF4;

  localparam SPI_REG_RD_START      = 8'hF5;
  localparam SPI_REG_RD_ADDR_WAIT  = 8'hF6;
  localparam SPI_REG_RD_DUMMY_START= 8'hF7;
  localparam SPI_REG_RD_DUMMY_WAIT = 8'hF8;
  localparam SPI_REG_RD_DONE       = 8'hF9;


  //Initialization State Parameters
  // Define initialization states here
  localparam INIT_IDLE = 8'h00;
  localparam INIT_RESET = 8'h01;
  localparam INIT_WAIT_RESET = 8'h02;
  localparam INIT_CHECK_RESET = 8'h03;
  localparam INIT_TMODE = 8'h04;
  localparam INIT_TPRESCALER = 8'h05;
  localparam INIT_TRELOADREGH = 8'h06;
  localparam INIT_TRELOADREGL = 8'h07;
  localparam INIT_TXMODEREG = 8'h08;
  localparam INIT_RXMODEREG = 8'h09;
  localparam INIT_MODEREG = 8'h0A;
  localparam INIT_TXASKREG = 8'h0B;
  localparam INIT_RFCFGREG = 8'h0C;
  localparam INIT_RXTHRESHOLDREG = 8'h0D;
  localparam INIT_MODWIDTH = 8'h10;
  localparam INIT_DEMOD = 8'h11;
  localparam INIT_TXCONTROLREG = 8'h0E;  //turns on antenna
  localparam INIT_VERSION_CHECK = 8'h0F;



  //Helper Parameters
  localparam Read = 1'b1;
  localparam Write = 1'b0;

  //Register Adresses
  localparam CommandReg = 7'h01 << 1;
  localparam ComIEnReg = 7'h02 << 1;
  localparam ComIrqReg = 7'h04 << 1;
  localparam ErrorReg = 7'h06 << 1;
  localparam FIFODataReg = 7'h09 << 1;
  localparam FIFOLevelReg = 7'h0A << 1;
  localparam ControlReg = 7'h0C << 1;
  localparam BitFramingReg = 7'h0D << 1;
  localparam ModeReg = 7'h11 << 1;
  localparam TxModeReg = 7'h12 << 1;
  localparam TxControlReg = 7'h14 << 1;
  localparam TxASKReg = 7'h15 << 1;
  localparam RxModeReg = 7'h13 << 1;
  localparam RxThresholdReg = 7'h18 << 1;
  localparam DemodReg = 7'h19 << 1;
  localparam ModWidthReg = 7'h24 << 1;
  localparam RFCfgReg = 7'h26 << 1;
  localparam TModeReg = 7'h2A << 1;
  localparam TPrescalerReg = 7'h2B << 1;
  localparam TReloadReg1 = 7'h2C << 1;
  localparam TReloadReg2 = 7'h2D << 1;
  localparam TReloadRegH = 7'h2C << 1;
  localparam TReloadRegL = 7'h2D << 1;
  localparam VersionReg = 7'h37 << 1;

  //Commands
  //CommandReg Commands
  localparam CommandRegReset = 8'h0F;
  localparam CommandRegResetSuc = 8'h20;
  localparam CommandRegTransceive = 8'h0C;
  localparam FIFOLevelRegFlush = 8'h80;
  localparam ComIrqRegFlushFIFO = 8'h7F;

  //Init Values
  localparam TModeRegInit = 8'h80;
  localparam TPrescalerRegInit = 8'hA9;
  localparam TReloadRegHInit = 8'h2E; // 300 ms instead of 25ms
  localparam TReloadRegLInit = 8'hE0;
  localparam TxModeRegInit = 8'h00;
  localparam RxModeRegInit = 8'h00;
  localparam ModeRegInit = 8'h3D;
  localparam TxASKRegInit = 8'h40;
  localparam RFCfgRegInit = 8'h58;
  localparam RxThresholdRegInit = 8'h86;
  localparam ModWidthRegInit = 8'h26;       // ISO14443-A Type A modulation width
  localparam DemodRegInit = 8'h4D;           // Demodulator settings
  localparam TxControlRegInit = 8'h83;
  /* verilator lint_on UNUSEDPARAM */

  reg [19:0] reset_delay_cnt; // New register for 50ms reset delay

  //Main State Machine
  always @(posedge clk or posedge rst) begin
    if (rst) begin
      reset_delay_cnt <= 20'd0;
      main_state_reg <= STATE_NINIT;
      init_state_reg <= 8'h00;        //Start in INIT_IDLE
      init_instr_step <= 3'h0;
      read_state_reg <= 8'h00;
      write_state_reg <= 8'h00;
      wait_cnt_reg <= 8'h00;
      poll_count <= 8'h0;  // Initialize polling counter
      poll_delay_cnt <= 17'h0;  // Initialize polling delay counter
      byte_index <= 6'h0;  // Initialize byte index

      // Initialize centralized SPI control registers
      target_reg_addr <= 7'h0;
      target_reg_data <= 8'h0;
      read_reg_data <= 8'h0;
      spi_return_state <= 8'h0;
      spi_substate <= SPI_REG_WR_START;

      spi_open_cs1 <= 1'b0;
      spi_start_tx <= 1'b0;
      busy <= 1'b0;
      data_rdy <= 1'b0;
      rx_num_bytes <= 6'h0;

      // Initialize output signals
      ready_for_transaction <= 1'b0;

      // Initialize remaining registers to avoid X propagation in GL sim
      spi_tx_data <= 8'h0;
      buffer <= 512'h0;
      main_return_state <= 8'h0;
      bytes_left <= 6'h0;
      len_last <= 3'h0;
    end else begin
      case (main_state_reg)

        // =========================
        // STATE_NINIT: RC522 Initialization Sequence
        // =========================
        // Configures all necessary RC522 registers for ISO14443-A operation:
        // 1. Reset the RC522 chip
        // 2. Configure timer (TMode, TPrescaler, TReload registers)
        // 3. Configure communication modes (TxMode, RxMode)
        // 4. Configure modulation and RF settings
        // 5. Turn on antenna
        STATE_NINIT: begin
          case (init_state_reg)
            // ===== RESET SEQUENCE =====
            // Issue soft reset command to RC522
            INIT_IDLE: begin
                if(start_transaction) begin
                  init_state_reg <= 8'h01;          //Change state to INIT_RESET
                end
            end

            INIT_RESET: begin
              if (init_instr_step == 3'h0) begin
                // Setup write: CommandReg = CommandRegReset
                target_reg_addr <= CommandReg;
                target_reg_data <= CommandRegReset;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_RESET;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                // Returned from SPI write, move to next init state
                init_instr_step <= 3'h0;
                //init_state_reg <= 8'h4;  // Next: INIT_TMODE
                init_state_reg <= INIT_WAIT_RESET; 
                reset_delay_cnt <= 20'd5;     // Load 50ms delay (at 10MHz)
              end
            end
            INIT_WAIT_RESET: begin
            if (reset_delay_cnt != 0) begin
                // Wait for 50ms
                reset_delay_cnt <= reset_delay_cnt - 1;
            end else begin
                // Delay complete, NOW proceed to TMODE configuration
                init_state_reg <= INIT_TMODE; // 8'h04
            end
        end
            // Wait a few miliseconds
            /*
            INIT_WAIT_RESET: begin
              if (wait_cnt_reg < 8'hFF) begin
                wait_cnt_reg <= wait_cnt_reg + 1;
              end else begin
                wait_cnt_reg   <= 8'h00;
                init_state_reg <= 8'h03;
              end
            end

            // Check CommandReg for successful reset
            // SPI read requires 2 bytes: address byte + dummy byte to clock out response
            INIT_CHECK_RESET: begin
              if (!spi_busy && init_instr_step == 3'h0) begin
                init_instr_step <= 3'h1;
                spi_tx_data <= {Read, CommandReg};  // First byte: read address
                spi_open_cs1 <= 1'b1;
                spi_start_tx <= 1'b1;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h2;
                spi_start_tx <= 1'b0;
              end else if (!spi_busy && init_instr_step == 3'h2) begin
                // First byte sent, now send dummy byte to clock out data
                spi_tx_data <= 8'h00;  // Second byte: dummy data to clock out response
                spi_start_tx <= 1'b1;
                init_instr_step <= 3'h3;
              end else if (init_instr_step == 3'h3) begin
                init_instr_step <= 3'h4;
                spi_start_tx <= 1'b0;
              end else if (!spi_busy && init_instr_step == 3'h4) begin
                init_instr_step <= 3'h5;
              end else if (!spi_busy && init_instr_step == 3'h5) begin
                // Check if reset was successful
                if (spi_rx_data == CommandRegResetSuc) begin
                  // Proceed to next init state
                  init_state_reg <= 8'h04;
                end else begin
                  // Retry reset
                  init_state_reg <= 8'h01;
                end
                init_instr_step <= 3'h0;
                spi_open_cs1 <= 1'b0;
              end
            end
            */

            // Configure the timers
            INIT_TMODE: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= TModeReg;
                target_reg_data <= TModeRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_TMODE;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h5;  // Next: INIT_TPRESCALER
              end
            end

            INIT_TPRESCALER: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= TPrescalerReg;
                target_reg_data <= TPrescalerRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_TPRESCALER;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h06;  // Next: INIT_TRELOADREGH
              end
            end

            INIT_TRELOADREGH: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= TReloadRegH;
                target_reg_data <= TReloadRegHInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_TRELOADREGH;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h07;  // Next: INIT_TRELOADREGL
              end
            end

            INIT_TRELOADREGL: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= TReloadRegL;
                target_reg_data <= TReloadRegLInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_TRELOADREGL;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h08;  // Next: INIT_TXMODEREG
              end
            end

            //Set transmission parameters
            INIT_TXMODEREG: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= TxModeReg;
                target_reg_data <= TxModeRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_TXMODEREG;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h09;  // Next: INIT_RXMODEREG
              end
            end

            INIT_RXMODEREG: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= RxModeReg;
                target_reg_data <= RxModeRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_RXMODEREG;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h0A;  // Next: INIT_MODEREG
              end
            end

            INIT_MODEREG: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= ModeReg;
                target_reg_data <= ModeRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_MODEREG;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h0B;  // Next: INIT_TXASKREG
              end
            end

            INIT_TXASKREG: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= TxASKReg;
                target_reg_data <= TxASKRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_TXASKREG;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h0C;  // Next: INIT_RFCFGREG
              end
            end

            INIT_RFCFGREG: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= RFCfgReg;
                target_reg_data <= RFCfgRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_RFCFGREG;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h0D;  // Next: INIT_RXTHRESHOLDREG
              end
            end

            INIT_RXTHRESHOLDREG: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= RxThresholdReg;
                target_reg_data <= RxThresholdRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_RXTHRESHOLDREG;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= INIT_MODWIDTH;  // Next: INIT_MODWIDTH
              end
            end

            //Configure ModWidth for ISO14443-A
            INIT_MODWIDTH: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= ModWidthReg;
                target_reg_data <= ModWidthRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_MODWIDTH;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= INIT_DEMOD;  // Next: INIT_DEMOD
              end
            end

            //Configure Demodulator settings
            INIT_DEMOD: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= DemodReg;
                target_reg_data <= DemodRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_DEMOD;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= 8'h0E;  // Next: INIT_TXCONTROLREG
              end
            end

            //Turn on the antenna
            INIT_TXCONTROLREG: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= TxControlReg;
                target_reg_data <= TxControlRegInit;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_TXCONTROLREG;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_WR_START;
              end else if (init_instr_step == 3'h1) begin
                init_instr_step <= 3'h0;
                init_state_reg <= INIT_VERSION_CHECK;  // Next: INIT_VERSION_CHECK
              end
            end

            // Read VersionReg to verify RC522 presence
            INIT_VERSION_CHECK: begin
              if (init_instr_step == 3'h0) begin
                target_reg_addr <= VersionReg;
                main_return_state <= STATE_NINIT;
                spi_return_state <= INIT_VERSION_CHECK;
                init_instr_step <= 3'h1;
                main_state_reg <= SPI_REG_RD_START;  // Use READ state machine
              end else if (init_instr_step == 3'h1) begin
                // Returned from SPI read, check version in read_reg_data
                if ((read_reg_data == 8'h91) || (read_reg_data == 8'h92) || (read_reg_data == 8'h88)) begin
                  // SUCCESS: RC522 chip detected
                  rx_num_bytes <= 6'd1;
                end else begin
                  // FAILURE: Invalid version (chip not present or wrong CS)
                  rx_num_bytes <= 6'd0;
                end
                init_instr_step <= 3'h0;
                init_state_reg <= 8'hFF;
                main_state_reg <= STATE_READY;
              end
            end

            // default case
            default: begin
              if (wait_cnt_reg < 8'hFF) begin
                wait_cnt_reg <= wait_cnt_reg + 1;
              end else begin
                wait_cnt_reg   <= 8'h00;
                init_state_reg <= 8'h04;
              end
            end
          endcase
        end  // STATE_NINIT

        // =========================
        // STATE_READY
        // =========================
        STATE_READY: begin
          // Update status signals to indicate ready state
          ready_for_transaction <= 1'b1;  // Indicate ready to accept new transaction
          data_rdy              <= 1'b0;  // Clear data ready flag
          busy                  <= 1'b0;  // Not busy

          if (setup_transaction == 1'b1) begin
            // New transaction requested, transition to WRITE state
            main_state_reg        <= STATE_WRITE;
            busy                  <= 1'b1;
            ready_for_transaction <= 1'b0;  // No longer ready for new transaction
            bytes_left            <= num_bytes;
            len_last              <= len_last_byte;
            buffer                <= data_in;
            write_state_reg       <= 8'h0;
          end else begin
            main_state_reg <= STATE_READY;
          end
        end

        // =========================
        // STATE_WRITE
        // =========================
        STATE_WRITE: begin
          case (write_state_reg)
            // ===== PREPARATION SEQUENCE =====
            
            // Step 1: STOP any active command (CommandReg = 0x00)
            // This MUST be done first to prevent new IRQs from being generated while we clear them.
            8'h00: begin
              target_reg_addr <= CommandReg;
              target_reg_data <= 8'h00;  // Idle Command
              main_return_state <= STATE_WRITE;
              spi_return_state <= 8'h01;
              main_state_reg <= SPI_REG_WR_START;
            end

            // Step 2: Clear ComIrqReg (reset interrupts)
            8'h01: begin
              target_reg_addr <= ComIrqReg;
              target_reg_data <= ComIrqRegFlushFIFO; // 0x7F
              main_return_state <= STATE_WRITE;
              spi_return_state <= 8'h02;
              main_state_reg <= SPI_REG_WR_START;
            end

            // Step 3: Flush FIFO
            8'h02: begin
              target_reg_addr <= FIFOLevelReg;
              target_reg_data <= FIFOLevelRegFlush; // 0x80
              main_return_state <= STATE_WRITE;
              spi_return_state <= 8'h03;
              main_state_reg <= SPI_REG_WR_START;
            end

            // ===== DATA WRITING SEQUENCE =====
            // Step 4: Write data bytes to FIFO (loop)
            8'h03: begin
              if (bytes_left >= 6'h1) begin
                // Write one byte to FIFO
                target_reg_addr <= FIFODataReg;
                target_reg_data <= buffer[511:504];  // Load data byte from buffer
                buffer          <= buffer << 8;       // Shift buffer left for next byte
                bytes_left      <= bytes_left - 1;    // Decrement counter
                main_return_state <= STATE_WRITE;
                spi_return_state <= 8'h03;  // Loop back to this state
                main_state_reg <= SPI_REG_WR_START;
              end else begin
                // All bytes written, proceed to configure BitFramingReg
                write_state_reg <= 8'h04;
              end
            end

            // Step 5: Configure BitFramingReg for framing (no StartSend yet)
            8'h04: begin
              target_reg_addr <= BitFramingReg;
              target_reg_data <= {5'b00000, len_last};  // Set number of valid bits in last byte
              main_return_state <= STATE_WRITE;
              spi_return_state <= 8'h05;  // Next state after write completes
              main_state_reg <= SPI_REG_WR_START;
            end

            // Step 6: Issue Transceive command
            8'h05: begin
              target_reg_addr <= CommandReg;
              target_reg_data <= CommandRegTransceive;  // 0x0C
              main_return_state <= STATE_WRITE;
              spi_return_state <= 8'h06;  // Next state after write completes
              main_state_reg <= SPI_REG_WR_START;
            end

            // Step 7: Start transmission by setting BitFramingReg[7] (StartSend bit)
            8'h06: begin
              target_reg_addr <= BitFramingReg;
              target_reg_data <= {5'b10000, len_last};  // Set StartSend bit to begin transmission
              main_return_state <= STATE_WRITE;
              spi_return_state <= 8'h07;  // Next state after write completes
              main_state_reg <= SPI_REG_WR_START;
            end

            // Step 8: Transition to READ state to poll for completion
            8'h07: begin
              // Transmission started, now move to READ state to wait for response
              write_state_reg <= 8'h0;
              main_state_reg <= STATE_READ;
              poll_count     <= 8'h0;
              read_state_reg <= 8'h0;
            end
            default: write_state_reg <= write_state_reg;
          endcase
        end  // STATE_WRITE

        // =========================
        // STATE_READ
        // =========================
        STATE_READ: begin
          case (read_state_reg)
            // ===== STEP 1: POLL ComIrqReg =====
            // Poll ComIrqReg to wait for RxIRq bit (bit 5 = 0x20)
            8'h0: begin
              // Clear buffer before reading response to avoid stale data
              buffer <= 512'h0;
              // Start SPI read of ComIrqReg
              target_reg_addr <= ComIrqReg;
              main_return_state <= STATE_READ;
              spi_return_state <= 8'h1;  // Next state after read completes
              main_state_reg <= SPI_REG_RD_START;
            end

            8'h1: begin
              // Check if RxIRq (0x20) OR IdleIRq (0x10) is set indicating reception complete
              if ((read_reg_data & 8'h30) != 8'h0) begin
                // Reception complete, proceed to clear StartSend
                read_state_reg <= 8'h2;

              end else begin
                // Check for timeout
                if (poll_count >= 8'd50) begin
                  // TIMEOUT: RC522 not responding, abort transaction
                  data_rdy       <= 1'b0;
                  busy           <= 1'b0;
                  read_state_reg <= 8'h0;
                  main_state_reg <= STATE_READY;
                end else begin
                  // Not complete yet, wait and poll again
                  poll_count     <= poll_count + 1;
                  read_state_reg <= 8'h10;  // Go to wait state
                end
              end
            end

            // Wait state between polling attempts for proper timing
            8'h10: begin
              poll_delay_cnt <= 17'd80000;  // 8ms delay at 10 MHz (allows HW timeout to fire)
              read_state_reg <= 8'h11;
            end
            8'h11: begin
              if (poll_delay_cnt > 17'd0) begin
                poll_delay_cnt <= poll_delay_cnt - 17'd1;  // Count down 8ms delay
              end else begin
                // Delay complete, retry polling
                read_state_reg <= 8'h0;
              end
            end

            // ===== STEP 2: CLEAR StartSend BIT =====
            // Clear the StartSend bit in BitFramingReg to stop transmission
            8'h2: begin
              target_reg_addr <= BitFramingReg;
              target_reg_data <= {5'b00000, len_last};  // Clear StartSend bit (bit 7)
              main_return_state <= STATE_READ;
              spi_return_state <= 8'h3;  // Next state after write completes
              main_state_reg <= SPI_REG_WR_START;
            end

            // ===== STEP 3: CHECK ErrorReg =====
            // Read ErrorReg to check for communication errors
            8'h3: begin
              target_reg_addr <= ErrorReg;
              main_return_state <= STATE_READ;
              spi_return_state <= 8'h4;  // Next state after read completes
              main_state_reg <= SPI_REG_RD_START;
            end

            8'h4: begin
              // Check ErrorReg for errors (mask 0x13: BufferOvfl, ParityErr, ProtocolErr)
              if ((read_reg_data & 8'h13) != 8'h00) begin
                // ERROR: Communication error detected, abort transaction
                data_rdy       <= 1'b0;
                busy           <= 1'b0;
                read_state_reg <= 8'h0;
                main_state_reg <= STATE_READY;
              end else begin
                // No errors, proceed to read FIFO level
                read_state_reg <= 8'h5;
              end
            end

            // ===== STEP 4: READ FIFOLevelReg =====
            // Read FIFOLevelReg to determine how many bytes to read from FIFO
            8'h5: begin
              target_reg_addr <= FIFOLevelReg;
              main_return_state <= STATE_READ;
              spi_return_state <= 8'h6;  // Next state after read completes
              main_state_reg <= SPI_REG_RD_START;
            end

            8'h6: begin
              // Store number of bytes to read from FIFO
              rx_num_bytes <= read_reg_data[5:0];  // Report how many bytes are returned
              bytes_left   <= read_reg_data[5:0];
              byte_index   <= 6'h0;  // Reset byte index for reading
              read_state_reg <= 8'h7;
            end

            // ===== STEP 5: READ FIFO DATA BYTES =====
            // Read all response bytes from FIFO (loop)
            8'h7: begin
              if (bytes_left >= 6'h1) begin
                // Read one byte from FIFO
                target_reg_addr <= FIFODataReg;
                main_return_state <= STATE_READ;
                spi_return_state <= 8'h8;  // Next state after read completes
                main_state_reg <= SPI_REG_RD_START;
              end else begin
                // All bytes read, set data_rdy flag and proceed to cleanup
                data_rdy       <= 1'b1;
                read_state_reg <= 8'h9;
              end
            end

            8'h8: begin
              // Place each byte at correct position using byte_index
              // byte_index=0 (first byte) → buffer[511:504]
              // byte_index=1 (second byte) → buffer[503:496]
              // byte_index=N → buffer[(511 - N*8) : (504 - N*8)]
              buffer[(511 - byte_index*8) -: 8] <= read_reg_data;
              bytes_left      <= bytes_left - 6'h1;
              byte_index      <= byte_index + 6'h1;  // Increment for next byte
              read_state_reg  <= 8'h7;  // Loop back to read next byte
            end

            // ===== CLEANUP SEQUENCE =====
            // Clear ComIrqReg
            8'h9: begin
              target_reg_addr <= ComIrqReg;
              target_reg_data <= 8'h7F;  // Clear all interrupt flags
              main_return_state <= STATE_READ;
              spi_return_state <= 8'hA;  // Next state after write completes
              main_state_reg <= SPI_REG_WR_START;
            end

            // Flush FIFO
            8'hA: begin
              target_reg_addr <= FIFOLevelReg;
              target_reg_data <= FIFOLevelRegFlush;  // 0x80 to flush FIFO
              main_return_state <= STATE_READ;
              spi_return_state <= 8'hB;  // Next state after write completes
              main_state_reg <= SPI_REG_WR_START;
            end

            // Transaction complete
            8'hB: begin
              read_state_reg <= 8'h0;
              data_rdy       <= 1'b0;  // Clear data_rdy for next transaction
              busy           <= 1'b0;  // Clear busy flag
              main_state_reg <= STATE_READY;
            end
            default: read_state_reg <= read_state_reg;
          endcase
        end  // STATE_READ

        // =========================
        // Centralized SPI Register Write State Machine
        // =========================
        SPI_REG_WR_START: begin
          // Start address byte transaction
          spi_open_cs1 <= 1'b1;
          spi_tx_data <= {Write, target_reg_addr};
          spi_start_tx <= 1'b1;
          if (spi_busy) begin  // Wait for busy to GO HIGH (handshake)
            main_state_reg <= SPI_REG_WR_ADDR_WAIT;
          end
        end

        SPI_REG_WR_ADDR_WAIT: begin
          spi_open_cs1 <= 1'b1;
          if (spi_busy) begin
            spi_start_tx <= 1'b0;  // Deassert once busy is HIGH
          end else begin
            main_state_reg <= SPI_REG_WR_DATA_START;  // Busy went LOW, transaction complete
          end
        end

        SPI_REG_WR_DATA_START: begin
          // Start data byte transaction
          spi_open_cs1 <= 1'b1;
          spi_tx_data <= target_reg_data;
          spi_start_tx <= 1'b1;
          if (spi_busy) begin  // Wait for busy to GO HIGH
            main_state_reg <= SPI_REG_WR_DATA_WAIT;
          end
        end

        SPI_REG_WR_DATA_WAIT: begin
          spi_open_cs1 <= 1'b1;
          if (spi_busy) begin
            spi_start_tx <= 1'b0;  // Deassert once busy is HIGH
          end else begin
            main_state_reg <= SPI_REG_WR_DONE;  // Transaction complete
            wait_cnt_reg <= 8'd0;
          end
        end

        SPI_REG_WR_DONE: begin
          spi_open_cs1 <= 1'b0;  // Close CS
          spi_start_tx <= 1'b0;  // Ensure start is low
            
           if (wait_cnt_reg < 8'd50) begin
             wait_cnt_reg <= wait_cnt_reg + 1;
          end else begin
             wait_cnt_reg <= 8'd0;
          // Restore appropriate sub-state register based on main state
          case (main_return_state)
            STATE_NINIT: init_state_reg <= spi_return_state;
            STATE_WRITE: write_state_reg <= spi_return_state;
            STATE_READ:  read_state_reg <= spi_return_state;
            default:     init_state_reg <= spi_return_state;
          endcase

          // Transition to target main state
          main_state_reg <= main_return_state;
          end
        end

        // =========================
        // Centralized SPI Register Read State Machine
        // =========================
        SPI_REG_RD_START: begin
          // Start address byte transaction (with read bit set)
          spi_open_cs1 <= 1'b1;
          spi_tx_data <= {Read, target_reg_addr};
          spi_start_tx <= 1'b1;
          if (spi_busy) begin
            main_state_reg <= SPI_REG_RD_ADDR_WAIT;
          end
        end

        SPI_REG_RD_ADDR_WAIT: begin
          spi_open_cs1 <= 1'b1;
          if (spi_busy) begin
            spi_start_tx <= 1'b0;
          end else begin
            main_state_reg <= SPI_REG_RD_DUMMY_START;
          end
        end

        SPI_REG_RD_DUMMY_START: begin
          // Start dummy byte to clock out data
          spi_open_cs1 <= 1'b1;
          spi_tx_data <= 8'h00;
          spi_start_tx <= 1'b1;
          if (spi_busy) begin
            main_state_reg <= SPI_REG_RD_DUMMY_WAIT;
          end
        end

        SPI_REG_RD_DUMMY_WAIT: begin
          spi_open_cs1 <= 1'b1;
          if (spi_busy) begin
            spi_start_tx <= 1'b0;
          end else begin
            read_reg_data <= spi_rx_data;  // Capture read data
            main_state_reg <= SPI_REG_RD_DONE;
            wait_cnt_reg <= 8'd0;
          end
        end

        SPI_REG_RD_DONE: begin
          spi_open_cs1 <= 1'b0;
          spi_start_tx <= 1'b0;
           
           if (wait_cnt_reg < 8'd50) begin
             wait_cnt_reg <= wait_cnt_reg + 1;
          end else begin
             wait_cnt_reg <= 8'd0;
          // Restore appropriate sub-state register based on main state
          case (main_return_state)
            STATE_NINIT: init_state_reg <= spi_return_state;
            STATE_WRITE: write_state_reg <= spi_return_state;
            STATE_READ:  read_state_reg <= spi_return_state;
            default:     init_state_reg <= spi_return_state;
          endcase

          // Transition to target main state
          main_state_reg <= main_return_state;
          end
        end

        // =========================
        // Default
        // =========================
        default: main_state_reg <= main_state_reg;
      endcase
    end
  end
endmodule
