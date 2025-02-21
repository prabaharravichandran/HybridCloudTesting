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
ACCESSJSON = '/gpfs/fs7/aafc/phenocart/PhenomicsProjects/UFPSGPSCProject/5_Data/MongoDB/config.json'
DB = "NewPhenocartDB"
COLLECTION = "PhenotypingData"
MONGO_CONFIG = "/gpfs/fs7/aafc/phenocart/IDEs/MongoDB/mongod.conf"
MONGO_LOG = os.path.expanduser("~/mongod.log")
OUTPUT_PATH = "/gpfs/fs7/aafc/phenocart/PhenomicsProjects/UFPSGPSCProject/2_RGB/FloweringandMaturity/Output/"

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
                f'export PATH="/gpfs/fs7/aafc/phenocart/IDEs/MongoDB/bin/:$PATH" && '
                f'mongod --fork --logpath {MONGO_LOG} --config {MONGO_CONFIG}'
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(5)  # Wait for MongoDB to initialize
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


def save_image(file_id, file_prefix, folder_name):
    file_id = str(file_id)

    try:
        gridout = fs.get(document["rgbimage_ids"][0])  # Retrieve from GridFS
        img_array = np.load(BytesIO(gridout.read()))  # Read binary content

        # If dtype is float, normalize to uint8
        if img_array.dtype == np.float32 or img_array.dtype == np.float64:
            img_array = (255 * (img_array - img_array.min()) / (img_array.max() - img_array.min())).astype(np.uint8)

        # Ensure valid shape (H, W, C)
        if img_array.ndim == 2:  # Grayscale image
            img_array = np.expand_dims(img_array, axis=-1)  # Convert to (H, W, 1)
        elif img_array.ndim != 3 or img_array.shape[2] not in [1, 3, 4]:
            print(f"Skipping {file_id}: Unsupported shape {img_array.shape}")
            return None

        # Convert NumPy array to Image
        img = Image.fromarray(img_array.squeeze(), mode="L" if img_array.shape[2] == 1 else "RGB")

        # Create filename
        file_list = [f for f in os.listdir(folder_name) if f.startswith(file_prefix)]
        count = len(file_list) + 1
        filename = f"{file_prefix}_{count}.tif"

        # Save Image
        img.save(os.path.join(folder_name, filename))
        print(f"Saved: {filename}")
        return filename

    except Exception as e:
        print(f"Skipping {file_id}: Error loading image - {e}")
        return None

# Function to save .npy files
def save_npy(file_id, file_prefix, folder_name):
    file_data = fs.get(ObjectId(file_id)).read()
    np_array = np.frombuffer(file_data, dtype=np.float32)  # Adjust dtype as needed
    filename = f"{file_prefix}.npy"
    np.save(os.path.join(folder_name, filename), np_array)
    return filename

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
    client = pymongo.MongoClient(uri)
    db = client[DB]
    fs = GridFS(db)
    collection = db[COLLECTION]

    # Trigger server selection to check if connection is successful
    print("Attempting to ping the MongoDB server...")
    db.command('ping')  # Sending a ping command to the database
    print("Ping to MongoDB server successful.")

    criteria = {
        "$and": [
            {"year": 2024},
            {"location": "Ottawa"},
            {"rgbimage_ids": {"$exists": True, "$not": {"$size": 0}}},
            {"nirimage_ids": {"$exists": True, "$not": {"$size": 0}}},
            {"seedingdate": {"$exists": True}},
            {"weather_id": {"$exists": True}},
            {"lidar_id": {"$exists": True}},
            {"flowering": {"$exists": True, "$ne": float("NaN")}},
            {"maturity": {"$exists": True, "$ne": float("NaN")}},
            {
                "$expr": {
                    "$eq": [{"$size": "$rgbimage_ids"}, {"$size": "$nirimage_ids"}]
                }
            }
        ]
    }

    documents = list(collection.find(criteria).limit(3))
    print(f"Number of Documents: {len(documents)}")

    for document in tqdm(documents, desc="Processing documents"):
        # Create a folder to save data
        folder_name = f"/gpfs/fs7/aafc/phenocart/IDEs/MongoDB/test/{document['year']}_{document['location']}_{document['date']}_{document['plot']}/"
        os.makedirs(folder_name, exist_ok=True)

        # File counter for naming
        nir_count = 1
        rgb_count = 1

        # Update document by replacing OIDs with filenames
        updated_document = document.copy()

        # Replace Lidar and Weather IDs
        updated_document["lidar_id"] = save_npy(document["lidar_id"], "lidar", folder_name)
        updated_document["weather_id"] = save_npy(document["weather_id"], "weather", folder_name)

        # Replace NIR Image IDs
        updated_document["nirimage_ids"] = [
            save_image(img, "nir", folder_name) for img in document["nirimage_ids"]
        ]

        # Replace RGB Image IDs
        updated_document["rgbimage_ids"] = [
            save_image(img, "rgb", folder_name) for img in document["rgbimage_ids"]
        ]

        # Remove MongoDB _id field
        del updated_document["_id"]

        # Save remaining data as JSON
        json_filename = os.path.join(folder_name, "metadata.json")
        with open(json_filename, "w") as json_file:
            json.dump(updated_document, json_file, indent=4)

        print(f"Data successfully saved in {folder_name}")

# %% STOP MongoDB
finally:
    print("Stopping MongoDB before exiting...")
    stop_mongod()

    # To stop monitoring later, call:
    stop_mongod()
    monitor_thread.join()  # Wait for the thread to exit