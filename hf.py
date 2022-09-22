from typing import List, Optional

import requests
import typer
from enum import Enum
from git import Repo
import os
import re
import pdb

app = typer.Typer()

JENKINS_USERNAME = 'sid'
JENKINS_TOKEN = '1164b1f1f006a22b2728c8da714833790f'
REPO_BASE = "/Users/siddharthbidasaria/propelo/code/"


class Service(Enum):
    SERVER_API = "server-api"
    DEVOPS = "devops-levelops"
    COMMONS = "commons-levelops"


SERVICE_TO_VERSION_KEY = {
    Service.SERVER_API: "SERVERAPI_VERSION"
}

SERVICE_TO_REPO_NAME = {
    Service.SERVER_API: "api-levelops",
    Service.DEVOPS: "devops-levelops",
    Service.COMMONS: "commons-levelops",
}

SERVICE_TO_MASTER_BRANCH = {
    Service.SERVER_API: "dev",
    Service.DEVOPS: "main",
    Service.COMMONS: "main",
}

SERVICE_TO_BUILD_FILE = {
    Service.SERVER_API: "build.gradle"
}

SERVICE_TO_JENKINS_BUILD = {
    Service.COMMONS: "Build-commons-levelops"
}


SERVICE_TO_REPO_MAP = {}


def generate_jenkins_url(service: Service) -> str:
    return f"https://{JENKINS_USERNAME}:{JENKINS_TOKEN}@jenkins.dev.levelops.io/job/{SERVICE_TO_JENKINS_BUILD[service]}/buildWithParameters?"


def build_commons(branch: str, suffix: str):
    url = generate_jenkins_url(Service.COMMONS)
    headers = {}
    payload = {}
    params = {
        "token": "commonsAuthToken",
        "cause": "hot fix script",
        "BRANCH_NAME": branch,
        "VERSION_SUFFIX": suffix,
    }
    response = requests.request("POST", url, params=params, headers=headers, data=payload)
    print(response)
    return response


def get_repo_path(service: Service) -> str:
    return REPO_BASE + SERVICE_TO_REPO_NAME[service]


def get_version_from_file(filePath: str, service: Service) -> str:
    with open(filePath) as f:
        lines = [i.strip().split("=") for i in f.readlines()]
        versions = {v[0]: v[1] for v in lines}
        return versions[SERVICE_TO_VERSION_KEY[service]]


def get_git_repo(service: Service) -> Repo:
    if service in SERVICE_TO_REPO_MAP:
        return SERVICE_TO_REPO_MAP[service]

    path = get_repo_path(service)
    repo = Repo(path)
    SERVICE_TO_REPO_MAP[service] = repo
    return repo


def ensure_repo_is_clean(repo: Repo) -> bool:
    return not repo.is_dirty() and len(repo.untracked_files) == 0


def log_git_result(result: str):
    print(f"[GIT] {result}")


def switch_to_master_branch(service: Service, should_pull: bool):
    repo = get_git_repo(service)
    if not ensure_repo_is_clean(repo):
        print(
            f"{service} repo is not clean. Please ensure a clean repo before continuing.")
        return
    master_branch = SERVICE_TO_MASTER_BRANCH[service]
    active_branch = repo.active_branch if not repo.head.is_detached else "detached head"
    print(f"{service} switching from {active_branch} to {master_branch}")
    log_git_result(repo.git.checkout(master_branch))
    if should_pull:
        print("Pulling latest changes")
        log_git_result(repo.git.pull("origin", master_branch))


def get_latest_service_version(service: Service):
    switch_to_master_branch(service.DEVOPS, True)
    devops_repo = get_git_repo(service.DEVOPS)
    version_file_path = devops_repo.working_tree_dir + "/k8s/overlays/{env}/versions.txt"
    return get_version_from_file(version_file_path.format(env="prod"), service)


def get_commons_version_from_file(file_path: str) -> str:
    with open(file_path) as f:
        content = f.read()
        results = re.search('ext.levelopsCommonsVersion\s+=\s+"(.*)"', content)
        return results.groups()[0]


def get_current_commons_version_for_service(service: Service):
    switch_to_master_branch(service, True)
    repo = get_git_repo(service)
    build_file_path = os.path.join(repo.working_tree_dir,
                                   SERVICE_TO_BUILD_FILE[service])
    return get_commons_version_from_file(build_file_path)


def get_commons_version_from_tag(service: Service, tag: str):
    switch_to_master_branch(service, True)
    repo = get_git_repo(service)
    print("Fetching all tags")
    log_git_result(repo.git.fetch('--all', '--tags'))
    all_tags = repo.git.tag().split("\n")
    found_tag = None
    for t in all_tags:
        if tag in t:
            found_tag = t
            print(f"Found tag {tag}")
    if not found_tag:
        print("A matching tag was not found")
        return

    print(f"Checking out {found_tag}")
    log_git_result(repo.git.checkout(found_tag))
    build_file_path = os.path.join(repo.working_tree_dir,
                                   SERVICE_TO_BUILD_FILE[service])

    commons_version = get_commons_version_from_file(build_file_path)
    switch_to_master_branch(service, False)
    return commons_version


def get_github_new_pr_link(service: Service, hf_branch_name: str):
    # https://github.com/levelops/commons-levelops/pull/new/test-hf
    return f"https://github.com/levelops/{SERVICE_TO_REPO_NAME[service]}/pull/new/{hf_branch_name}"


def get_github_compare_link(service: Service, comparison_branch: str, comparison_tag: str):
    # https://github.com/levelops/commons-levelops/compare/v0.1.7085-hf...test-hf?expand=1
    return f"https://github.com/levelops/{SERVICE_TO_REPO_NAME[service]}/compare/{comparison_tag}...{comparison_branch}"

def test():
    # print(get_latest_service_version(Service.SERVER_API))
    # print(get_current_commons_version_for_service(Service.SERVER_API))
    get_commons_version_from_tag(Service.SERVER_API, "v0.1.4564-hf")


@app.command()
def hotfix(
        service: str,
        hf_branch_name: Optional[str] = typer.Option(None,
                                                     help="Name of new hot fix branch you want to "
                                                          "create. This will be the same across all"
                                                          " repos."),
        commons_commit_shas: Optional[str] = typer.Option(None,
                                                          help="Comma seperated string of commons "
                                                               "commit shas")):
    print(f"Hot fixing {service}")
    latest_service_version = get_latest_service_version(Service.SERVER_API)
    prod_commons_version = get_commons_version_from_tag(Service.SERVER_API,
                                                        latest_service_version)
    latest_common_version = get_current_commons_version_for_service(
        Service.SERVER_API)

    # commons - gcb <hfBranchName> <tag>
    # commons - git cherry pick <commits>
    # commons - ggp
    # create a build and get the version number
    # service - gcb <hfBranchName> <tag>
    # service - git cherry pick <commits>
    # service - change the commons version number to what we got earlier
    # service - ggp
    # create a build -> note version number
    # devops - gco master
    # devops - ggl
    # devops - gcb <hfBranchName>
    # devops - change version number for all prod and staging files
    # devops - ggp
    # devops - get the compare git urls for both commons and the particular service

    print("============================================================")
    print(f"Current {service} version in prod: {latest_service_version}")
    print(f"Commons version for {service} in prod: {prod_commons_version}")
    print(f"Latest commons version in main: {latest_common_version}")

    print("============================================================")
    print("Preparing commons branch")
    print("============================================================")
    if commons_commit_shas:
        commons_commit_shas = commons_commit_shas.split(",")
        commons_repo = get_git_repo(Service.COMMONS)
        if hf_branch_name in [i.name for i in commons_repo.heads]:
            raise Exception(f"Branch {hf_branch_name} already exists in commons")
        print("Fetching commons tags")
        log_git_result(commons_repo.git.fetch('--all', '--tags'))
        print(f"Checking out commons tag {prod_commons_version} to branch {hf_branch_name}")
        log_git_result(commons_repo.git.checkout("-b", hf_branch_name, prod_commons_version))
        print(f"Cherry-picking commons commits: {commons_commit_shas}")
        log_git_result(commons_repo.git.cherry_pick(*commons_commit_shas))
        print(f"Pushing to origin")
        log_git_result(commons_repo.git.push("origin", hf_branch_name))

        print(f"Github compare link for commons: "
              f"{get_github_compare_link(Service.COMMONS, hf_branch_name, prod_commons_version)}")

        print("Building commons now!")
        response = build_commons(hf_branch_name, "-sid-test")
        pdb.set_trace()

    print(hf_branch_name)
    print(commons_commit_shas)




@app.command()
def hf():
    print("hf")


if __name__ == "__main__":
    app()
    # test()
