import os
os.environ["TF_FORCE_GPU_ALLOW_GROWTH"] = "true"

import pymongo
from urllib.parse import quote_plus
from gridfs import GridFS
from io import BytesIO
import subprocess
import time
import json
import signal
import gc
import psutil
import random
import threading

import numpy as np
from sklearn.decomposition import PCA
from sklearn.model_selection import train_test_split
from tensorflow.keras import layers, regularizers, models, Model, Input
import cv2
from datetime import datetime, timedelta
import tensorflow as tf
from tensorflow.keras.optimizers import Adam
import pandas as pd
from tqdm import tqdm
from tensorflow.python.client import device_lib

import tensorflow as tf
from tensorflow.python.client import device_lib
import plotly.graph_objects as go
import plotly.io as pio

pio.renderers.default = "svg"

# TensorFlow, CUDA, and cuDNN versions
build_info = tf.sysconfig.get_build_info()
print(f"TensorFlow version: {tf.__version__}")
print(f"CUDA version: {build_info.get('cuda_version', 'N/A')}")
print(f"CUDNN version: {build_info.get('cudnn_version', 'N/A')}")

# Detect GPUs and print details
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    gpu_details = [d.physical_device_desc for d in device_lib.list_local_devices() if d.device_type == 'GPU']
    print(f"GPU(s) detected: {gpu_details}")

    # Enable memory growth for GPUs
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        print("Memory growth enabled for GPUs")
    except RuntimeError as e:
        print(f"Error enabling memory growth: {e}")
else:
    print("No GPU detected.")

# Path to the MongoDB config and log files
MONITOR_SCRIPT_PATH = "/home/ubuntu/scripts/SystemMonitor.sh"
MONGO_CONFIG = "/home/ubuntu/mongod.config"
OUTPUT_PATH = "/mnt/phenocart-app/prr000/Projects/Training/4_Output"
ACCESS_CONFIG = "/home/ubuntu/config.json"

# Set a fixed random seed for reproducibility
SEED = 42
tf.random.set_seed(SEED)
np.random.seed(SEED)
random.seed(SEED)
os.environ['PYTHONHASHSEED'] = str(SEED)

import threading
import time
import signal
import os
import psutil
import subprocess

def start_monitoring():
    print("Starting system monitoring...")
    process = subprocess.Popen(
        ["bash", MONITOR_SCRIPT_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid
    )

    # Wait a moment to see if it fails immediately
    time.sleep(2)

    # If process.poll() is not None, the process has exited
    retcode = process.poll()
    if retcode is not None:
        error_output = process.stderr.read().decode('utf-8').strip()
        print(f"Monitoring script failed to start (exit code: {retcode}).")
        print(f"stderr: {error_output}")
    else:
        print("Monitoring script started successfully, running in the background.")

    return process


def terminate_monitoring(process):
    print("Stopping system monitoring...")
    os.killpg(os.getpgid(process.pid), signal.SIGTERM)  # Terminate the process group

# Example usage:
process = start_monitoring()

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
                f'mongod --fork --config {MONGO_CONFIG}'
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


# Start MongoDB before monitoring
start_mongod()

# Start monitoring in a separate thread
monitor_thread = threading.Thread(target=monitor_mongod, daemon=True)
monitor_thread.start()

# %% Database Access
with open(ACCESS_CONFIG) as config_file:
    config = json.load(config_file)

username = quote_plus(config['mongodb_username'])
password = quote_plus(config['mongodb_password'])
uri = f"mongodb://{username}:{password}@localhost:27018/"
client = pymongo.MongoClient(uri)
db = client["Data4AWS"]
fs = GridFS(db)
collection = db["2024"]

# Trigger server selection to check if connection is successful
print("Attempting to ping the MongoDB server...")
db.command('ping')  # Sending a ping command to the database
print("Ping to MongoDB server successful.")

# %% Extract data from documents
img_rows, img_cols = int(2048 / 4), int(2448 / 4)

# Projection function
def projection3x(lidar_raw):
    # Check if the lidar data has enough points (at least 2 samples and features)
    if lidar_raw.shape[0] < 2 or lidar_raw.shape[1] < 2:
        raise ValueError(
            f"Insufficient lidar data: {lidar_raw.shape[0]} samples and {lidar_raw.shape[1]} features. PCA cannot be applied.")

    # Separate the data into x, y, z
    x, y, z = lidar_raw[:, 0], lidar_raw[:, 1], lidar_raw[:, 2]

    # Scale coordinates to centimeters
    x = x * 100
    y = y * 100
    z = z * 100

    # Set minimum of each axis to 0 cm
    x -= np.min(x)
    y -= np.min(y)
    z -= np.min(z)

    # PCA for dominant direction in X-Y plane (optional for rotation)
    points = np.vstack((x, y)).T
    pca = PCA(n_components=2)
    pca.fit(points)
    angle = np.arctan2(pca.components_[0, 1], pca.components_[0, 0])

    # Rotate points to align with grid axes
    rotation_matrix = np.array([
        [np.cos(-angle), -np.sin(-angle)],
        [np.sin(-angle), np.cos(-angle)]
    ])
    rotated_points = points @ rotation_matrix.T
    rotated_x, rotated_y = rotated_points[:, 0], rotated_points[:, 1]

    # Flip the x and y coordinates for X-Z and Y-Z projections if needed
    rotated_x = np.max(rotated_x) - rotated_x  # Flip x-axis for X-Z plane
    rotated_y = np.max(rotated_y) - rotated_y  # Flip y-axis for Y-Z plane

    # Define resolution for each plane
    xy_resolution = 1  # Adjusted to 1 cm for X-Y plane
    xz_resolution = 1  # Adjusted to 1 cm for X-Z plane
    yz_resolution = 1  # Adjusted to 1 cm for Y-Z plane

    # Define boundaries for each plane
    x_min, x_max = np.min(rotated_x), np.max(rotated_x)
    y_min, y_max = np.min(rotated_y), np.max(rotated_y)
    z_min, z_max = np.min(z), np.max(z)

    # Calculate grid sizes
    grid_x_size_xy = int((x_max - x_min) / xy_resolution) + 1
    grid_y_size_xy = int((y_max - y_min) / xy_resolution) + 1
    grid_x_size_xz = int((x_max - x_min) / xz_resolution) + 1
    grid_z_size_xz = int((z_max - z_min) / xz_resolution) + 1
    grid_y_size_yz = int((y_max - y_min) / yz_resolution) + 1
    grid_z_size_yz = int((z_max - z_min) / yz_resolution) + 1

    # Initialize grids with NaNs
    grid_xy = np.full((grid_y_size_xy, grid_x_size_xy), np.nan, dtype=np.float32)
    grid_xz = np.full((grid_z_size_xz, grid_x_size_xz), np.nan, dtype=np.float32)
    grid_yz = np.full((grid_z_size_yz, grid_y_size_yz), np.nan, dtype=np.float32)

    # Project Z onto X-Y plane using maximum aggregation
    for i in range(len(rotated_x)):
        grid_x = int((rotated_x[i] - x_min) / xy_resolution)
        grid_y = int((rotated_y[i] - y_min) / xy_resolution)
        if np.isnan(grid_xy[grid_y, grid_x]):
            grid_xy[grid_y, grid_x] = z[i]
        else:
            grid_xy[grid_y, grid_x] = max(grid_xy[grid_y, grid_x], z[i])

    # Project Z onto X-Z plane using maximum aggregation
    for i in range(len(rotated_x)):
        grid_x = int((rotated_x[i] - x_min) / xz_resolution)
        grid_z = int((z[i] - z_min) / xz_resolution)
        if np.isnan(grid_xz[grid_z, grid_x]):
            grid_xz[grid_z, grid_x] = z[i]  # Use z[i] for the X-Z projection
        else:
            grid_xz[grid_z, grid_x] = max(grid_xz[grid_z, grid_x], z[i])

    # Project Z onto Y-Z plane using maximum aggregation
    for i in range(len(rotated_y)):
        grid_y = int((rotated_y[i] - y_min) / yz_resolution)
        grid_z = int((z[i] - z_min) / yz_resolution)
        if np.isnan(grid_yz[grid_z, grid_y]):
            grid_yz[grid_z, grid_y] = z[i]  # Use z[i] for the Y-Z projection
        else:
            grid_yz[grid_z, grid_y] = max(grid_yz[grid_z, grid_y], z[i])

    # Replace NaNs with zero
    grid_xy = np.nan_to_num(grid_xy, nan=0.0)
    grid_xz = np.nan_to_num(grid_xz, nan=0.0)
    grid_yz = np.nan_to_num(grid_yz, nan=0.0)

    # Optionally resize grids for display purposes
    resized_grid_xy = cv2.resize(grid_xy, (300, 100), interpolation=cv2.INTER_NEAREST)
    resized_grid_xz = cv2.resize(grid_xz, (300, 100), interpolation=cv2.INTER_NEAREST)
    resized_grid_yz = cv2.resize(grid_yz, (300, 100), interpolation=cv2.INTER_NEAREST)

    return np.dstack((resized_grid_xy, resized_grid_xz, resized_grid_yz))


def image_processing(image_raw, target_size=(img_rows, img_cols), is_nir=False):
    """
    Processes an image by resizing it to the target size and ensuring the correct number of channels.

    Args:
        image_raw: The raw input image (numpy array or PIL image).
        target_size: Tuple (height, width) specifying the size to resize the image.
        is_nir: Boolean flag; if True, treats the image as a grayscale NIR image.

    Returns:
        Processed image resized to (img_rows, img_cols, channels),
        where channels = 3 for RGB, 1 for grayscale NIR.
    """
    # Convert to grayscale if NIR image
    if is_nir:
        image_resized = cv2.resize(image_raw, (target_size[1], target_size[0]), interpolation=cv2.INTER_LINEAR)
        if len(image_resized.shape) == 2:  # Ensure it remains grayscale (1 channel)
            image_resized = np.expand_dims(image_resized, axis=-1)  # Shape (H, W, 1)
    else:
        # Convert RGB image to 3 channels if necessary
        image_resized = cv2.resize(image_raw, (target_size[1], target_size[0]), interpolation=cv2.INTER_LINEAR)
        if len(image_resized.shape) == 2:  # Convert grayscale to RGB if needed
            image_resized = cv2.cvtColor(image_resized, cv2.COLOR_GRAY2RGB)

    return image_resized


def get_julian_day(date_str):
    """
    Convert a date in YYMMDD format to Julian Day (DDD).

    Args:
        date_str (str): Date in YYMMDD format (e.g., "230825").

    Returns:
        int: Julian day of the year (DDD).
    """
    # Parse the input date string
    date = datetime.strptime(str(date_str), "%y%m%d")

    # Extract the Julian day (day of the year)
    julian_day = date.timetuple().tm_yday  # Day of the year
    return julian_day

def clear_gpu_memory():
    """Clear GPU memory by resetting the session and deleting unused variables."""
    tf.keras.backend.clear_session()  # Clear the TensorFlow backend
    gc.collect()  # Force garbage collection
    print("GPU memory cleared.")


def print_distribution(data, label, num_bins=10):
    """
    Prints the distribution of a dataset by splitting it into bins.

    Parameters:
    - data (numpy array): The dataset to be binned.
    - label (str): Label for the dataset (e.g., "Flowering Days" or "Maturity Days").
    - num_bins (int): Number of bins to split the data into.
    """
    hist, bins = np.histogram(data, bins=num_bins)

    print(f"\n{label} Distribution:")
    print("| Bin | Range (Days) | Count |")
    print("|----|-------------|-------|")
    for i in range(num_bins):
        print(f"| {i + 1}  | {bins[i]:.1f} - {bins[i + 1]:.1f} | {hist[i]}  |")


def plot_histogram(data, label, num_bins=10, filename="histogram.svg"):
    """
    Plots a simple histogram using Plotly with tick marks at bin centers.

    Parameters:
    - data (numpy array): The dataset to be plotted.
    - label (str): Label for the dataset (e.g., "Flowering Days" or "Maturity Days").
    - num_bins (int): Number of bins to split the data into.
    - filename (str): File path to save the SVG plot.
    """
    min_val, max_val = np.min(data), np.max(data)
    bin_edges = np.linspace(min_val, max_val, num_bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2  # Compute bin centers

    # Determine if the data is continuous or discrete
    is_continuous = np.any(data % 1)  # True if at least one value has decimals

    # Format tick labels: integers for discrete, two decimals for continuous
    tick_labels = [f"{b:.2f}" if is_continuous else f"{int(b)}" for b in bin_centers]

    fig = go.Figure(go.Histogram(
        x=data.flatten(),
        xbins=dict(start=min_val, end=max_val, size=(max_val - min_val) / num_bins),
        marker_color="#35b779",  # Bar color
        opacity=0.75
    ))

    fig.update_layout(
        width=1200,
        height=800,
        font=dict(size=22),  # Global font size
        # title=f"{label} Distribution",
        xaxis_title=label,
        yaxis_title="Count",
        template="plotly_white",
        plot_bgcolor='rgba(0,0,0,0)',  # Transparent background
        paper_bgcolor='rgba(0,0,0,0)',  # Transparent outer background
        xaxis=dict(
            tickmode="array",
            tickvals=bin_centers,  # Set ticks at bin centers
            ticktext=tick_labels,  # Use formatted labels
            showline=True,
            linecolor='rgba(0,0,0,0)',  # Axis line color
            linewidth=2,  # Axis line width
            ticklen=10,  # Tick length
            tickcolor='rgba(0,0,0,0)'  # Tick color
        ),
        yaxis=dict(
            showline=True,
            linecolor='rgba(0,0,0,0)',  # Axis line color
            linewidth=2,  # Axis line width
            ticklen=10,  # Tick length
            tickcolor='rgba(0,0,0,0)'  # Tick color
        ),
        bargap=0.05,
    )

    fig.write_image(filename)
    print(f"Histogram saved as {filename}")


try:

    # %% Step 1: Filter documents based on criteria
    # Clear GPU memory after processing the chunk
    clear_gpu_memory()

    criteria = {
        "$and": [
            {"year": 2024},
            {"rgbimage_ids": {"$exists": True, "$not": {"$size": 0}}},  # Ensure rgbimage_ids exists & is not empty
            {"nirimage_ids": {"$exists": True, "$not": {"$size": 0}}},  # Ensure nirimage_ids exists & is not empty
            {"seedingdate": {"$exists": True}},
            {"weather_id": {"$exists": True}},
            {"lidar_id": {"$exists": True}},
            {"yield": {"$exists": True, "$ne": float("NaN")}},
            {
                "$expr": {
                    "$eq": [{"$size": "$rgbimage_ids"}, {"$size": "$nirimage_ids"}]
                }
            },  # Ensures rgbimage_ids and nirimage_ids have the same length
            {
                "$expr": {
                    "$lt": [{"$size": "$rgbimage_ids"}, 10]
                }
            }  # Ensures rgbimage_ids has fewer than 10 elements
        ]
    }

    documents = list(collection.find(criteria))

    # Shuffle the documents
    random.shuffle(documents)

    # Count matching documents
    document_count = collection.count_documents(criteria)
    print(f"Number of matching documents: {document_count}")

    # %%Get data from MongoDB
    # Initialize empty lists for training data

    x_rgbimage, x_nirimage, x_weather, x_lidar = [], [], [], []
    x_imagedate, x_seedingdate = [], []
    y_yield = []

    for document in tqdm(documents, desc="Processing documents"):
        rgbimage_ids = document.get('rgbimage_ids', [])
        nirimage_ids = document.get('nirimage_ids', [])

        for rgb_id, nir_id in zip(rgbimage_ids, nirimage_ids):
            rgb_data, nir_data, weather_data, lidar_data = None, None, None, None
            imagedate_data, seedingdate_data = None, None
            yield_data = None
            append_data = True  # Flag to track if there was an error for the document

            try:
                # Fetch the RGB image
                try:
                    gridout_rgb = fs.get(rgb_id)
                    rgb_image_raw = np.load(BytesIO(gridout_rgb.read()))
                    resized_rgb_image = image_processing(rgb_image_raw, is_nir=False)  # Process the RGB image
                    rgb_data = resized_rgb_image  # Store the processed RGB image

                except Exception as e:
                    print(f"Error reading RGB image with rgb_id {rgb_id}: {e}")
                    append_data = False  # Mark as False if reading fails

                # Fetch the NIR image
                try:
                    gridout_nir = fs.get(nir_id)
                    nir_image_raw = np.load(BytesIO(gridout_nir.read()))
                    resized_nir_image = image_processing(nir_image_raw, is_nir=True)  # Process the NIR image
                    nir_data = resized_nir_image  # Store the processed NIR image

                except Exception as e:
                    print(f"Error reading NIR image with nir_id {nir_id}: {e}")
                    append_data = False  # Mark as False if reading fails

                # Weather data
                try:
                    gridout_weather = fs.get(document['weather_id'])
                    weather_data = np.load(BytesIO(gridout_weather.read()))
                except Exception as e:
                    print(f"Error reading weather data for document {document.get('id', 'Unknown')}: {e}")
                    append_data = False  # Mark as False if reading weather data fails

                # Lidar data
                try:
                    gridout_lidar = fs.get(document['lidar_id'])
                    lidar_data_raw = np.load(BytesIO(gridout_lidar.read()))
                    lidar_data = projection3x(lidar_data_raw)
                except Exception as e:
                    print(f"Error reading lidar data for document {document.get('id', 'Unknown')}: {e}")
                    append_data = False  # Mark as False if reading lidar data fails

                # Image date, seeding date, and yield labels
                try:
                    seedingdate_data = get_julian_day(document['seedingdate'])
                    imagedate_data = get_julian_day(document['date'])

                    # get yield
                    yield_data = document['yield'] / 1000

                except Exception as e:
                    print(f"Error reading date and label data for document {document.get('id', 'Unknown')}: {e}")
                    append_data = False  # Mark as False if reading date or labels fails

                # If all required data is available, append the data to the lists
                if append_data:
                    x_rgbimage.append(rgb_data)
                    x_nirimage.append(nir_data)
                    x_weather.append(weather_data)
                    x_lidar.append(lidar_data)
                    x_imagedate.append(imagedate_data)
                    x_seedingdate.append(seedingdate_data)
                    y_yield.append(yield_data)

            except Exception as e:
                print(f"Error: {e}")
                append_data = False
                continue  # Skip the entire document if there's an error

    # %%DL
    # Convert inputs to NumPy arrays
    x_rgbimage = np.array(x_rgbimage)
    x_nirimage = np.array(x_nirimage)
    x_seedingdate = np.array(x_seedingdate).reshape(-1, 1)
    x_imagedate = np.array(x_imagedate).reshape(-1, 1)
    x_weather = np.array(x_weather).transpose(0, 2, 3, 1) # Rearrange dimensions to (batch_size, height, width, channels)
    x_lidar = np.array(x_lidar)

    # Convert outputs to NumPy arrays
    y_yield = np.array(y_yield).reshape(-1, 1)

    # distribution:
    # print_distribution(y_flowering, "Flowering Days")
    # print_distribution(y_maturity, "Maturity Days")

    # Save histograms as SVG files
    # plot_histogram_and_save(y_flowering, "Flowering Days", filename=f"{OUTPUT_PATH}flowering_histogram.svg")
    # plot_histogram_and_save(y_maturity, "Maturity Days", filename=f"{OUTPUT_PATH}maturity_histogram.svg")

    print(f"x_train_rgbimage: {type(x_rgbimage)}, shape: {x_rgbimage.shape}")
    print(f"x_train_nirimage: {type(x_nirimage)}, shape: {x_nirimage.shape}")
    print(f"x_train_seedingdate: {type(x_seedingdate)}, shape: {x_seedingdate.shape}")
    print(f"x_train_imagedate: {type(x_imagedate)}, shape: {x_imagedate.shape}")
    print(f"x_train_lidar: {type(x_lidar)}, shape: {x_lidar.shape}")
    print(f"x_train_weather: {type(x_weather)}, shape: {x_weather.shape}")
    print(f"y_train_yield: {type(y_yield)}, shape: {y_yield.shape}")

    print("Checking for NaNs or infinities in the data...")
    print("RGB Images:", np.isnan(x_rgbimage).any() or np.isinf(x_rgbimage).any())
    print("NIR Images:", np.isnan(x_nirimage).any() or np.isinf(x_nirimage).any())
    print("Seeding Date:", np.isnan(x_seedingdate).any() or np.isinf(x_seedingdate).any())
    print("Image Date:", np.isnan(x_imagedate).any() or np.isinf(x_imagedate).any())
    print("LiDAR Data:", np.isnan(x_lidar).any() or np.isinf(x_lidar).any())
    print("Weather Data:", np.isnan(x_weather).any() or np.isinf(x_weather).any())
    print("yield:", np.isnan(y_yield).any() or np.isinf(y_yield).any())

# %% STOP MongoDB
finally:
    print("Stopping MongoDB before exiting...")
    stop_mongod()

# To stop monitoring later, call:
stop_mongod()
monitor_thread.join()  # Wait for the thread to exit
# %%
# -----------------------------
# 1. NORMALIZATION HELPERS
# -----------------------------
def conv_bn_relu(x, filters, kernel_size=3, strides=1, padding='same',
                 use_bias=False, kernel_regularizer=None):
    """Conv -> BN -> ReLU."""
    x = layers.Conv2D(
        filters, kernel_size, strides=strides, padding=padding,
        use_bias=use_bias, kernel_regularizer=kernel_regularizer
    )(x)
    x = layers.BatchNormalization()(x)
    x = layers.ReLU()(x)
    return x


def squeeze_excite_block(x, reduction=16):
    """Squeeze-and-Excitation block."""
    filters = x.shape[-1]
    se = layers.GlobalAveragePooling2D()(x)
    # Squeeze
    se = layers.Dense(filters // reduction, activation='relu')(se)
    # Excite
    se = layers.Dense(filters, activation='sigmoid')(se)
    # Scale
    x = layers.multiply([x, se])
    return x


def bottleneck_res_se_block(inputs, filters, strides=1, reduction=16,
                            kernel_regularizer=None):
    """Bottleneck block with Squeeze-and-Excitation."""
    shortcut = inputs

    # Adjust shortcut if needed
    if (inputs.shape[-1] != filters) or (strides != 1):
        shortcut = layers.Conv2D(
            filters, kernel_size=1, strides=strides, padding='same',
            kernel_regularizer=kernel_regularizer, use_bias=False
        )(shortcut)
        shortcut = layers.BatchNormalization()(shortcut)

    # Bottleneck
    x = conv_bn_relu(inputs, filters // 4, kernel_size=1,
                     kernel_regularizer=kernel_regularizer)
    x = conv_bn_relu(x, filters // 4, kernel_size=3, strides=strides,
                     kernel_regularizer=kernel_regularizer)
    x = layers.Conv2D(filters, (1, 1), padding='same', use_bias=False,
                      kernel_regularizer=kernel_regularizer)(x)
    x = layers.BatchNormalization()(x)

    # Squeeze-and-Excite
    x = squeeze_excite_block(x, reduction=reduction)

    # Merge
    x = layers.Add()([x, shortcut])
    x = layers.ReLU()(x)
    return x


# -----------------------------
# 2. BRANCHES
# -----------------------------
def build_image_branch(
        input_shape,
        initial_filters=32,
        num_blocks=3,
        name_prefix="image_branch",
        kernel_regularizer=None,
        scale_factor=1.0 / 255.0,  # <--- specify default
):
    """
    Builds a CNN branch for image-like input.
    The first layer rescales so you don't have to do x/255 externally.
    """
    inputs = Input(shape=input_shape, name=name_prefix + "_input")

    # Rescale so you do NOT have to do image/255 outside the model
    x = layers.Rescaling(scale_factor)(inputs)

    # Initial Conv -> BN -> ReLU
    x = conv_bn_relu(x, initial_filters, kernel_size=3,
                     kernel_regularizer=kernel_regularizer)
    x = layers.MaxPooling2D((2, 2))(x)

    # Residual SE blocks
    filters = initial_filters * 2
    for i in range(num_blocks):
        x = bottleneck_res_se_block(
            x, filters=filters,
            strides=2 if i == 0 else 1,
            kernel_regularizer=kernel_regularizer
        )
    x = layers.GlobalAveragePooling2D()(x)
    return Model(inputs, x, name=name_prefix)


def build_dense_branch(
        input_dim,
        units_list=[64, 128, 256],
        name_prefix="dense_branch",
        kernel_regularizer=None,
        scalar_scale=None,  # <--- new option for dividing scalars
):
    """
    Builds an MLP branch for scalar input.
    If scalar_scale is not None, apply x/scalar_scale inside the model.
    """
    inputs = Input(shape=(input_dim,), name=f"{name_prefix}_input")

    # If you want x / 365 for days, do it here:
    if scalar_scale is not None:
        x = layers.Lambda(lambda z: z / scalar_scale)(inputs)
    else:
        x = inputs

    for i, units in enumerate(units_list):
        x = layers.Dense(
            units, activation='relu', kernel_regularizer=kernel_regularizer,
            name=f"{name_prefix}_dense_{i}"
        )(x)
    return Model(inputs, x, name=name_prefix)


def build_weather_branch(
        input_shape,
        initial_filters=64,
        num_blocks=2,
        name_prefix="weather_branch",
        kernel_regularizer=None,
        scale_factor=None
):
    """
    Builds a CNN branch for weather data.
    If scale_factor is provided, you can do a Rescaling inside.
    """
    inputs = Input(shape=input_shape, name=name_prefix + "_input")
    x = inputs

    # If you want to do some scale like x/100 or x/1000 for weather, do it:
    if scale_factor is not None:
        x = layers.Rescaling(scale_factor)(x)

    x = conv_bn_relu(x, initial_filters, kernel_size=3,
                     kernel_regularizer=kernel_regularizer)
    x = layers.MaxPooling2D(pool_size=(2, 2))(x)

    filters = initial_filters * 2
    for i in range(num_blocks):
        x = bottleneck_res_se_block(
            x, filters=filters, strides=1,
            kernel_regularizer=kernel_regularizer
        )

    x = layers.GlobalAveragePooling2D()(x)
    return Model(inputs, x, name=name_prefix)


# -----------------------------
# 3. BUILD / COMPILE MODEL
# -----------------------------
strategy = tf.distribute.MirroredStrategy()

with strategy.scope():
    reg = regularizers.l2(1e-5)

    # Image branches
    rgb_branch = build_image_branch(
        input_shape=(512, 612, 3),
        initial_filters=16,
        num_blocks=4,
        name_prefix="rgb",
        kernel_regularizer=reg,
        scale_factor=1.0 / 255.0
    )
    nir_branch = build_image_branch(
        input_shape=(512, 612, 1),
        initial_filters=16,
        num_blocks=4,
        name_prefix="nir",
        kernel_regularizer=reg,
        scale_factor=1.0 / 255.0
    )
    lidar_branch = build_image_branch(
        input_shape=(100, 300, 3),
        initial_filters=32,
        num_blocks=4,
        name_prefix="lidar",
        kernel_regularizer=reg,
        scale_factor=1.0 / 150.0  # e.g., if LiDAR range ~150
    )

    # Scalar branches
    seeding_branch = build_dense_branch(
        input_dim=1,
        units_list=[64, 128, 256],
        name_prefix="seeding",
        kernel_regularizer=reg,
        scalar_scale=365.0
    )
    image_date_branch = build_dense_branch(
        input_dim=1,
        units_list=[64, 128, 256],
        name_prefix="image_date_branch",
        kernel_regularizer=reg,
        scalar_scale=365.0
    )

    # Weather branch
    weather_branch = build_weather_branch(
        input_shape=(8, 8, 146),
        initial_filters=64,
        num_blocks=4,
        name_prefix="weather",
        kernel_regularizer=reg,
        scale_factor=1.0/100.0
    )

    # Inputs
    rgb_input = tf.keras.Input(shape=(512, 612, 3), name="rgb_image")
    nir_input = tf.keras.Input(shape=(512, 612, 1), name="nir_image")
    lidar_input = tf.keras.Input(shape=(100, 300, 3), name="lidar_data")
    seeding_input = tf.keras.Input(shape=(1,), name="seeding_date")
    image_date_input = tf.keras.Input(shape=(1,), name="image_date")
    weather_input = tf.keras.Input(shape=(8, 8, 146), name="weather_data")

    # Extract features
    rgb_features = rgb_branch(rgb_input)
    nir_features = nir_branch(nir_input)
    lidar_features = lidar_branch(lidar_input)
    seeding_features = seeding_branch(seeding_input)
    image_date_features = image_date_branch(image_date_input)
    weather_features = weather_branch(weather_input)

    # Concatenate
    combined = layers.Concatenate()([
        rgb_features,
        nir_features,
        lidar_features,
        seeding_features,
        image_date_features,
        weather_features
    ])

    # Shared dense layers
    x = layers.Dense(512, activation='relu', kernel_regularizer=reg)(combined)
    x = layers.LayerNormalization()(x)
    x = layers.Dropout(0.2)(x)

    x = layers.Dense(1024, activation='relu', kernel_regularizer=reg)(x)
    x = layers.LayerNormalization()(x)
    x = layers.Dropout(0.2)(x)

    x = layers.Dense(512, activation='relu', kernel_regularizer=reg)(x)
    x = layers.LayerNormalization()(x)
    x = layers.Dropout(0.2)(x)

    # Single output: yield
    gyield = layers.Dense(128, activation='relu', kernel_regularizer=reg)(x)
    gyield = layers.LayerNormalization()(gyield)
    gyield = layers.Dropout(0.1)(gyield)
    gyield = layers.Dense(64, activation='relu', kernel_regularizer=reg)(gyield)
    gyield = layers.LayerNormalization()(gyield)
    yield_output = layers.Dense(1, activation='linear', name="yield")(gyield)

    # Build & compile
    model = Model(
        inputs=[rgb_input, nir_input, lidar_input,
                seeding_input, image_date_input, weather_input],
        outputs=yield_output,
        name="MultiModal_ResSE_Model_yield"
    )

    optimizer = Adam(learning_rate=1e-4, clipnorm=1.0)
    model.compile(
        optimizer=optimizer,
        loss="mse",  # Single output => single loss
        metrics=["mae"]  # or any other relevant metrics
    )

model.summary()

# Set up early stopping
early_stopping = tf.keras.callbacks.EarlyStopping(
    monitor='val_loss', patience=10, restore_best_weights=True
)

# Initialize best metrics for tracking (yield only)
best_r2_yield = -np.inf
best_rmse_yield = np.inf

# Results storage
results = []

# Use an independent random seed for shuffling
shuffle_seed = np.random.randint(0, 10000)
np.random.seed(shuffle_seed)

# Shuffle data before splitting
shuffle_indices = np.random.permutation(len(x_rgbimage))
x_rgbimage = x_rgbimage[shuffle_indices]
x_nirimage = x_nirimage[shuffle_indices]
x_seedingdate = x_seedingdate[shuffle_indices]
x_imagedate = x_imagedate[shuffle_indices]
x_lidar = x_lidar[shuffle_indices]
x_weather = x_weather[shuffle_indices]
y_yield = y_yield[shuffle_indices]

# Split a test dataset (20% of total data)
(
    x_train_rgbimage, x_test_rgbimage,
    x_train_nirimage, x_test_nirimage,
    x_train_seedingdate, x_test_seedingdate,
    x_train_imagedate, x_test_imagedate,
    x_train_lidar, x_test_lidar,
    x_train_weather, x_test_weather,
    y_train_yield, y_test_yield
) = train_test_split(
    x_rgbimage, x_nirimage, x_seedingdate, x_imagedate, x_lidar, x_weather,
    y_yield, test_size=0.2, random_state=None
)

# Run the training process N times
for repetition in range(1, 3):
    print(f"Repetition: {repetition}")

    # Define the desired chunk size
    desired_chunk_size = 1000

    # Calculate the number of chunks needed
    total_train_samples = len(x_train_rgbimage)
    num_chunks = max(1, total_train_samples // desired_chunk_size)

    # Generate split indices
    split_indices = [i * desired_chunk_size for i in range(1, num_chunks)]
    split_indices.append(total_train_samples)

    print(f"Total samples: {total_train_samples}")
    print(f"Chunk size: {desired_chunk_size}")
    print(f"Number of chunks: {num_chunks}")
    print(f"Split indices: {split_indices}")

    # Iterate over training chunks
    for i, (start, end) in enumerate(zip([0] + split_indices[:-1], split_indices)):
        print(f"Processing training chunk {i + 1}...")

        # Extract the current chunk
        x_chunk_rgbimage = x_train_rgbimage[start:end]
        x_chunk_nirimage = x_train_nirimage[start:end]
        x_chunk_seedingdate = x_train_seedingdate[start:end]
        x_chunk_imagedate = x_train_imagedate[start:end]
        x_chunk_lidar = x_train_lidar[start:end]
        x_chunk_weather = x_train_weather[start:end]
        y_chunk_yield = y_train_yield[start:end]

        # Split chunk into training/validation
        (
            x_chunk_rgbimage_train, x_chunk_rgbimage_val,
            x_chunk_nirimage_train, x_chunk_nirimage_val,
            x_chunk_seedingdate_train, x_chunk_seedingdate_val,
            x_chunk_imagedate_train, x_chunk_imagedate_val,
            x_chunk_lidar_train, x_chunk_lidar_val,
            x_chunk_weather_train, x_chunk_weather_val,
            y_chunk_yield_train, y_chunk_yield_val
        ) = train_test_split(
            x_chunk_rgbimage, x_chunk_nirimage,
            x_chunk_seedingdate, x_chunk_imagedate,
            x_chunk_lidar, x_chunk_weather,
            y_chunk_yield,
            test_size=0.2,
            random_state=None
        )

        # Train the model on the current chunk
        history = model.fit(
            {
                "rgb_image": x_chunk_rgbimage_train,
                "nir_image": x_chunk_nirimage_train,
                "lidar_data": x_chunk_lidar_train,
                "seeding_date": x_chunk_seedingdate_train,
                "image_date": x_chunk_imagedate_train,
                "weather_data": x_chunk_weather_train,
            },
            y_chunk_yield_train,
            validation_data=(
                {
                    "rgb_image": x_chunk_rgbimage_val,
                    "nir_image": x_chunk_nirimage_val,
                    "lidar_data": x_chunk_lidar_val,
                    "seeding_date": x_chunk_seedingdate_val,
                    "image_date": x_chunk_imagedate_val,
                    "weather_data": x_chunk_weather_val,
                },
                y_chunk_yield_val,
            ),
            epochs=100,
            batch_size=1,
            callbacks=[early_stopping],
            verbose=1
        )

        # Clear GPU memory if you wish (custom function)
        clear_gpu_memory()

    # Validation predictions and metrics calculation
    y_pred = model.predict(
        {
            "rgb_image": x_test_rgbimage,
            "nir_image": x_test_nirimage,
            "lidar_data": x_test_lidar,
            "seeding_date": x_test_seedingdate,
            "image_date": x_test_imagedate,
            "weather_data": x_test_weather,
        }
    )

    # Flatten the predictions & true values
    y_pred_yield = y_pred.flatten()
    y_true_yield = y_test_yield.flatten()

    # Metrics for yield
    R2_yield = 1 - np.sum((y_true_yield - y_pred_yield) ** 2) / np.sum(
        (y_true_yield - np.mean(y_true_yield)) ** 2
    )
    RMSE_yield = np.sqrt(np.mean((y_true_yield - y_pred_yield) ** 2))
    MAPE_yield = np.mean(np.abs((y_true_yield - y_pred_yield) / y_true_yield)) * 100

    # Track the best model for yield
    if R2_yield > best_r2_yield or RMSE_yield < best_rmse_yield:
        best_r2_yield = R2_yield
        best_rmse_yield = RMSE_yield
        best_model_path_yield = f'{OUTPUT_PATH}/Y.h5'
        model.save(best_model_path_yield)
        print(f"New best yield model saved with R²: {R2_yield:.2f}, RMSE: {RMSE_yield:.2f}")

    # Append results
    results.append({
        'Repetition': repetition,
        'R2 Score yield (%)': R2_yield * 100,
        'RMSE yield': RMSE_yield,
        'MAPE yield (%)': MAPE_yield
    })

    # Print iteration results
    print(f"Repetition {repetition}")
    print(f"R2 Score yield (%): {R2_yield * 100:.2f}")
    print(f"RMSE yield: {RMSE_yield:.2f}")
    print(f"MAPE yield (%): {MAPE_yield:.2f}")
    print("-" * 50)

    # Save results to an Excel file
    results_df = pd.DataFrame(results)
    results_file_path = f'{OUTPUT_PATH}/Y_Results.xlsx'
    results_df.to_excel(results_file_path, index=False)
    print(f"Results saved to {results_file_path}")
'''
# Define the email command dynamically using the results_file_path variable
email_command = (
    f'export PATH=/gpfs/fs7/aafc/phenocart/IDEs/Mutt/bin:$PATH && '
    f'echo "Please find the results attached." | mutt -s "SLURM Job Result" '
    f'-a {results_file_path} -- prabahar.ravichandran@agr.gc.ca'
)

# Execute the command
try:
    subprocess.run(email_command, shell=True, check=True)
    print("Email sent successfully.")
except subprocess.CalledProcessError as e:
    print(f"Failed to send email: {e}")
'''

# Later, when you want to stop monitoring:
terminate_monitoring(process)
