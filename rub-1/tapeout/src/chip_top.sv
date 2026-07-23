// SPDX-FileCopyrightText: © 2025 Fl
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module rubteam1 (
    `ifdef USE_POWER_PINS
    inout wire IOVDD,
    inout wire IOVSS,
    inout wire VDD,
    inout wire VSS,
    `endif
    // IO Pads
    inout wire rst_PAD,
    inout wire sys_clk_PAD,
    inout wire uart_clk_PAD,
    inout wire user_io_0_PAD,
    inout wire uart_rx_PAD,
    inout wire uart_tx_PAD,
    inout wire user_io_1_PAD,
    inout wire user_io_2_PAD,
    inout wire user_io_3_PAD,
    inout wire user_io_4_PAD,
    inout wire cs_0_PAD,
    inout wire cs_1_PAD,
    inout wire spi_miso_PAD,
    inout wire spi_mosi_PAD,
    inout wire spi_sclk_PAD,
    inout wire status_unlock_PAD,
    inout wire status_fault_PAD,
    inout wire status_busy_PAD
);

    //----------------------------------
    // PAD2CORE and CORE2PAD wires
    //----------------------------------
    wire rst_PAD2CORE, sys_clk_PAD2CORE, uart_clk_PAD2CORE, user_io_0_PAD2CORE, uart_rx_PAD2CORE, uart_tx_CORE2PAD;
    wire user_io_1_CORE2PAD, user_io_2_CORE2PAD, user_io_3_CORE2PAD, user_io_4_CORE2PAD;
    wire status_busy_CORE2PAD, status_fault_CORE2PAD, status_unlock_CORE2PAD;
    wire spi_sclk_CORE2PAD, spi_mosi_CORE2PAD, spi_miso_PAD2CORE, cs_0_CORE2PAD, cs_1_CORE2PAD;

    //----------------------------------
    // Power / ground pad instances
    //----------------------------------
    // VDD South
    (* keep *) sg13g2_IOPadVdd vdd_south_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS)
        `endif
    );

    // VSS South
    (* keep *) sg13g2_IOPadVss vss_south_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS)
        `endif
    );

    // IO VDD North
    (* keep *) sg13g2_IOPadIOVdd iovdd_north_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS)
        `endif
    );

    // IO VSS North
    (* keep *) sg13g2_IOPadIOVss iovss_north_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS)
        `endif
    );

    // VDD North
    (* keep *) sg13g2_IOPadVdd vdd_north_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS)
        `endif
    );

    // VSS East
    (* keep *) sg13g2_IOPadVss vss_east_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS)
        `endif
    );

    //----------------------------------
    // Input pad instances
    //----------------------------------
    // rst
    sg13g2_IOPadIn rst_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .p2c    (rst_PAD2CORE),
        .pad    (rst_PAD)
    );

    // sys_clk
    sg13g2_IOPadIn sys_clk_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .p2c    (sys_clk_PAD2CORE),
        .pad    (sys_clk_PAD)
    );

    // uart_clk
    sg13g2_IOPadIn uart_clk_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .p2c    (uart_clk_PAD2CORE),
        .pad    (uart_clk_PAD)
    );

    // user_io_0
    sg13g2_IOPadIn user_io_0_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .p2c    (user_io_0_PAD2CORE),
        .pad    (user_io_0_PAD)
    );

    // uart_rx
    sg13g2_IOPadIn uart_rx_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .p2c    (uart_rx_PAD2CORE),
        .pad    (uart_rx_PAD)
    );

    // spi_sclk
    sg13g2_IOPadOut30mA spi_sclk_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (spi_sclk_CORE2PAD),
        .pad    (spi_sclk_PAD)
    );

    // spi_miso
    sg13g2_IOPadIn spi_miso_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .p2c    (spi_miso_PAD2CORE),
        .pad    (spi_miso_PAD)
    );

    //----------------------------------
    // Output pad instances
    //----------------------------------
    // user_io_1
    sg13g2_IOPadOut30mA user_io_1_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (user_io_1_CORE2PAD),
        .pad    (user_io_1_PAD)
    );

    // user_io_2
    sg13g2_IOPadOut30mA user_io_2_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (user_io_2_CORE2PAD),
        .pad    (user_io_2_PAD)
    );

    // user_io_3
    sg13g2_IOPadOut30mA user_io_3_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (user_io_3_CORE2PAD),
        .pad    (user_io_3_PAD)
    );

    // user_io_4
    sg13g2_IOPadOut30mA user_io_4_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (user_io_4_CORE2PAD),
        .pad    (user_io_4_PAD)
    );

    // uart_tx
    sg13g2_IOPadOut30mA uart_tx_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (uart_tx_CORE2PAD),
        .pad    (uart_tx_PAD)
    );

    // cs_0
    sg13g2_IOPadOut30mA cs_0_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (cs_0_CORE2PAD),
        .pad    (cs_0_PAD)
    );

    // cs_1
    sg13g2_IOPadOut30mA cs_1_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (cs_1_CORE2PAD),
        .pad    (cs_1_PAD)
    );

    // spi_mosi
    sg13g2_IOPadOut30mA spi_mosi_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (spi_mosi_CORE2PAD),
        .pad    (spi_mosi_PAD)
    );

    // status_busy
    sg13g2_IOPadOut30mA status_busy_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (status_busy_CORE2PAD),
        .pad    (status_busy_PAD)
    );

    // status_fault
    sg13g2_IOPadOut30mA status_fault_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (status_fault_CORE2PAD),
        .pad    (status_fault_PAD)
    );

    // status_unlock
    sg13g2_IOPadOut30mA status_unlock_pad (
        `ifdef USE_POWER_PINS
        .iovdd  (IOVDD),
        .iovss  (IOVSS),
        .vdd    (VDD),
        .vss    (VSS),
        `endif
        .c2p    (status_unlock_CORE2PAD),
        .pad    (status_unlock_PAD)
    );


    //----------------------------------
    // Instantiate core design
    //----------------------------------
    (* keep *) main_controller i_main_controller (
        .clk         (sys_clk_PAD2CORE),
        .uart_clk_in (uart_clk_PAD2CORE),
        .rst         (rst_PAD2CORE),
        .mode        (user_io_0_PAD2CORE),
        .uart_rxd    (uart_rx_PAD2CORE),
        .uart_txd    (uart_tx_CORE2PAD),
        .spi_sclk    (spi_sclk_CORE2PAD),
        .spi_mosi    (spi_mosi_CORE2PAD),
        .spi_miso    (spi_miso_PAD2CORE),
        .spi_cs_0    (cs_0_CORE2PAD),
        .spi_cs_1    (cs_1_CORE2PAD),
        .busy        (status_busy_CORE2PAD),
        .hard_fault  (status_fault_CORE2PAD),
        .unlock      (status_unlock_CORE2PAD)
    );

    // Tie off unused output pads to logic LOW
    assign user_io_1_CORE2PAD = 1'b0;
    assign user_io_2_CORE2PAD = 1'b0;
    assign user_io_3_CORE2PAD = 1'b0;
    assign user_io_4_CORE2PAD = 1'b0;

endmodule

`default_nettype wire
