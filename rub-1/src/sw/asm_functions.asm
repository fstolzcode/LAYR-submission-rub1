CALL .main

.stop_simulation:
@ This routine is at PC=1, the simulation in software stops if PC 1 is reached. This does nothing in the real chip.
RET

.main:
@ Reset Card
LOCK 0
ROMRST
RNGRST
AESRST
STACKFLSH
RC522RST

@ README The following two lines simulate potential RAM artifacts from previous iterations. These should be enabled during software development, but disabled at tapeout.
@ REP 1, 63
@ RNGGET 0

@ Set permanent RAM values
IMMLD 0x00, 0 @ RAM[0] is always 0
IMMLD 0x01, 1 @ RAM[1] is always 1

@@ send_reqa_receive_atqa @@
.try_send_reqa:
RC522BUFRST         @ Clear FIFO buffer
RC522BLEN 7
IMMLD 0x26, 31       @ Load REQA command 0x26 into RAM[31]
RC522PUSH 31         @ Push RAM[31] to FIFO
RC522TRCVE

@ check if correct number of bits was received
RC522RXNUM	31
IMMLD 0x02, 32
CMPEQ 31, 32
JMPNC .try_send_reqa

@ receive atqa
RC522POP 31
RC522POP 32

@ verify atqa
IMMLD 0x08, 33
CMPEQ 31, 33
JMPNC .try_send_reqa

IMMLD 0x00, 33
CMPEQ 32, 33
JMPNC .try_send_reqa
@@ send_reqa_receive_atqa @@

@@ rc522_anticoll @@
RC522BUFRST         @ Clear FIFO buffer

IMMLD 0x93, 31       @ Load ANTICOLLISION command into RAM[31]
IMMLD 0x20, 32       @ Load 0x20 into RAM[32]

RC522PUSH 31         @ Push RAM[31]=0x93 to FIFO
RC522PUSH 32         @ Push RAM[32]=0x20 to FIFO
RC522BLEN 0         @ Set bit length to full byte
RC522TRCVE

@ Pop UID_0 to UID_3 and BCC
REP 1, 5
RC522POP 20
@@ rc522_anticoll @@

@@ rc522_check_bcc @@
@ The BCC is the XOR of all 4 UID bytes and acts an error check
@ UID has to be in RAM[20-23], BCC in RAM[24]

MOV 20, 15
XOR  21, 15
XOR  22, 15
XOR  23, 15
CMPEQ 15, 24

JMPNC .error_handler

@@ rc522_check_bcc @@

@@ rc522_select @@
RC522BUFRST         @ Clear FIFO buffer
CRCRST              @ Reset CRC core

IMMLD 0x93, 18
IMMLD 0x70, 19
CRCPW 18, 7

@ Push ANTICOLLISION from RAM[18] to FIFO
@ Push SEL from RAM[19] to FIFO
@ Push UID_0 from RAM[20] to FIFO
@ Push UID_1 from RAM[21] to FIFO
@ Push UID_2 from RAM[22] to FIFO
@ Push UID_3 from RAM[23] to FIFO
@ Push BCC from RAM[24] to FIFO
REP 1, 9
RC522PUSH 18

RC522TRCVE
@@ rc522_select @@

@@ receive_SAK @@
@ receive 3 bytes: 0x20, CRC, CRC

REP 1, 3
RC522POP 31

IMMLD 0x20, 30
CMPEQ 31, 30

CRCRST
CRCPC 31, 1
JMPNC .error_handler

JMPNC .error_handler

@@ receive_SAK @@

@@ rats @@
@0xE0, 0x40, CRC_L,CRC_H
RC522BUFRST
CRCRST

IMMLD 0xE0, 31
IMMLD 0x40, 32 @ 64
CRCPW 31, 2

REP 1, 4
RC522PUSH 31
RC522TRCVE
@@ rats @@

@@ receive_ATS @@
REP 1, 12
RC522POP 31 @ length of the message

CRCRST
CRCPC 31, 10
JMPNC .error_handler

@@ receive_ATS @@

@@ applet_selection @@
@ ===== APDU MESSAGES ======
RC522BUFRST
CRCRST

@ --- 1. I-Block Header ---
IMMLD 0x02, 31       @ PCB
IMMLD 0x00, 32       @ CLA: ISO/IEC 7816-4
IMMLD 0xA4, 33       @ INS: SELECT
IMMLD 0x04, 34       @ P1: Select by DF name (AID)
IMMLD 0x00, 35       @ P2: First or only occurrence
IMMLD 0x06, 36       @ LC Byte
IMMLD 0xF0, 37       @ AID Byte 1
IMMLD 0x00, 38       @ AID Byte 2
IMMLD 0x00, 39       @ AID Byte 3
IMMLD 0x0C, 40       @ AID Byte 4
IMMLD 0xDC, 41       @ AID Byte 5
IMMLD 0x01, 42       @ AID Byte 6
CRCPW  31, 12         @ --- 5. add calc CRC over 12 byte starting at 31 and add LO HI into RAM ---

REP 1, 14
RC522PUSH 31
RC522TRCVE
@@ applet_selection @@

@@ applet_selection_response @@
@ Response should be PCB, 0x90, 0x00, CRC_L, CRC_H if successful
CRCRST

REP 1, 5
RC522POP 31

@ verify the success case

IMMLD 0x90, 4
CMPEQ  32, 4
JMPNC .error_handler

IMMLD 0x00, 5
CMPEQ  33, 5
JMPNC .error_handler

CRCPC 31, 3
JMPNC .error_handler
@@ applet_selection_response @@

@@ auth_init_request @@
IMMLD 0x10, 33       @ INS = 0x10
CALL .send_case2_apdu
@@ auth_init_request @@

CALL .WTX_handler

@@ receive_auth_init_response @@
@ Card generates random 8-byte nonce (CN), computes AES_psk(rc || 00..00) using the pre-shared key and returns the ciphertext.
AESBUFRST @ only once, this flushes the key as well

@Addresses: 0-15 key1
@16-31: key 2
REP 10, 16
ROMRD 0, 31
ROMRD 16, 32
RNGGET 33
XOR 33, 31
XOR 33, 32
AESPUSHK0 31
AESPUSHK1 32
IMMLD 0, 31 @ remove secret values from ram
IMMLD 0, 32
IMMLD 0, 33

CALL .auth_message_init_verification

@ push RT (RAM[14..21]) then RC (RAM[6..13]) to AES for encryption
REP 2, 8
RNGGET 14
AESPUSHD 14

REP 1, 8
AESPUSHD 6

AESMODE 1 @  enc

@ build header 02 80 11 00 00 10
CRCRST
RC522BUFRST

IMMLD 0x02, 31
IMMLD 0x80, 32
IMMLD 0x11, 33
IMMLD 0x00, 34
IMMLD 0x00, 35
IMMLD 0x10, 36
IMMLD 0x10, 53

AESSTART
REP 1, 16
AESPOP 37

CRCPW 31, 23

REP 1, 25
RC522PUSH 31
RC522TRCVE
@@ receive_auth_init_response @@

CALL .WTX_handler

@@ receive_auth_completed @@
AESBUFRST

REP 6, 16
RNGGET 0
XOR 0, 6
AESPUSHK0 6
AESPUSHK1 0
IMMLD 0, 0
IMMLD 0, 6
IMMLD 1, 1

CALL .auth_message_init_verification

@ verify crc
REP 2, 2
RC522POP 31
CRCLD 31

CRCL 4
CRCH 5

REP 3, 2
RC522POP 6
CMPEQ 4, 6
JMPNC .error_handler

@ Partial verification of the decrypted AES content: 53 55 43 43 45 53 53 -> success
@ ignore AUTH_ because both legal messages start with AUTH_. Further, the terminal does not send security relevant information after this message. Chance for false positive is 2^-56
IMMLD 0x53, 31 @ S
IMMLD 0x55, 32 @ U
IMMLD 0x43, 33 @ C
IMMLD 0x43, 34 @ C
IMMLD 0x45, 35 @ E
IMMLD 0x53, 36 @ S
IMMLD 0x53, 37 @ S

REP 2, 7
CMPEQ 11, 31
JMPNC .error_handler
@@ receive_auth_completed @@

@@ getID_request @@
IMMLD 0x12, 33       @ INS = 0x12
CALL .send_case2_apdu
@@ getID_request @@

CALL .WTX_handler

@@ parse_getID @@
@ ephemeral key is used

@ RC522POP 31 is handled in the WTX handler
CALL .rc522_to_aes
AESMODE 0 @  dec
AESSTART
@@ parse_getID @@

@@ verify_ID @@
@ 32-47: id
REP 6, 16
ROMRD 32, 48
AESPOP 31
CMPEQ 31, 48
IMMLD 0x00, 48
IMMLD 0x00, 31
JMPNC .error_handler

@ auth_success (inlined)
IMMLD 0x42, 63
LOCK 1
@@ verify_ID @@

CALL .stop_simulation
CALL .done

@ --- Shared APDU Case 2 sender ---
@ CALLer sets RAM[33] = INS byte before CALLing
.send_case2_apdu:
RC522BUFRST
CRCRST

IMMLD 0x03, 31 @ PCB = 0x03
IMMLD 0x80, 32 @ CLA = 0x80
@ INS from RAM[33] (set by CALLer)
IMMLD 0x0, 34 @ P1 = 0x00 
IMMLD 0x0, 35 @ P2 = 0x00
IMMLD 0x10, 36 @ Le = 0x10
CRCPW 31, 6

REP 1, 8
RC522PUSH 31

RC522TRCVE
RET

.WTX_handler: @checks if incoming message is a WTX_message and responds accordingly
IMMLD 0xF2, 4 @First WTX byte
RC522POP 31
CMPEQ 31, 4
JMPNC .end_of_WTX_handler

IMMLD 4, 4 @First WTX byte
RC522RXNUM 62
CMPEQ 4, 62
JMPNC .error_handler

RC522POP 32
RC522POP 33
RC522POP 34

@ verifies CRC
CRCRST
CRCPC 31, 2
JMPNC .error_handler
RC522BUFRST

REP 1, 4
RC522PUSH 31

RC522TRCVE

JMPC .WTX_handler
.end_of_WTX_handler:
RET


.rc522_to_aes:
REP 3, 16
RC522POP 31
CRCLD 31
AESPUSHD 31
RET

.error_handler:
IMMLD 0x63,63
LOCK 0
CALL .stop_simulation
CALL .main

.auth_message_init_verification:
IMMLD 21, 4
RC522RXNUM 62
CMPEQ 4, 62
JMPNC .error_handler

CRCRST

@ WTX_handler pops first byte to 31
CRCLD 31

CALL .rc522_to_aes

AESMODE 0 @  dec
AESSTART
REP 1, 16
AESPOP 6
RET

.done:
@ Infinite loop at end
JMPC .done
JMPNC .done
