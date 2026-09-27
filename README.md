# Job Finder and Application Pipeline

This repository contains a **modular job‑search pipeline** built with Python and
FastAPI, together with a tiny automation framework that processes a local issue
tracker (`issues.md`).

## Quick start (local development)

```bash
# Create a virtual environment and activate it
python -m venv .venv
source .venv/bin/activate

# Install the project's dependencies
pip install -r job-pipeline/requirements.txt

# Run the FastAPI app (if you want to explore the API)
uvicorn job-pipeline/app.main:app --reload
```

## Running the automation loop

The automation utilities live under `job-pipeline/automation`.  The convenient
namespace package `automation` (see `automation/__init__.py`) makes it possible
to run the loop from the repository root:

```bash
python -m automation.run_issue_loop
```

During the first run you will see the message

```
Skipping git commit/push – not a git repository.
```

that is printed because the repository has not been initialised as a Git repo.
If you want the automation to **commit and push** the generated placeholder
implementation files, you need a Git repository with a remote.

## Initialising a GitHub repository and pushing the code

1. **Create a new repository on GitHub** – go to https://github.com/new and
   choose a name (e.g. `job-pipeline`).  Do **not** initialise it with a README,
   `.gitignore` or license – we will push our existing files.

2. **Run the helper script** that ships with this project (added in this
   commit) to initialise a local Git repository and push it to the remote:

   ```bash
   # Make the script executable (only needed once)
   chmod +x scripts/init_git_repo.sh

   # Replace the URL below with the SSH or HTTPS URL of your new GitHub repo
   ./scripts/init_git_repo.sh git@github.com:YOUR_USERNAME/job-pipeline.git
   ```

   The script will:

   * `git init` the repository (if not already initialised)
   * add all files and create an initial commit
   * set the default branch to `main`
   * add the remote `origin` pointing at the URL you provided
   * push the commit to GitHub

   After a successful push you will see something like:

   ```
   Repository successfully pushed to git@github.com:YOUR_USERNAME/job-pipeline.git
   ```

3. Verify on GitHub that the files have been uploaded and that the repository
   contains a `main` branch.

## Using GitHub Issues instead of the local `issues.md`

The current implementation uses a simple markdown file (`job-pipeline/issues.md`)
as an issue tracker.  This design makes the automation self‑contained and works
without any external service, which is convenient for the kata‑style tests.

If you prefer to use **GitHub Issues**, you will need a GitHub repository –
issues are always associated with a repository.  The automation code would have
to be extended to talk to the GitHub REST or GraphQL API, for example:

* **Listing open issues** – GET `/repos/:owner/:repo/issues?state=open`
* **Creating a comment** – POST `/repos/:owner/:repo/issues/:issue_number/comments`
* **Closing an issue** – PATCH `/repos/:owner/:repo/issues/:issue_number` with
  `{"state": "closed"}`

Authentication is performed with a **personal access token** (PAT) that must be
provided via the `GITHUB_TOKEN` environment variable.  A minimal wrapper could
be added to `job-pipeline/automation/issue_tracker.py` that switches between the
local markdown file and the GitHub API based on the presence of that token.

> **Key point:** *You cannot use GitHub Issues without having a Git repository*
> because the issues are stored on GitHub **per‑repository**.  The automation
> script already expects a `.git` directory for committing changes; after you
> push the repository to GitHub you can safely replace the local issue handling
> with the API‑based approach if desired.

## Contributing

Feel free to open issues or submit pull requests on GitHub.  When contributing
code, make sure the test suite continues to pass:

```bash
pytest -q
```

Happy hacking!
