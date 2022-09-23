Setup Instructions:
1. Download poetry
2. `poetry install` in the top level directory
3. Change the environment variables in hf.py
4. `python hf.py hotfix --help`


This tool does the following:
1. Checks which version of your service is running in prod
2. Checks which version of commons corresponds with #1
3. Prepares your commons hot fix branch, pushes it and spawns a Jenkins build
4. Prepares your service hot fix branch and pushes it
5. Displays the git compare links for both commons and your version