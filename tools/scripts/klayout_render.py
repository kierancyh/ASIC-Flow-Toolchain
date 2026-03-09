# KLayout batch script: reads INPUT GDS and writes OUTPUT PNG
import pya

app = pya.Application.instance()

inp = app.get_config("rd.INPUT")
out = app.get_config("rd.OUTPUT")
width = app.get_config("rd.WIDTH")
height = app.get_config("rd.HEIGHT")

W = int(width) if width else 1600
H = int(height) if height else 1200

ly = pya.Layout()
ly.read(inp)

mw = pya.MainWindow.instance()
lv = mw.create_layout(0)
cv = lv.active_cellview()
cv.layout().assign(ly)
cv.cell = ly.top_cell()

lv.add_missing_layers()
lv.zoom_fit()
lv.save_image(out, W, H)