from hotfix.hf import get_jenkins_build_url_from_queue


def test_jenkins_build_url():
    get_jenkins_build_url_from_queue(
        "https://jenkins.dev.levelops.io/queue/item/63585/"
    )
