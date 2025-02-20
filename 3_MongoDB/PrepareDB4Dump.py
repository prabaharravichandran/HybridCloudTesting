import os
import pymongo
from urllib.parse import quote_plus
from gridfs import GridFS
import json
import psutil
import subprocess
import time
import signal
from bson import ObjectId
from pymongo.errors import BulkWriteError

# %% Start MongoDB Process
process = subprocess.Popen(
    [
        "/bin/bash", "-c",
        'export PATH="/gpfs/fs7/aafc/phenocart/IDEs/MongoDB/bin/:$PATH" && '
        'mongod --fork --logpath ~/mongod.log --config /gpfs/fs7/aafc/phenocart/IDEs/MongoDB/mongod.conf'
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

print(f"'mongod' started with PID: {process.pid}")

# Allow MongoDB some time to start
time.sleep(10)

# %% Load MongoDB Credentials
with open('/gpfs/fs7/aafc/phenocart/PhenomicsProjects/UFPSGPSCProject/5_Data/MongoDB/config.json') as config_file:
    config = json.load(config_file)

# Connect to MongoDB Server
username = quote_plus(config['mongodb_username'])
password = quote_plus(config['mongodb_password'])
uri = f"mongodb://{username}:{password}@localhost:27018/"
client = pymongo.MongoClient(uri)

# Access Databases
source_db = client["UFPS"]
target_db = client["Data4AWS"]

source_collection = source_db["Data"]
target_collection = target_db["2024"]

source_fs = GridFS(source_db)  # Source GridFS
target_fs = GridFS(target_db)  # Target GridFS

# %% Define Filtering Criteria
criteria = {
    "$and": [
        {"year": 2024},
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

# %% Retrieve Filtered Documents
documents = list(source_collection.find(criteria))

if not documents:
    print("No matching documents found. Exiting.")
    exit()

# Insert Filtered Documents into Target Collection
try:
    target_collection.insert_many(documents, ordered=False)
    print(f"✅ Inserted {len(documents)} documents into 'Data4AWS.2024'.")
except BulkWriteError as e:
    print("⚠ Some documents were skipped due to duplicates.")
    print(f"Error details: {e.details}")


# %% Collect Only Relevant File IDs
file_ids_to_copy = set()

for doc in documents:
    if "rgbimage_ids" in doc and isinstance(doc["rgbimage_ids"], list):
        file_ids_to_copy.update(doc["rgbimage_ids"])
    if "nirimage_ids" in doc and isinstance(doc["nirimage_ids"], list):
        file_ids_to_copy.update(doc["nirimage_ids"])
    if "lidar_id" in doc:
        file_ids_to_copy.add(doc["lidar_id"])
    if "weather_id" in doc:
        file_ids_to_copy.add(doc["weather_id"])

# Remove None values
file_ids_to_copy.discard(None)

# %% Copy Only Selected GridFS Files and Corresponding Chunks
print("Copying selected GridFS files and chunks...")

# Define GridFS collections
source_files_collection = source_db["fs.files"]
source_chunks_collection = source_db["fs.chunks"]

target_files_collection = target_db["fs.files"]
target_chunks_collection = target_db["fs.chunks"]

# Copy metadata (`fs.files`) and corresponding data (`fs.chunks`)
copied_files = 0
copied_chunks = 0

for file_id in file_ids_to_copy:
    file_doc = source_files_collection.find_one({"_id": file_id})

    if file_doc:
        # Copy file metadata
        target_files_collection.insert_one(file_doc)
        copied_files += 1

        # Copy corresponding chunks
        source_chunks_cursor = source_chunks_collection.find({"files_id": file_id})
        for chunk in source_chunks_cursor:
            target_chunks_collection.insert_one(chunk)
            copied_chunks += 1

        print(f"Copied file {file_doc.get('filename', 'Unknown')} with ID {file_id} to Data4AWS GridFS.")
    else:
        print(f"File with ID {file_id} not found in GridFS.")

print(f"Selected {copied_files} GridFS files and {copied_chunks} chunks copied successfully.")

# %% Verify File Transfer
print("Verifying transferred files...")

source_file_count = source_files_collection.count_documents({"_id": {"$in": list(file_ids_to_copy)}})
target_file_count = target_files_collection.count_documents({"_id": {"$in": list(file_ids_to_copy)}})
source_chunk_count = source_chunks_collection.count_documents({"files_id": {"$in": list(file_ids_to_copy)}})
target_chunk_count = target_chunks_collection.count_documents({"files_id": {"$in": list(file_ids_to_copy)}})

print(f"Total files in source GridFS: {source_file_count}")
print(f"Total files in target GridFS: {target_file_count}")
print(f"Total chunks in source GridFS: {source_chunk_count}")
print(f"Total chunks in target GridFS: {target_chunk_count}")

if source_file_count == target_file_count and source_chunk_count == target_chunk_count:
    print("File transfer verified successfully!")
else:
    print("File count mismatch! Some files may not have been copied correctly.")

# %% Stop MongoDB Process
print("Stopping MongoDB process...")
found = False

for proc in psutil.process_iter(['pid', 'name']):
    if 'mongod' in proc.info['name']:
        found = True
        print(f"Terminating 'mongod' process with PID: {proc.info['pid']}")
        os.kill(proc.info['pid'], signal.SIGTERM)  # Graceful shutdown

if not found:
    print("No 'mongod' processes found.")

# Double-check for any remaining 'mongod' processes
print("Double-checking for remaining 'mongod' processes...")
for proc in psutil.process_iter(['pid', 'name']):
    if 'mongod' in proc.info['name']:
        print(f"Forcefully killing 'mongod' process with PID: {proc.info['pid']}")
        os.kill(proc.info['pid'], signal.SIGKILL)  # Force kill

print("All 'mongod' processes terminated.")
