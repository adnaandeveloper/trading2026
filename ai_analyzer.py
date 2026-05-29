import cv2
import numpy as np
import re
import easyocr

reader = easyocr.Reader(['en'], gpu=False)

def analyze_trade_image(path):
    img = cv2.imread(path)
    if img is None:
        return {"instrument":"UNKNOWN","size":1,"direction":"long","entry":0,"tp":0,"sl":0}
    h, w = img.shape[:2]

    texts = reader.readtext(img, detail=0)
    full = " ".join(texts).upper()

    instrument = "UNKNOWN"
    if "MICRO GOLD" in full: instrument = "MGC"
    elif "GOLD" in full: instrument = "GC"
    elif "US500" in full or "SPX" in full: instrument = "ES"
    elif "NAS" in full: instrument = "NQ"
    elif "EURUSD" in full: instrument = "EURUSD"

    size_match = re.search(r'(\d+\.?\d*)\s*C', full)
    size = float(size_match.group(1)) if size_match else 1.0

    prices = []
    for t in texts:
        t_clean = t.replace(',','').strip()
        if re.match(r'^\d{3,5}\.\d$', t_clean):
            try: prices.append(float(t_clean))
            except: pass
    top_price = max(prices) if prices else 4550
    bot_price = min(prices) if prices else 4520

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, np.array([100,50,50]), np.array([130,255,255]))
    red_mask = cv2.inRange(hsv, np.array([0,70,50]), np.array([10,255,255])) + cv2.inRange(hsv, np.array([160,70,50]), np.array([180,255,255]))

    blue_ys = np.where(blue_mask>0)[0]
    red_ys = np.where(red_mask>0)[0]

    tp_y = int(blue_ys.min()) if len(blue_ys) else int(h*0.2)
    sl_y = int(red_ys.max()) if len(red_ys) else int(h*0.8)
    entry_y = int(h*0.5)

    def y_to_price(y): return round(top_price - (y/h)*(top_price-bot_price),1)

    tp = y_to_price(tp_y)
    sl = y_to_price(sl_y)
    entry = y_to_price(entry_y)
    direction = "long" if tp > sl else "short"

    return {
        "instrument": instrument,
        "size": size,
        "direction": direction,
        "entry": entry,
        "tp": tp,
        "sl": sl
    }