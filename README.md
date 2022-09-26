This project was built using Python 3.8.10 - for best results please install `pyenv` and setup your local version to `3.8.10` before continuing.

Setup Instructions:
1. Download poetry (v 1.2.1)
2. `poetry install` in the top level directory
3. `poetry shell` to activate the virtual environment
4. Define the following environment variables or set the globals in hf.py
```
JENKINS_USERNAME = "" 
JENKINS_TOKEN = "" Generate from Jenkins settings
REPO_BASE = "" # Top level folder where all your Propelo repos live
```
5. Ensure that you have Jenkins DNS settings set up correctly. The script hits  https://jenkins.dev.levelops.io/ for spawning build
6. python hotfix/hf.py hotfix --help`




This tool does the following:
1. Checks which version of your service is running in prod
2. Checks which version of commons corresponds with #1
3. Prepares your commons hot fix branch, pushes it and spawns a Jenkins build
4. Prepares your service hot fix branch and pushes it
5. Displays the git compare links for both commons and your version

If a conflict is found, the script gives an opportunity to resolve conflicts and continue

NOTE: The script does not spawn any builds other than commons, so you can be rest assured that your service will not be 
auto deployed to dev.
