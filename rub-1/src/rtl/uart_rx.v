module uart_rx(
    input wire clk,
    input wire en,
    input wire rst,
    input wire clk_in,
    input wire rx_in,

    output reg [7:0] rx_out,
    output wire ready,
    output reg frame_error
);

    localparam 
        CLOCK_DIVIDER = 16,
        NUM_BITS = 9,
        COUNTER_END = NUM_BITS * CLOCK_DIVIDER + 7;

    localparam 
        STATE_IDLE = 0,
        STATE_WAIT = 1,
        STATE_RECIEVING = 2,
        STATE_FINISHED = 3;

    reg [1:0] state;

    // Majority voting and bit tracking
    reg [2:0] sample_buffer;
    reg [3:0] sample_position;
    reg [3:0] bit_index;
    reg majority_bit;
    
    // Combinational majority vote computation
    wire majority_vote;
    assign majority_vote = (sample_buffer[0] + sample_buffer[1] + sample_buffer[2]) >= 2;

    // Clock synchronisation
    reg [2:0] clk_in_ff;
    wire clk_in_pulse = (clk_in_ff[1] && !clk_in_ff[2]);

    always @(posedge clk) begin
        if(rst) begin
            clk_in_ff <= 3'b111;
        end else if (en) begin
            clk_in_ff <= {clk_in_ff[1:0], clk_in};
        end
    end

    // Simple 2FF input synchronizer
    reg rxd_sync1, rxd_sync2;
    always @(posedge clk) begin
        if (rst) begin
            rxd_sync1 <= 1'b1;
            rxd_sync2 <= 1'b1;
        end else if (en) begin
            rxd_sync1 <= rx_in;
            rxd_sync2 <= rxd_sync1;
        end
    end
    wire rxd = rxd_sync2;

    // Counter for 9*16 clock cycles + 8 for initial wait
    reg [$clog2(COUNTER_END):0] clk_count;

    // ==========================================
    // DATA PATH: Counters and Sampling Logic
    // ==========================================
    always @(posedge clk) begin
        if(rst) begin
            clk_count <= 0;
            rx_out <= 0;
            sample_position <= 0;
            bit_index <= 0;
            sample_buffer <= 0;
            majority_bit <= 0;
        
        // -----------------------------------------------------------------
        // FIX 1: Synchronous Reset
        // Force reset immediately when state is FINISHED.
        // This runs on the 10MHz system clock, ensuring clk_count is 0 
        // before the next start bit arrives.
        // -----------------------------------------------------------------
        end else if (state == STATE_FINISHED) begin
            clk_count <= 0;

        end else if(clk_in_pulse) begin
            
            // --- Default Counter Logic ---
            // Run counter if we are active (not IDLE)
            if(en && state != STATE_IDLE) begin
                if(clk_count < COUNTER_END) begin
                    clk_count <= clk_count + 1;
                end
            end else if(rxd) begin
                // Keep counter reset while line is Idle (High)
                clk_count <= 0;
            end

            // --- State-Specific Overrides & Logic ---
            case (state)
                STATE_WAIT: begin
                    // Case 1: False Start (glitch) detected
                    if(clk_count == 7 && rxd) begin
                        clk_count <= 0; // Reset counter
                    end
                    // Case 2: Start bit valid, transition to Receiving
                    // FIX 2: Corrected timing. Wait exactly 1 bit period (16 ticks) 
                    // minus 2 (setup) to align RECEIVING state to start of D0.
                    // Previous value (7 + 16 - 2) caused sampling to happen at end of bit.
                    else if(clk_count == CLOCK_DIVIDER - 2) begin
                        sample_position <= 0; 
                        bit_index <= 0;
                    end
                end

                STATE_RECIEVING: begin
                    if(en) begin
                        // 1. Increment Sample Position
                        if(sample_position < 15) begin
                            sample_position <= sample_position + 1;
                        end else begin
                            sample_position <= 0;
                            // 2. Increment Bit Index
                            if(bit_index < 8) begin
                                bit_index <= bit_index + 1;
                            end
                        end

                        // 3. Collect Samples
                        case(sample_position)
                            7: sample_buffer[0] <= rxd;
                            8: sample_buffer[1] <= rxd;
                            9: sample_buffer[2] <= rxd;
                            10: begin
                                majority_bit <= majority_vote;
                                if(bit_index < 8) begin
                                    rx_out <= {majority_vote, rx_out[7:1]};
                                end
                            end
                            default: ;
                        endcase

                        // 4. End of Byte Check is handled in State Machine
                    end
                end
                default: ;
            endcase
        end
    end

    // ==========================================
    // CONTROL PATH: State Machine Transitions
    // ==========================================
    always @(posedge clk) begin
        if(rst) begin
            state <= STATE_IDLE;
        end else if(en) begin
            case (state)
                STATE_IDLE: begin
                    if(!rxd) state <= STATE_WAIT;
                end

                STATE_WAIT: begin
                    // Check for False Start at mid-point
                    if(clk_count == 7 && rxd) begin
                        state <= STATE_IDLE;
                    end
                    // Transition to Receiving after full start bit duration
                    // FIX 2: Corrected timing. Move to RECEIVING after exactly 1 bit period.
                    else if(clk_count == CLOCK_DIVIDER - 1) begin
                        state <= STATE_RECIEVING;
                    end
                end

                STATE_RECIEVING: begin
                    // Check Stop Bit (Bit 8, Position 11)
                    if(bit_index == 8 && sample_position == 11) begin
                        if(majority_bit) begin
                            state <= STATE_FINISHED; // Valid Stop Bit
                        end else begin
                            state <= STATE_IDLE;     // Framing Error
                        end
                    end
                end

                STATE_FINISHED: begin
                    // Return to IDLE immediately
                    state <= STATE_IDLE;
                end
            endcase
        end
    end

    // ==========================================
    // ERROR FLAGS
    // ==========================================
    always @(posedge clk) begin
        if(rst) begin
            frame_error <= 0;
        end else if(en) begin
            frame_error <= 0; // Auto-clear
            
            // Error on False Start
            if(state == STATE_WAIT && clk_count == 7 && rxd) begin
                frame_error <= 1;
            end

            // Error on Invalid Stop Bit
            if(state == STATE_RECIEVING && bit_index == 8 && sample_position == 11 && !majority_bit) begin
                frame_error <= 1;
            end
        end
    end

    assign ready = (state == STATE_FINISHED);

endmodule
