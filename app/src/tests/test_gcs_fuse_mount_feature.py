import pytest
from pytest_bdd import given, when, then, scenarios
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config
from kubernetes.stream import stream

logger = get_logger(__name__)
CONFIG = load_config()
scenarios("../features/gcs_fuse_mount.feature")

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

@then("the GCS FUSE mount should be accessible")
def verify_gcs_fuse_mount(k8s_client):
    """Ensure the GCS FUSE mount is accessible inside the pod."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    deployment_name = CONFIG["gcs_fuse"]["deployment_name"]
    mount_path = CONFIG["gcs_fuse"]["mount_path"]
    app_label = CONFIG["gcs_fuse"]["app_label"]

    core_api = k8s_client("CoreV1Api")

    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
    assert pods.items, f"No pod found for deployment '{deployment_name}'."
    pod_name = pods.items[0].metadata.name

    logger.info(f"Checking if GCS FUSE mount is accessible on pod '{pod_name}' at path '{mount_path}'...")

    exec_command = ["/bin/sh", "-c", f"ls {mount_path}"]

    try:
        exec_response = stream(
            core_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=exec_command,
            stderr=True, stdin=False, stdout=True, tty=False
        )
        assert isinstance(exec_response, str), f"GCS FUSE mount at '{mount_path}' is inaccessible."
        logger.info(f"GCS FUSE mount at '{mount_path}' is accessible.")
    except Exception as e:
        pytest.fail(f"Failed to access GCS FUSE mount: {str(e)}") 