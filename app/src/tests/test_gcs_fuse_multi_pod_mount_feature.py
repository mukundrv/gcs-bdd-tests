import pytest
from pytest_bdd import given, when, then, scenarios
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config
from kubernetes.stream import stream

logger = get_logger(__name__)
# Load configuration once at module level
CONFIG = load_config()
# Link the Gherkin feature file
scenarios("../features/gcs_fuse_multi_pod_mount.feature")

# Store original replica count
original_replicas = None

@given("a GKE cluster is running")
def verify_cluster_running(k8s_client):
    """Verify that the Kubernetes cluster is accessible."""
    logger.info("Verifying Kubernetes cluster is running...")
    assert k8s_client is not None, "Kubernetes client could not be initialized."
    logger.info("Kubernetes cluster verification successful.")


@given('a deployment named "gcs-fuse" exists in the "default" namespace')
def verify_deployment_exists(k8s_client):
    """Ensure the deployment exists in the specified namespace."""
    global original_replicas
    namespace = CONFIG["gcs_fuse"]["namespace"]
    deployment_name = CONFIG["gcs_fuse"]["deployment_name"]
    replicas = CONFIG["gcs_fuse"]["replicas"]

    # Retrieve AppsV1Api client
    apps_api = k8s_client("AppsV1Api")
    logger.info(f"Checking if deployment '{deployment_name}' exists in namespace '{namespace}'...")
    
    # Update the deployment to have multiple replicas for multi-pod testing
    try:
        deployment = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        # Store original replica count
        original_replicas = deployment.spec.replicas
        logger.info(f"Original deployment had {original_replicas} replicas")

        if deployment.spec.replicas < replicas:
            logger.info(f"Updating deployment '{deployment_name}' to have {replicas} replicas...")
            deployment.spec.replicas = replicas
            apps_api.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )
            logger.info(f"Deployment updated to have {replicas} replicas.")
            time.sleep(10)  # Give time for new pods to start
    except Exception as e:
        pytest.fail(f"Failed to read or update deployment: {str(e)}")
    
    response = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    assert response is not None, f"Deployment '{deployment_name}' does not exist in namespace '{namespace}'."
    logger.info(f"Deployment '{deployment_name}' exists with {response.spec.replicas} replicas.")

@pytest.fixture(autouse=True)
def cleanup_deployment(k8s_client):
    """Cleanup fixture to restore original replica count after test."""
    logger.info("Starting test - cleanup fixture will run after test completion")
    yield  # Test runs here
    logger.info("Test completed - running cleanup to restore original replica count")
    
    # After test completion, restore original replica count
    if original_replicas is not None:
        namespace = CONFIG["gcs_fuse"]["namespace"]
        deployment_name = CONFIG["gcs_fuse"]["deployment_name"]
        apps_api = k8s_client("AppsV1Api")
        
        try:
            deployment = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            logger.info(f"Restoring deployment to original {original_replicas} replicas...")
            deployment.spec.replicas = original_replicas
            apps_api.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )
            logger.info(f"Deployment restored to {original_replicas} replicas.")
            
            # Wait for pods to scale down
            time.sleep(10)
        except Exception as e:
            logger.error(f"Failed to restore deployment replicas: {str(e)}")

@when('the deployment starts')
def verify_pod_running(k8s_client):
    """Ensure the pods for the deployment are running."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    deployment_name = CONFIG["gcs_fuse"]["deployment_name"]
    app_label = CONFIG["gcs_fuse"]["app_label"]
    replicas = CONFIG["gcs_fuse"]["replicas"]
    retry_count = CONFIG["gcs_fuse"]["retry_count"]
    retry_interval = CONFIG["gcs_fuse"]["retry_interval"]

    # Retrieve CoreV1Api client for Pod checks
    core_api = k8s_client("CoreV1Api")

    for _ in range(retry_count):
        logger.info(f"Checking if pods for deployment '{deployment_name}' are running...")
        pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
        running_pods = [pod for pod in pods.items if pod.status.phase == "Running"]
        
        if len(running_pods) >= replicas:
            logger.info(f"Found {len(running_pods)} running pods for deployment '{deployment_name}'.")
            return True
        
        time.sleep(retry_interval)
    
    pytest.fail(f"Not enough pods for deployment '{deployment_name}' are running.")

@then("the GCS FUSE mount should be accessible by all pods in the deployment")
def verify_gcs_fuse_mount_multi_pod(k8s_client):
    """Ensure the GCS FUSE mount is accessible inside all pods."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    mount_path = CONFIG["gcs_fuse"]["mount_path"]
    app_label = CONFIG["gcs_fuse"]["app_label"]
    test_filename = CONFIG["test"]["multi_pod_test_filename"]
    test_content = CONFIG["test"]["multi_pod_test_content"]

    # Create a test file in the first pod
    core_api = k8s_client("CoreV1Api")
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
    
    assert len(pods.items) >= 2, "Not enough pods found for the multi-pod test."
    
    # Write a test file in the first pod
    test_filepath = f"{mount_path}/{test_filename}"
    first_pod = pods.items[0]
    logger.info(f"Writing test file from pod '{first_pod.metadata.name}'...")
    
    write_command = ["/bin/sh", "-c", f"echo '{test_content}' > {test_filepath}"]
    stream(
        core_api.connect_get_namespaced_pod_exec,
        name=first_pod.metadata.name,
        namespace=namespace,
        command=write_command,
        stderr=True, stdin=False, stdout=True, tty=False
    )
    
    # Verify the file is accessible from all other pods
    for pod in pods.items[1:]:
        pod_name = pod.metadata.name
        logger.info(f"Reading test file from pod '{pod_name}'...")
        
        read_command = ["/bin/sh", "-c", f"cat {test_filepath}"]
        try:
            read_response = stream(
                core_api.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=namespace,
                command=read_command,
                stderr=True, stdin=False, stdout=True, tty=False
            )
            
            assert read_response.strip() == test_content, \
                f"Content mismatch in pod '{pod_name}'. Expected: '{test_content}', Got: '{read_response.strip()}'"
            logger.info(f"File successfully read from pod '{pod_name}'.")
        except Exception as e:
            pytest.fail(f"Failed to access test file in pod '{pod_name}': {str(e)}")
    
    logger.info("All pods can access the GCS FUSE mount successfully.") 