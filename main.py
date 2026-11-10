"""
Daily Balance - Calorie & Budget Tracker (Kivy, runs on desktop and Android)
Desktop test:   pip install kivy certifi  &&  python main.py
Android APK:    see buildozer.spec
"""
import json
import os
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as C

import estimator

# Soft, easy-on-the-eyes palette
BG, CARD, INK, MUTE, LINE = "#EEF5F1", "#FFFFFF", "#2F3E3A", "#6F8580", "#DCE8E2"
SAGE, SAGE_SOFT, SKY, SKY_SOFT, PEACH = "#6FB29A", "#DDF0E8", "#7FA8D9", "#E0ECF8", "#F0A98B"
GREEN_TXT, ORANGE_TXT = "#3F8F76", "#C9775A"

EXPENSE_CATS = ["Food", "Transport", "Bills", "Shopping", "Health", "Fun", "Other"]
INCOME_CATS = ["Salary", "Gift", "Other"]
MEALS = ["Breakfast", "Lunch", "Dinner", "Snack"]
TIP = 'Type what you ate and calories fill in automatically. Try "2 eggs" or "150g rice".'
NOT_FOUND = "Not in the built-in list. Press Add to search online, or type calories yourself."

Window.clearcolor = C(BG)
Window.softinput_mode = "below_target"      # keyboard doesn't cover the text box


# ------------------------------------------------------------------ small UI helpers
def L(text="", size=14, color=INK, bold=False, halign="left", min_h=20, **kw):
    """Auto-wrapping label that grows to fit its text."""
    lb = Label(text=text, font_size=sp(size), color=C(color), bold=bold, halign=halign,
               valign="middle", size_hint_y=None, **kw)
    lb.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
    lb.bind(texture_size=lambda i, s: setattr(i, "height", max(s[1], dp(min_h))))
    return lb


def RL(text="", size=14, color=INK, bold=False, halign="left", **kw):
    """Label that fills its row."""
    lb = Label(text=text, font_size=sp(size), color=C(color), bold=bold, halign=halign, valign="middle", **kw)
    lb.bind(size=lambda i, s: setattr(i, "text_size", s))
    return lb


def B(text, cb=None, bg=LINE, fg=INK, h=44, **kw):
    b = Button(text=text, font_size=sp(15), bold=True, background_normal="", background_down="",
               background_color=C(bg), color=C(fg), size_hint_y=None, height=dp(h), **kw)
    if cb:
        b.bind(on_release=lambda *_: cb())
    return b


def T(hint="", text="", **kw):
    return TextInput(hint_text=hint, text=text, multiline=False, font_size=sp(15), size_hint_y=None,
                     height=dp(44), padding=[dp(10), dp(12)], background_normal="", background_active="",
                     background_color=C(BG), foreground_color=C(INK), hint_text_color=C(MUTE),
                     cursor_color=C(SAGE), **kw)


def S(values):
    return Spinner(text=values[0], values=values, font_size=sp(15), size_hint_y=None, height=dp(44),
                   background_normal="", background_color=C(BG), color=C(INK))


def row(*children, h=44, spacing=8):
    r = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(spacing))
    for c in children:
        r.add_widget(c)
    return r


class Card(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(14), spacing=dp(10), size_hint_y=None, **kw)
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*C(CARD))
            self._bg = RoundedRectangle(radius=[dp(18)])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *_):
        self._bg.pos, self._bg.size = self.pos, self.size


class Ring(Widget):
    pct = NumericProperty(0)
    over = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(size_hint=(None, None), size=(dp(120), dp(120)), **kw)
        self.bind(pos=self.draw, size=self.draw, pct=self.draw, over=self.draw)

    def draw(self, *_):
        self.canvas.clear()
        r = min(self.width, self.height) / 2 - dp(9)
        with self.canvas:
            Color(*C(SAGE_SOFT))
            Line(circle=(self.center_x, self.center_y, r), width=dp(9))
            if self.pct > 0:
                Color(*C(PEACH if self.over else SAGE))
                Line(circle=(self.center_x, self.center_y, r, 0, min(self.pct, 0.9999) * 360),
                     width=dp(9), cap="round")


class Bar(Widget):
    def __init__(self, frac=0, color=SKY, **kw):
        super().__init__(size_hint_y=None, height=dp(10), **kw)
        self.frac, self.color = frac, color
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*C(BG))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
            if self.frac > 0:
                Color(*C(self.color))
                RoundedRectangle(pos=self.pos, size=(self.width * min(self.frac, 1), self.height), radius=[dp(5)])


def scroller():
    sv = ScrollView(bar_width=dp(3))
    col = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(12), spacing=dp(12))
    col.bind(minimum_height=col.setter("height"))
    sv.add_widget(col)
    return sv, col


def list_box():
    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    box.bind(minimum_height=box.setter("height"))
    return box


# ------------------------------------------------------------------ app
class DailyBalance(App):
    title = "Daily Balance"

    # ---------- storage (app-private folder, survives closing the app)
    @property
    def data_path(self):
        return os.path.join(self.user_data_dir, "daily_balance_data.json")

    def load(self):
        data = {"goal": 2000, "limit": 0.0, "cur": "$", "foods": [], "tx": []}
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except (OSError, ValueError):
            pass
        return data

    def save(self):
        try:
            os.makedirs(self.user_data_dir, exist_ok=True)
            tmp = self.data_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.data_path)
        except OSError as e:
            self.note("Could not save", str(e))

    def on_pause(self):
        self.save()
        return True          # keeps the app alive when you switch away on Android

    def on_resume(self):
        pass

    def on_stop(self):
        self.save()

    # ---------- popups
    def note(self, title, msg):
        self._popup(title, msg, [("OK", None, SAGE)])

    def confirm(self, title, msg, yes):
        self._popup(title, msg, [("Cancel", None, LINE), ("Add", yes, SAGE)])

    def _popup(self, title, msg, buttons):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
        lb = Label(text=msg, color=C(INK), halign="center", valign="middle")
        lb.bind(size=lambda i, s: setattr(i, "text_size", s))
        box.add_widget(lb)
        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        pop = Popup(title=title, content=box, size_hint=(0.88, 0.42), background="", background_color=C(CARD),
                    title_color=C(INK), separator_color=C(SAGE), auto_dismiss=False)
        for text, action, color in buttons:
            def go(a=action):
                pop.dismiss()
                if a:
                    a()
            btn_row.add_widget(B(text, go, bg=color))
        box.add_widget(btn_row)
        pop.open()

    # ---------- layout
    def build(self):
        self.data = self.load()
        self.day = date.today()
        self.year, self.month = self.day.year, self.day.month
        self.kind = "out"
        self.cal_manual = False
        self._auto = False

        root = BoxLayout(orientation="vertical", padding=[dp(12), dp(10), dp(12), 0], spacing=dp(8))
        root.add_widget(L("Daily Balance", 22, bold=True, min_h=30))

        self.sm = ScreenManager(transition=NoTransition())
        self.tabs = []
        tab_row = row(h=44)
        for name, label in (("cal", "Calories"), ("bud", "Budget")):
            tb = ToggleButton(text=label, group="tabs", allow_no_selection=False, font_size=sp(15), bold=True,
                              background_normal="", background_down="", color=C(INK),
                              state="down" if name == "cal" else "normal")
            tb.screen_name = name
            tb.bind(state=self._tab_state)
            self.tabs.append(tb)
            tab_row.add_widget(tb)
        root.add_widget(tab_row)
        self._tab_state()

        for builder, name in ((self.build_cal, "cal"), (self.build_bud, "bud")):
            scr = Screen(name=name)
            scr.add_widget(builder())
            self.sm.add_widget(scr)
        root.add_widget(self.sm)
        self.refresh_cal()
        self.refresh_bud()
        return root

    def _tab_state(self, *_):
        for tb in self.tabs:
            tb.background_color = C(SAGE_SOFT if tb.state == "down" else LINE)
            if tb.state == "down" and self.sm.has_screen(tb.screen_name):
                self.sm.current = tb.screen_name

    # ================================================================ CALORIES
    def build_cal(self):
        sv, col = scroller()
        self.day_lbl = RL("", 16, bold=True, halign="center")
        col.add_widget(row(B("<", lambda: self.shift_day(-1), size_hint_x=None, width=dp(48)), self.day_lbl,
                           B(">", lambda: self.shift_day(1), size_hint_x=None, width=dp(48))))

        card = Card()
        self.ring = Ring()
        self.eaten_lbl = L("", 20, bold=True, halign="center")
        info = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(120), spacing=dp(4))
        self.goal_lbl, self.rem_lbl = L("", 15, bold=True), L("", 15, bold=True)
        info.add_widget(self.eaten_lbl)
        info.add_widget(self.goal_lbl)
        info.add_widget(self.rem_lbl)
        card.add_widget(row(self.ring, info, h=120, spacing=14))
        self.goal_in = T("Daily goal (kcal)", input_filter="int")
        card.add_widget(row(self.goal_in, B("Save goal", self.set_goal, size_hint_x=None, width=dp(110))))
        col.add_widget(card)

        add = Card()
        add.add_widget(L("Add food", 16, bold=True))
        self.name_in = T("e.g. 2 eggs and toast")
        self.name_in.bind(text=self.on_name)
        add.add_widget(self.name_in)
        self.hint = L(TIP, 12, MUTE)
        add.add_widget(self.hint)
        self.cal_in = T("Calories", input_filter="int")
        self.cal_in.bind(text=self.on_cal)
        self.meal_sp = S(MEALS)
        add.add_widget(row(self.cal_in, self.meal_sp))
        add.add_widget(B("Add food", self.add_food, bg=SAGE, fg="#17302A"))
        col.add_widget(add)

        lst = Card()
        lst.add_widget(L("Meals logged", 16, bold=True))
        self.food_box = list_box()
        lst.add_widget(self.food_box)
        col.add_widget(lst)
        return sv

    def shift_day(self, n):
        self.day += timedelta(days=n)
        self.refresh_cal()

    def set_goal(self):
        try:
            v = int(self.goal_in.text)
            if v <= 0:
                raise ValueError
        except ValueError:
            self.note("Check goal", "Enter a whole number above 0.")
            return
        self.data["goal"] = v
        self.save()
        self.refresh_cal()

    def _set_cal(self, value):
        self._auto = True
        self.cal_in.text = value
        self._auto = False

    def on_cal(self, _inst, text):
        if not self._auto:
            self.cal_manual = bool(text.strip())

    def on_name(self, _inst, text):
        text = text.strip()
        r = estimator.estimate(text)
        if r:
            total, descs, missing = r
            msg = "Estimate: " + " + ".join(descs) + f" = {total} kcal"
            if missing:
                msg += "  (not found: " + ", ".join(missing) + ")"
            self.hint.text = msg
            if not self.cal_manual:
                self._set_cal(str(total))
        else:
            self.hint.text = NOT_FOUND if text else TIP
            if not self.cal_manual:
                self._set_cal("")

    def add_food(self):
        name = self.name_in.text.strip()
        if not name:
            self.note("Check entry", "Enter a food name first.")
            return
        if self.cal_in.text.strip():
            self.commit_food(name, int(self.cal_in.text))
            return
        r = estimator.estimate(name)
        if r:
            self.commit_food(name, r[0])
            return
        self.hint.text = "Searching online..."
        threading.Thread(target=self._online, args=(name,), daemon=True).start()

    def _online(self, name):
        found = estimator.online_estimate(name)
        Clock.schedule_once(lambda dt: self._online_done(name, found))

    def _online_done(self, name, found):
        self.hint.text = NOT_FOUND
        if not found:
            self.note("Not found", "Couldn't estimate that food. Please type the calories yourself.")
            return
        self.confirm("Online estimate", f"{found[1]}\n\nAbout {found[0]} kcal. Add this?",
                     lambda: self.commit_food(name, found[0]))

    def commit_food(self, name, cal):
        self.data["foods"].append({"id": datetime.now().isoformat(), "name": name, "cal": cal,
                                   "meal": self.meal_sp.text, "date": self.day.isoformat()})
        self.cal_manual = False
        self.name_in.text = ""
        self._set_cal("")
        self.hint.text = TIP
        self.save()
        self.refresh_cal()

    def del_food(self, fid):
        self.data["foods"] = [f for f in self.data["foods"] if f["id"] != fid]
        self.save()
        self.refresh_cal()

    def refresh_cal(self):
        key = self.day.isoformat()
        self.day_lbl.text = "Today" if self.day == date.today() else self.day.strftime("%a, %b %d %Y")
        items = [f for f in self.data["foods"] if f["date"] == key]
        total = sum(f["cal"] for f in items)
        goal = self.data["goal"]
        left = goal - total
        self.eaten_lbl.text = f"{total:,} kcal eaten"
        self.goal_lbl.text = f"Goal: {goal:,} kcal"
        self.rem_lbl.text = f"{left:,} kcal left" if left >= 0 else f"{-left:,} kcal over"
        self.rem_lbl.color = C(INK if left >= 0 else ORANGE_TXT)
        self.ring.pct = total / goal if goal else 0
        self.ring.over = left < 0
        self.goal_in.text = str(goal)
        self.food_box.clear_widgets()
        if not items:
            self.food_box.add_widget(L("Nothing logged yet.", 13, MUTE, halign="center", min_h=36))
        for f in items:
            self.food_box.add_widget(row(
                RL(f"{f['name']}\n{f['meal']}", 14),
                RL(f"{f['cal']} kcal", 14, bold=True, halign="right", size_hint_x=None, width=dp(80)),
                B("x", lambda fid=f["id"]: self.del_food(fid), size_hint_x=None, width=dp(40), h=40), h=52))

    # ================================================================ BUDGET
    def money(self, n):
        return f"{self.data['cur']}{n:,.2f}"

    def build_bud(self):
        sv, col = scroller()
        self.month_lbl = RL("", 16, bold=True, halign="center")
        col.add_widget(row(B("<", lambda: self.shift_month(-1), size_hint_x=None, width=dp(48)), self.month_lbl,
                           B(">", lambda: self.shift_month(1), size_hint_x=None, width=dp(48))))

        card = Card()
        self.in_lbl, self.out_lbl, self.bal_lbl = L("", 15, GREEN_TXT, True), L("", 15, ORANGE_TXT, True), L("", 15, INK, True)
        for w in (self.in_lbl, self.out_lbl, self.bal_lbl):
            card.add_widget(w)
        self.lim_lbl = L("", 13, MUTE)
        self.lim_bar = Bar()
        card.add_widget(self.lim_lbl)
        card.add_widget(self.lim_bar)
        self.lim_in = T("Monthly limit", input_filter="float")
        self.cur_in = T("$", size_hint_x=None, width=dp(60))
        card.add_widget(row(self.lim_in, self.cur_in, B("Save", self.set_limit, size_hint_x=None, width=dp(80))))
        col.add_widget(card)

        add = Card()
        add.add_widget(L("Add transaction", 16, bold=True))
        self.kind_btns = {}
        kr = row(h=44)
        for k, label in (("out", "Expense"), ("in", "Income")):
            tb = ToggleButton(text=label, group="kind", allow_no_selection=False, font_size=sp(14), bold=True,
                              background_normal="", background_down="", color=C(INK),
                              state="down" if k == "out" else "normal")
            tb.kind = k
            tb.bind(state=self._kind_state)
            self.kind_btns[k] = tb
            kr.add_widget(tb)
        add.add_widget(kr)
        self.note_in = T("Note (e.g. Groceries)")
        self.amt_in = T("Amount", input_filter="float")
        self.cat_sp = S(EXPENSE_CATS)
        self.date_in = T("YYYY-MM-DD", text=date.today().isoformat())
        add.add_widget(self.note_in)
        add.add_widget(row(self.amt_in, self.cat_sp))
        add.add_widget(self.date_in)
        add.add_widget(B("Add transaction", self.add_tx, bg=SKY, fg="#14283F"))
        col.add_widget(add)
        self._kind_state()

        cats = Card()
        cats.add_widget(L("Where your money goes", 16, bold=True))
        self.cat_box = list_box()
        cats.add_widget(self.cat_box)
        col.add_widget(cats)

        lst = Card()
        lst.add_widget(L("Transactions", 16, bold=True))
        self.tx_box = list_box()
        lst.add_widget(self.tx_box)
        col.add_widget(lst)
        return sv

    def _kind_state(self, *_):
        k = "in" if self.kind_btns["in"].state == "down" else "out"
        for key, tb in self.kind_btns.items():
            tb.background_color = C(SKY_SOFT if key == k else LINE)
        if k != self.kind:
            self.kind = k
            cats = EXPENSE_CATS if k == "out" else INCOME_CATS
            self.cat_sp.values = cats
            self.cat_sp.text = cats[0]

    def shift_month(self, n):
        m = self.month - 1 + n
        self.year += m // 12
        self.month = m % 12 + 1
        self.refresh_bud()

    def set_limit(self):
        try:
            self.data["limit"] = max(0.0, float(self.lim_in.text or 0))
        except ValueError:
            self.note("Check limit", "Enter a number.")
            return
        self.data["cur"] = self.cur_in.text.strip() or "$"
        self.save()
        self.refresh_bud()

    def add_tx(self):
        try:
            amt = float(self.amt_in.text)
            if amt <= 0:
                raise ValueError
        except ValueError:
            self.note("Check amount", "Enter an amount above 0.")
            return
        try:
            d = datetime.strptime(self.date_in.text.strip(), "%Y-%m-%d").date()
        except ValueError:
            self.note("Check date", "Use YYYY-MM-DD, for example 2026-11-03.")
            return
        kind = "in" if self.kind_btns["in"].state == "down" else "out"
        self.data["tx"].append({"id": datetime.now().isoformat(), "kind": kind, "amt": amt,
                                "note": self.note_in.text.strip(), "cat": self.cat_sp.text, "date": d.isoformat()})
        self.amt_in.text = ""
        self.note_in.text = ""
        self.year, self.month = d.year, d.month
        self.save()
        self.refresh_bud()

    def del_tx(self, tid):
        self.data["tx"] = [t for t in self.data["tx"] if t["id"] != tid]
        self.save()
        self.refresh_bud()

    def refresh_bud(self):
        prefix = f"{self.year}-{self.month:02d}"
        self.month_lbl.text = date(self.year, self.month, 1).strftime("%B %Y")
        items = sorted((t for t in self.data["tx"] if t["date"].startswith(prefix)),
                       key=lambda t: t["date"], reverse=True)
        inc = sum(t["amt"] for t in items if t["kind"] == "in")
        out = sum(t["amt"] for t in items if t["kind"] == "out")
        self.in_lbl.text = f"Income: {self.money(inc)}"
        self.out_lbl.text = f"Spent: {self.money(out)}"
        self.bal_lbl.text = f"Balance: {self.money(inc - out)}"
        lim = self.data["limit"]
        self.lim_in.text = str(lim) if lim else ""
        self.cur_in.text = self.data["cur"]
        if lim > 0:
            p = out / lim
            self.lim_bar.frac, self.lim_bar.color = p, PEACH if p > 1 else SKY
            self.lim_lbl.text = f"Monthly limit: {self.money(out - lim)} over" if p > 1 else \
                f"Monthly limit: {self.money(lim - out)} left"
        else:
            self.lim_bar.frac = 0
            self.lim_lbl.text = "Monthly limit: not set"
        self.lim_bar.draw()

        by = defaultdict(float)
        for t in items:
            if t["kind"] == "out":
                by[t["cat"]] += t["amt"]
        self.cat_box.clear_widgets()
        if not by:
            self.cat_box.add_widget(L("No expenses this month yet.", 13, MUTE, halign="center", min_h=36))
        for cat, v in sorted(by.items(), key=lambda kv: -kv[1])[:6]:
            self.cat_box.add_widget(row(RL(cat, 13), RL(self.money(v), 13, bold=True, halign="right"), h=26))
            bar = Bar(v / out)
            self.cat_box.add_widget(bar)
            bar.draw()

        self.tx_box.clear_widgets()
        if not items:
            self.tx_box.add_widget(L("No transactions yet.", 13, MUTE, halign="center", min_h=36))
        for t in items:
            sign, color = ("+", GREEN_TXT) if t["kind"] == "in" else ("-", ORANGE_TXT)
            self.tx_box.add_widget(row(
                RL(f"{t['note'] or t['cat']}\n{t['cat']} - {t['date']}", 14),
                RL(f"{sign}{self.money(t['amt'])}", 14, color, True, "right", size_hint_x=None, width=dp(110)),
                B("x", lambda tid=t["id"]: self.del_tx(tid), size_hint_x=None, width=dp(40), h=40), h=52))


if __name__ == "__main__":
    DailyBalance().run()
