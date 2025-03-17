#!/bin/bash

OUTPUT_FILE="/mnt/phenocart-app/prr000/Projects/Training/4_Output/system_monitor_log.csv"

# Number of samples (1 per second) for a 5-second average
NUM_SAMPLES=5

# Write CSV header if the file doesn't exist
if [[ ! -f "$OUTPUT_FILE" ]]; then
    # Basic header for memory
    echo -n "Timestamp,Used_Mem(MB),Avail_Mem(MB)" > "$OUTPUT_FILE"

    # Check if nvidia-smi is available
    if command -v nvidia-smi &> /dev/null; then
        # Determine the number of GPUs
        NUM_GPUS=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
        # Add columns for each GPU
        for ((i=0; i<NUM_GPUS; i++)); do
            echo -n ",GPU${i}_Util(%),GPU${i}_MemUsed(MB),GPU${i}_MemFree(MB)" >> "$OUTPUT_FILE"
        done
    fi

    echo "" >> "$OUTPUT_FILE"
fi

echo "5-second average system monitoring started. Logging to $OUTPUT_FILE ..."
echo "Press Ctrl + C to stop."

while true; do

    # Accumulators for system memory
    SUM_USED_MEM=0
    SUM_AVAIL_MEM=0

    # GPU accumulators (if nvidia-smi is available)
    declare -A SUM_GPU_UTIL
    declare -A SUM_GPU_USED
    declare -A SUM_GPU_FREE

    if command -v nvidia-smi &> /dev/null; then
        NUM_GPUS=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
        # Initialize accumulators to 0
        for ((i=0; i<NUM_GPUS; i++)); do
            SUM_GPU_UTIL[$i]=0
            SUM_GPU_USED[$i]=0
            SUM_GPU_FREE[$i]=0
        done
    fi

    # Collect data for NUM_SAMPLES (one sample per second)
    for ((s=1; s<=NUM_SAMPLES; s++)); do
        # Capture system memory usage (MB)
        USED_MEM=$(free -m | awk '/Mem:/ {print $3}')
        AVAIL_MEM=$(free -m | awk '/Mem:/ {print $7}')
        SUM_USED_MEM=$((SUM_USED_MEM + USED_MEM))
        SUM_AVAIL_MEM=$((SUM_AVAIL_MEM + AVAIL_MEM))

        # Capture GPU stats if nvidia-smi is available
        if command -v nvidia-smi &> /dev/null; then
            # Query: index, util.gpu, memory.used, memory.free
            while IFS=, read -r idx gpu_util mem_used mem_free; do
                idx=$(echo "$idx" | tr -d ' ')
                gpu_util=$(echo "$gpu_util" | tr -d ' ')
                mem_used=$(echo "$mem_used" | tr -d ' ')
                mem_free=$(echo "$mem_free" | tr -d ' ')

                # Accumulate values
                SUM_GPU_UTIL[$idx]=$(( ${SUM_GPU_UTIL[$idx]} + gpu_util ))
                SUM_GPU_USED[$idx]=$(( ${SUM_GPU_USED[$idx]} + mem_used ))
                SUM_GPU_FREE[$idx]=$(( ${SUM_GPU_FREE[$idx]} + mem_free ))
            done < <(nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.free --format=csv,noheader,nounits)
        fi

        # Sleep 1 second before next sample
        sleep 1
    done

    # Calculate averages
    AVG_USED_MEM=$((SUM_USED_MEM / NUM_SAMPLES))
    AVG_AVAIL_MEM=$((SUM_AVAIL_MEM / NUM_SAMPLES))

    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

    # Write system memory data
    echo -n "$TIMESTAMP,$AVG_USED_MEM,$AVG_AVAIL_MEM" >> "$OUTPUT_FILE"

    # Write GPU data (averages)
    if command -v nvidia-smi &> /dev/null; then
        for ((i=0; i<NUM_GPUS; i++)); do
            AVG_GPU_UTIL=$(( ${SUM_GPU_UTIL[$i]} / NUM_SAMPLES ))
            AVG_GPU_USED=$(( ${SUM_GPU_USED[$i]} / NUM_SAMPLES ))
            AVG_GPU_FREE=$(( ${SUM_GPU_FREE[$i]} / NUM_SAMPLES ))
            echo -n ",$AVG_GPU_UTIL,$AVG_GPU_USED,$AVG_GPU_FREE" >> "$OUTPUT_FILE"
        done
    fi

    echo "" >> "$OUTPUT_FILE"

    # Print a quick status to console
    echo "[$TIMESTAMP] RAM Used: ${AVG_USED_MEM}MB | RAM Avail: ${AVG_AVAIL_MEM}MB"
done
