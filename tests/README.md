<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://data.atoti.io/notebooks/banners/Atoti_Logo_White-01.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://data.atoti.io/notebooks/banners/Atoti_Logo_Purple-01.svg">
    <img alt="atoti-logo" width="50%">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/atoti/atoti/releases/latest"><img src="https://img.shields.io/github/v/release/atoti/atoti?color=#4cc71f" alt="github"></a>
  <a href="https://pypistats.org/packages/atoti"><img src="https://img.shields.io/pypi/dm/atoti" alt="github"></a>
  <a href="https://github.com/atoti/atoti/actions/workflows/test.yaml"><img src="https://github.com/atoti/atoti/actions/workflows/test.yaml/badge.svg" alt="gha"></a>
  <a href="https://github.com/atoti/atoti/discussions"><img src="https://img.shields.io/github/discussions/atoti/atoti" alt="GitHub Discussion"></a>
</p> 

<p align="center">
  <a href="https://www.linkedin.com/company/activeviam/"><img src="https://img.shields.io/badge/linkedin-%230077B5.svg?style=for-the-badge&logo=linkedin&logoColor=white" alt="linkedin"></a>
</p>

## Testing

Run the following `make` rules at the root of the repository:

`make test`

Tests notebooks using [pytest](https://docs.pytest.org/en/stable/) and [nbmake](https://github.com/treebeardtech/nbmake) to test code cells with a specified version of `atoti` in `pyproject.toml`. Formatted results are outputted to `./reports`.

`make render`

Automates web browser execution using `jupyterlab` and `playwright` to generate and embed images of Atoti-specific JupyterLab widgets and data model visualizations within notebooks.

`make upgrade`

Combines the `make test` and `make render` rules to comprehensively test notebook code cells and render JupyterLab widgets.