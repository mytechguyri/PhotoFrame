import email
import imaplib
import os
import time
from datetime import datetime
from PIL import Image
import pyheif
from multiprocessing import Process, Queue

# Function to download an image
def download_image(email_id, queue):
    # Fetch the email
    result, data = mail.uid('fetch', email_id, '(BODY.PEEK[])')
    raw_email = data[0][1]

    # Parse the raw email to get the actual message
    email_message = email.message_from_bytes(raw_email)

    # Check if the email has an attachment
    for part in email_message.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        # Get the file name of the attachment
        file_name = part.get_filename()

        # If the file is an image, save it
        if file_name.endswith('.jpg') or file_name.endswith('.png') or file_name.endswith('.heic'):
            # Save the image to the tmpfs
            image_path = '/mnt/tmpfs/' + file_name
            with open(image_path, 'wb') as f:
                f.write(part.get_payload(decode=True))

            # If the image is a HEIC file, convert it to a PNG
            if file_name.endswith('.heic'):
                heif_file = pyheif.read(image_path)
                image = Image.frombytes(
                    heif_file.mode, 
                    heif_file.size, 
                    heif_file.data,
                    "raw",
                    heif_file.mode,
                    heif_file.stride,
                )
                image_path = image_path.replace('.heic', '.png')
                image.save(image_path)

            # Put the image path in the queue
            queue.put(image_path)

# IMAP settings
EMAIL = 'your-email@gmail.com'
PASSWORD = 'your-password'
SERVER = 'imap.gmail.com'

# Connect to the server
mail = imaplib.IMAP4_SSL(SERVER)
mail.login(EMAIL, PASSWORD)

# Select the mailbox you want to delete in
# If you want SPAM, use "INBOX.SPAM"
mail.select('inbox')

# Create a tmpfs mount point for temporary image storage
os.system('sudo mount -t tmpfs -o size=50M tmpfs /mnt/tmpfs')

# Retrieve email ids
result, data = mail.uid('search', None, "ALL")
email_ids = data[0].split()

# Create a queue to hold the image paths
queue = Queue()

# Start the first image download
p = Process(target=download_image, args=(email_ids[0], queue))
p.start()

# Main loop
while True:
    # Fetch each email
    for i in range(1, len(email_ids)):
        # Wait for the download to finish and get the image path
        p.join()
        image_path = queue.get()

        # Get the current time
        current_time = datetime.now().time()

        # If the current time is between 11pm and 7am, sleep
        if current_time >= time(23, 0) or current_time <= time(7, 0):
            # Sleep for 30 seconds before checking the time again
            time.sleep(30)
            continue

        # Display the image using a library like PIL
        img = Image.open(image_path)
        img.show()

        # Sleep for 30 seconds before showing the next image
        time.sleep(30)

        # Delete the image after displaying it
        os.remove(image_path)

        # Start downloading the next image
        p = Process(target=download_image, args=(email_ids[i], queue))
        p.start()

    # Wait for the last download to finish and get the image path
    p.join()
    image_path = queue.get()

    # Display the last image
    img = Image.open(image_path)
    img.show()

    # Sleep for 30 seconds before ending the program
    time.sleep(30)

    # Delete the last image
    os.remove(image_path)
