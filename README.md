# CODA

CODA is a software to manage funding requests for open access fees.
It is still very early in development and should not be used in production and there will be breaking changes frequently.

## Development

We provide a Docker Compose and devcontainer configuration to develop CODA in a Docker environment. Using an editor or IDE with devcontainer support (like VS Code or PyCharm) should be enough to get started. All necessary dependencies will be installed in the devcontainer.
When launching the devcontainer, CODA will automatically be started at `localhost:8000`

### Project management

CODA uses `pdm` to manage the project and its dependencies. See [pdm's documentation](https://pdm-project.org/en/stable/) for more details.


### Pre-Commit Configuration

CODA uses a rather strict `pre-commit` configuration, a tool that runs checks on the code base before allowing a git commit to be persisted.

1. `mypy`:
we run `mypy` in strict mode to ensure that everything in the code base is properly typed.

2. `ruff`: ruff is a linter used to ensure proper coding style.

3. `black`: we use black as a code formatter to ensure that all code looks uniform.

4. `djlint`: in strict mode to ensure that everything in the code base is properly typed.

2. `ruff`: ruff is a linter used to ensure proper coding style.

3. `black`: we use black as a code formatter to ensure that all code looks uniform.

4. `djlint`: `djlint` is used to check django templates for proper code style.

5. `commitizen`:  is used to check django templates for proper code style.

5. `commitizen`: `commitizen` is a tool to enforce [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/)

#### Committing

As we use `commitizen` to ensure correct commit formatting, we recommend using its commandline tool to generate the commit message.

```
pdm run cz commit
```

## Deployment

CODA provides a Docker Compose configuration to launch the application in productio mode.
For this, additional environment variables must be provided in `.envs/.production/django.env` and `.envs/.production/postgres.env`.

To launch the project, run:
```
make up
```
