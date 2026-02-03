# CODA

CODA is a software to manage funding requests for open access fees.
For a full documentation visit: [https://coda-oa.github.io/coda/](https://coda-oa.github.io/coda/)

## Development

We provide a Docker Compose and devcontainer configuration to develop CODA in a Docker environment. Using an editor or IDE with devcontainer support (like VS Code or PyCharm) should be enough to get started. All necessary dependencies will be installed in the devcontainer.
When launching the devcontainer, CODA will automatically be started at `localhost:8000`

### Project management

CODA uses `pdm` to manage the project and its dependencies. See [pdm's documentation](https://pdm-project.org/en/stable/) for more details.

### Pre-Commit Configuration

CODA uses a rather strict `pre-commit` configuration, a tool that runs checks on the code base before allowing a git commit to be persisted.

1. `mypy`: We run `mypy` in strict mode to ensure that everything in the code base is properly typed.

2. `ruff`: Ruff is used for both linting and code formatting to ensure proper coding style and uniform code appearance. Ruff is significantly faster than traditional tools while maintaining Black-compatible formatting.

3. `djlint`: `djlint` is used to check Django templates for proper code style and formatting.

4. `commitizen`: `commitizen` is a tool to enforce [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/).

#### Code Formatting and Linting

To format your code locally:

```bash
# Format code with Ruff
pdm run format

# Check if code is properly formatted
pdm run format-check

# Check linting
pdm run lint

# Auto-fix linting issues (where possible)
pdm run lint-fix
```

The pre-commit hooks will automatically run these checks before each commit. To run all pre-commit hooks manually:

```bash
pre-commit run --all-files
```

#### Committing

As we use `commitizen` to ensure correct commit formatting, we recommend using its commandline tool to generate the commit message.

```
pdm run cz commit
```

## Deployment

CODA provides a Docker Compose configuration to launch the application in production mode.
For this, additional environment variables must be provided in `.envs/.production/django.env` and `.envs/.production/postgres.env`.

To launch the project, run:

```
./commands/start-coda.sh --production
```
