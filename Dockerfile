FROM python:3.10-slim-bookworm
RUN pip install pip install atoti atoti-jupyterlab atoti-aws atoti-sql
COPY . /
WORKDIR /atoti
RUN [ "jupyter-lab", "--ip 0.0.0.0"]