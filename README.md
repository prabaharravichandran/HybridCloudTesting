# University of Saskatchewan Field Phenotying System (UFPS) / Phenocart Data Management & Pipeline Development

2024 - 2025 Annual Progress Meeting: https://xd.adobe.com/view/8b5255ab-b37b-4aff-8341-a37f998aab88-de01/?fullscreen

## Creating and building apptainers for testing

Defs, makefile and bash scripts for creating containers are located here /home/prr000/Documents/Projects/Training/2_Containers/
Based on nvidia/cuda:12.5.0-devel-ubuntu22.04 image

--fakeroot --sandbox essential

Build .sifs later, if required

```bash
apptainer build trainingcontainer_v1.sif trainingcontainer_v1_sandbox
```

## MongoDB tools and applications

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

# Restore Mongodump

mongorestore --host localhost --port 27018 --username '<username>' --password '<password>'' --authenticationDatabase admin --db Data4AWS .
