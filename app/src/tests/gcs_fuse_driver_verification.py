import pytest
from pytest_bdd import given, when, then, scenarios
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config

logger = get_logger(__name__)
# Load configuration once at module level
CONFIG = load_config()
# Link the Gherkin feature file
scenarios("../features/gcs_fuse_driver_verification.feature")


@given("a GKE cluster is running")
def verify_cluster_running(k8s_client):
    """Verify that the Kubernetes cluster is accessible."""
    logger.info("Verifying Kubernetes cluster is running...")
    core_api = k8s_client("CoreV1Api")
    
    try:
        nodes = core_api.list_node()
        assert nodes.items, "No nodes found in the cluster"
        logger.info(f"Kubernetes cluster verification successful. Found {len(nodes.items)} nodes.")
    except Exception as e:
        pytest.fail(f"Failed to verify cluster is running: {str(e)}")


@then("the GCS FUSE CSI driver should be installed on the cluster")
def verify_gcs_fuse_csi_driver(k8s_client):
    """Verify that the GCS FUSE CSI driver is installed on the cluster."""
    logger.info("Verifying GCS FUSE CSI driver is installed...")
    
    # Get configuration values
    driver_namespace = CONFIG["gcs_fuse"]["driver_namespace"]
    
    # Get the CoreV1Api client for pod operations
    core_api = k8s_client("CoreV1Api")
    
    try:
        # List pods with name prefix 'gcsfusecsi-node'
        pods = core_api.list_namespaced_pod(
            namespace=driver_namespace,
            field_selector="status.phase=Running",
            label_selector=f"app.kubernetes.io/name=gcsfusecsi-node"
        )
        
        # Verify that GCS FUSE pods exist and are running
        assert pods.items, f"No GCS FUSE CSI driver pods found in {driver_namespace} namespace"
        
        # Log information about each pod
        for pod in pods.items:
            logger.info(f"Found GCS FUSE pod: {pod.metadata.name}")
            logger.info(f"Pod status: {pod.status.phase}")
            
            # Check container status
            container_count = len(pod.status.container_statuses)
            ready_containers = sum(1 for c in pod.status.container_statuses if c.ready)
            logger.info(f"Containers ready: {ready_containers}/{container_count}")
            
            # Verify all containers are ready
            assert ready_containers == container_count, \
                f"Not all containers are ready in pod {pod.metadata.name}"
        
        logger.info(f"GCS FUSE CSI driver is installed and running with {len(pods.items)} node pods")
        
    except Exception as e:
        pytest.fail(f"Failed to verify GCS FUSE CSI driver pods: {str(e)}")


@then("all GCS FUSE CSI node pods should be running with all containers ready")
def verify_csi_node_pods(k8s_client):
    """Verify that all GCS FUSE CSI node pods are running and their containers are ready."""
    logger.info("Verifying GCS FUSE CSI node pods...")
    
    core_api = k8s_client("CoreV1Api")
    namespace = "kube-system"
    
    try:
        # List pods with name prefix 'gcsfusecsi-node'
        pods = core_api.list_namespaced_pod(
            namespace=namespace,
            field_selector="status.phase=Running",
            label_selector="k8s-app=gcs-fuse-csi-driver"
        )
        
        assert pods.items, "No GCS FUSE CSI node pods found in kube-system namespace"
        
        # Check each pod and its containers
        for pod in pods.items:
            logger.info(f"Checking pod: {pod.metadata.name}")
            
            # Verify pod is running
            assert pod.status.phase == "Running", \
                f"Pod {pod.metadata.name} is not running (status: {pod.status.phase})"
            
            # Verify all containers are ready
            container_statuses = pod.status.container_statuses
            if not container_statuses:
                pytest.fail(f"No container status information found for pod {pod.metadata.name}")
            
            for container in container_statuses:
                logger.info(f"Container '{container.name}': Ready={container.ready}")
                assert container.ready, \
                    f"Container '{container.name}' in pod '{pod.metadata.name}' is not ready"
            
            logger.info(f"Pod {pod.metadata.name} is running with {len(container_statuses)}/"\
                       f"{len(container_statuses)} containers ready")
        
        logger.info(f"All {len(pods.items)} GCS FUSE CSI node pods are running with all containers ready")
    
    except Exception as e:
        pytest.fail(f"Failed to verify CSI node pods: {str(e)}")