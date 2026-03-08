// Function: Forward Conversion (Binary → Residues)
// Hardware counterpart of Python encode(): encode(x, [3, 5, 7, 11])

// Data Path: Stage 2 – Encoder Bank
// Control:
//   - CU asserts Encode_EN
//   - Encoder outputs Encode_Done high for 1 cycle
// Moduli Set: M0 = 3, M1 = 5, M2 = 7, M3 = 11

// Notes:
//   - Unsigned domain only (x ≥ 0).
//   - One-cycle latency.
//   - Modulus operations are constant-mod (synthesizable)

`timescale 1ns/1ps

module rns_encoder #(
    parameter WIDTH_IN = 16,   // Width of binary input integer

    // Moduli (pairwise coprime)
    parameter M0 = 3,
    parameter M1 = 5,
    parameter M2 = 7,
    parameter M3 = 11,

    // Bit-width of each residue (must hold 0..Mi-1)
    parameter W0 = 2,          // ceil(log2(3))
    parameter W1 = 3,          // ceil(log2(5))
    parameter W2 = 3,          // ceil(log2(7))
    parameter W3 = 4           // ceil(log2(11))
)(
    // Clock & Reset
    input  wire                 clk,
    input  wire                 rst_n,

    // Control from CU
    input  wire                 Encode_EN,    

    // Binary input (unsigned)
    input  wire [WIDTH_IN-1:0]  x,

    // Handshake back to CU
    output reg                  Encode_Done,  

    // Residue outputs
    output reg [W0-1:0]         r0,  // x mod M0
    output reg [W1-1:0]         r1,  // x mod M1
    output reg [W2-1:0]         r2,  // x mod M2
    output reg [W3-1:0]         r3   // x mod M3
);

    // Internal Temporaries 
    integer tmp0, tmp1, tmp2, tmp3;

    // Sequential Modulo Computation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            Encode_Done <= 1'b0;

            r0 <= {W0{1'b0}};
            r1 <= {W1{1'b0}};
            r2 <= {W2{1'b0}};
            r3 <= {W3{1'b0}};
        end
        else begin
            Encode_Done <= 1'b0;   // default every cycle

            if (Encode_EN) begin
                tmp0 = x % M0;
                tmp1 = x % M1;
                tmp2 = x % M2;
                tmp3 = x % M3;

                // Assign residues
                r0 <= tmp0[W0-1:0];
                r1 <= tmp1[W1-1:0];
                r2 <= tmp2[W2-1:0];
                r3 <= tmp3[W3-1:0];

                // Signal completion
                Encode_Done <= 1'b1;
            end
        end
    end

endmodule
