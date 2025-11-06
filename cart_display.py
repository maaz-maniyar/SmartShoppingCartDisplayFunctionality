#!/usr/bin/env python3
from flask import Flask, request, jsonify
from PIL import Image, ImageDraw, ImageFont
import threading
import time
import os
from evdev import InputDevice, categorize, ecodes, list_devices
import socket

# ----------------------------
# Display & Font Config
# ----------------------------
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
scroll_index = 0
VISIBLE_ROWS = 4
TRI_SIZE = 20
last_rendered_state = None

app = Flask(__name__)

# ----------------------------
# Utility: Safe render
# ----------------------------
def safe_write_to_fb(data):
    """Handle framebuffer write safely."""
    try:
        with open(FB_PATH, "wb") as f:
            f.write(data)
    except Exception as e:
        print(f"[WARN] Framebuffer not ready: {e}")

# ----------------------------
# Rendering
# ----------------------------
def rgb_to_rgb565(image):
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
    draw.text((10, 10), "🛒 Smart Cart", font=font_header, fill=(255, 255, 255))

def draw_cart_items(draw, start_y=60, row_height=45):
    global scroll_index
    y = start_y
    visible_items = cart_items[scroll_index:scroll_index + VISIBLE_ROWS]
    for idx, item in enumerate(visible_items):
        bg_color = COLOR_ROW1 if idx % 2 == 0 else COLOR_ROW2
        draw.rounded_rectangle([(10, y), (470, y+row_height-5)], radius=10, fill=bg_color)
        draw.text((20, y+10), item["name"], font=font_item, fill=COLOR_TEXT)
        draw.text((360, y+10), f"₹{item['price']}", font=font_item, fill=COLOR_TEXT)
        y += row_height
    # arrows
    if scroll_index > 0:
        draw.polygon([(240, start_y-10), (260, start_y-10), (250, start_y-30)], fill=(255, 0, 0))
    if scroll_index + VISIBLE_ROWS < len(cart_items):
        draw.polygon([(240, start_y+VISIBLE_ROWS*row_height), 
                      (260, start_y+VISIBLE_ROWS*row_height), 
                      (250, start_y+VISIBLE_ROWS*row_height+20)], fill=(255, 0, 0))

def draw_total(draw, start_y):
    total = sum(item['price'] for item in cart_items)
    draw.rectangle([(0, start_y), (WIDTH, start_y + 50)], fill=COLOR_TOTAL_BG)
    draw.text((10, start_y+10), f"Total: ₹{total}", font=font_total, fill=COLOR_TOTAL_TEXT)

def render_cart(force=False):
    global last_rendered_state
    current_state = str(cart_items) + str(scroll_index)
    if not force and current_state == last_rendered_state:
        return  # Skip rendering if nothing changed
    last_rendered_state = current_state

    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)
    draw_gradient_header(draw)
    draw_cart_items(draw)
    draw_total(draw, start_y=260)
    img_bytes = rgb_to_rgb565(img)
    safe_write_to_fb(img_bytes)

# ----------------------------
# Flask Endpoints
# ----------------------------
@app.route('/add_item', methods=['POST'])
def add_item():
    data = request.get_json()
    if not data or 'name' not in data or 'price' not in data:
        return jsonify({"error": "Missing name or price"}), 400
    cart_items.append({
        "name": data["name"],
        "price": int(data["price"]),
    })
    render_cart(force=True)
    return jsonify({"message": "Item added", "cart_size": len(cart_items)}), 200

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    cart_items.clear()
    render_cart(force=True)
    return jsonify({"message": "Cart cleared"}), 200

# ----------------------------
# Background Threads
# ----------------------------
def display_updater():
    while True:
        render_cart()
        time.sleep(1)

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    threading.Thread(target=display_updater, daemon=True).start()
    ip = socket.gethostbyname(socket.gethostname())
    print(f"TFT Display Server running at http://{ip}:5000")
    app.run(host="0.0.0.0", port=5000)
