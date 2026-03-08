// Function: Per-Modulus RNS ALU Slice (ADD / SUB / MUL)
// Hardware counterpart of Python per-channel ops in ops.py:
//   add(a, b, m) = (a + b) % m
//   sub(a, b, m) = (a - b) % m
//   mul(a, b, m) = (a * b) % m

// Data Path: Stage 3 – Modular ALUs
// Control:
//   - CU asserts ALU_EN (start operation for the specific slice)
//   - Slice asserts ALU_Done HIGH exactly one cycle later (Handshake)

// Operation Select (op_sel):
//   2'b00 : ADD
//   2'b01 : SUB
//   2'b10 : MUL
//   others: result = 0

`timescale 1ns/1ps

module rns_slice #(
    // Modulus for the specific slice (e.g. 3, 5, 7, or 11)
    parameter MODULUS = 3,

    // Bit-width of residue (must hold 0..MODULUS-1)
    parameter WIDTH   = 2
)(
    // Clock & Reset
    input  wire                 clk,
    input  wire                 rst_n,

    // Control from CU
    input  wire                 ALU_EN,     

    // Operation select - 00=ADD, 01=SUB, 10=MUL
    input  wire [1:0]           op_sel,     

    // Operand residues 
    input  wire [WIDTH-1:0]     a,
    input  wire [WIDTH-1:0]     b,

    // Result residue
    output reg  [WIDTH-1:0]     y,

    // Handshake back to CU
    output reg                  ALU_Done   
);

    // Next-cycle result (Combinational)
    reg [WIDTH-1:0] y_next;

    // Delay of ALU_EN to generate ALU_Done with 1-cycle latency
    reg             start_d;

    // Temporary Register used for modulo computations
    integer tmp;

    // Combinational core: compute next residue y_next
    always @* begin
        y_next = {WIDTH{1'b0}};
        tmp    = 0;

        case (op_sel)
            2'b00: begin
                // ADD: (a + b) mod MODULUS
                tmp    = a + b;
                tmp    = tmp % MODULUS;
                y_next = tmp[WIDTH-1:0];
            end

            2'b01: begin
                // SUB: (a - b) mod MODULUS
                // Implemented as (a + MODULUS - b) to stay non-negative
                tmp    = a + MODULUS - b;
                tmp    = tmp % MODULUS;
                y_next = tmp[WIDTH-1:0];
            end

            2'b10: begin
                // MUL: (a * b) mod MODULUS
                tmp    = a * b;
                tmp    = tmp % MODULUS;
                y_next = tmp[WIDTH-1:0];
            end

            default: begin
                // Undefined op_sel -> safe default
                y_next = {WIDTH{1'b0}};
            end
        endcase
    end

    // Sequential Interface:
    //   - When ALU_EN = 1, capture y_next on this clock edge.
    //   - ALU_Done goes HIGH on the *next* cycle.

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            y        <= {WIDTH{1'b0}};
            start_d  <= 1'b0;
            ALU_Done <= 1'b0;
        end
        else begin
            // Delay ALU_EN by one cycle to generate ALU_Done
            ALU_Done <= start_d;
            start_d  <= ALU_EN;

            // Capture result when enabled
            if (ALU_EN) begin
                y <= y_next;
            end
        end
    end

endmodule
