import sys
try:
    import qrcode
except ImportError:
    print("Please install qrcode: pip install qrcode[pil]")
    sys.exit(1)

phone_number = "233557635680"
url = f"https://wa.me/{phone_number}?text=HI"
img = qrcode.make(url)
img.save("bot_qr.png")
print("Generated bot_qr.png")
