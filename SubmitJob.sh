#!/bin/bash -l

cd /fs/phenocart-app/prr000/Projects/Training/2_Containers
apptainer exec \
   --nv \
   --fakeroot \
   --bind /fs:/mnt \
   --contain \
   --no-home \
   trainingcontainer_sandbox/ \
   bash -c ". /home/venv/bin/activate && python /home/ubuntu/scripts/yestimation.py"
