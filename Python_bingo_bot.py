# bingo_bot_with_history.py
# pip install pyTelegramBotAPI
import telebot
import random
import sqlite3
import json
from datetime import datetime

# ===== Config =====
API_TOKEN = "8480193439:AAFuzjjbJaMBT78nWsUVfaQb93Vr6ucddWM"
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")
ADMIN_CHAT_ID = 7890879757  # <-- የዳይረክተሩ Telegram ID ይቀይሩ

# ===== DB setup =====
DB = "bingo.db"
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

# users: balance
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
""")

# games: current active game per user (card + marked)
cur.execute("""
CREATE TABLE IF NOT EXISTS games (
    user_id INTEGER PRIMARY KEY,
    card TEXT,
    marked TEXT,
    bingo INTEGER DEFAULT 0,
    last_played TEXT
)
""")

# plays: history of plays (each time user played a card)
cur.execute("""
CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    card TEXT,
    marked TEXT,
    cost INTEGER,
    played_at TEXT
)
""")

# calls: global called numbers history
cur.execute("""
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER,
    called_at TEXT
)
""")

# winners: record winners when they first win for a call
cur.execute("""
CREATE TABLE IF NOT EXISTS winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    number INTEGER,
    won_at TEXT
)
""")

conn.commit()

# ===== Helpers =====
TELEBIRR_NUMBERS = ["+251966512930", "+251970022024"]

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

def generate_card():
    card = []
    ranges = {"B": range(1,16), "I": range(16,31), "N": range(31,46), "G": range(46,61), "O": range(61,76)}
    for key in "BINGO":
        nums = random.sample(ranges[key],5)
        card.append(nums)
    card[2][2] = "FREE"
    # transpose to rows
    return [[card[col][row] for col in range(5)] for row in range(5)]

def save_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users(user_id, balance) VALUES(?, ?)", (user_id, 0))
    conn.commit()

def get_balance(user_id):
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    r = cur.fetchone()
    return r[0] if r else 0

def update_balance(user_id, delta):
    save_user(user_id)
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

def save_game(user_id, card, marked):
    cur.execute("REPLACE INTO games(user_id, card, marked, bingo, last_played) VALUES(?,?,?,?,?)",
                (user_id, json.dumps(card), json.dumps(marked), 0, now_iso()))
    conn.commit()

def save_play_history(user_id, card, marked, cost):
    cur.execute("INSERT INTO plays(user_id, card, marked, cost, played_at) VALUES (?,?,?,?,?)",
                (user_id, json.dumps(card), json.dumps(marked), cost, now_iso()))
    conn.commit()

def record_call(number):
    cur.execute("INSERT INTO calls(number, called_at) VALUES (?,?)", (number, now_iso()))
    conn.commit()

def get_call_history(limit=100):
    cur.execute("SELECT number, called_at FROM calls ORDER BY id DESC LIMIT ?", (limit,))
    return cur.fetchall()

def record_winner(user_id, number):
    cur.execute("INSERT INTO winners(user_id, number, won_at) VALUES (?,?,?)", (user_id, number, now_iso()))
    conn.commit()

def get_user_plays(user_id, limit=50):
    cur.execute("SELECT id, cost, played_at, card FROM plays WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))
    return cur.fetchall()

def get_recent_winners(limit=20):
    cur.execute("SELECT user_id, number, won_at FROM winners ORDER BY id DESC LIMIT ?", (limit,))
    return cur.fetchall()

# bingo helpers
def mark_card(card, marked, number):
    for i in range(5):
        for j in range(5):
            if card[i][j] == number or card[i][j] == "FREE":
                marked[i][j] = True
    return marked

def check_bingo(marked):
    # rows
    for row in marked:
        if all(row):
            return True
    # cols
    for c in range(5):
        if all(marked[r][c] for r in range(5)):
            return True
    # diagonals
    if all(marked[i][i] for i in range(5)) or all(marked[i][4-i] for i in range(5)):
        return True
    return False

# ===== Commands =====
@bot.message_handler(commands=['start'])
def cmd_start(m):
    save_user(m.from_user.id)
    bot.send_message(m.chat.id, f"👋 ሰላም {m.from_user.first_name}! /deposit ይጫኑ። የታሪክ ለማየት /calls ፣ ለግለሰቦች /myplays")

@bot.message_handler(commands=['deposit'])
def cmd_deposit(m):
    save_user(m.from_user.id)
    bot.send_message(m.chat.id, f"💵 ክፍያ ለማድረግ ከዚህ ቁጥሮች አንዱን ይጠቀሙ:\n{', '.join(TELEBIRR_NUMBERS)}\nAdmin ከፈቀድ /approve <user_id> <amount>")

@bot.message_handler(commands=['approve'])
def cmd_approve(m):
    if m.from_user.id != ADMIN_CHAT_ID:
        return bot.send_message(m.chat.id, "⛔ ለAdmin ብቻ ነው")
    parts = m.text.split()
    if len(parts) < 3:
        return bot.send_message(m.chat.id, "Usage: /approve <user_id> <amount>")
    try:
        uid = int(parts[1]); amount = int(parts[2])
    except:
        return bot.send_message(m.chat.id, "telegram id and amount must be numbers")
    update_balance(uid, amount)
    bot.send_message(uid, f"✅ Deposit approved — +{amount} ብር. /play ይጫኑ.")
    bot.send_message(m.chat.id, f"User {uid} given +{amount} balance")

@bot.message_handler(commands=['balance'])
def cmd_balance(m):
    bal = get_balance(m.from_user.id)
    bot.send_message(m.chat.id, f"💰 Your balance: {bal} ብር")

@bot.message_handler(commands=['play'])
def cmd_play(m):
    uid = m.from_user.id
    bal = get_balance(uid)
    if bal <= 0:
        return bot.send_message(m.chat.id, "💰 ክፍያ አልተከፈለም. /deposit ይጫኑ.")
    # consume cost (example cost 1)
    cost = 1
    update_balance(uid, -cost)
    # generate and save game
    card = generate_card()
    marked = [[False]*5 for _ in range(5)]
    marked[2][2] = True
    save_game(uid, card, marked)
    save_play_history(uid, card, marked, cost)
    # show card
    text = "<b>Your Bingo Card</b>\n" + "\n".join(" | ".join(str(x).rjust(2) for x in row) for row in card)
    bot.send_message(m.chat.id, text)
    bot.send_message(m.chat.id, f"✅ Played (cost {cost}). New balance: {get_balance(uid)} ብር")

# Admin calls a number; records in calls table and checks winners
@bot.message_handler(commands=['call'])
def cmd_call(m):
    if m.from_user.id != ADMIN_CHAT_ID:
        return bot.send_message(m.chat.id, "⛔ ለAdmin ብቻ ነው")
    # choose number not called before
    cur.execute("SELECT number FROM calls")
    called = [r[0] for r in cur.fetchall()]
    choices = [n for n in range(1,76) if n not in called]
    if not choices:
        return bot.send_message(m.chat.id, "Game over: all numbers called.")
    number = random.choice(choices)
    record_call(number)
    # check all saved current games
    cur.execute("SELECT user_id, card, marked, bingo FROM games")
    rows = cur.fetchall()
    winners = []
    for row in rows:
        uid, card_json, marked_json, bingo_flag = row
        card = json.loads(card_json)
        marked = json.loads(marked_json)
        marked = mark_card(card, marked, number)
        won = check_bingo(marked)
        # update game state
        cur.execute("UPDATE games SET marked=?, bingo=?, last_played=? WHERE user_id=?",
                    (json.dumps(marked), int(won or bingo_flag), now_iso(), uid))
        conn.commit()
        if won and not bingo_flag:
            winners.append(uid)
            record_winner(uid, number)
    # broadcast
    msg = f"🎯 Number Called: {number}\n"
    if winners:
        names = []
        for w in winners:
            try:
                names.append(bot.get_chat(w).first_name)
            except:
                names.append(str(w))
        msg += "🏆 Winners: " + ", ".join(names)
    bot.send_message(m.chat.id, msg)

# view called numbers history
@bot.message_handler(commands=['calls'])
def cmd_calls(m):
    rows = get_call_history(100)
    if not rows:
        return bot.send_message(m.chat.id, "No numbers called yet.")
    text = "<b>Called numbers (recent first):</b>\n"
    for num, ts in rows:
        text += f"{num}  — {ts}\n"
    bot.send_message(m.chat.id, text)

# view player's own play history
@bot.message_handler(commands=['myplays'])
def cmd_myplays(m):
    uid = m.from_user.id
    rows = get_user_plays(uid, 50)
    if not rows:
        return bot.send_message(m.chat.id, "You have no plays yet.")
    text = "<b>Your play history (recent first):</b>\n"
    for pid, cost, played_at, card_json in rows:
        text += f"#{pid} — cost: {cost} — at: {played_at}\n"
    bot.send_message(m.chat.id, text)

# view recent winners
@bot.message_handler(commands=['winners'])
def cmd_winners(m):
    rows = get_recent_winners(50)
    if not rows:
        return bot.send_message(m.chat.id, "No winners yet.")
    text = "<b>Recent winners:</b>\n"
    for uid, number, won_at in rows:
        try:
            name = bot.get_chat(uid).first_name
        except:
            name = str(uid)
        text += f"{name} ({uid}) — won on number {number} at {won_at}\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(commands=['help'])
def cmd_help(m):
    bot.send_message(m.chat.id,
                     "/start /deposit /approve <user_id> <amount> (admin)\n"
                     "/balance /play /myplays /calls /winners /call (admin) /help")

# run
print("🤖 bingo_bot with history running...")
bot.infinity_polling()