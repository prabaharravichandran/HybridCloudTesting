import glob
import os
import pandas as pd
import plotly.graph_objects as go

# Define the base folder where the CSV files are stored
folder_path = '/fs/phenocart-app/prr000/Projects/Training/4_Output/Sucessful'

# Use '**' for recursive matching of 'system_monitor_log.csv' files
file_list = glob.glob(os.path.join(folder_path, '**', 'system_monitor_log.csv'), recursive=True)

# List to hold each DataFrame
dfs = []

for file in file_list:
    # Extract the parent folder name (e.g., 'compute-g5-12xlarge-b32')
    parent_folder = os.path.basename(os.path.dirname(file))

    # Read the CSV file into a DataFrame
    df = pd.read_csv(file)

    # Add a new column with the parent folder name
    df['ParentFolder'] = parent_folder

    # Append the modified DataFrame to the list
    dfs.append(df)

# Concatenate all DataFrames into one combined DataFrame
combined_df = pd.concat(dfs, ignore_index=True)

# Save the combined DataFrame to a new CSV file
output_file = '/fs/phenocart-app/prr000/Projects/Training/5_Visualization/combined_output.csv'
combined_df.to_csv(output_file, index=False)
print("Combined CSV created successfully at:", output_file)

# -------------------------------------------------
# 1) Calculate Duration in Minutes for Each Partition
# -------------------------------------------------
# Convert the Timestamp column to datetime
combined_df['Timestamp'] = pd.to_datetime(combined_df['Timestamp'])

# Group by ParentFolder and compute the minimum and maximum timestamps
job_times = combined_df.groupby('ParentFolder')['Timestamp'].agg(['min', 'max']).reset_index()

# Calculate the duration (as a timedelta) and convert to seconds
job_times['duration'] = job_times['max'] - job_times['min']
job_times['duration_seconds'] = job_times['duration'].dt.total_seconds()

# Create a DataFrame from job_times
df_durations = pd.DataFrame(job_times)

# Extract GPU type (g5/g6) and batch size from the ParentFolder string
df_durations[['gpu', 'batch_size']] = df_durations['ParentFolder'].str.extract(r'compute-(g\d+)-12xlarge-b(\d+)', expand=True)
df_durations['batch_size'] = df_durations['batch_size'].astype(int)

# Convert duration to minutes
df_durations['duration_minutes'] = df_durations['duration_seconds'] / 60

# Sort by batch size so that the x-axis is in order
df_durations = df_durations.sort_values(by='batch_size')

# Create bar traces using duration in minutes
trace_g5_time = go.Bar(
    x=df_durations[df_durations['gpu'] == 'g5']['batch_size'],
    y=df_durations[df_durations['gpu'] == 'g5']['duration_minutes'],
    name='G5'
)

trace_g6_time = go.Bar(
    x=df_durations[df_durations['gpu'] == 'g6']['batch_size'],
    y=df_durations[df_durations['gpu'] == 'g6']['duration_minutes'],
    name='G6'
)

# Create the figure with grouped bar mode
fig_time = go.Figure(data=[trace_g5_time, trace_g6_time])
fig_time.update_layout(
    xaxis=dict(
        title="Batch Size",
        type='category',
        categoryorder='array',
        categoryarray=[str(b) for b in sorted(df_durations['batch_size'].unique())]
    ),
    yaxis_title="Duration (minutes)",
    barmode="group",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)"
)

# Save the figure as an SVG with transparent background
fig_time.write_image("job_duration_minutes.svg")
fig_time.show()

# -------------------------------------------------
# 2) Calculate and Plot Max VRAM Used in GB
# -------------------------------------------------
# Sum the GPU memory used columns for each row (already in MB)
combined_df['total_gpu_mem'] = (
    combined_df['GPU0_MemUsed(MB)'] +
    combined_df['GPU1_MemUsed(MB)'] +
    combined_df['GPU2_MemUsed(MB)'] +
    combined_df['GPU3_MemUsed(MB)']
)

# For each partition, compute the maximum total GPU memory used (in MB)
max_vram = combined_df.groupby('ParentFolder')['total_gpu_mem'].max().reset_index()

# Extract GPU type (g5/g6) and batch size from the ParentFolder string
max_vram[['gpu', 'batch_size']] = max_vram['ParentFolder'].str.extract(r'compute-(g\d+)-12xlarge-b(\d+)', expand=True)
max_vram['batch_size'] = max_vram['batch_size'].astype(int)

# Convert MB to GB (using 1024 MB = 1 GB)
max_vram['total_gpu_mem_gb'] = max_vram['total_gpu_mem'] / 1024

# Sort by batch size
max_vram = max_vram.sort_values(by='batch_size')

# Create bar traces for VRAM usage in GB
trace_g5_vram = go.Bar(
    x=max_vram[max_vram['gpu'] == 'g5']['batch_size'].astype(str),
    y=max_vram[max_vram['gpu'] == 'g5']['total_gpu_mem_gb'],
    name='G5'
)

trace_g6_vram = go.Bar(
    x=max_vram[max_vram['gpu'] == 'g6']['batch_size'].astype(str),
    y=max_vram[max_vram['gpu'] == 'g6']['total_gpu_mem_gb'],
    name='G6'
)

# Create the figure with grouped bar mode for VRAM usage
fig_vram = go.Figure(data=[trace_g5_vram, trace_g6_vram])
fig_vram.update_layout(
    xaxis=dict(
        title="Batch Size",
        type='category',
        categoryorder='array',
        categoryarray=[str(b) for b in sorted(max_vram['batch_size'].unique())]
    ),
    yaxis_title="Max Total GPU Memory Used (GB)",
    barmode="group",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    width=800,
    height=600
)

# Save the figure as an SVG with transparent background
fig_vram.write_image("max_vram_used_gb.svg")
fig_vram.show()
