// Function: Control Unit for RNS ALU (CU FSM)

// Controls the pipeline: 
//   IDLE -> LOAD -> ENCODE -> ALU -> RECON -> OUT -> DONE

// Controls:
//   - rns_encoder.v   (Encode_EN / Encode_Done)
//   - rns_slice.v     (ALU_EN / ALU_Done)
//   - rns_crt_recon.v (CRT_Start / CRT_Done)
//   - rns_mrc_recon.v (MRC_Start / MRC_Done)

// Reconstruction Selection (runtime):
//   Recon_Mode = 0 -> use CRT
//   Recon_Mode = 1 -> use MRC

`timescale 1ns/1ps

module rns_cu (
    // Clock & Reset
    input  wire clk,
    input  wire rst_n,

    // External control
    input  wire Start,         // Start a new operation
    input  wire Recon_Mode,    // 0 = CRT, 1 = MRC
    output reg  Done,          // High when full operation completed
    output wire [2:0] CU_state_dbg, // Debug: Current CU FSM state

    // Handshakes from Data Path
    input  wire Encode_Done,   // Encoders finished
    input  wire ALU_Done,      // All ALU slices finished
    input  wire CRT_Done,      // CRT reconstructor finished
    input  wire MRC_Done,      // MRC reconstructor finished

    // Control outputs to Data Path 
    output reg  Load_IN,       // Latch A, B, OpSel into input regs
    output reg  Encode_EN,     // Enable encoders
    output reg  ALU_EN,        // Enable modular ALUs
    output reg  CRT_Start,     // Trigger CRT reconstruction
    output reg  MRC_Start,     // Trigger MRC reconstruction
    output reg  Out_EN         // Latch final X_out register
);

    // State Encoding
    localparam [2:0]
        S_IDLE   = 3'd0,
        S_LOAD   = 3'd1,
        S_ENCODE = 3'd2,
        S_ALU    = 3'd3,
        S_RECON  = 3'd4,
        S_OUT    = 3'd5,
        S_DONE   = 3'd6;

    reg [2:0] state, next_state;

    // State Register
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= S_IDLE;
        else
            state <= next_state;
    end

    // Next-State Logic
    wire recon_done_sel;
    assign recon_done_sel = (Recon_Mode == 1'b0) ? CRT_Done : MRC_Done;

    always @* begin
        next_state = state; // Default hold

        case (state)
            S_IDLE:   if (Start)       next_state = S_LOAD;
            S_LOAD:                    next_state = S_ENCODE;
            S_ENCODE: if (Encode_Done) next_state = S_ALU;
            S_ALU:    if (ALU_Done)    next_state = S_RECON;
            S_RECON:  if (recon_done_sel) next_state = S_OUT;
            S_OUT:                     next_state = S_DONE;
            S_DONE:   if (!Start)      next_state = S_IDLE;
            default:                   next_state = S_IDLE;
        endcase
    end

    // Output Logic (Moore FSM)
    always @* begin
        // Default all controls LOW
        Load_IN   = 1'b0;
        Encode_EN = 1'b0;
        ALU_EN    = 1'b0;
        CRT_Start = 1'b0;
        MRC_Start = 1'b0;
        Out_EN    = 1'b0;
        Done      = 1'b0;

        case (state)
            S_LOAD:   Load_IN   = 1'b1;
            S_ENCODE: Encode_EN = 1'b1;
            S_ALU:    ALU_EN    = 1'b1;

            S_RECON: begin
                if (Recon_Mode == 1'b0)
                    CRT_Start = 1'b1;
                else
                    MRC_Start = 1'b1;
            end

            S_OUT:  Out_EN = 1'b1;
            S_DONE: Done   = 1'b1;
        endcase
    end

    // Expose internal state for debugging
    assign CU_state_dbg = state;

endmodule
