// Function: SEQUENTIAL MRC-Based RNS → Binary Reconstruction
// Moduli: [3, 5, 7, 11]
//
// This version is truly sequential:
//   - Latches residues on start (edge)
//   - Runs Stage1..Stage4 across 4 cycles
//   - Pulses MRC_Done for 1 cycle when finished
//
// Handshake compatibility with your CU:
//   - CU holds MRC_Start high in S_RECON until MRC_Done is seen.
//   - This block triggers only once per operation using a start edge detector.

`timescale 1ns/1ps

module rns_mrc_recon #(
    parameter W0        = 2,   // for modulus 3
    parameter W1        = 3,   // for modulus 5
    parameter W2        = 3,   // for modulus 7
    parameter W3        = 4,   // for modulus 11
    parameter OUT_WIDTH = 16
)(
    input  wire                 clk,
    input  wire                 rst_n,

    input  wire                 MRC_Start,

    input  wire [W0-1:0]        r0,
    input  wire [W1-1:0]        r1,
    input  wire [W2-1:0]        r2,
    input  wire [W3-1:0]        r3,

    output reg  [OUT_WIDTH-1:0] X_out,
    output reg                  MRC_Done
);

    // Constants for moduli [3,5,7,11]
    localparam integer M1 = 3;
    localparam integer M2 = 5;
    localparam integer M3 = 7;
    localparam integer M4 = 11;

    localparam integer MPREV1 = 3;    // 3
    localparam integer MPREV2 = 15;   // 3*5
    localparam integer MPREV3 = 105;  // 3*5*7
    localparam integer M      = 1155; // 3*5*7*11

    // Precomputed inverses:
    // inv_12   = (3)^(-1) mod 5  = 2
    // inv_123  = (15)^(-1) mod 7 = 1
    // inv_1234 = (105)^(-1) mod 11 = 2
    localparam integer INV_12   = 2;
    localparam integer INV_123  = 1;
    localparam integer INV_1234 = 2;

    // FSM states
    localparam [2:0]
        S_IDLE = 3'd0,
        S_S1   = 3'd1,
        S_S2   = 3'd2,
        S_S3   = 3'd3,
        S_S4   = 3'd4,
        S_DONE = 3'd5;

    reg [2:0] state;

    // Start edge detect (because CU holds MRC_Start high while in S_RECON)
    reg start_d;
    wire start_pulse = MRC_Start & ~start_d;

    // Latch residues (so they don't change mid-reconstruction)
    reg [W0-1:0] r0_r;
    reg [W1-1:0] r1_r;
    reg [W2-1:0] r2_r;
    reg [W3-1:0] r3_r;

    // Intermediate registers
    integer X1_r, X2_r, X3_r;
    integer t2, t3, t4;
    integer X4;
    integer tmp;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= S_IDLE;
            start_d  <= 1'b0;

            r0_r <= {W0{1'b0}};
            r1_r <= {W1{1'b0}};
            r2_r <= {W2{1'b0}};
            r3_r <= {W3{1'b0}};

            X1_r <= 0;
            X2_r <= 0;
            X3_r <= 0;

            X_out    <= {OUT_WIDTH{1'b0}};
            MRC_Done <= 1'b0;
        end else begin
            start_d  <= MRC_Start;
            MRC_Done <= 1'b0; // pulse only in S_DONE

            case (state)
                // Wait for a new operation
                S_IDLE: begin
                    if (start_pulse) begin
                        // latch inputs once
                        r0_r <= r0;
                        r1_r <= r1;
                        r2_r <= r2;
                        r3_r <= r3;
                        state <= S_S1;
                    end
                end

                // Cycle 1: X1 = r0 mod 3
                S_S1: begin
                    X1_r <= (r0_r % M1);
                    state <= S_S2;
                end

                // Cycle 2: t2 and X2
                // t2 = ((r1 - (X1 mod 5)) * inv_12) mod 5
                // X2 = X1 + t2*3
                S_S2: begin
                    t2 = ( (r1_r % M2) - (X1_r % M2) );
                    if (t2 < 0) t2 = t2 + M2;

                    t2 = (t2 * INV_12) % M2;
                    if (t2 < 0) t2 = t2 + M2;

                    X2_r <= X1_r + t2 * MPREV1; // + t2*3
                    state <= S_S3;
                end

                // Cycle 3: t3 and X3
                // t3 = ((r2 - (X2 mod 7)) * inv_123) mod 7
                // X3 = X2 + t3*15
                S_S3: begin
                    t3 = ( (r2_r % M3) - (X2_r % M3) );
                    if (t3 < 0) t3 = t3 + M3;

                    t3 = (t3 * INV_123) % M3; // INV_123=1
                    if (t3 < 0) t3 = t3 + M3;

                    X3_r <= X2_r + t3 * MPREV2; // + t3*15
                    state <= S_S4;
                end

                // Cycle 4: t4, X4, final reduction, write output
                // t4 = ((r3 - (X3 mod 11)) * inv_1234) mod 11
                // X4 = X3 + t4*105
                S_S4: begin
                    t4 = ( (r3_r % M4) - (X3_r % M4) );
                    if (t4 < 0) t4 = t4 + M4;

                    t4 = (t4 * INV_1234) % M4;
                    if (t4 < 0) t4 = t4 + M4;

                    X4 = X3_r + t4 * MPREV3; // + t4*105

                    // reduce into [0..1154]
                    tmp = X4 % M;
                    if (tmp < 0) tmp = tmp + M;

                    X_out <= tmp[OUT_WIDTH-1:0];
                    state <= S_DONE;
                end

                // Done pulse (1 cycle), then go idle
                S_DONE: begin
                    MRC_Done <= 1'b1;
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule