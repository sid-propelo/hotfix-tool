import typer
from enum import Enum
from git import Repo
import os
import re
import pdb


app = typer.Typer()

class Service(Enum):
	SERVER_API = "server-api"
	DEVOPS = "devops-levelops"

SERVICE_TO_VERSION_KEY = {
	Service.SERVER_API: "SERVERAPI_VERSION"
}

SERVICE_TO_REPO_NAME = {
	Service.SERVER_API: "api-levelops",
	Service.DEVOPS: "devops-levelops"
}

SERVICE_TO_MASTER_BRANCH = {
	Service.SERVER_API: "dev",
	Service.DEVOPS: "main"
}

SERVICE_TO_BUILD_FILE = {
	Service.SERVER_API: "build.gradle"
}

REPO_BASE = "/Users/siddharthbidasaria/propelo/code/"

SERVICE_TO_REPO_MAP = {}


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
		print(f"{service} repo is not clean. Please ensure a clean repo before continuing.")
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
	build_file_path = os.path.join(repo.working_tree_dir, SERVICE_TO_BUILD_FILE[service])
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
	build_file_path = os.path.join(repo.working_tree_dir, SERVICE_TO_BUILD_FILE[service])

	commons_version = get_commons_version_from_file(build_file_path)
	switch_to_master_branch(service, False)
	return commons_version
	

def test():
	# print(get_latest_service_version(Service.SERVER_API))
	# print(get_current_commons_version_for_service(Service.SERVER_API))
	get_commons_version_from_tag(Service.SERVER_API, "v0.1.4564-hf")


@app.command()
def hotfix(service: str, common_commit_shas: List[str]):
	print(f"Hot fixing {service}")
	latest_service_version = get_latest_service_version(Service.SERVER_API)
	prod_commons_version = get_commons_version_from_tag(Service.SERVER_API, latest_service_version)
	latest_common_version = get_current_commons_version_for_service(Service.SERVER_API)

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
	print(f"Latest commons version in main: {current_commons_version}")

	print("============================================================")
	print(common_commit_shas)



@app.command()
def hf():
	print("hf")


if __name__ == "__main__":
    app()
    # test()
