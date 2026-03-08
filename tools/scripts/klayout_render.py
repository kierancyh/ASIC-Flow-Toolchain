# KLayout batch script: reads INPUT GDS and writes OUTPUT PNG
import pya, os

inp = pya.Application.instance().get_config("rd.INPUT")
out = pya.Application.instance().get_config("rd.OUTPUT")

ly = pya.Layout()
ly.read(inp)

# Create a view in batch mode
mw = pya.MainWindow.instance()
lv = mw.create_layout(0)
cv = lv.active_cellview()
cv.layout().assign(ly)
cv.cell = ly.top_cell()

# Show all and export
lv.add_missing_layers()
lv.zoom_fit()

# Width/height in pixels
W, H = 1600, 1200
lv.save_image(out, W, H)