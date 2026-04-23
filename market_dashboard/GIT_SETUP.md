# Pushing this to your Git

I (the Claude in this chat) cannot push directly to your repository — I'm in a sandboxed environment without network access to GitHub/GitLab and without your credentials. But you have Claude Code on your laptop, and Claude Code *can* do this for you with full access to your local git config.

## Option 1: Hand it to Claude Code (recommended, easiest)

After you download and unzip the project on your laptop, open a terminal in the project folder and run:

```
claude
```

(or `claude-code` depending on your install). Then paste this prompt:

> I have a Python project in this folder called market_dashboard. Please:
> 1. Initialize a git repository here if one doesn't exist
> 2. Verify .gitignore is set up so .env, cached data, and output HTML are not tracked
> 3. Make an initial commit with message "Initial commit: market stress dashboard"
> 4. Create a new GitHub repo called "market-dashboard" (private) under my account using the GitHub CLI
> 5. Push the initial commit to that new repo
> 6. Verify the .env file is NOT in the remote
>
> If you don't have GitHub CLI configured, ask me before installing it. If I already have a remote in mind, ask me for the URL instead of creating a new repo.

Claude Code will walk you through any setup it needs (mostly: confirming your GitHub CLI is authenticated). It can make the repo, push, and verify in one go.

## Option 2: Push manually

If you'd rather not delegate, here are the commands. Run these in the project folder.

### First-time setup

```bash
cd path/to/market_dashboard

# Initialize repo
git init -b main

# Verify .gitignore is in place (it should already be from the zip)
cat .gitignore

# Stage everything except gitignored files
git add .

# Sanity check — make sure .env is NOT in the list
git status

# Commit
git commit -m "Initial commit: market stress dashboard"
```

### Push to GitHub (if you have the gh CLI)

```bash
gh repo create market-dashboard --private --source=. --remote=origin --push
```

### Push to GitHub (if you don't have gh CLI)

1. Create the empty repo on GitHub.com manually (no README, no .gitignore — keep it empty)
2. Then in your terminal:

```bash
git remote add origin git@github.com:YOUR_USERNAME/market-dashboard.git
git push -u origin main
```

### Push to GitLab / Bitbucket / self-hosted

Same flow — create empty repo on the remote, then `git remote add origin <url>` and `git push -u origin main`.

## Critical safety check

**Before any push, verify your `.env` is not being tracked:**

```bash
git status                  # .env should NOT appear in the list
git ls-files | grep .env   # should output nothing, or only .env.example
```

If `.env` ever does get committed by accident, treat any keys in it as compromised — rotate them immediately at FRED, Anthropic, etc. The `.gitignore` in this project should prevent this, but always double-check on initial push.

## Ongoing workflow

Once pushed, normal git workflow:

```bash
# Daily: pull latest if working across machines
git pull

# Made changes to weights.yaml or thresholds.yaml?
git add config/
git commit -m "Tune microstructure weight"
git push

# Don't commit data/ — it's local cache, refreshed on each run
```

## What's safe to commit

- All `.py` files in `src/` and `run_dashboard.py`
- `config/weights.yaml` and `config/thresholds.yaml` (your model)
- `requirements.txt`, `README.md`, `.env.example`, `.gitignore`, `GIT_SETUP.md`

## What's NOT safe to commit (gitignore handles these)

- `.env` — your API keys
- `data/*.json` — cached data, manual overrides (may contain notes you don't want public), alert state
- `data/history.csv` — your composite history (might be sensitive depending on your view of that)
- `output/dashboard.html` — regenerated every run
- `__pycache__/` — Python compiled bytecode
