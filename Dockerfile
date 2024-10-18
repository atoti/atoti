# Set explicit platform (for ARM-based Macbooks)
FROM --platform=linux/amd64 python:3.10.13-slim-bookworm

# Copy files to container and set working dir
COPY . /atoti
WORKDIR /atoti

# Install dependencies in container (uv style)
RUN pip install uv && \
    uv sync

# Set container executable
CMD [ "uv", "run", "jupyter-lab", "--ip=0.0.0.0", "--allow-root", "--no-browser" ]
