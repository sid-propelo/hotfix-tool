import time
from typing import List, Optional

import requests
import typer
from enum import Enum
from git import Repo, GitCommandError
import os
import re
import in_place
from rich import print
from rich.prompt import Prompt

import pdb


def configure_settings():
    print("Configuring settings")
    global JENKINS_USERNAME, JENKINS_TOKEN, REPO_BASE
    if not JENKINS_USERNAME:
        JENKINS_USERNAME = os.getenv("JENKINS_USERNAME")
    if not JENKINS_TOKEN:
        JENKINS_TOKEN = os.getenv("JENKINS_TOKEN")
    if not REPO_BASE:
        REPO_BASE = os.getenv("REPO_BASE")


app = typer.Typer(callback=configure_settings)

# Change ME!
JENKINS_USERNAME = ""
JENKINS_TOKEN = ""
REPO_BASE = ""


class Service(Enum):
    DEVOPS = "devops"
    COMMONS = "commons"
    SERVER_API = "server-api"
    INTERNAL_API = "internal-api"
    AGGS = "aggs"


SERVICE_TO_VERSION_KEY = {
    Service.SERVER_API: "SERVERAPI_VERSION",
    Service.INTERNAL_API: "INTERNAL_API_VERSION",
    Service.AGGS: "AGGREGATIONS_SERVICE_VERSION",
}

SERVICE_TO_REPO_NAME = {
    Service.SERVER_API: "api-levelops",
    Service.DEVOPS: "devops-levelops",
    Service.COMMONS: "commons-levelops",
    Service.INTERNAL_API: "internal-api-levelops",
    Service.AGGS: "aggregations-levelops",
}

SERVICE_TO_MASTER_BRANCH = {
    Service.SERVER_API: "dev",
    Service.INTERNAL_API: "dev",
    Service.AGGS: "dev",
    Service.DEVOPS: "main",
    Service.COMMONS: "main",
}

SERVICE_TO_BUILD_FILE = {
    Service.SERVER_API: "build.gradle",
    Service.INTERNAL_API: "build.gradle",
    Service.AGGS: "build.gradle",
}

SERVICE_TO_JENKINS_BUILD = {Service.COMMONS: "Build-commons-levelops"}

SERVICE_TO_REPO_MAP = {}


def generate_jenkins_base_url() -> str:
    return f"https://{JENKINS_USERNAME}:{JENKINS_TOKEN}@jenkins.dev.levelops.io"


def generate_jenkins_url(service: Service) -> str:
    return f"{generate_jenkins_base_url()}/job/{SERVICE_TO_JENKINS_BUILD[service]}/buildWithParameters?"


def get_jenkins_build_url_from_queue(queue_url: str) -> str:
    queue_url = queue_url + "/api/json"
    queue_url = (
        generate_jenkins_base_url() + "/" + re.search("(queue.*)", queue_url).group()
    )
    count = 0

    while True:
        response = requests.request("GET", queue_url)
        if response.ok and "executable" in response.json():
            break
        elif count > 15:
            raise Exception("Unable to get Jenkins build url. Something went wrong")
        else:
            print(
                f"[yellow]Waiting for Jenkins build information to show up. Count {count}"
            )
            time.sleep(2)
            count += 1

    build_url = response.json()["executable"]["url"]
    build_version = typer.prompt(
        f"Please visit this build url: {build_url} and enter the build version "
        f"number after the build succeeds"
    )
    return build_version


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
    response = requests.request(
        "POST", url, params=params, headers=headers, data=payload
    )
    if response.status_code == 201:
        queue_url = response.headers["Location"]
        print(f"[green]Successfully created commons build. Queue url: {queue_url}")
    else:
        raise Exception(
            f"Unable to spawn commons build. Response: {response.status_code} {response.content}"
        )
    return get_jenkins_build_url_from_queue(queue_url)


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
    return
    # print(f"[GIT] {result}")


def switch_to_master_branch(service: Service, should_pull: bool):
    repo = get_git_repo(service)
    if not ensure_repo_is_clean(repo):
        raise Exception(
            f"{service} repo is not clean. Please ensure a clean repo before continuing."
        )
    master_branch = SERVICE_TO_MASTER_BRANCH[service]
    active_branch = repo.active_branch if not repo.head.is_detached else "detached head"
    print(f"[yellow]{service} switching from {active_branch} to {master_branch}")
    log_git_result(repo.git.checkout(master_branch))
    if should_pull:
        print(f"[yellow]Pulling latest changes from {service}")
        log_git_result(repo.git.pull("origin", master_branch))
        repo.git.fetch("--all", "--tags")


def get_latest_service_version(service: Service):
    switch_to_master_branch(service.DEVOPS, True)
    devops_repo = get_git_repo(service.DEVOPS)
    version_file_path = (
        devops_repo.working_tree_dir + "/k8s/overlays/{env}/versions.txt"
    )
    return get_version_from_file(version_file_path.format(env="prod"), service)


def get_commons_version_from_file(file_path: str) -> str:
    with open(file_path) as f:
        content = f.read()
        results = re.search('ext.levelopsCommonsVersion\s+=\s+"(.*)"', content)
        return results.groups()[0]


def get_current_commons_version_for_service(service: Service):
    switch_to_master_branch(service, True)
    repo = get_git_repo(service)
    build_file_path = os.path.join(
        repo.working_tree_dir, SERVICE_TO_BUILD_FILE[service]
    )
    return get_commons_version_from_file(build_file_path)


def switch_commons_version_for_service(service: Service, new_version: str):
    repo = get_git_repo(service)
    build_file_path = os.path.join(
        repo.working_tree_dir, SERVICE_TO_BUILD_FILE[service]
    )
    with in_place.InPlace(build_file_path) as f:
        for line in f:
            if re.search("ext.levelopsCommonsVersion", line):
                line = re.sub("v\d+.\d+.\d+", new_version, line)
            f.write(line)


def get_commons_version_from_tag(service: Service, tag: str):
    print(f"[green]Getting commons version of {service} version {tag}")
    switch_to_master_branch(service, True)
    repo = get_git_repo(service)
    log_git_result(repo.git.fetch("--all", "--tags"))
    all_tags = repo.git.tag().split("\n")
    found_tag = None
    for t in all_tags:
        if tag in t:
            found_tag = t
            print(f"[yellow]Found tag {tag}")
    if not found_tag:
        raise Exception("A matching tag was not found")

    print(f"[yellow]Checking out {found_tag} for {service}")
    log_git_result(repo.git.checkout(found_tag))
    build_file_path = os.path.join(
        repo.working_tree_dir, SERVICE_TO_BUILD_FILE[service]
    )

    commons_version = get_commons_version_from_file(build_file_path)
    switch_to_master_branch(service, False)
    print(f"[green]Commons version found for {service} {tag} = {commons_version}")
    return commons_version


def get_github_new_pr_link(service: Service, hf_branch_name: str):
    # https://github.com/levelops/commons-levelops/pull/new/test-hf
    return f"https://github.com/levelops/{SERVICE_TO_REPO_NAME[service]}/pull/new/{hf_branch_name}"


def get_github_compare_link(
    service: Service, comparison_branch: str, comparison_tag: str
):
    # https://github.com/levelops/commons-levelops/compare/v0.1.7085-hf...test-hf?expand=1
    return f"https://github.com/levelops/{SERVICE_TO_REPO_NAME[service]}/compare/{comparison_tag}...{comparison_branch}"


def print_green(s: str):
    print(f"[green][bold]{s}")


def print_blue(s: str):
    print(f"[blue] {s}")


def create_and_push_hotfix_branch(
    service: Service, commit_shas: List[str], hf_branch_name: str, tag: str
):
    switch_to_master_branch(service, True)
    repo = get_git_repo(service)
    if hf_branch_name in [i.name for i in repo.heads]:
        raise Exception(f"Branch {hf_branch_name} already exists in {service}")
    print(f"[yellow]Checking out commons tag {tag} to branch {hf_branch_name}")
    log_git_result(repo.git.checkout("-b", hf_branch_name, tag))
    print(f"[yellow]Cherry-picking commons commits: {commit_shas}")
    try:
        log_git_result(repo.git.cherry_pick(*commit_shas))
    except GitCommandError as e:
        print(e)
        user_response = typer.prompt(
            f"Looks like the cherry-pick on {service} failed. "
            f"Please resolve conflicts and press yes to continue"
        )
        if user_response == "y" or user_response == "yes":
            if repo.is_dirty():
                raise Exception("Looks like repo is still dirty. Failing now")
        else:
            raise Exception("User discontinued hotfix :( :sad:")

    print(f"[blue]Pushing to origin")
    log_git_result(repo.git.push("origin", hf_branch_name))


def test():
    # print(get_latest_service_version(Service.SERVER_API))
    # print(get_current_commons_version_for_service(Service.SERVER_API))
    get_commons_version_from_tag(Service.SERVER_API, "v0.1.4564-hf")


@app.command()
def cleanup(service: str, branch: str):
    service = Service(service)
    print(f"Git deleting branch {branch} from {service}")
    repo = get_git_repo(service)
    switch_to_master_branch(service, False)
    print(repo.git.branch("-D", branch))
    print(repo.git.push("origin", "--delete", branch))


@app.command()
def hotfix(
    service: str,
    hf_branch_name: Optional[str] = typer.Option(
        None,
        help="Name of new hot fix branch you want to "
        "create. This will be the same across all"
        " repos.",
    ),
    service_commit_shas: str = typer.Option(
        ...,
        help="Comma seperated string of commit shas for the service you want to hot fix",
    ),
    commons_commit_shas: Optional[str] = typer.Option(
        None, help="Comma seperated string of commons " "commit shas"
    ),
):
    service = Service(service)
    print(f"[green]Hot fixing {service}")
    latest_service_version = get_latest_service_version(service)
    prod_commons_version = get_commons_version_from_tag(service, latest_service_version)

    print_green(f"{service} version in prod = {latest_service_version}")
    print_green(
        f"Commons version corresponding to {service} {latest_service_version}= {prod_commons_version}"
    )

    print("============================================================")
    print("Preparing commons branch")
    print("============================================================")
    new_commons_version = None
    if commons_commit_shas:
        commons_commit_shas = commons_commit_shas.split(",")
        create_and_push_hotfix_branch(
            Service.COMMONS, commons_commit_shas, hf_branch_name, prod_commons_version
        )
        print_green(
            f"[bold]Github compare link for commons: "
            f"{get_github_compare_link(Service.COMMONS, hf_branch_name, prod_commons_version)}"
        )

        print_green("Building commons now!")
        new_commons_version = build_commons(hf_branch_name, "-sid-test")

    print("============================================================")
    print(f"Preparing {service} branch")
    print("============================================================")
    switch_to_master_branch(service, True)
    service_commit_shas = service_commit_shas.split(",")
    create_and_push_hotfix_branch(
        service, service_commit_shas, hf_branch_name, latest_service_version
    )
    if new_commons_version:
        switch_commons_version_for_service(service, new_commons_version)
        repo = get_git_repo(service)
        repo.git.add("--all")
        repo.git.commit("-m", "Updating commons version")
        repo.git.push("origin", hf_branch_name)

    service_comparison_link = get_github_compare_link(
        service, hf_branch_name, latest_service_version
    )

    # Change the version of commons in the build file

    if commons_commit_shas:
        print_green(
            f"Commons comparison link: {get_github_compare_link(Service.COMMONS, hf_branch_name, service_comparison_link)}"
        )

    print_green(
        f"Service comparison link: {get_github_compare_link(service, hf_branch_name, latest_service_version)}"
    )


if __name__ == "__main__":
    app()
    # test()
