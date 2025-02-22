import pymongo
from urllib.parse import quote_plus
from gridfs import GridFS
from io import BytesIO
import json
import numpy as np
import os
import json
from pymongo import MongoClient
from bson import ObjectId
from gridfs import GridFS
from PIL import Image
from io import BytesIO
import threading
import time
import signal
import os
import psutil
import subprocess
from tqdm import tqdm

# Path to the MongoDB config and log files
ACCESSJSON = '/home/prr000/Documents/Projects/Training/1_Scripts/prr000/config.json'
DB = "Data4AWS"
COLLECTION = "2024"
MONGO_CONFIG = "/home/prr000/Documents/Projects/Training/1_Scripts/prr000/mongod.config"
MONGO_LOG = os.path.expanduser("~/mongod.log")
# Path where extracted folders are stored
BASE_FOLDER = "/fs/phenocart-work/prr000/Extracted_Data"

stop_monitoring = False  # Flag to stop the monitoring thread

def is_mongod_running():
    """Check if mongod is running."""
    for proc in psutil.process_iter(['pid', 'name']):
        if 'mongod' in proc.info['name']:
            return proc.info['pid']
    return None

def start_mongod():
    """Start mongod if not already running."""
    if not is_mongod_running():
        print("Starting MongoDB...")
        process = subprocess.Popen(
            [
                "/bin/bash", "-c",
                f'export PATH="/home/prr000/Documents/MongoDB/Daemon/usr/bin/:$PATH" && '
                f'mongod --fork --config {MONGO_CONFIG}'
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(15)  # Wait for MongoDB to initialize
        pid = is_mongod_running()
        if pid:
            print(f"MongoDB started successfully with PID: {pid}")
        else:
            print("Failed to start MongoDB. Check logs for details.")

def stop_mongod():
    """Gracefully stop mongod if running."""
    global stop_monitoring
    stop_monitoring = True  # Set flag to stop monitoring loop

    print("Searching for 'mongod' processes...")
    found = False

    for proc in psutil.process_iter(['pid', 'name']):
        if 'mongod' in proc.info['name']:
            found = True
            print(f"Terminating 'mongod' process with PID: {proc.info['pid']}")
            os.kill(proc.info['pid'], signal.SIGTERM)  # Graceful shutdown

    if not found:
        print("No 'mongod' processes found.")

    time.sleep(5)

    print("Double-checking for remaining 'mongod' processes...")
    for proc in psutil.process_iter(['pid', 'name']):
        if 'mongod' in proc.info['name']:
            print(f"Forcefully killing 'mongod' process with PID: {proc.info['pid']}")
            os.kill(proc.info['pid'], signal.SIGKILL)  # Force kill

    print("All 'mongod' processes terminated.")


def monitor_mongod():
    """Monitor MongoDB and restart if it stops."""
    global stop_monitoring
    while not stop_monitoring:
        if not is_mongod_running():
            print("MongoDB is not running! Restarting...")
            start_mongod()
        time.sleep(5)  # Check every 5 seconds
    print("Monitoring thread stopped.")

# Start MongoDB before monitoring
start_mongod()

# Start monitoring in a separate thread
monitor_thread = threading.Thread(target=monitor_mongod, daemon=True)
monitor_thread.start()

# %% Database Access
try:
    with open(ACCESSJSON) as config_file:
        config = json.load(config_file)

    username = quote_plus(config['mongodb_username'])
    password = quote_plus(config['mongodb_password'])
    uri = f"mongodb://{username}:{password}@localhost:27018/"

    # Connect to MongoDB
    client = pymongo.MongoClient(uri)

    # Create and Use a New Database
    db = client[DB]  # Change to your preferred name

    # Create a GridFS Bucket for the New Database
    fs = GridFS(db)

    # Create a Collection (Table Equivalent)
    collection = db[COLLECTION]  # Change collection name if needed

    # Test the connection
    print("Attempting to ping the MongoDB server...")
    db.command('ping')  # Check if the connection is successful
    print(f"Successfully connected to MongoDB: {db.name}")

    print("Connected to MongoDB")

    # %% Defs
    # Function to upload images to GridFS and return ObjectId
    def upload_image(file_path):
        """ Upload an image as a NumPy array in GridFS """
        with Image.open(file_path) as img:
            img_array = np.array(img)  # Convert to NumPy array

        img_bytes = BytesIO()
        np.save(img_bytes, img_array)
        img_bytes.seek(0)

        file_id = fs.put(img_bytes, filename=os.path.basename(file_path))
        return file_id


    # Function to upload NumPy files to GridFS and return ObjectId
    def upload_npy(file_path):
        np_data = np.load(file_path)  # Load .npy file
        file_id = fs.put(np_data.tobytes(), filename=os.path.basename(file_path))
        return file_id


    # %% Process each folder
    for folder in tqdm(os.listdir(BASE_FOLDER), desc="Processing documents"):
        folder_path = os.path.join(BASE_FOLDER, folder)

        if not os.path.isdir(folder_path):  # Skip if not a folder
            continue

        metadata_path = os.path.join(folder_path, "metadata.json")

        if not os.path.exists(metadata_path):
            print(f"Skipping {folder}: No metadata.json found")
            continue

        # Load metadata
        with open(metadata_path, "r") as json_file:
            metadata = json.load(json_file)

        print(f"Processing {folder}...")

        # Upload Lidar & Weather Data
        metadata["lidar_id"] = upload_npy(os.path.join(folder_path, "lidar.npy"))
        metadata["weather_id"] = upload_npy(os.path.join(folder_path, "weather.npy"))

        # Upload NIR images
        metadata["nirimage_ids"] = [
            upload_image(os.path.join(folder_path, img)) for img in sorted(os.listdir(folder_path))
            if img.startswith("nir_") and img.endswith(".tif")
        ]

        # Upload RGB images
        metadata["rgbimage_ids"] = [
            upload_image(os.path.join(folder_path, img)) for img in sorted(os.listdir(folder_path))
            if img.startswith("rgb_") and img.endswith(".tif")
        ]

        # Insert document into MongoDB
        inserted_id = collection.insert_one(metadata).inserted_id
        print(f"Inserted document with ID: {inserted_id}")

    print("All folders processed successfully!")

# %% STOP MongoDB
finally:
    print("Stopping MongoDB before exiting...")
    stop_mongod()

    # To stop monitoring later, call:
    stop_mongod()
    monitor_thread.join()  # Wait for the thread to exit