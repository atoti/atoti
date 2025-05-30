# Set explicit platform (to account for ARM-based Macbooks)
FROM --platform=linux/amd64 python:3.10.13-slim-bookworm

# Install system and dependencies
RUN apt-get update \
 && apt-get install -y \
      git \
      git-lfs \
      debian-archive-keyring \
      build-essential \
      ca-certificates \
 && pip install uv \   
 && rm -rf /var/lib/apt/lists/*
   
# Copy files to container and set working dir
COPY . /atoti
WORKDIR /atoti

# Install uv/python dependencies
RUN uv sync

# Set container executable
CMD [ "uv", "run", "jupyter-lab", "--ip=0.0.0.0", "--allow-root", "--no-browser", "--NotebookApp.token=''", "--NotebookApp.password=''" ]
