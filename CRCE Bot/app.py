from chatbot import chatbot
# Monkey-patch jinja2 to export Markup (required by flask-recaptcha in modern jinja2 versions)
import markupsafe
import jinja2
jinja2.Markup = markupsafe.Markup

from flask import Flask, render_template, request, session, url_for, redirect, flash
from flask_recaptcha import ReCaptcha
import mysql.connector
import sqlite3
import os

# Helper to load .env manually (avoiding extra library dependency issues)
def load_env():
    # Try current directory first, then the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(script_dir, '.env')
    ]
    for env_path in candidates:
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        # Remove quotes if present
                        val = val.strip().strip('"').strip("'")
                        os.environ[key.strip()] = val
            break

# Load env variables
load_env()

app = Flask(__name__)
app.static_folder = 'static'

# Get ReCaptcha Configurations from Environment
recaptcha_enabled = os.environ.get('RECAPTCHA_ENABLED', 'False').lower() == 'true'
recaptcha_site_key = os.environ.get('RECAPTCHA_SITE_KEY', '6LdbAx0aAAAAAANl04WHtDbraFMufACHccHbn09L')
recaptcha_secret_key = os.environ.get('RECAPTCHA_SECRET_KEY', '6LdbAx0aAAAAAMmkgBKJ2Z9xsQjMD5YutoXC6Wee')

app.config.update(dict(
    RECAPTCHA_ENABLED = recaptcha_enabled,
    RECAPTCHA_SITE_KEY = recaptcha_site_key,
    RECAPTCHA_SECRET_KEY = recaptcha_secret_key
))

recaptcha = ReCaptcha(app=app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cairocoders-ednalan')
app.secret_key = app.config['SECRET_KEY']

# Database connection class supporting SQLite and MySQL dynamically
class DatabaseConnection:
    def __init__(self):
        self.db_type = os.environ.get('DB_TYPE', 'sqlite').lower()
        self.conn = None
        self.cur = None
        self.connect()

    def connect(self):
        try:
            if self.db_type == 'mysql':
                mysql_config = {
                    'host': os.environ.get('MYSQL_HOST', 'localhost'),
                    'port': int(os.environ.get('MYSQL_PORT', '3306')),
                    'user': os.environ.get('MYSQL_USER', 'root'),
                    'password': os.environ.get('MYSQL_PASSWORD', 'candida1'),
                    'database': os.environ.get('MYSQL_DB', 'register')
                }
                self.conn = mysql.connector.connect(**mysql_config)
                self.cur = self.conn.cursor()
                self._init_mysql_tables()
            else:
                # Use sqlite3
                sqlite_path = os.environ.get('SQLITE_DB_PATH', 'database.sqlite3')
                if not os.path.isabs(sqlite_path):
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    # Check if database.sqlite3 is in workspace root (parent of CRCE Bot)
                    parent_dir_path = os.path.join(script_dir, '..', sqlite_path)
                    if os.path.exists(os.path.join(script_dir, '..')):
                        sqlite_path = parent_dir_path
                    else:
                        sqlite_path = os.path.join(script_dir, sqlite_path)
                self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
                self.cur = self.conn.cursor()
                self._init_sqlite_tables()
        except Exception as err:
            self.conn = None
            self.cur = None
            print(f"Warning: Database connection failed: {err}")

    def _init_sqlite_tables(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS suggestion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def _init_mysql_tables(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        """)
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS suggestion (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                message TEXT NOT NULL
            )
        """)
        self.conn.commit()

class SafeCursor:
    def __init__(self, db_conn):
        self.db_conn = db_conn

    def execute(self, query, params=None):
        if self.db_conn.cur is None:
            self.db_conn.connect()
        if self.db_conn.cur is None:
            raise Exception("Database is unavailable.")
        
        # SQLite uses '?' instead of '%s'
        if self.db_conn.db_type == 'sqlite' and params is not None:
            query = query.replace('%s', '?')
            
        if params is not None:
            self.db_conn.cur.execute(query, params)
        else:
            self.db_conn.cur.execute(query)

    def fetchall(self):
        if self.db_conn.cur is None:
            return []
        return self.db_conn.cur.fetchall()

class SafeConn:
    def __init__(self, db_conn):
        self.db_conn = db_conn

    def commit(self):
        if self.db_conn.conn:
            self.db_conn.conn.commit()

db = DatabaseConnection()
if db.conn and db.cur:
    cur = SafeCursor(db)
    conn = SafeConn(db)
else:
    cur = None
    conn = None

@app.route("/index")
def home():
    if 'id' in session:
        return render_template('index.html')
    else:
        return redirect('/')

@app.route('/')
def login():
    return render_template("login.html")

@app.route('/register')
def about():
    return render_template('register.html')

@app.route('/forgot')
def forgot():
    return render_template('forgot.html')

@app.route('/login_validation', methods=['POST'])
def login_validation():
    if cur is None:
        flash('Database is unavailable. Please try again later.')
        return redirect('/')

    email = request.form.get('email')
    password = request.form.get('password')

    cur.execute("SELECT * FROM `users` WHERE `email` = %s AND `password` = %s", (email, password))
    users = cur.fetchall()
    if len(users) > 0:
        session['id'] = users[0][0]
        flash('You were successfully logged in')
        return redirect('/index')
    else:
        flash('Invalid credentials !!!')
        return redirect('/')

@app.route('/add_user', methods=['POST'])
def add_user():
    if cur is None or conn is None:
        flash('Database is unavailable. Please try again later.')
        return redirect('/register')

    name = request.form.get('name') 
    email = request.form.get('uemail')
    password = request.form.get('upassword')

    # check if user already exists to prevent duplicate emails
    cur.execute("SELECT * FROM `users` WHERE `email` = %s", (email,))
    existing_user = cur.fetchall()
    if len(existing_user) > 0:
        flash('Email is already registered!')
        return redirect('/register')

    cur.execute("INSERT INTO users(name,email,password) VALUES(%s,%s,%s)", (name, email, password))
    conn.commit()
    cur.execute("SELECT * FROM `users` WHERE `email` = %s", (email,))
    myuser = cur.fetchall()
    flash('You have successfully registered!')
    session['id'] = myuser[0][0]
    return redirect('/index')

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    if cur is None or conn is None:
        flash('Database is unavailable. Please try again later.')
        return redirect('/forgot')

    name = request.form.get('name')
    email = request.form.get('uemail')
    password = request.form.get('upassword')

    cur.execute("SELECT * FROM `users` WHERE `name` = %s AND `email` = %s", (name, email))
    user = cur.fetchall()
    if len(user) > 0:
        cur.execute("UPDATE users SET password = %s WHERE name = %s AND email = %s", (password, name, email))
        conn.commit()
        flash('Password reset successfully! Please login.')
        return redirect('/')
    else:
        flash('User not found with specified Name and Email!')
        return redirect('/forgot')

@app.route('/suggestion', methods=['POST'])
def suggestion():
    if cur is None or conn is None:
        flash('Database is unavailable. Please try again later.')
        return redirect('/index')

    email = request.form.get('uemail')
    suggesMess = request.form.get('message')

    cur.execute("INSERT INTO suggestion(email,message) VALUES(%s,%s)", (email, suggesMess))
    conn.commit()
    flash('Your suggestion is successfully sent!')
    return redirect('/index')

@app.route('/logout')
def logout():
    session.pop('id', None)
    return redirect('/')

@app.route("/get")
def get_bot_response():
    userText = request.args.get('msg')  
    return str(chatbot.get_response(userText))

if __name__ == "__main__":
    app.run()
