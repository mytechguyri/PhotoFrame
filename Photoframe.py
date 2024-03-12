#!/bin/python3
import email
from imapclient import IMAPClient
import os
from datetime import datetime
from PIL import Image
import pygame
from pygame.locals import FULLSCREEN
import tkinter as tk
from tkinter import messagebox
import logging
from email.utils import parseaddr
import subprocess
import time
from datetime import datetime, time as dt_time
import configparser
import cv2
import signal
import sqlite3

# create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('debug.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

#make sure the necessary directories and files are defined
cache_path = os.path.expanduser("~/image_cache")
sqlite_db = os.path.expanduser("~/image_cache.db")
config_path = os.path.expanduser("~/photoframe.cfg")

#Create SQLite database
conn = sqlite3.connect(sqlite_db)
c = conn.cursor()
try:
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            email_id TEXT,
            image_index INTEGER,
            image_path TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (email_id, image_index)
            )
    ''')
    conn.commit()
except sqlite3.Error as e:
    print(f"{e}")

# Read Config file and set variables
config = configparser.ConfigParser()
read_config = config.read(config_path)
if not read_config:
    logger.error(
        "Failed to read the config file at {config_path}.  Did you forget to create it?")
    exit(1)
try:
    EMAIL = config['EMAIL']['login']
    PASSWORD = config['EMAIL']['password']
    SERVER = config['EMAIL']['server']
    FOLDER = config['EMAIL']['folder']
    PASSWORD_SUBJECT = config['EMAIL']['subject_pw'].lower()
    DELAY = int(config['SCREEN']['delay']) * 10
    SLEEP = config['SCREEN']['sleep']
    AWAKE = config['SCREEN']['awake']
    screen_width = int(config['SCREEN']['width'])
    screen_height = int(config['SCREEN']['height'])
except KeyError as e:
    key = e.args[0]
    logger.error(
        f"Failed to find '{e.args[0]}' value in {config_path} config file")
    raise

# Define functions
def signal_handler(sig, frame):
    logger.info('SIGTERM received.  Exiting gracefully')
    mail.logout()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)

def parse_time(time_str):
    try:
        hours, minutes = map(int, time_str.split(':'))
        return dt_time(hours, minutes)
    except ValueError:
        raise ValueError("Invalid time format. Please use HH:MM format.")

def check_cache(email_id, index):
    c.execute('SELECT image_path FROM cache WHERE email_id = ? AND image_index = ?', (email_id, index))
    result = c.fetchone()
    return result[0] if result else None

def add_to_cache(email_id, index, image_path):
    total, used, free = shutil.disk_usage("/")
    min_free = total // 10
    c.execute('INSERT OR REPLACE INTO cache (email_id, image_index, image_path) VALUES (?, ?, ?)', (email_id, index, image_path))
    conn.commit()
    c.execute('SELECT COUNT(*) FROM cache')
    rows = c.fetchone()
    count = rows[0]
    if free < min_free:
        c.execute('SELECT image_path FROM cache ORDER BY timestamp LIMIT 1')
        rows = c.fetchone()
        oldest_image_path = rows[0]
        os.remove(oldest_image_path)
        c.execute('DELETE FROM cache WHERE timestamp = (SELECT MIN(timestamp) FROM cache)')
        conn.commit()

def clean_cache(client, c, messages):
    existing_ids = [msg.decode() for msg in messages]
    c.execute('SELECT DISTINCT email_id FROM cache')
    cached_ids = [row[0] for row in c.fetchall()]
    for email_id in cached_ids:
        if email_id not in existing_ids:
            c.execute('SELECT image_path FROM cache WHERE email_id = ?', (email_id,))
            image_paths = c.fetchall()
            for path in image_paths:
                os.remove(path[0])  # Delete image file
            c.execute('DELETE FROM cache WHERE email_id = ?', (email_id,))  # Delete cache entry
            conn.commit()
            
def generate_unique_filename_and_download(part, email_id, index):
    file_name = part.get_filename().lower()
    cache_hit = check_cache(email_id, index)
    if cache_hit:
        return cache_hit
    else:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        base_name, extension = os.path.splitext(file_name)
        unique_file_path = os.path.join(cache_path, f'{base_name}_{timestamp}{extension}')
        with open(unique_file_path, 'wb') as f:
            f.write(part.get_payload(decode=True))
        if file_name.endswith('.heic'):
            heif_file = pyheif.read(unique_file_path)
            image = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
            unique_file_path = unique_file_path.replace('.heic', '.png')
            image.save(unique_file_path)
        command = [
            'convert',
            unique_file_path,
            '-resize', f'{screen_width}x{screen_height}',
            '-gravity', 'center', '-background', 'black',
            '-extent', f'{screen_width}x{screen_height}',
            '-gravity', 'SouthWest',
            '-pointsize', '20',
            '-fill', 'white',
            '-annotate', '+5+10', f'Sent by: {sender_name} via {sender} on {msg_date} at {msg_time}',
            unique_file_path]
        subprocess.run(command)
        add_to_cache(email_id, index, unique_file_path)
        return unique_file_path

def display_image(img_path):
    #pygame.mouse.set_visible(False)
    screen.fill((0, 0, 0))
    pygame.display.flip()
    img = pygame.image.load(img_path)
    screen.blit(img, (0,0))
    pygame.display.flip()
    for _ in range(DELAY):
        for event in pygame.event.get():
            if event.type == pygame.FINGERDOWN:
                action_dict = {1: 'Message deleted', 2: 'Message Archived', 3: 'Continuing...'}
                action = dialog_box(msgid)
                logger.info(action_dict[action])
                return
        time.sleep(0.1)

def dialog_box(msgid):
    def on_delete():
        client.move(msgid, '[Gmail]/Trash')
        c.execute('SELECT image_path FROM cache WHERE email_id = ?', (msgid,))
        rows = c.fetchall()
        for row in rows:
            os.remove(row[0])
        c.execute('DELETE FROM cache WHERE email_id = ?', (msgid,))
        conn.commit()
        root.destroy()
        result.set(1)

    def on_archive():
        client.move(msgid, 'Stored')
        c.execute('SELECT image_path FROM cache WHERE email_id = ?', (msgid,))
        rows = c.fetchall()
        for row in rows:
            os.remove(row[0])
        c.execute('DELETE FROM cache WHERE email_id = ?', (msgid,))
        conn.commit()
        root.destroy()
        result.set(2)

    def on_continue():
        root.destroy()
        result.set(3)

    root = tk.Tk()
    result = tk.IntVar()
    root.geometry("675x50+290+325")
    root.title("Please select an option")
    button_font = ("Helvetica", 14)
    button_width = 20
    button_height = 2
    delete_button = tk.Button(root, text="Delete", command=on_delete, font=button_font, width=button_width, height=button_height)
    archive_button = tk.Button(root, text="Archive", command=on_archive, font=button_font, width=button_width, height=button_height)
    continue_button = tk.Button(root, text="Continue", command=on_continue, font=button_font, width=button_width, height=button_height)
    delete_button.grid(row=0, column=0)
    archive_button.grid(row=0, column=1)
    continue_button.grid(row=0, column=2)
    root.mainloop()
    exitcode = result.get()
    return exitcode

def play_movie(movie_path):
    cap = cv2.VideoCapture(movie_path)
    roi_window = cv2.namedWindow('VideoPlayer', cv2.WINDOW_NORMAL)
    cv2.setWindowProperty('VideoPlayer', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    while(cap.isOpened()):
       ret, frame = cap.read()
       if not ret:
           break
       cv2.imshow('VideoPlayer', frame)
       for event in pygame.event.get():
           if event.type == pygame.FINGERDOWN:
               break
       else:
           continue
    cap.release()
    cv2.destroyAllWindows()

def screen_sleep(state):
    os.system(f'xset dpms force {state}')
    return state

def sleep_time(stop_time, start_time):
    now_time = datetime.now().time()
    if stop_time < start_time:
       start_time, stop_time = stop_time, start_time
    if start_time <= now_time <= stop_time:
       return False
    return True

screen_state = screen_sleep("off")
CACHE_SIZE=50
if SLEEP:
    SLEEP_TIME = parse_time(SLEEP)
if AWAKE:
    AWAKE_TIME = parse_time(AWAKE)
pygame.init()
screen = pygame.display.set_mode((screen_width, screen_height), FULLSCREEN)
pygame.mouse.set_visible(False)
screen.fill((0, 0, 0))
pygame.display.flip()
os.makedirs(cache_path, exist_ok=True)
connection_attempts = 0
while True:
        try:
            client = IMAPClient(SERVER)
            client.login(EMAIL, PASSWORD)
            select_info = client.select_folder(FOLDER)
            folders = client.list_folders(directory='', pattern='*')
            print(f'Folders: {folders}')
            break
        except Exception as e:
            logger.error("Failed to connect to the IMAP server, retrying:", e)
            time.sleep(10)

# Main loop
while True:
    messages = client.search('ALL')
    clean_cache(client, c, messages)
    for msgid in messages:
        current_image_index = 0
        if SLEEP and AWAKE:
            while sleep_time(SLEEP_TIME, AWAKE_TIME):
                logger.info(f"Current: {datetime.now().time()}  Sleep: {SLEEP_TIME}  Awake: {AWAKE_TIME}")
                while screen_state == "on":
                    logger.info("Entering sleep mode")
                    screen_state = screen_sleep("off")
                time.sleep(900)
            else:
                while screen_state == "off":
                    logger.info("Waking up")
                    screen_state = screen_sleep("on")
        else:
            while screen_state == "off":
                screen_state = screen_sleep("on")

        response = client.fetch(msgid, ['BODY.PEEK[]'])
        raw_email = response[msgid][b'BODY[]']
        email_message = email.message_from_bytes(raw_email)
        subject = email_message['subject'].lower()
        if PASSWORD_SUBJECT and PASSWORD_SUBJECT not in subject:
            client.move(msgid, 'password reject')
            continue
        sender = parseaddr(email_message['From'])[1]
        sender_name = parseaddr(email_message['From'])[0]
        date_header = email_message['Date']
        if date_header:
            date_tuple = email.utils.parsedate_tz(date_header)
            if date_tuple:
                local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                msg_date = local_date.strftime("%m/%d/%Y")
                msg_time = local_date.strftime("%H:%M")
        for part in email_message.walk():
            if part.get('Content-Disposition') is None or part.get('Content-Disposition').lower().startswith('inline'):
               continue
            file_name = part.get_filename().lower()
            if file_name.endswith('.jpg') or file_name.endswith('.png') or file_name.endswith('.gif') or file_name.endswith('.heic'):
                image_path = generate_unique_filename_and_download(part, msgid, current_image_index)
                display_image(image_path)
                current_image_index += 1
            elif file_name.endswith('.mp4') or file_name.endswith('.mov'):
                image_path = generate_unique_filename_and_download(part, msgid, current_image_index)
                play_movie(image_path)
                current_image_index += 1
            else:
                break

