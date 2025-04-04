import pytest
from pytest_bdd import given, when, then, scenarios
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config
from kubernetes.stream import stream

logger = get_logger(__name__)
CONFIG = load_config()
scenarios("../features/gcs_fuse_write_read_file.feature")


@given("a GKE cluster is running")
def verify_cluster_running(k8s_client):
    """Verify that the Kubernetes cluster is accessible."""
    logger.info("Verifying Kubernetes cluster is running...")
    assert k8s_client is not None, "Kubernetes client could not be initialized."
    logger.info("Kubernetes cluster verification successful.")


@given('a deployment named "gcs-fuse" exists in the "default" namespace')
def verify_deployment_exists(k8s_client):
    """Ensure the deployment exists in the specified namespace."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    deployment_name = CONFIG["gcs_fuse"]["deployment_name"]

    apps_api = k8s_client("AppsV1Api")
    logger.info(f"Checking if deployment '{deployment_name}' exists in namespace '{namespace}'...")
    response = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    assert response is not None, f"Deployment '{deployment_name}' does not exist in namespace '{namespace}'."
    logger.info(f"Deployment '{deployment_name}' exists.")

@when('the deployment starts')
def verify_pod_running(k8s_client):
    """Ensure the pod for the deployment is running."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    deployment_name = CONFIG["gcs_fuse"]["deployment_name"]
    app_label = CONFIG["gcs_fuse"]["app_label"]
    retry_count = CONFIG["gcs_fuse"]["retry_count"]
    retry_interval = CONFIG["gcs_fuse"]["retry_interval"]

    core_api = k8s_client("CoreV1Api")

    for _ in range(retry_count):
        logger.info(f"Checking if pod for deployment '{deployment_name}' is running...")
        pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
        for pod in pods.items:
            if pod.status.phase == "Running":
                logger.info(f"Pod '{pod.metadata.name}' is running.")
                return pod.metadata.name
        time.sleep(retry_interval)
    
    pytest.fail(f"Pod for deployment '{deployment_name}' did not start running.")

@then("a file can be written to and read from the GCS FUSE mount")
def test_gcs_fuse_read_write(k8s_client):
    """Test read and write operations on the GCS FUSE mount."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    mount_path = CONFIG["gcs_fuse"]["mount_path"]
    app_label = CONFIG["gcs_fuse"]["app_label"]
    test_filename = CONFIG["test"]["test_filename"]
    test_content = CONFIG["test"]["test_content"]

    core_api = k8s_client("CoreV1Api")

    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
    assert pods.items, f"No pods found for app '{app_label}' in namespace '{namespace}'."
    pod_name = pods.items[0].metadata.name

    test_filepath = f"{mount_path}/{test_filename}"

    logger.info(f"Writing test file '{test_filename}' to GCS FUSE...")
    write_command = ["/bin/sh", "-c", f"echo '{test_content}' > {test_filepath}"]
    stream(
        core_api.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=namespace,
        command=write_command,
        stderr=True, stdin=False, stdout=True, tty=False
    )

    logger.info(f"Reading test file '{test_filename}' from GCS FUSE...")
    read_command = ["/bin/sh", "-c", f"cat {test_filepath}"]
    read_response = stream(
        core_api.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=namespace,
        command=read_command,
        stderr=True, stdin=False, stdout=True, tty=False
    )

    assert read_response.strip() == test_content, \
        f"Content mismatch. Expected: '{test_content}', Got: '{read_response.strip()}'"
    logger.info("Read/write test passed.") 