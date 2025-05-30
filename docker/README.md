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

Run the following commands at the root of the repository for the given Dockerfile:

`Dockerfile`

> **Note:** You must enable [host network mode](https://docs.docker.com/engine/network/drivers/host/#docker-desktop).

```bash
docker build -f docker/Dockerfile -t atoti/notebooks .
docker run -it --rm -v "$PWD":/atoti --net=host atoti/notebooks
```

`Dockerfile.playwright`

```bash
docker build -f docker/Dockerfile.playwright -t atoti/playwright .
docker run -it --rm -v "$PWD":/atoti atoti/playwright
```
