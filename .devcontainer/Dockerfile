# Set explicit platform for ARM-based Macbooks
FROM --platform=linux/amd64 python:3.10.13-slim-bookworm

# Install dependencies in container (pip style)
RUN apt-get update && \
    apt-get install -y nodejs graphviz && \
    pip install atoti \
                atoti-jupyterlab \
                atoti-aws \
                atoti-sql \
                jupyter-server-proxy
                # atoti-directquery-bigquery \
                # atoti-directquery-clickhouse \
                # atoti-directquery-databricks \
                # atoti-directquery-mssql \
                # atoti-directquery-redshift \
                # atoti-directquery-snowflake \
                # atoti-directquery-synapse

# Copy files to container and set working dir
COPY . /atoti
WORKDIR /atoti

# Install dependencies in container (poetry style)
# RUN pip install poetry && \
#     poetry config virtualenvs.create false && \
#     poetry install

# Set container executable
CMD [ "jupyter-lab", "--ip=0.0.0.0", "--allow-root", "--no-browser" ]
