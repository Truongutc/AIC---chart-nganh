from PIL import Image
import os

# Paths
input_png = r"D:\Github\logoaic.png"
output_ico = r"d:\Github\Phan-mem-xuat-ban\app_icon.ico"

try:
    img = Image.open(input_png)
    # Windows icons usually contain multiple sizes: 16x16, 32x32, 48x48, 64x64, 128x128, 256x256
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(output_ico, format='ICO', sizes=icon_sizes)
    print(f"Successfully converted {input_png} to {output_ico}")
except Exception as e:
    print(f"Error converting icon: {e}")
