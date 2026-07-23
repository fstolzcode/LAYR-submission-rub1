module crc (
    input wire clk,
    input wire rst,  // Active-high reset
    input wire [7:0] data_in,  // Input (MSB first)
    input wire load_byte,  // Pulse high to load and process a byte
    output reg [15:0] crc_out,  // Output CRC
    output reg busy  // High while processing
);

    localparam POLY = 16'h8408;  // x^16 + x^12 + x^5 + 1 in reversed
    localparam INITIAL_CRC = 16'h6363;  // Initial value to 0x6363

    // States
    localparam IDLE = 1'b0;
    localparam PROCESSING = 1'b1;

    reg state;
    reg [2:0] bit_counter;  // Simple counter from 0-7
    reg [7:0] data_buffer;  // Store byte to process

    always @(posedge clk) begin
        if (rst) begin
            // RESET
            crc_out <= INITIAL_CRC;
            busy <= 1'b0;
            state <= IDLE;
            bit_counter <= 3'd0;
            data_buffer <= 8'h00;
        end else begin
            case (state)
                IDLE: begin
                    busy <= 1'b0;

                    if (load_byte) begin
                        // Load new byte
                        data_buffer <= data_in;
                        bit_counter <= 3'd0;
                        state <= PROCESSING;
                        busy <= 1'b1;
                    end
                end

                PROCESSING: begin
                    // Process one bit per clock cycle
                    // Data comes in MSB-first per byte, but CRC algorithm is LSB-first
                    // So we process from bit 0, then 1, then 2, etc. (LSB to MSB)

                    // XOR the LSB of CRC with current data bit (LSB of buffer)
                    if (crc_out[0] ^ data_buffer[0]) begin
                        crc_out <= (crc_out >> 1) ^ POLY;
                    end else begin
                        crc_out <= crc_out >> 1;
                    end

                    data_buffer <= data_buffer >> 1;

                    // Increment counter
                    if (bit_counter == 3'd7) begin
                        // Finished
                        state <= IDLE;
                        busy  <= 1'b0;
                    end else begin
                        bit_counter <= bit_counter + 1;
                    end
                end

                default: begin
                    state <= IDLE;
                end
            endcase
        end
    end

endmodule
