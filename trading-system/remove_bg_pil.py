import sys
from PIL import Image

def remove_dark_background(input_path, output_path, threshold=40):
    img = Image.open(input_path).convert("RGBA")
    datas = img.getdata()

    new_data = []
    for item in datas:
        # Check if pixel is dark (r, g, b are all below threshold)
        if item[0] < threshold and item[1] < threshold and item[2] < threshold:
            # Change to transparent
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)

    img.putdata(new_data)
    img.save(output_path, "PNG")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        remove_dark_background(sys.argv[1], sys.argv[2])
    else:
        print("Provide input and output paths.")
