from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime
import random

app = Flask(__name__)

app.secret_key = "bardzo_tajne_haslo"

def take_pp(username, amount=1, reason='game_fee'):
    conn = get_db_connection()
    user = conn.execute('SELECT pp FROM users WHERE username=?', (username,)).fetchone()
    if not user or user['pp'] < amount:
        conn.close()
        return False

    conn.execute('UPDATE users SET pp = pp - ? WHERE username=?', (amount, username))
    conn.execute(
        'INSERT INTO history (user_from, amount, type, date_time) VALUES (?,?,?,?)',
        (username, amount, reason, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True


DB_NAME = 'users.db'
transfer_blocked = False

# --- POŁĄCZENIE Z BAZĄ ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# --- INICJALIZACJA BAZY ---
def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            pp INTEGER DEFAULT 10
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_from TEXT,
            user_to TEXT,
            amount INTEGER,
            date_time TEXT,
            type TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- FUNKCJE POMOCNICZE ---
def add_pp(username, amount, game_type='game_win'):
    conn = get_db_connection()
    conn.execute('UPDATE users SET pp = pp + ? WHERE username = ?', (amount, username))
    conn.execute('INSERT INTO history (user_from, type, amount, date_time) VALUES (?, ?, ?, ?)',
                 (username, game_type, amount, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def check_win(board, player):
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    return any(board[a]==board[b]==board[c]==player for a,b,c in wins)

# --- STRONY GŁÓWNE ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    message = ''
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        if not username or not password:
            message = "Wypełnij wszystkie pola."
        else:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO users (username,password,pp) VALUES (?,?,10)', (username,password))
                conn.commit()
                message = "Konto utworzone. Masz 10 PP."
            except sqlite3.IntegrityError:
                message = "Taki użytkownik już istnieje."
            finally:
                conn.close()
    return render_template('register.html', message=message)

@app.route('/login', methods=['GET','POST'])
def login():
    message = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # admin
        if username=="Bartosz" and password=="Bartek2011@":
            conn = get_db_connection()
            users = conn.execute('SELECT * FROM users').fetchall()
            history = conn.execute('SELECT * FROM history ORDER BY date_time DESC').fetchall()
            conn.close()
            return render_template('admin.html', users=users, history=history, transfer_blocked=transfer_blocked)
        # zwykły użytkownik
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username=? AND password=?', (username,password)).fetchone()
        if user:
            conn.execute('INSERT INTO history (user_from,type,date_time) VALUES (?,?,?)',
                         (username,'login',datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return redirect(url_for('account', username=username))
        conn.close()
        message = "Błędny login lub hasło."
    return render_template('login.html', message=message)

# --- KONTO UŻYTKOWNIKA ---
@app.route('/account/<username>')
def account(username):
    message = request.args.get('message','')
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    conn.close()
    if not user:
        return redirect(url_for('login'))
    return render_template('account.html', user=user, message=message)

# --- TRANSFER PP ---
@app.route('/transfer', methods=['POST'])
def transfer():
    global transfer_blocked
    sender = request.form['sender']
    password = request.form['password']
    receiver = request.form['receiver']
    try:
        amount = int(request.form['amount'])
    except:
        return redirect(url_for('account', username=sender, message="Niepoprawna kwota."))
    if amount<=0:
        return redirect(url_for('account', username=sender, message="Kwota musi być dodatnia."))

    conn = get_db_connection()
    sender_user = conn.execute('SELECT * FROM users WHERE username=? AND password=?', (sender,password)).fetchone()
    receiver_user = conn.execute('SELECT * FROM users WHERE username=?', (receiver,)).fetchone()

    if not sender_user:
        message="Błędne hasło."
    elif not receiver_user:
        message="Odbiorca nie istnieje."
    elif transfer_blocked:
        message="Przelewy są zablokowane."
    elif sender_user['pp']<amount:
        message="Brak wystarczających PP."
    else:
        conn.execute('UPDATE users SET pp=pp-? WHERE username=?', (amount,sender))
        conn.execute('UPDATE users SET pp=pp+? WHERE username=?', (amount,receiver))
        conn.execute('INSERT INTO history (user_from,user_to,amount,type,date_time) VALUES (?,?,?,?,?)',
                     (sender,receiver,amount,'transfer',datetime.now().isoformat()))
        conn.commit()
        message=f"Przelano {amount} PP do {receiver}."
    conn.close()
    return redirect(url_for('account', username=sender, message=message))

# --- PANEL ADMINA ---
@app.route('/admin_action', methods=['POST'])
def admin_action():
    global transfer_blocked
    conn = get_db_connection()
    action = request.form['action']
    if action=='change_pp':
        user_id=int(request.form['user_id'])
        pp_change=int(request.form['pp_change'])
        conn.execute('UPDATE users SET pp=pp+? WHERE id=?',(pp_change,user_id))
        conn.commit()
    elif action=='delete':
        user_id=int(request.form['user_id'])
        conn.execute('DELETE FROM users WHERE id=?',(user_id,))
        conn.commit()
    elif action=='toggle_block':
        transfer_blocked = not transfer_blocked
    conn.close()
    return redirect(url_for('login'))

# --- RANKING CZŁONKÓW ---
@app.route('/members/<username>')
def show_members(username):
    conn = get_db_connection()
    members_list = conn.execute('SELECT username,pp FROM users ORDER BY pp DESC').fetchall()
    conn.close()
    return render_template('members.html', members=members_list, username=username)

# --- KÓŁKO KRZYŻYK ---
tictactoe_boards = {}
@app.route('/tictactoe/<username>', methods=['GET','POST'])
def play_tictactoe(username):

    if username not in tictactoe_boards:
        # POBIERAMY 1 PP ZA START GRY
        if not take_pp(username, 1, 'tictactoe_fee'):
            return redirect(url_for('account', username=username, message="Brak PP na rozpoczęcie gry."))

        tictactoe_boards[username] = [''] * 9

    board = tictactoe_boards[username]
    message = ''

    if request.method == 'POST':
        move = int(request.form['move'])

        if board[move] == '':
            board[move] = 'X'

            empty = [i for i,v in enumerate(board) if v=='']
            if empty:
                board[random.choice(empty)] = 'O'

            if check_win(board,'X'):
                add_pp(username, 2, 'tictactoe_win')
                message = "Wygrałeś! +2 PP"
                tictactoe_boards.pop(username)
            elif check_win(board,'O'):
                message = "Przegrałeś!"
                tictactoe_boards.pop(username)
            elif '' not in board:
                message = "Remis!"
                tictactoe_boards.pop(username)

    return render_template(
        'tictactoe.html',
        board=board,
        message=message,
        username=username
    )



# --- WISIELEC ---
hangman_words = ["domki","kwiat","rycer","woda","księżyc","rower","jabłko","zegar","miasto","laska",
                 "owoce","mosty","piesi","wiatr","chleb","torba","słoń","marchew","lampa","morze",
                 "serce","dźwięk","śnieg","stół","drzewo","jabłoń","okno","mleko","krzak","ptaki",
                 "oko","ziemi","miłość","kreda","palma","liść","nosić","rybak","góry","smok",
                 "kwiatki","rowerek","wiosna","zegarek","domowy","jabłecznik","królestwo","mosty",
                 "piłkarz","wiatrak","chlebek","trampolina","słońce","piekarz"]

hangman_games = {}
@app.route('/hangman/<username>', methods=['GET','POST'])
def play_hangman(username):

    if username not in hangman_games:
        if not take_pp(username, 1, 'hangman_fee'):
            return redirect(url_for('account', username=username, message="Brak PP na rozpoczęcie gry."))

        word = random.choice(hangman_words)
        hangman_games[username] = {
            'word': word,
            'display': ['_'] * len(word),
            'tries': 0,
            'letters': set()
        }

    game = hangman_games[username]
    message = ''

    if request.method == 'POST':
        guess = request.form['letter'].lower()

        if guess in game['letters']:
            message = "Ta litera była już użyta."
        else:
            game['letters'].add(guess)
            if guess in game['word']:
                for i, c in enumerate(game['word']):
                    if c == guess:
                        game['display'][i] = c
            else:
                game['tries'] += 1

        if '_' not in game['display']:
            add_pp(username, 5, 'hangman_win')
            message = f"Wygrałeś! +5 PP. Słowo: {game['word']}"
            hangman_games.pop(username)

        elif game['tries'] >= 6:
            message = f"Przegrałeś! Słowo: {game['word']}"
            hangman_games.pop(username)

    return render_template(
        'hangman.html',
        game=game,
        message=message,
        username=username
    )


if __name__ == "__main__":
    app.run()


