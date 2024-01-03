# Set explicit platform for ARM-based Macbooks
FROM --platform=linux/amd64 python:3.10.13-slim-bookworm

# Install dependencies and copy over files to container
RUN apt-get update && \
    apt-get install -y nodejs && \
    pip install atoti \
                atoti-jupyterlab \
                atoti-aws \
                atoti-sql
                # atoti-directquery-bigquery \
                # atoti-directquery-clickhouse \
                # atoti-directquery-databricks \
                # atoti-directquery-mssql \
                # atoti-directquery-redshift \
                # atoti-directquery-snowflake \
                # atoti-directquery-synapse
COPY . /atoti
WORKDIR /atoti

# Set container executable
CMD [ "jupyter-lab", "--ip=0.0.0.0", "--allow-root", "--no-browser" ]