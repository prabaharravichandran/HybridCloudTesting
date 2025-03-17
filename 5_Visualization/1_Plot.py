import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Read the CSV file (adjust the filename if needed)
df = pd.read_csv("/4_Output/compute-g6-12xlarge_b32/system_monitor_log-g6-12xlarge.csv")

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

# Convert the Timestamp column to datetime and compute elapsed minutes
df['Timestamp'] = pd.to_datetime(df['Timestamp'])
start_time = df['Timestamp'].min()
df['Time (min)'] = (df['Timestamp'] - start_time).dt.total_seconds() / 60

# Dynamically detect GPU utilization and memory used columns
gpu_util_cols = [col for col in df.columns if col.startswith("GPU") and "Utilization" in col and "Average" not in col]
gpu_mem_cols = [col for col in df.columns if col.startswith("GPU") and "Memory Used" in col and "Average" not in col]

# Compute dynamic averages
df['Computed Average GPU Utilization'] = df[gpu_util_cols].mean(axis=1)
df['Computed Average GPU Memused'] = df[gpu_mem_cols].mean(axis=1)

# Create Plotly traces
trace_memory = go.Scatter(
    x=df["Time (min)"],
    y=df["Used Memory (MB)"],
    mode="lines",
    name="Used Memory (MB)"
)

trace_gpu_memused = go.Scatter(
    x=df["Time (min)"],
    y=df["Computed Average GPU Memused"],
    mode="lines",
    name="Computed Average GPU Memused"
)

trace_gpu_util = go.Scatter(
    x=df["Time (min)"],
    y=df["Computed Average GPU Utilization"],
    mode="lines",
    name="Computed Average GPU Utilization"
)

# Create a figure with a secondary y-axis
fig = make_subplots(specs=[[{"secondary_y": True}]])

# Add traces to the figure
fig.add_trace(trace_memory, secondary_y=False)
fig.add_trace(trace_gpu_memused, secondary_y=False)
fig.add_trace(trace_gpu_util, secondary_y=True)

# Update layout and axis labels
fig.update_layout(
    title="System Metrics Over Time",
    xaxis_title="Time (min)"
)
fig.update_yaxes(title_text="Memory (MB)", secondary_y=False)
fig.update_yaxes(title_text="Utilization (%)", secondary_y=True, range=[0, 100])

# Save the plot as an HTML file
fig.write_html("plot.html")

# Display the interactive plot
fig.show()
