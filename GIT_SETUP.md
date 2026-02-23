# PDF Poly Lingo – Git Setup & Revert Instructions

**Done:** The incorrect `origin` remote (py-poc) has been removed.

---

## 1. Reverting the mistaken remote add and push

**Already done:** The wrong remote was removed. If you had pushed pdf-poly-lingo into py-poc:

If you still have a remote pointing to `py-poc`:

### A. Remove the incorrect remote

```bash
cd e:\Development\pdf-poly-lingo
git remote -v                    # confirm which remote exists
git remote remove origin          # remove the wrong remote
git remote -v                     # verify it's gone
```

### B. Undo changes in py-poc (if you pushed pdf-poly-lingo into it)

If you pushed to `samartomar/py-poc` and that repo should not contain pdf-poly-lingo:

**Option 1: Force-push an empty or previous state (dangerous)**

Only do this if you are sure you want to overwrite what’s on GitHub:

```bash
# From py-poc repo (not pdf-poly-lingo), after cloning/cd into py-poc:
git push origin main --force
# Or reset to a known good commit first, then force push
```

**Option 2: Revert the last push on GitHub (safer)**

1. Open `https://github.com/samartomar/py-poc`.
2. If the mistaken push is the latest commit:
   - Go to **Commits** → open the last commit → **Revert**.
3. If you prefer to delete the mistaken branch:
   - Go to **Branches**.
   - Delete the branch that has pdf-poly-lingo content.

---

## 2. Create the pdf-poly-lingo repo on GitHub

1. Go to https://github.com/new
2. Set:
   - **Repository name:** `pdf-poly-lingo`
   - **Visibility:** Private or Public
   - Leave “Add a README” and “.gitignore” unchecked (you already have them locally).
3. Click **Create repository**
4. You’ll see a page with clone URL and “push an existing repository” commands.

---

## 3. Configure pdf-poly-lingo to use its own repo

From `e:\Development\pdf-poly-lingo`:

```bash
# Add the correct remote (if you removed it)
git remote add origin https://github.com/samartomar/pdf-poly-lingo.git

# Or with SSH:
# git remote add origin git@github.com:samartomar/pdf-poly-lingo.git

# Push your code
git push -u origin master
```

If your default branch should be `main`:

```bash
git branch -M main
git push -u origin main
```

---

## 4. Wire Code Connections to pdf-poly-lingo (if needed)

The pipeline uses:

`arn:aws:codeconnections:us-west-2:674763518102:connection/a4712769-a210-4d9a-9eed-8f244e3cc48d`

1. In AWS Console → **Developer Tools** → **Connections**
2. Open that connection and ensure `samartomar/pdf-poly-lingo` is connected
3. If you previously only connected `py-poc`, add or update the connection to include `pdf-poly-lingo`

---

## 5. Redeploy the pipeline

After pushing to `pdf-poly-lingo` and confirming the connection:

```bash
cd e:\Development\pdf-poly-lingo
cdk deploy PipelineStack --require-approval never
```

The pipeline will then use `samartomar/pdf-poly-lingo` on branch `main`.
