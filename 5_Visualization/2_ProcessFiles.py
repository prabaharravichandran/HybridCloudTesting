import glob
import os
import pandas as pd
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

# Convert the Timestamp column to datetime in the combined DataFrame
combined_df['Timestamp'] = pd.to_datetime(combined_df['Timestamp'])

# Group by ParentFolder and compute the minimum and maximum timestamps for each group
job_times = combined_df.groupby('ParentFolder')['Timestamp'].agg(['min', 'max']).reset_index()

# Calculate the duration (as a timedelta) and convert it to seconds
job_times['duration'] = job_times['max'] - job_times['min']
job_times['duration_seconds'] = job_times['duration'].dt.total_seconds()

data = job_times

# Create a DataFrame
df = pd.DataFrame(data)

# Extract GPU type (g5/g6) and batch size from the ParentFolder string
df[['gpu', 'batch_size']] = df['ParentFolder'].str.extract(r'compute-(g\d+)-12xlarge-b(\d+)', expand=True)
df['batch_size'] = df['batch_size'].astype(int)

# Get unique batch sizes available in the data
unique_batches = sorted(df['batch_size'].unique())
# Convert them to strings for a categorical axis
unique_batches_str = [str(b) for b in unique_batches]

# Sort by batch size so that the x-axis is in order
df = df.sort_values(by='batch_size')

# Create a trace for each GPU type
trace_g5 = go.Bar(
    x=df[df['gpu'] == 'g5']['batch_size'],
    y=df[df['gpu'] == 'g5']['duration_seconds'],
    name='G5'
)

trace_g6 = go.Bar(
    x=df[df['gpu'] == 'g6']['batch_size'],
    y=df[df['gpu'] == 'g6']['duration_seconds'],
    name='G6'
)

# Create the figure with grouped bar mode
fig = go.Figure(data=[trace_g5, trace_g6])
fig.update_layout(
    xaxis=dict(
        title="Batch Size",
        type='category',  # forces the x-axis to be categorical
        categoryorder='array',
        categoryarray=unique_batches_str  # only these tick labels will be used
    ),
    yaxis_title="Duration (seconds)",
    barmode="group",
    plot_bgcolor="rgba(0,0,0,0)",   # Transparent plot background
    paper_bgcolor="rgba(0,0,0,0)"    # Transparent overall background
)

# Save the figure as a PNG with transparent background (requires kaleido)
fig.write_image("job_duration.svg")

# Sum the GPU memory used columns for each row. Column names must match your CSV.
combined_df['total_gpu_mem'] = (combined_df['GPU0_MemUsed(MB)'] +
                                combined_df['GPU1_MemUsed(MB)'] +
                                combined_df['GPU2_MemUsed(MB)'] +
                                combined_df['GPU3_MemUsed(MB)'])

# For each partition, compute the maximum total GPU memory used during the run
max_vram = combined_df.groupby('ParentFolder')['total_gpu_mem'].max().reset_index()

# Extract GPU type (g5 or g6) and batch size from the ParentFolder string
max_vram[['gpu', 'batch_size']] = max_vram['ParentFolder'].str.extract(r'compute-(g\d+)-12xlarge-b(\d+)', expand=True)
max_vram['batch_size'] = max_vram['batch_size'].astype(int)

# For the x-axis, we can use the batch size; here we use only the unique values available in the data.
expected_batch_sizes = sorted(max_vram['batch_size'].unique())
expected_batch_sizes_str = [str(b) for b in expected_batch_sizes]

# Create a trace for each GPU type
trace_g5 = go.Bar(
    x=max_vram[max_vram['gpu'] == 'g5']['batch_size'].astype(str),
    y=max_vram[max_vram['gpu'] == 'g5']['total_gpu_mem'],
    name='G5'
)
trace_g6 = go.Bar(
    x=max_vram[max_vram['gpu'] == 'g6']['batch_size'].astype(str),
    y=max_vram[max_vram['gpu'] == 'g6']['total_gpu_mem'],
    name='G6'
)

# Create the figure with grouped bar mode
fig = go.Figure(data=[trace_g5, trace_g6])
fig.update_layout(
    xaxis=dict(
        title="Batch Size",
        type='category',  # force x-axis to be categorical
        categoryorder='array',
        categoryarray=expected_batch_sizes_str
    ),
    yaxis_title="Max Total GPU Memory Used (MB)",
    barmode="group",
    plot_bgcolor="rgba(0,0,0,0)",   # Transparent plot background
    paper_bgcolor="rgba(0,0,0,0)",    # Transparent overall background
    width=800,    # Set figure width in pixels
    height=600    # Set figure height in pixels
)

# Save the figure as a PNG with transparent background (requires kaleido)
fig.write_image("max_vram_used.svg")