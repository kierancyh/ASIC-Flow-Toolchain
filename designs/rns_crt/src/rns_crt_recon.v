// Function: CRT-Based RNS → Binary Reconstruction
// Hardware counterpart of Python crt.reconstruct() for moduli: [3, 5, 7, 11]   

// Formula implemented:
//   M   = 3 * 5 * 7 * 11 = 1155
//   Mi  = [385, 231, 165, 105]
//   inv = [1, 1, 2, 2]
//
//   X = ( x0 * 385 * 1
//       + x1 * 231 * 1
//       + x2 * 165 * 2
//       + x3 * 105 * 2 ) mod 1155

// Control:
//   - CU asserts CRT_Start to trigger reconstruction
//   - Block asserts CRT_Done HIGH exactly one cycle later

// Notes:
//   - Unsigned domain [0 .. M-1] = [0 .. 1154]
//   - OUT_WIDTH can be ≥ 11; default 16 bits for convenience.

`timescale 1ns/1ps

module rns_crt_recon #(
    // Bit-widths of each residue (must match encoder/ALU slices)
    parameter W0        = 2,   // for modulus 3
    parameter W1        = 3,   // for modulus 5
    parameter W2        = 3,   // for modulus 7
    parameter W3        = 4,   // for modulus 11

    // Output width (11 bits needed for 0..1154; use 16 for alignment)
    parameter OUT_WIDTH = 16
)(
    // Clock & Reset
    input  wire                 clk,
    input  wire                 rst_n,

    // Control from CU
    input  wire                 CRT_Start,   // Start reconstruction

    // Residue inputs from modular ALUs
    input  wire [W0-1:0]        r0,         // residue mod 3
    input  wire [W1-1:0]        r1,         // residue mod 5
    input  wire [W2-1:0]        r2,         // residue mod 7
    input  wire [W3-1:0]        r3,         // residue mod 11

    // Reconstructed integer output
    output reg  [OUT_WIDTH-1:0] X_out,

    // Handshake back to CU
    output reg                  CRT_Done
);

    // Precomputed CRT constants for moduli [3, 5, 7, 11]
    // Product of all moduli
    localparam integer M    = 1155;

    // Mi = M / mi
    localparam integer M0   = 385;  // 1155 / 3
    localparam integer M1   = 231;  // 1155 / 5
    localparam integer M2   = 165;  // 1155 / 7
    localparam integer M3   = 105;  // 1155 / 11

    // inv_i = (Mi^-1 mod mi)
    localparam integer INV0 = 1;    // 385^-1 mod 3
    localparam integer INV1 = 1;    // 231^-1 mod 5
    localparam integer INV2 = 2;    // 165^-1 mod 7
    localparam integer INV3 = 2;    // 105^-1 mod 11

    // Internal Temporaries (Combinational)
    integer term0, term1, term2, term3;
    integer total;
    reg [OUT_WIDTH-1:0] X_next;

    // One-cycle delay for done signal
    reg start_d;

    // Combinational CRT core: Compute next reconstructed value X_next

    always @* begin
        term0 = 0;
        term1 = 0;
        term2 = 0;
        term3 = 0;
        total = 0;
        X_next = {OUT_WIDTH{1'b0}};

        // Each term: (xi % mi) * Mi * inv_i
        // Since residues are already < mi, the "% mi" is redundant but harmless.
        term0 = (r0 % 3)  * M0 * INV0;
        term1 = (r1 % 5)  * M1 * INV1;
        term2 = (r2 % 7)  * M2 * INV2;
        term3 = (r3 % 11) * M3 * INV3;

        total = term0 + term1 + term2 + term3;

        // Final reduction modulo M
        total = total % M;

        // Truncate/fit into OUT_WIDTH (OUT_WIDTH >= 11 recommended)
        X_next = total[OUT_WIDTH-1:0];
    end

    // Sequential Interface:
    //   - On CRT_Start, capture X_next into X_out.
    //   - CRT_Done pulses HIGH one cycle later.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            X_out    <= {OUT_WIDTH{1'b0}};
            CRT_Done <= 1'b0;
            start_d  <= 1'b0;
        end
        else begin
            // One-cycle delayed start used to assert CRT_Done
            CRT_Done <= start_d;
            start_d  <= CRT_Start;

            // Capture new result when reconstruction is triggered
            if (CRT_Start) begin
                X_out <= X_next;
            end
        end
    end

endmodule
