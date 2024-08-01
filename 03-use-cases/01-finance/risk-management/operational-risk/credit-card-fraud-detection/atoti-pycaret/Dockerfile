# Set explicit platform (for ARM-based Macbooks)
FROM --platform=linux/amd64 python:3.8-slim-bookworm

# Copy files to container and set working dir
COPY . /atoti-pycaret
WORKDIR /atoti-pycaret

# Install dependencies in container (apt-get style)
RUN apt-get update && \
    apt-get install -y libgomp1

# Install dependencies in container (poetry style)
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install

# Set container executable
CMD [ "poetry", "run", "python", "./automl/prediction.py" ]