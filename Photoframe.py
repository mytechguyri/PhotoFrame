#!/bin/python3
import email
import imaplib
import os
from datetime import datetime
from PIL import Image
import pygame
from pygame.locals import FULLSCREEN
import logging
from email.utils import parseaddr
import subprocess
import time
from datetime import datetime, time as dt_time
import configparser
import cv2
import numpy as np


# create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('debug.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
# Read Config file and set variables
config = configparser.ConfigParser()
read_config = config.read('/home/john/photoframe.cfg')
if not read_config:
    logger.error(
        "Failed to read the config file at ~/photoframe.cfg.  Did you forget to create it?")
    exit(1)
try:
    EMAIL = config['EMAIL']['login']
    PASSWORD = config['EMAIL']['password']
    SERVER = config['EMAIL']['server']
    FOLDER = config['EMAIL']['folder']
    PASSWORD_SUBJECT = config['EMAIL']['subject_pw']
    SLEEP = config['SCREEN']['sleep']
    AWAKE = config['SCREEN']['awake']
    screen_width = int(config['SCREEN']['width'])
    screen_height = int(config['SCREEN']['height'])-17
except KeyError as e:
    key = e.args[0]
    logger.error(
        f"Failed to find '{e.args[0]}' value in ~/photoframe.cfg config file")
    raise

def parse_time(time_str):
    # Convert time string in format HH:MM to datetime.time object
    try:
        hours, minutes = map(int, time_str.split(':'))
        return dt_time(hours, minutes)
    except ValueError:
        raise ValueError("Invalid time format. Please use HH:MM format.")

def generate_unique_filename_and_download(part, base_dir='/tmp/'):
    file_name = part.get_filename().lower()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    base_name, extension = os.path.splitext(file_name)
    unique_file_path = os.path.join(base_dir, f'{base_name}_{timestamp}{extension}')
    # Download the attachment
    with open(unique_file_path, 'wb') as f:
        f.write(part.get_payload(decode=True))
    return unique_file_path

def display_image(img_path):
    # Save the image to the tmpfs
    with open(img_path, 'wb') as f:
        f.write(part.get_payload(decode=True))

    # If the image is a HEIC file, convert it to a PNG
    if file_name.lower().endswith('.heic'):
        heif_file = pyheif.read(img_path)
        image = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw",
            heif_file.mode,
            heif_file.stride,
        )
        img_path = img_path.replace('.heic', '.png')
        image.save(img_path)

    # Annotate the image with the sender's email address
    command = [
        'convert',
        img_path,
        '-resize', f'{screen_width}x{screen_height}',
        '-gravity', 'center', '-background', 'black',
        '-extent', f'{screen_width}x{screen_height}',
        '-gravity', 'SouthWest',
        '-pointsize', '20',
        '-fill', 'white',
        '-annotate', '+5+10', f'Sent by: {sender_name} via {sender}',
        '-rotate', '180',
        img_path]
    subprocess.run(command)
    # Display the image
    screen.fill((0, 0, 0))
    pygame.display.flip()
    img = pygame.image.load(img_path)
    screen.blit(img, (0,0))
    pygame.display.flip()
    # Wait for 30 seconds before showing the next image
    time.sleep(30)
    return(img_path)

def play_movie(movie_path):
    cap = cv2.VideoCapture(movie_path)
    
    # Create a named window with a black background
    cv2.namedWindow('VideoPlayer', cv2.WINDOW_NORMAL)
    cv2.setWindowProperty('VideoPlayer', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setWindowProperty('VideoPlayer', cv2.WND_PROP_BG_COLOR, (0, 0, 0))

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow('VideoPlayer', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()

# Initialize
SLEEP_TIME = parse_time(SLEEP)
AWAKE_TIME = parse_time(AWAKE)
pygame.init()
screen = pygame.display.set_mode((0, 0), FULLSCREEN)
pygame.mouse.set_visible(False)
prev_image_path = None

# Connect to the IMAP server
while True: 
    try:
        mail = imaplib.IMAP4_SSL(SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select(FOLDER)
        break
    except imaplib.IMAP4.error as e:
        logger.error("Failed to connect to the IMAP server, retrying:", e)
        time.sleep(30)

# Main loop
while True:
    # Retrieve email ids
    result, data = mail.uid('search', None, "ALL")
    email_ids = data[0].split()
    # Fetch each email
    for email_id in email_ids:
        # Fetch the email
        result, data = mail.uid('fetch', email_id, '(BODY.PEEK[])')
        raw_email = data[0][1]
        current_time =  datetime.now()
        # Parse the raw ail to get the actual message
        email_message = email.message_from_bytes(raw_email)

        # Extract the sender's email address
        sender = parseaddr(email_message['From'])[1]
        sender_name = parseaddr(email_message['From'])[0]
        # Check if the email has an attachment
        for part in email_message.walk():
            if part.get('Content-Disposition') is None or part.get('Content-Disposition').lower().startswith('inline'):
                continue
            # Get the file name of the attachment
            file_name = part.get_filename()

            # If the file is an image, save it
            if file_name.lower().endswith('.jpg') or file_name.lower().endswith('.png') or file_name.lower().endswith('.gif') or file_name.lower().endswith('.heic'):
                image_path=generate_unique_filename_and_download(part)
                image_path = display_image(image_path)
            elif file_name.lower().endswith('.mp4') or file_name.lower().endswith('.mov'):
                image_path=generate_unique_filename_and_download(part)
                play_movie(image_path)
            else:
                break
            # Delete the previous image
            if prev_image_path is not None:
                os.remove(prev_image_path)

            # Update the previous image path
            prev_image_path = image_path
