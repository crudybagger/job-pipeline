#!/usr/bin/env bash

# ================================================================
# Helper script to initialize a local git repository and push it to a
# newly‑created GitHub repository.
#
# Usage:
#   ./scripts/init_git_repo.sh <github-repository-ssh-or-https-url>
#
# Example:
#   ./scripts/init_git_repo.sh git@github.com:username/project.git
#
# This script performs the following steps:
#   1. Initializes a new git repository (if one does not already exist).
#   2. Adds all files to the index and creates an initial commit.
#   3. Sets the default branch to ``main``.
#   4. Adds the remote ``origin`` pointing at the provided URL.
#   5. Pushes the initial commit to the remote repository.
#
# The script is deliberately simple and does not attempt to handle every
# edge‑case (e.g. an existing repository with a remote already configured). It
# is intended for quick boot‑strapping of the project in a clean environment.
# ================================================================

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <github-repo-url>"
    echo "Example: $0 git@github.com:myuser/myrepo.git"
    exit 1
fi

REPO_URL="$1"

# Initialize a git repository if none exists.
if [ ! -d ".git" ]; then
    echo "Initializing a new git repository..."
    git init
else
    echo "Git repository already initialized."
fi

# Stage all files and commit if there are any changes.
git add .
# Only commit if there is something to commit (i.e., the index is not empty).
if ! git diff --cached --quiet; then
    git commit -m "Initial commit"
else
    echo "No changes to commit."
fi

# Set the default branch to main.
git branch -M main

# Add the remote origin if it does not exist.
if git remote get-url origin > /dev/null 2>&1; then
    echo "Remote 'origin' already configured. Updating URL to $REPO_URL"
    git remote set-url origin "$REPO_URL"
else
    git remote add origin "$REPO_URL"
fi

# Push to GitHub.
echo "Pushing to $REPO_URL..."
git push -u origin main

echo "Repository successfully pushed to $REPO_URL"
