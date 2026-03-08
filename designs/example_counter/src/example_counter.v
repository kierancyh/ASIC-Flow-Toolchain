module example_counter (
    input  wire clk,
    input  wire rst_n,
    output reg  [7:0] count
);
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) count <= 8'd0;
    else        count <= count + 8'd1;
  end
endmodule
