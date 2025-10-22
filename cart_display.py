#!/usr/bin/env python3
from flask import Flask, request, jsonify
from PIL import Image, ImageDraw, ImageFont
import threading
import time
import os


FB_PATH = "/dev/fb1"  # TFT framebuffer
WIDTH, HEIGHT = 480, 320
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


font_header = ImageFont.truetype(FONT_PATH, 28)
font_item = ImageFont.truetype(FONT_PATH, 22)
font_total = ImageFont.truetype(FONT_PATH, 26)


COLOR_HEADER_TOP = (0, 120, 255)
COLOR_HEADER_BOTTOM = (0, 180, 255)
COLOR_ROW1 = (245, 245, 245)
COLOR_ROW2 = (220, 220, 220)
COLOR_TEXT = (0, 0, 0)
COLOR_TOTAL_BG = (50, 50, 50)
COLOR_TOTAL_TEXT = (255, 255, 255)

cart_items = []


app = Flask(__name__)

@app.route('/add_item', methods=['POST'])
def add_item():
    data = request.get_json()
    if not data or 'name' not in data or 'price' not in data:
        return jsonify({"error": "Missing name or price"}), 400
    item = {
        "name": data["name"],
        "price": int(data["price"]),
    }
    cart_items.append(item)
    return jsonify({"message": "Item added", "cart_size": len(cart_items)}), 200

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    cart_items.clear()
    return jsonify({"message": "Cart cleared"}), 200

def rgb_to_rgb565(image):
    """Convert PIL RGB image to 16-bit RGB565 bytes for TFT."""
    arr = image.convert("RGB").load()
    w, h = image.size
    data = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = arr[x, y]
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            data.append((rgb565 >> 8) & 0xFF)
            data.append(rgb565 & 0xFF)
    return bytes(data)


def draw_gradient_header(draw):
    for i in range(50):
        ratio = i / 50
        r = int(COLOR_HEADER_TOP[0]*(1-ratio) + COLOR_HEADER_BOTTOM[0]*ratio)
        g = int(COLOR_HEADER_TOP[1]*(1-ratio) + COLOR_HEADER_BOTTOM[1]*ratio)
        b = int(COLOR_HEADER_TOP[2]*(1-ratio) + COLOR_HEADER_BOTTOM[2]*ratio)
        draw.line([(0, i), (WIDTH, i)], fill=(r, g, b))
    draw.text((10,10), "🛒 Smart Cart", font=font_header, fill=(255,255,255))

def draw_cart_items(draw, start_y=60, row_height=45):
    y = start_y
    for idx, item in enumerate(cart_items[-5:]):  # last 5 items
        bg_color = COLOR_ROW1 if idx % 2 == 0 else COLOR_ROW2
        draw.rounded_rectangle([(10, y), (470, y+row_height-5)], radius=10, fill=bg_color)
        draw.text((20, y+10), item["name"], font=font_item, fill=COLOR_TEXT)
        draw.text((360, y+10), f"₹{item['price']}", font=font_item, fill=COLOR_TEXT)
        y += row_height

def draw_total(draw, start_y):
    total = sum(item['price'] for item in cart_items)
    draw.rectangle([(0, start_y), (WIDTH, start_y+50)], fill=COLOR_TOTAL_BG)
    draw.text((10, start_y+10), f"Total: ₹{total}", font=font_total, fill=COLOR_TOTAL_TEXT)


def render_cart():
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)
    draw_gradient_header(draw)
    draw_cart_items(draw)
    draw_total(draw, start_y=260)

    # Convert to RGB565 before writing to framebuffer
    img_bytes = rgb_to_rgb565(img)
    try:
        with open(FB_PATH, "wb") as f:
            f.write(img_bytes)
    except Exception as e:
        print("Framebuffer error:", e)


def display_updater():
    while True:
        render_cart()
        time.sleep(1)


if __name__ == "__main__":
    threading.Thread(target=display_updater, daemon=True).start()
    print("Server running at http://<your_pi_ip>:5000")
    app.run(host="0.0.0.0", port=5000)
