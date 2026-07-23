module rom (
    input wire [8:0] address, // for now 10 bit address (1024 possible locations)
    output wire [17:0] data, // for now 18 bits (can be larger)

    input wire [8:0] dbg_address,
    output wire [17:0] dbg_data
);

reg [17:0] memory [0:511]; // 1024 18 bit locations

initial begin
    $readmemh("rtl/rom.mem", memory);
end
assign data = memory[address];
assign dbg_data = memory[dbg_address];

endmodule
