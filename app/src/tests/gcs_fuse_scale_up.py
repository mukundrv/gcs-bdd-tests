import pytest
from pytest_bdd import given, when, then, scenarios
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config

logger = get_logger(__name__)
CONFIG = load_config()
scenarios("../features/gcs_fuse_scale_up.feature")

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

@given("the cluster autoscaler is configured properly")
def verify_autoscaler_config(k8s_client):
    """Verify cluster autoscaler configuration."""
    logger.info("Verifying cluster autoscaler configuration...")
    core_api = k8s_client("CoreV1Api")
    
    try:
        configmap = core_api.read_namespaced_config_map(
            name="cluster-autoscaler-status",
            namespace="kube-system"
        )
        assert configmap.data is not None, "Autoscaler configuration not found"
        logger.info("Cluster autoscaler is properly configured")
    except Exception as e:
        pytest.fail(f"Failed to verify autoscaler configuration: {str(e)}")

@given("the initial pod count is recorded")
def record_initial_pod_count(k8s_client, context):
    """Record the initial number of pods."""
    logger.info("Recording initial pod count...")
    core_api = k8s_client("CoreV1Api")
    
    try:
        pods = core_api.list_namespaced_pod(
            namespace=CONFIG['gcs_fuse']['namespace']
        )
        context.initial_pod_count = len(pods.items)
        logger.info(f"Initial pod count: {context.initial_pod_count}")
    except Exception as e:
        pytest.fail(f"Failed to record initial pod count: {str(e)}")

@when('I scale the "gcs-fuse" deployment to configured target replicas')
def scale_up_deployment(k8s_client):
    """Scale up the deployment to target replicas."""
    logger.info("Scaling up deployment...")
    apps_api = k8s_client("AppsV1Api")
    target_replicas = CONFIG['scaling']['max_replicas']
    
    try:
        apps_api.patch_namespaced_deployment_scale(
            name=CONFIG['gcs_fuse']['deployment_name'],
            namespace=CONFIG['gcs_fuse']['namespace'],
            body={"spec": {"replicas": target_replicas}}
        )
        logger.info(f"Deployment scaled to {target_replicas} replicas")
    except Exception as e:
        pytest.fail(f"Failed to scale deployment: {str(e)}")


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

@then("the system should start scaling up the deployment")
def verify_scaling_up_started(k8s_client):
    """Verify that the deployment has started scaling up."""
    logger.info("Verifying scale-up operation has started...")
    apps_api = k8s_client("AppsV1Api")
    
    try:
        time.sleep(CONFIG['scaling']['interval'])
        deployment = apps_api.read_namespaced_deployment(
            name=CONFIG['gcs_fuse']['deployment_name'],
            namespace=CONFIG['gcs_fuse']['namespace']
        )
        assert deployment.status.replicas <= deployment.spec.replicas, \
            "Deployment is not in scaling up state"
        logger.info("Scale-up operation verified")
    except Exception as e:
        pytest.fail(f"Failed to verify scale-up operation: {str(e)}")

# @then("I should see new nodes being provisioned by the cluster autoscaler")
# def verify_node_provisioning(k8s_client):
#     """Verify that new nodes are being provisioned."""
#     logger.info("Verifying node provisioning...")
#     core_api = k8s_client("CoreV1Api")
#     initial_nodes = len(core_api.list_node().items)
#     timeout = time.time() + CONFIG['scaling']['node_provision_timeout']
#
#     try:
#         while time.time() < timeout:
#             current_nodes = len(core_api.list_node().items)
#             if current_nodes > initial_nodes:
#                 logger.info(f"New nodes provisioned: {current_nodes - initial_nodes}")
#                 return
#             time.sleep(CONFIG['scaling']['scale_check_interval'])
#         raise AssertionError("No new nodes were provisioned within timeout")
#     except Exception as e:
#         pytest.fail(f"Failed to verify node provisioning: {str(e)}")

@then("within configured timeout all pods should be running")
def verify_all_pods_running(k8s_client):
    """Verify all pods are running within the configured timeout."""
    logger.info("Verifying all pods are running...")
    core_api = k8s_client("CoreV1Api")
    timeout = time.time() + CONFIG['scaling']['scale_up_timeout']
    target_replicas = CONFIG['scaling']['max_replicas']
    
    try:
        while time.time() < timeout:
            pods = core_api.list_namespaced_pod(
                namespace=CONFIG['gcs_fuse']['namespace'],
                label_selector=f"app={CONFIG['gcs_fuse']['app_label']}"
            )
            running_pods = sum(1 for pod in pods.items if pod.status.phase == "Running")
            
            if running_pods == target_replicas:
                logger.info(f"All {target_replicas} pods are running")
                return
            
            logger.info(f"Current running pods: {running_pods}/{target_replicas}")
            time.sleep(CONFIG['scaling']['scale_check_interval'])
        
        raise AssertionError("Not all pods are running within timeout")
    except Exception as e:
        pytest.fail(f"Failed to verify running pods: {str(e)}")

@then("all pods should have access to the GCS FUSE mount point")
def verify_gcs_fuse_access(k8s_client):
    """Verify GCS FUSE mount access for all pods."""
    logger.info("Verifying GCS FUSE mount access...")
    core_api = k8s_client("CoreV1Api")
    
    try:
        pods = core_api.list_namespaced_pod(
            namespace=CONFIG['gcs_fuse']['namespace'],
            label_selector=f"app={CONFIG['gcs_fuse']['app_label']}"
        )
        
        from kubernetes.stream import stream
        
        for pod in pods.items:
            if pod.status.phase != "Running":
                continue
                
            exec_command = [
                "/bin/sh", 
                "-c", 
                f"ls {CONFIG['gcs_fuse']['mount_path']}"
            ]
            
            resp = stream(core_api.connect_get_namespaced_pod_exec,
                name=pod.metadata.name,
                namespace=CONFIG['gcs_fuse']['namespace'],
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            
            if resp.strip():
                logger.info(f"GCS FUSE mount verified in pod {pod.metadata.name}")
            else:
                raise AssertionError(f"Empty response from pod {pod.metadata.name} when checking mount point")
                
    except Exception as e:
        pytest.fail(f"Failed to verify GCS FUSE mount access: {str(e)}")

@then("the cluster should have sufficient nodes to handle the load")
def verify_cluster_capacity(k8s_client):
    """Verify cluster has sufficient capacity for all pods."""
    logger.info("Verifying cluster capacity...")
    core_api = k8s_client("CoreV1Api")
    
    try:
        nodes = core_api.list_node()
        total_capacity = sum(
            int(node.status.allocatable['cpu'].replace('m', '')) 
            for node in nodes.items
        )
        
        pods = core_api.list_namespaced_pod(
            namespace=CONFIG['gcs_fuse']['namespace']
        )
        total_requests = sum(
            int(container.resources.requests['cpu'].replace('m', ''))
            for pod in pods.items
            for container in pod.spec.containers
            if container.resources.requests 
            and 'cpu' in container.resources.requests
        )
        
        assert total_capacity >= total_requests, \
            "Cluster doesn't have sufficient CPU capacity"
        logger.info(f"Cluster capacity verified: {total_capacity}m CPU available, {total_requests}m CPU requested")
    except Exception as e:
        pytest.fail(f"Failed to verify cluster capacity: {str(e)}") 