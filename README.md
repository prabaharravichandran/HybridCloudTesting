# University of Saskatchewan Field Phenotying System (UFPS) / Phenocart Data Management & Pipeline Development

2024 - 2025 Annual Progress Meeting: https://xd.adobe.com/view/8b5255ab-b37b-4aff-8341-a37f998aab88-de01/?fullscreen

<img src="https://prabahar.s3.ca-central-1.amazonaws.com/static/articles/Phenocart.jpg" alt="Phenocart" width="3000">

## Creating and building apptainers for testing

Defs, makefile and bash scripts for creating containers are located here /home/prr000/Documents/Projects/Training/2_Containers/
Based on nvidia/cuda:12.5.0-devel-ubuntu22.04 image

--fakeroot --sandbox essential

Build .sifs later, if required

```bash
apptainer build trainingcontainer_v1.sif trainingcontainer_v1_sandbox
```

## MongoDB tools and applications

### Preparing a new filtered DB
Check out...
```
/home/prr000/Documents/Projects/Training/3_MongoDB/PrepareDB4Dump.py
```

### Preparing mongodump

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
export PATH="/home/prr000/Documents/MongoDB/Compass/bin:$PATH"
export PATH="/home/prr000/Documents/MongoDB/Daemon/usr/bin:$PATH"
export PATH="/home/prr000/Documents/MongoDB/Shell/usr/bin:$PATH"
export PATH="/home/prr000/Documents/MongoDB/Tools/bin:$PATH"
```

## Start MongoDB

```bash
mongod --fork --config /home/prr000/mongod.config
```

## Bind data to apptainer for MongoDB

```bash
apptainer shell --bind /fs/phenocart-work/prr000/MongoDBData/Data:/mnt/mongodb trainingcontainer_v1_sandbox
```
To contain everything to the sandbox or .sif

```bash
apptainer shell \
  --writable \
  --bind /fs/phenocart-work/prr000/MongoDBData/Data:/mnt/mongodb \
  --contain \
  --no-home \
  trainingcontainer_v1_sandbox
```

## Mongorestore

```bash
mongorestore --host localhost --port 27018 --username '<username>' --password '<password>'' --authenticationDatabase admin --db Data4AWS .
```

# Working with SLURM

```bash
srun -p compute-g5-xlarge --pty bash -i
sbatch -p <partition> <jobscript>

# list partition - Check instances.sinfo
sinfo 
```
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





