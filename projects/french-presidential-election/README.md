# Atoti Project Adaptation

This project shows how we can translate the Atoti notebook - [French presidential election 2022](https://github.com/atoti/atoti/tree/main/notebooks/01-use-cases/other-industries/french-presidential-election) - into an actual project, ready for deployment into Heroku.  

The current build is based on [Atoti v0.8.2](https://docs.atoti.io/latest/releases/0.8.2.html).

It is adapted from the [Atoti project template](https://github.com/atoti/project-template).

On top of the `atoti` package, it comes with:

- Dependency management with [Poetry](https://python-poetry.org/)
- Settings management with [Pydantic](https://docs.pydantic.dev/latest/usage/settings)
- Testing with [pytest](https://docs.pytest.org/)
- Type checking with [mypy](http://mypy-lang.org/)
- Formatting with [Black](https://black.readthedocs.io/) and [isort](https://pycqa.github.io/isort/)
- Linting with [Ruff](https://beta.ruff.rs)


## Usage

### Installation

- [Install `poetry`](https://python-poetry.org/docs/#installation)
- Install the dependencies:

  ```bash
  poetry install
  ```

### Commands

To get a list of the commands that can be executed to interact with the project, run:

```bash
poetry run app --help
```

A few examples:

- Start the app:

  ```bash
  poetry run app start
  ```

- Reformat the code:

  ```bash
  poetry run app format
  ```

## Atoti

This version includes authentication which requires [the locked version](https://docs.atoti.io/latest/how_tos/unlock_all_features.html) of Atoti.  
Authentication is required in order to control access to the web application and prevent overwriting of dashboards by unauthorised personnel.  
Refer to [create_users.py](app/create_users.py) for the authorised users and their access rights.

You can [register online for an evaluation license](https://atoti.io/evaluation-license-request/) and check out how to [unlock all features of Atoti](https://docs.atoti.io/latest/how_tos/unlock_all_features.html).
  
  
### Required environment variables

- `ATOTI_LICENSE`: contains the Base64 encoded content of your license key file that is required to start the application.

Refer to Atoti documentation on [how to set up the license key](https://docs.atoti.io/latest/how_tos/unlock_all_features.html#Setting-up-the-license-key).  


## Deploy to Heroku

This project also includes [the modifications](https://github.com/atoti/project-template/compare/deploy-to-heroku) required to deploy it to Heroku.

Click on the button below to deploy this project to Heroku:

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

_Note_: to deploy a project started from this template, remember to change the `repository` value in [app.json](app.json).
