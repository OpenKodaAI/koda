from PIL import Image

# Open the original image
img_path = "/Users/larissamiyoshi/Downloads/freepik_recrie-essa-logo-para-uma_2829097707.jpeg"
try:
    img = Image.open(img_path)
    width, height = img.size

    # Define portrait target (e.g. 4:5 aspect ratio)
    # Since we want it to be portrait, we make height the max, and width smaller.
    # Current is 2048x2048.
    target_height = height
    target_width = int(height * 0.75) # 3:4 aspect ratio

    if target_width < width:
        left = (width - target_width) / 2
        right = (width + target_width) / 2
        top = 0
        bottom = height
        img_cropped = img.crop((left, top, right, bottom))
        # Save giving it a new name
        out_path = "docs/assets/brand/koda_hero.jpg"
        img_cropped.save(out_path, quality=95)
        print("Image cropped and saved!")
    else:
        print("Image already portrait or narrow enough")
except Exception as e:
    print(f"Error: {e}")
