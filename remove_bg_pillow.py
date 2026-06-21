
import sys
from PIL import Image

def remove_black_background(img_path):
    img = Image.open(img_path).convert('RGBA')
    pixels = img.load()
    width, height = img.size
    
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            lum = 0.299*r + 0.587*g + 0.114*b
            if lum < 45:
                # Make dark pixels transparent
                # We'll fade alpha out smoothly
                # If lum is 0, alpha is 0. If lum is 45, alpha is 255.
                alpha = int((lum / 45.0) * 255)
                # Apply a curve to make it more aggressive
                alpha = int((alpha / 255.0) ** 2 * 255)
                pixels[x, y] = (r, g, b, min(a, alpha))
                
    img.save(img_path)

remove_black_background(sys.argv[1])

