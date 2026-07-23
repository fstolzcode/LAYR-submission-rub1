module aes_wrapper(
    input wire clk,
    input wire rst,

    input wire en,

    input wire do_reset,
    input wire do_push_data,
    input wire do_push_key0,
    input wire do_push_key1,
    input wire do_pop,
    input wire do_set_mode,
    input wire do_start,
    input wire do_buffer_rst,

    input wire [7:0] data_input,
    output reg [7:0] data_output,

    input wire [331:0] randomness,

    output wire module_busy
);

// Internal registers for AES data
reg [127:0] data_in_reg;
reg [127:0] key_in_0_reg;
reg [127:0] key_in_1_reg;
reg enc_mode_reg;

// No counters needed - using shift-based operations

// AES control signals
reg manual_rst;
reg aes_start;

// AES interface wires
wire aes_busy;
wire aes_done;
wire [127:0] aes_out;

// FSM state encoding
localparam IDLE        = 4'd0;
localparam RESET       = 4'd1;
localparam PUSH_DATA   = 4'd2;
localparam PUSH_KEY0   = 4'd3;
localparam PUSH_KEY1   = 4'd4;
localparam POP         = 4'd5;
localparam SET_MODE    = 4'd6;
localparam START_AES   = 4'd7;
localparam WAIT_AES    = 4'd8;
localparam BUFFER_RST  = 4'd9;

reg [3:0] state;

// Module busy signal: busy when AES is busy, command is being issued, or FSM is not idle
assign module_busy = aes_busy | en | (state != IDLE);

// Main FSM
always @(posedge clk) begin
    if (rst == 1'b1) begin
        manual_rst <= 0;
        aes_start <= 0;
        data_in_reg <= 0;
        key_in_0_reg <= 0;
        key_in_1_reg <= 0;
        enc_mode_reg <= 0;
        data_output <= 0;
        state <= IDLE;
    end else begin
        case(state)
            IDLE: begin
                manual_rst <= 0;
                if(en == 1'b1) begin
                    if(do_reset) state <= RESET;
                    else if(do_push_data) state <= PUSH_DATA;
                    else if(do_push_key0) state <= PUSH_KEY0;
                    else if(do_push_key1) state <= PUSH_KEY1;
                    else if(do_pop) state <= POP;
                    else if(do_set_mode) state <= SET_MODE;
                    else if(do_start) state <= START_AES;
                    else if(do_buffer_rst) state <= BUFFER_RST;
                end else begin
                    state <= IDLE;
                end
            end

            RESET: begin
                manual_rst <= 1;
                state <= IDLE;
            end

            PUSH_DATA: begin
                data_in_reg <= {data_in_reg[119:0], data_input};
                state <= IDLE;
            end

            PUSH_KEY0: begin
                key_in_0_reg <= {key_in_0_reg[119:0], data_input};
                state <= IDLE;
            end

            PUSH_KEY1: begin
                key_in_1_reg <= {key_in_1_reg[119:0], data_input};
                state <= IDLE;
            end

            POP: begin
                data_output <= data_in_reg[127:120];
                data_in_reg <= {data_in_reg[119:0], 8'b0};
                state <= IDLE;
            end

            SET_MODE: begin
                enc_mode_reg <= data_input[0];
                state <= IDLE;
            end

            BUFFER_RST: begin
                data_in_reg <= 0;
                key_in_0_reg <= 0;
                key_in_1_reg <= 0;
                state <= IDLE;
            end

            START_AES: begin
                aes_start <= 1;
                state <= WAIT_AES;
            end

            WAIT_AES: begin
                aes_start <= 0;
                if (aes_done == 1'b1) begin
                    data_in_reg <= aes_out;
                    state <= IDLE;
                end
            end

            default: begin
                state <= IDLE;
            end
        endcase
    end
end

// Instantiate fault_protected_aes module
fault_protected_aes aes_inst (
    // Clock and Reset
    .clk(clk),
    .rst(rst | manual_rst),

    // Data Interface
    .data_in(data_in_reg),
    .key_in_0(key_in_0_reg),
    .key_in_1(key_in_1_reg),

    // Randomness
    .randomness(randomness),

    // Control
    .start(aes_start),
    .enc_mode(enc_mode_reg),

    // Output
    .fault_protect_aes_out(aes_out),
    .busy(aes_busy),
    .done(aes_done)
);

endmodule
