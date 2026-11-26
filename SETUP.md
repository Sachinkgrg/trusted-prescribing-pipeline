# Setup on Windows (Day 1)

Work through this top to bottom. It takes about an hour the first time.

## 1. Install three things

| Tool | Where | Watch out for |
|---|---|---|
| Python 3.12 or newer | Microsoft Store app: search **Python Install Manager** | Then run `python` once in PowerShell and answer **y** to each setup question |
| Git for Windows | git-scm.com | Accept the defaults |
| Visual Studio Code | code.visualstudio.com | Install the Python extension when it offers |

Also create a free account at github.com if you do not have one.

## 2. Open the project

1. Unzip the project to a simple path, for example `C:\projects\trusted-prescribing-pipeline`.
2. In VS Code: File > Open Folder, and pick that folder.
3. Open a terminal: Terminal > New Terminal. It should say PowerShell.

## 3. Create the Python environment

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If the second line is blocked with a "running scripts is disabled" error, run
this once and try again:

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

You know it worked when the terminal prompt starts with `(.venv)`.

## 4. Run the tests

```
pytest
```

Expected: `32 passed`. These tests do not use the internet.

## 5. Check the portal

```
python -m pipeline.discover
```

Expected: a list of 12 months, each with a resource name next to it, then a
list of column names with example values.

- If a month says `NOT FOUND`, the portal has not published it. Change
  `months` in `config/sources.yml` to months that exist.
- If it says the filter matched no rows, the area code is wrong. Run
  `python -m pipeline.discover --area "NORTH EAST"` to list area codes, then
  fix `where` in the config.

## 6. Load one month, then all of them

```
python -m pipeline.ingest --month 202608
python -m pipeline.ingest
python -m pipeline.peek
```

Expected: one line per month ending in `PASS`, then a table of loads and five
example rows.

## 7. Put it on GitHub

First time only, tell Git who you are:

```
git config --global user.name "Your Name"
git config --global user.email "the email on your GitHub account"
```

Then:

```
git init
git add .
git commit -m "Bronze layer: config driven ingestion with reconciliation and load log"
```

On github.com: New repository, name it `trusted-prescribing-pipeline`, public,
do **not** add a README. GitHub then shows three lines under "push an existing
repository". Copy and run them.

## 8. Before Day 2: can you answer these?

You will be asked about this project at interview. Read the code until you can
answer each of these out loud, without looking.

1. What happens, step by step, when you run `python -m pipeline.ingest`?
2. Why is every bronze column stored as text?
3. You run the same month twice. Why are there no duplicates? Which lines do that?
4. What does `FAIL` mean, and how is it different from `ERROR` and `MISSING`?
5. Why do the tests use `FakeApi` instead of the real portal?
6. You want to load antidepressants for a different area. What do you change?
7. What does "metadata driven" mean in this project?

Then break it on purpose and watch what happens: change `13T00` to `XXXXX` in
the config and run discover. Change it back afterwards.
