<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://data.atoti.io/notebooks/banners/Atoti_Logo_White-01.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://data.atoti.io/notebooks/banners/Atoti_Logo_Purple-01.svg">
    <img alt="atoti-logo" width="50%">
  </picture>
</p>

<p align="center">
  <img src="https://img.shields.io/github/v/release/atoti/atoti?color=#4cc71f" alt="github">
  <img src="https://img.shields.io/pypi/dm/atoti" alt="github">
  <img src="https://github.com/atoti/atoti/actions/workflows/test.yaml/badge.svg" alt="gha">
  <a href="https://github.com/atoti/atoti/discussions"><img src="https://img.shields.io/github/discussions/atoti/atoti" alt="GitHub Discussion"></a>
</p>

<p align="center">
  <a href="https://www.linkedin.com/company/activeviam/"><img src="https://img.shields.io/badge/linkedin-%230077B5.svg?style=for-the-badge&logo=linkedin&logoColor=white" alt="linkedin"></a>
</p>

## Building and running with Docker

[Docker](https://www.docker.com/) is a platform for packaging and running applications in lightweight, portable execution environments known as containers. Containers bundle application code together with its dependencies so that an application runs identically on any machine that has Docker installed. A [Dockerfile](https://docs.docker.com/reference/dockerfile/) is text-based “recipe” that tells Docker how to build an image. Docker images are the static, read-only snapshot of a filesystem/environment, while a container is a running instance of a particular image.

## Atoti Docker images

The following Dockerfiles each build a Docker image containing all Atoti notebooks and their dependencies for various use cases.

[Dockerfile](Dockerfile)

When built and run, `jupyterlab` will automatically start from within the container, supplying the necessary environment for a user to explore and execute notebooks in the repository.

> **Note:** You must enable [host network mode](https://docs.docker.com/engine/network/drivers/host/#docker-desktop).

```bash
docker build -f docker/Dockerfile -t atoti/notebooks .
docker run -it --rm -v "$PWD":/atoti --net=host atoti/notebooks
```

[Dockerfile.playwright](Dockerfile.playwright)

When built and run, `jupyterlab` starts up along with `playwright` to automate execution of targeted notebooks from with JupyterLab and render web-based JupyterLab widgets.

```bash
docker build -f docker/Dockerfile.playwright -t atoti/playwright .
docker run -it --rm -v "$PWD":/atoti atoti/playwright
```
