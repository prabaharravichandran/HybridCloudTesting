import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Path to your CSV
CSV_FILE = "/fs/phenocart-app/prr000/Projects/Training/4_Output/compute-g6-12xlarge-b32/system_monitor_log.csv"

# Read the CSV file
df = pd.read_csv(CSV_FILE)

# Debug: Print the loaded column names
print("Columns found:", df.columns.tolist())

# Clean up column names by stripping extra whitespace
df.columns = df.columns.str.strip()

# Rename column if necessary (e.g., if it's lowercase)
if 'timestamp' in df.columns and 'Timestamp' not in df.columns:
    df.rename(columns={'timestamp': 'Timestamp'}, inplace=True)

# Ensure that the Timestamp column exists
if 'Timestamp' not in df.columns:
    raise KeyError("The CSV file does not contain a 'Timestamp' column.")

# Convert the Timestamp column to datetime
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# Compute elapsed minutes from the earliest timestamp
start_time = df['Timestamp'].min()
df['Time (min)'] = (df['Timestamp'] - start_time).dt.total_seconds() / 60.0

# Identify the GPU utilization and GPU memory-used columns
gpu_util_cols = [col for col in df.columns if "Util(%)" in col]
gpu_mem_cols  = [col for col in df.columns if "MemUsed(MB)" in col]

# --- System RAM: convert from MB to GB ---
df["System_RAM_Used_GB"] = df["Used_Mem(MB)"] / 1024.0

# --- GPU memory: sum across all GPUs (MB), then convert to GB ---
df["Total_GPU_MemUsed_MB"] = df[gpu_mem_cols].sum(axis=1)
df["Total_GPU_MemUsed_GB"] = df["Total_GPU_MemUsed_MB"] / 1024.0

# --- Average GPU utilization across all GPU columns ---
df["Avg_GPU_Util(%)"] = df[gpu_util_cols].mean(axis=1)

# Create Plotly traces
trace_ram_used = go.Scatter(
    x=df["Time (min)"],
    y=df["System_RAM_Used_GB"],
    mode="lines",
    name="System RAM Used (GB)"
)

trace_gpu_mem = go.Scatter(
    x=df["Time (min)"],
    y=df["Total_GPU_MemUsed_GB"],
    mode="lines",
    name="Total GPU Mem Used (GB)"
)

trace_gpu_util = go.Scatter(
    x=df["Time (min)"],
    y=df["Avg_GPU_Util(%)"],
    mode="lines",
    name="Avg GPU Util (%)"
)

# Create a figure with a secondary y-axis
fig = make_subplots(specs=[[{"secondary_y": True}]])
# Add both memory traces (RAM + GPU) to the left axis
fig.add_trace(trace_ram_used, secondary_y=False)
fig.add_trace(trace_gpu_mem, secondary_y=False)
# Add GPU utilization to the right axis
fig.add_trace(trace_gpu_util, secondary_y=True)

max_x = df["Time (min)"].max()

fig.add_shape(
    type="line",
    x0=max_x,
    x1=max_x,
    yref="paper",
    y0=0,
    y1=1,
    line=dict(color="lightgray", width=1)
)

# Update layout (title, axis labels) and make background transparent
fig.update_layout(
    title="System & GPU Memory Usage vs. GPU Utilization",
    xaxis_title="Time (min)",
    # Transparent backgrounds
    paper_bgcolor="rgba(0,0,0,0)",  # outer “paper” area
    plot_bgcolor="rgba(0,0,0,0)",   # main plot area
)

fig.update_xaxes(
    showline=True,
    zeroline=True,
    range=[-1, max_x],
    zerolinecolor="lightgray",
    ticklabelposition="outside",  # Add padding to tick labels
    ticks="outside",
    ticklen=5,
    tickcolor="rgba(0, 0, 0, 0)",
    mirror = True
)

# Configure left y-axis for memory
fig.update_yaxes(
    title_text="Memory Used (GB)",
    secondary_y=False,
    range=[-1,101],
    showgrid=True,             # show horizontal grid lines
    gridcolor="lightgray",     # or any color you'd like
    zeroline=True,
    zerolinecolor="lightgray",
    ticklabelposition="outside",  # Add padding to tick labels
    ticks="outside",
    ticklen=5,
    tickcolor="rgba(0, 0, 0, 0)",
    mirror = True
)

# Configure right y-axis for GPU utilization
fig.update_yaxes(
    title_text="GPU Utilization (%)",
    secondary_y=True,
    range=[-1, 101],
    showgrid=True,             # show horizontal grid lines
    gridcolor="lightgray",     # match color from the other axis
    zeroline=True,
    zerolinecolor="lightgray",
    ticklabelposition="outside",  # Add padding to tick labels
    ticks="outside",
    ticklen=5,
    tickcolor="rgba(0, 0, 0, 0)",
    mirror = True
)

# Save the plot as an HTML file
fig.write_html("plot_b32.html")

# Save the plot as an PNG file
fig.write_image("plot_b32.png")

# Display the interactive plot (if running interactively)
fig.show()
