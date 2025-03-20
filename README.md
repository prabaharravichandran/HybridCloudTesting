# Testing hybrid cloud with phenomics data from UGVs

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

We test a hybrid cloud architecture for processing and analyzing phenomics data collected from UFPS uncrewed ground vehicles (UGVs). It combines containerized applications—built using Apptainer based on an NVIDIA CUDA development image—with a MongoDB-based data pipeline for filtering, transferring, and restoring data. In addition, the system leverages AWS HPC clusters managed by SLURM, using specialized GPU-enabled nodes.

<div align="center">
  <img src="https://prabahar.s3.ca-central-1.amazonaws.com/static/articles/Phenocart.jpg" alt="Phenocart" width="3000">
  <p><i>Figure 1: UFPS that includes RTK base station and wheeled robot controlled by remote controller.</i></p>
</div>

## Creating and building apptainers for testing

Defs, makefile and bash scripts for creating containers are located here, 2_Containers/

Based on ubuntu24.04 image; we'll install nvidia-cuda-tool, mongodb, python 2.18, tensorflow 2.18 along with all the other dependencies.

for mongodb, opencv(need some dependencies when installed over ubuntu 24.04), and nvidia toolkit
```text
apt-get install gnupg curl
curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | \
   gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg \
   --dearmor
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-8.0.list
apt-get update
apt-get install -y mongodb-org

for opencv
apt-get update
apt-get install -y libgl1-mesa-glx

wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update

apt install nvidia-cuda-toolkit
```

--sandbox essential

Build .sifs later, if required

```bash
apptainer build trainingcontainer.sif trainingcontainer_sandbox
```

## MongoDB tools and applications

### Preparing a new filtered DB
Check out...
```
/home/prr000/Documents/Projects/Training/3_MongoDB/PrepareDB4Dump.py
```

### Preparing mongodump
Mongodump is not working as expected. 

```bash
mongodump \
  --host localhost \
  --port 27018 \
  --db Data4AWS \
  --username 'username' \
  --password 'password' \
  --authenticationDatabase admin
```
archive dump # not required, but still
```bash
tar -xzvf dump.tar.gz dump
```
transfer dump
```
rsync --recursive --progress --stats --checksum -e "ssh -i /home/prr000/.ssh/hybridcloud2025_GPSC" dump/ 3.98.237.27:/fs/phenocart-work/prr000/dump
rsync --progress --stats --checksum -e "ssh -i /home/prr000/.ssh/hybridcloud2025_GPSC" ExtractedData.tar.gz 3.98.237.27:/fs/phenocart-work/prr000
```
extract dump
```bash
tar -tzvf dump.tar.gz
```
restore dump/db
```bash
mongorestore --port 27018 -u "username" -p "password" --authenticationDatabase "admin" ~/Desktop/dump
```

```bash
export PATH="/fs/phenocart-app/prr000/MongoDB/Compass/bin:$PATH"
export PATH="/fs/phenocart-app/prr000/MongoDB/Daemon/usr/bin:$PATH"
export PATH="/fs/phenocart-app/prr000/MongoDB/Shell/usr/bin:$PATH"
export PATH="/fs/phenocart-app/prr000/MongoDB/Tools/bin:$PATH"
export PATH="/fs/phenocart-app/prr000/PyCharm/bin:$PATH"
```

## Start MongoDB

```bash
# for testing
mongod --dbpath /mnt/phenocart-work/prr000/MongoDBData/Data --logpath ~/mongo.log --fork

# If everything is good, write a config
mongod --fork --config /home/prr000/mongod.config
```

## Bind data to apptainer for MongoDB

```bash
apptainer shell --bind /fs:/mnt trainingcontainer_sandbox
```
To contain everything to the sandbox or .sif

```bash
cd /home/prr000/Documents/Projects/Training/2_Containers
apptainer shell \
   --nv \
   --fakeroot \
   --bind /fs:/mnt \
   --contain \
   --no-home \
   trainingcontainer_sandbox/
```

## Mongorestore

```bash
mongorestore --host localhost --port 27018 --username '<username>' --password '<password>'' --authenticationDatabase admin --db Data4AWS .
```

# Working with SLURM

```bash
#Interactive session
srun -p <partition> --pty bash -i

#Submit job
sbatch -p <partition> <jobscript>

# list partition - Check instances.sinfo
sinfo 
```
# Plots comparing G5 (4 x NVIDIA A10) & G6 (4 x NVIDIA L4), each has 24GB VRAM

<figure style="text-align: center;">
  <img src="https://prabahar.s3.ca-central-1.amazonaws.com/static/articles/HC_job_duration.svg" alt="Plot description" style="display: block; margin: auto;">
  <figcaption>Figure 2:  Comparison of job completion times on G5 and G6 instances across varying batch sizes.</figcaption>
</figure>

<figure style="text-align: center;">
  <img src="https://prabahar.s3.ca-central-1.amazonaws.com/static/articles/HC_max_vram_used.svg" alt="Plot description" style="display: block; margin: auto;">
  <figcaption>Figure 3: Comparison of total VRAM utilization on G5 and G6 instances across varying batch sizes.</figcaption>
</figure>

# Compute Node Specifications

| Partition               | Instance Type  | vCPUs | Memory  | GPU                                    | Storage  | Networking   | Use Cases |
|-------------------------|---------------|-------|---------|----------------------------------------|----------|-------------|-----------|
| compute-g5-xlarge      | g5.xlarge      | 4     | 16 GiB  | 1 NVIDIA A10G (24 GiB)                 | EBS-only | Up to 10 Gbps | ML Inference, Graphics |
| compute-g6-xlarge      | g6.xlarge      | 4     | 16 GiB  | 1 NVIDIA A10G (24 GiB)                 | EBS-only | Up to 10 Gbps | ML Inference, Graphics |
| compute-m6i-large      | m6i.large      | 2     | 8 GiB   | None                                   | EBS-only | Up to 12.5 Gbps | General-purpose |
| compute-t3-2xlarge     | t3.2xlarge     | 8     | 32 GiB  | None                                   | EBS-only | Up to 5 Gbps | Burstable Performance |
| compute-t3-large       | t3.large       | 2     | 8 GiB   | None                                   | EBS-only | Up to 5 Gbps | Burstable Performance |
| compute-t3-xlarge      | t3.xlarge      | 4     | 16 GiB  | None                                   | EBS-only | Up to 5 Gbps | Burstable Performance |
| scompute-g5-xlarge     | g5.xlarge      | 4     | 16 GiB  | 1 NVIDIA A10G (24 GiB)                 | EBS-only | Up to 10 Gbps | ML Inference, Graphics |
| scompute-g6-xlarge     | g6.xlarge      | 4     | 16 GiB  | 1 NVIDIA A10G (24 GiB)                 | EBS-only | Up to 10 Gbps | ML Inference, Graphics |
| scompute-m6i-large     | m6i.large      | 2     | 8 GiB   | None                                   | EBS-only | Up to 12.5 Gbps | General-purpose |
| scompute-t3-2xlarge    | t3.2xlarge     | 8     | 32 GiB  | None                                   | EBS-only | Up to 5 Gbps | Burstable Performance |
| scompute-t3-large      | t3.large       | 2     | 8 GiB   | None                                   | EBS-only | Up to 5 Gbps | Burstable Performance |
| scompute-t3-xlarge     | t3.xlarge      | 4     | 16 GiB  | None                                   | EBS-only | Up to 5 Gbps | Burstable Performance |