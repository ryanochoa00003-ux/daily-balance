"""Calorie estimator (pure Python, no GUI). Used by main.py."""
import difflib
import json
import re
import ssl
import urllib.parse
import urllib.request


def _ssl_ctx():
    """Android needs certifi's certificate list for HTTPS."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


# ---------------------------------------------------------------- calorie estimator
# (names, kcal per serving, grams per serving, serving label)
FOODS = [
    (("egg", "boiled egg"), 78, 50, "large"),
    (("fried egg",), 90, 46, "large"),
    (("scrambled egg",), 91, 61, "large egg"),
    (("omelette", "omelet"), 154, 100, "2-egg"),
    (("white rice", "rice", "steamed rice", "cooked rice"), 205, 158, "cup cooked"),
    (("brown rice",), 216, 195, "cup cooked"),
    (("fried rice",), 238, 198, "cup"),
    (("bread", "toast", "white bread"), 75, 28, "slice"),
    (("wheat bread", "whole wheat bread"), 81, 33, "slice"),
    (("oatmeal", "oats", "porridge"), 154, 234, "cup cooked"),
    (("cereal", "corn flakes"), 100, 28, "cup"),
    (("pancake",), 90, 38, "medium"),
    (("waffle",), 218, 75, "piece"),
    (("banana",), 105, 118, "medium"),
    (("apple",), 95, 182, "medium"),
    (("orange",), 62, 131, "medium"),
    (("mango",), 99, 165, "cup sliced"),
    (("pineapple",), 82, 165, "cup"),
    (("grapes",), 104, 151, "cup"),
    (("strawberries",), 49, 152, "cup"),
    (("watermelon",), 46, 152, "cup"),
    (("avocado",), 240, 150, "whole"),
    (("chicken breast", "chicken", "grilled chicken"), 284, 172, "breast"),
    (("fried chicken",), 320, 130, "piece"),
    (("chicken adobo", "pork adobo", "adobo"), 300, 200, "serving"),
    (("steak", "beef steak"), 350, 170, "6 oz"),
    (("ground beef", "beef"), 250, 100, "100 g"),
    (("pork chop",), 340, 150, "chop"),
    (("pork",), 240, 100, "100 g"),
    (("bacon",), 43, 8, "slice"),
    (("sausage", "longganisa"), 90, 45, "link"),
    (("hotdog", "hot dog"), 150, 50, "piece"),
    (("salmon",), 280, 154, "fillet"),
    (("tuna",), 130, 85, "can drained"),
    (("shrimp",), 99, 100, "100 g"),
    (("fish",), 150, 100, "100 g"),
    (("tofu",), 94, 126, "1/2 cup"),
    (("beans", "black beans"), 225, 177, "cup cooked"),
    (("lentils",), 230, 198, "cup cooked"),
    (("baked potato", "potato"), 160, 173, "medium"),
    (("french fries", "fries"), 365, 117, "medium order"),
    (("mashed potato",), 214, 210, "cup"),
    (("sweet potato",), 112, 130, "medium"),
    (("spaghetti", "pasta", "noodles"), 220, 140, "cup cooked"),
    (("pancit",), 250, 200, "cup"),
    (("instant noodles", "ramen"), 380, 85, "pack"),
    (("pizza",), 285, 107, "slice"),
    (("hamburger", "burger"), 354, 110, "burger"),
    (("cheeseburger",), 400, 120, "burger"),
    (("sandwich",), 350, 150, "sandwich"),
    (("dumpling", "siomai", "gyoza"), 40, 25, "piece"),
    (("lumpia", "spring roll"), 60, 40, "piece"),
    (("sinigang",), 200, 300, "bowl"),
    (("sushi", "sushi roll"), 250, 180, "6 pieces"),
    (("salad", "green salad"), 35, 100, "bowl"),
    (("caesar salad",), 190, 150, "bowl"),
    (("broccoli",), 55, 156, "cup"),
    (("carrot",), 25, 61, "medium"),
    (("tomato",), 22, 123, "medium"),
    (("corn",), 132, 154, "cup"),
    (("milk",), 149, 244, "cup"),
    (("yogurt", "yoghurt"), 150, 245, "cup"),
    (("cheese",), 113, 28, "slice"),
    (("butter",), 102, 14, "tbsp"),
    (("olive oil", "oil"), 119, 14, "tbsp"),
    (("peanut butter",), 94, 16, "tbsp"),
    (("sugar",), 16, 4, "tsp"),
    (("honey",), 64, 21, "tbsp"),
    (("coffee", "black coffee"), 2, 240, "cup"),
    (("latte",), 190, 360, "12 oz"),
    (("cappuccino",), 120, 240, "8 oz"),
    (("tea",), 2, 240, "cup"),
    (("milk tea",), 300, 500, "medium"),
    (("soda", "cola", "coke"), 140, 355, "can"),
    (("orange juice", "juice"), 112, 248, "cup"),
    (("beer",), 153, 356, "can"),
    (("wine",), 125, 148, "glass"),
    (("chocolate", "chocolate bar"), 230, 43, "bar"),
    (("cookie",), 150, 30, "cookie"),
    (("ice cream",), 137, 66, "scoop"),
    (("cake",), 350, 100, "slice"),
    (("donut", "doughnut"), 269, 60, "donut"),
    (("chips", "potato chips"), 150, 28, "1 oz"),
    (("popcorn",), 31, 8, "cup"),
    (("almonds", "nuts"), 164, 28, "1 oz"),
    (("peanuts",), 166, 28, "1 oz"),
    (("granola bar",), 120, 30, "bar"),
    (("mac and cheese",), 310, 200, "cup"),
]
UNIT_G = {"g": 1, "gram": 1, "grams": 1, "kg": 1000, "oz": 28.35, "ml": 1}
WORDNUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "half": 0.5}
QTY_RE = re.compile(
    r"^\s*(?P<num>\d+\s+\d+/\d+|\d+/\d+|\d*\.?\d+)?\s*"
    r"(?:(?P<unit>kg|g|grams?|oz|ml)(?=\s|$))?\s*(?:of\s+)?(?P<name>.*)$", re.I)


def norm(s):
    """Lower-case and strip simple plurals so 'eggs' matches 'egg'."""
    words = re.findall(r"[a-z]+", s.lower())
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words)


INDEX = {}
for _entry in FOODS:
    for _nm in _entry[0]:
        INDEX.setdefault(norm(_nm), _entry)


def _to_num(s):
    try:
        s = s.strip()
        if " " in s and "/" in s:
            whole, frac = s.split()
            a, b = frac.split("/")
            return int(whole) + int(a) / int(b)
        if "/" in s:
            a, b = s.split("/")
            return int(a) / int(b)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


def parse_item(text):
    """'2 eggs' -> (2, '', 'eggs');  '150g chicken' -> (150, 'g', 'chicken')."""
    m = QTY_RE.match(text.strip())
    num = _to_num(m.group("num")) if m.group("num") else None
    unit = (m.group("unit") or "").lower()
    name = m.group("name").strip()
    if num is None:
        first, _, rest = name.partition(" ")
        if first.lower() in WORDNUM and rest:
            num, name = WORDNUM[first.lower()], rest.strip()
    return num, unit, name


def find_food(name, exact_only=False):
    n = norm(name)
    if not n:
        return None
    if n in INDEX:
        return INDEX[n]
    if exact_only:
        return None
    padded = f" {n} "
    hits = [k for k in INDEX if f" {k} " in padded]          # "grilled chicken breast" -> chicken breast
    if hits:
        return INDEX[max(hits, key=len)]
    hits = [k for k in INDEX if padded in f" {k} "]          # "chip" -> potato chip
    if hits:
        return INDEX[min(hits, key=len)]
    close = difflib.get_close_matches(n, list(INDEX), n=1, cutoff=0.82)   # typos
    return INDEX[close[0]] if close else None


def estimate_item(text, exact_only=False):
    num, unit, name = parse_item(text)
    entry = find_food(name, exact_only)
    if not entry:
        return None
    names, kcal, grams, label = entry
    if unit:
        amount = num or 100
        mult = amount * UNIT_G[unit] / grams
        desc = f"{amount:g} {unit} {names[0]}"
    else:
        mult = num or 1
        desc = f"{mult:g} x {names[0]} ({label})"
    return round(kcal * mult), desc


def estimate(text):
    """Return (total_kcal, [descriptions], [unrecognised parts]) or None."""
    text = text.strip()
    if not text:
        return None
    whole = estimate_item(text, exact_only=True)
    if whole:
        return whole[0], [whole[1]], []
    parts = [p for p in re.split(r",|\+|&|\band\b|\bwith\b", text, flags=re.I) if p.strip()]
    total, descs, missing = 0, [], []
    for p in parts:
        r = estimate_item(p)
        if r:
            total += r[0]
            descs.append(r[1])
        else:
            missing.append(p.strip())
    return (total, descs, missing) if descs else None


def online_estimate(text):
    """Fallback: search Open Food Facts (free, no key). Returns (kcal, description) or None."""
    num, unit, name = parse_item(text)
    if not name:
        return None
    try:
        q = urllib.parse.urlencode({"search_terms": name, "search_simple": 1, "action": "process",
                                    "json": 1, "page_size": 10, "fields": "product_name,nutriments"})
        req = urllib.request.Request("https://world.openfoodfacts.org/cgi/search.pl?" + q,
                                     headers={"User-Agent": "DailyBalance/1.0"})
        with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx()) as r:
            products = json.load(r).get("products", [])
    except Exception:
        return None
    for p in products:
        per100 = (p.get("nutriments") or {}).get("energy-kcal_100g")
        if per100:
            grams = (num or 100) * UNIT_G[unit] if unit else 100 * (num or 1)
            label = p.get("product_name") or name
            return round(float(per100) * grams / 100), f"{label} ({grams:g} g, per-100 g data from Open Food Facts)"
    return None
