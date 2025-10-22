#!/usr/bin/env python3
from flask import Flask, request, jsonify
from PIL import Image, ImageDraw, ImageFont
import threading
import time
import os
from evdev import InputDevice, categorize, ecodes, list_devices

# ----------------------------
# Display settings
# ----------------------------
FB_PATH = "/dev/fb1"  # TFT framebuffer
WIDTH, HEIGHT = 480, 320
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

scroll_index = 0        # Index of the first visible item
VISIBLE_ROWS = 4        # Number of rows visible at a time
TRI_SIZE = 20

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

# ----------------------------
# Flask App
# ----------------------------
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

# ----------------------------
# Image rendering functions
# ----------------------------
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
    global scroll_index
    y = start_y
    visible_items = cart_items[scroll_index:scroll_index+VISIBLE_ROWS]

    for idx, item in enumerate(visible_items):
        bg_color = COLOR_ROW1 if idx % 2 == 0 else COLOR_ROW2
        draw.rounded_rectangle([(10, y), (470, y+row_height-5)], radius=10, fill=bg_color)
        draw.text((20, y+10), item["name"], font=font_item, fill=COLOR_TEXT)
        draw.text((360, y+10), f"₹{item['price']}", font=font_item, fill=COLOR_TEXT)
        draw.text((450, y+10), "X", font=font_item, fill=COLOR_TEXT)
        y += row_height

    # Down arrow (if more items below, horizontally centered)
    if scroll_index + VISIBLE_ROWS < len(cart_items):
        x_mid = (WIDTH - TRI_SIZE) / 2
        y_top = start_y + VISIBLE_ROWS * row_height - TRI_SIZE + 16
        draw.polygon([
            (x_mid, y_top),
            (x_mid + TRI_SIZE, y_top),
            (x_mid + TRI_SIZE/2, y_top + TRI_SIZE)
        ], fill=(255, 0, 0))  # bright red

    # Up arrow (if items above, horizontally centered)
    if scroll_index > 0:
        x_mid = (WIDTH - TRI_SIZE) / 2
        y_top = start_y - 10
        draw.polygon([
            (x_mid, y_top + TRI_SIZE),
            (x_mid + TRI_SIZE, y_top + TRI_SIZE),
            (x_mid + TRI_SIZE/2, y_top)
        ], fill=(255, 0, 0))  # bright red

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

    img_bytes = rgb_to_rgb565(img)
    try:
        with open(FB_PATH, "wb") as f:
            f.write(img_bytes)
    except Exception as e:
        print("Framebuffer error:", e)

# ----------------------------
# Touch handling
# ----------------------------
def touch_listener():
    global scroll_index  # <-- FIX: Declare scroll_index as global
    devices = [InputDevice(fn) for fn in list_devices()]
    ts = None
    for dev in devices:
        if "Touchscreen" in dev.name:
            ts = dev
            break
    if not ts:
        print("Touchscreen not found")
        return

    cross_positions = [
        (1091, 589),
        (1671, 576),
        (2121, 581),
        (2732, 579),
    ]
    arrow_up_pos = (941, 2086)
    arrow_down_pos = (2993, 2090)
    tolerance = 150

    x_raw = 0
    y_raw = 0
    pressed = False
    for event in ts.read_loop():
        if event.type == ecodes.EV_ABS:
            if event.code == ecodes.ABS_X:
                x_raw = event.value
            elif event.code == ecodes.ABS_Y:
                y_raw = event.value
        elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
            pressed = event.value == 1

        if event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH and event.value == 0:
            # --- Handle row X deletion ---
            if cart_items:
                for idx, (cx, cy) in enumerate(cross_positions):
                    if abs(x_raw - cx) <= tolerance and abs(y_raw - cy) <= tolerance:
                        if idx < len(cart_items):
                            print(f"Removing item via X: {cart_items[idx]['name']}")
                            highlight_row(idx)
                            time.sleep(0.3)
                            del cart_items[idx]
                        break

            # --- Scroll up ---
            if abs(x_raw - arrow_up_pos[0]) <= tolerance and abs(y_raw - arrow_up_pos[1]) <= tolerance:
                if scroll_index > 0:
                    scroll_index -= 1
                    print(f"Scrolled up: scroll_index = {scroll_index}")
                    render_cart()

            # --- Scroll down ---
            if abs(x_raw - arrow_down_pos[0]) <= tolerance and abs(y_raw - arrow_down_pos[1]) <= tolerance:
                if scroll_index + VISIBLE_ROWS < len(cart_items):
                    scroll_index += 1
                    print(f"Scrolled down: scroll_index = {scroll_index}")
                    render_cart()

def highlight_row(index):
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)
    draw_gradient_header(draw)

    start_y = 60
    row_height = 45
    y = start_y
    for idx, item in enumerate(cart_items[-5:]):
        bg_color = (255, 0, 0) if idx == index else (245, 245, 245) if idx % 2 == 0 else (220, 220, 220)
        draw.rounded_rectangle([(10, y), (470, y+row_height-5)], radius=10, fill=bg_color)
        draw.text((20, y+10), item["name"], font=font_item, fill=COLOR_TEXT)
        draw.text((360, y+10), f"₹{item['price']}", font=font_item, fill=COLOR_TEXT)
        draw.text((440, y+10), "X", font=font_item, fill=(200, 0, 0))
        y += row_height

    draw_total(draw, start_y=260)
    img_bytes = rgb_to_rgb565(img)
    try:
        with open(FB_PATH, "wb") as f:
            f.write(img_bytes)
    except Exception as e:
        print("Framebuffer error:", e)

# ----------------------------
# Threads
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
    threading.Thread(target=touch_listener, daemon=True).start()
    print("Server running at http://<your_pi_ip>:5000")
    app.run(host="0.0.0.0", port=5000)
