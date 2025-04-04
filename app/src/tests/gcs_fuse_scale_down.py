import pytest
from pytest_bdd import given, when, then, scenarios
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config

logger = get_logger(__name__)
CONFIG = load_config()
scenarios("../features/gcs_fuse_scale_down.feature")

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

@given('the deployment "gcs-fuse" is running with maximum replicas')
def verify_max_replicas_running(k8s_client):
    """Verify deployment is running with maximum replicas and scale up if needed."""
    logger.info("Verifying deployment is at maximum replicas...")
    apps_api = k8s_client("AppsV1Api")
    max_replicas = CONFIG['scaling']['max_replicas']
    min_replicas = CONFIG['scaling']['min_replicas']
    
    try:
        deployment = apps_api.read_namespaced_deployment(
            name=CONFIG['gcs_fuse']['deployment_name'],
            namespace=CONFIG['gcs_fuse']['namespace']
        )
        current_replicas = deployment.spec.replicas

        if current_replicas == min_replicas:
            logger.info(f"Current replicas ({current_replicas}) equals minimum replicas. Skipping scale up.")
            pytest.skip("Deployment already at minimum replicas, skipping scale down test")
        elif current_replicas < max_replicas:
            logger.info(f"Current replicas ({current_replicas}) less than maximum ({max_replicas}). Scaling up first...")
            
            # Scale up to max replicas
            apps_api.patch_namespaced_deployment_scale(
                name=CONFIG['gcs_fuse']['deployment_name'],
                namespace=CONFIG['gcs_fuse']['namespace'],
                body={"spec": {"replicas": max_replicas}}
            )
            
            # Wait for pods to be ready
            timeout = time.time() + CONFIG['scaling']['scale_up_timeout']
            while time.time() < timeout:
                pods = k8s_client("CoreV1Api").list_namespaced_pod(
                    namespace=CONFIG['gcs_fuse']['namespace'],
                    label_selector=f"app={CONFIG['gcs_fuse']['app_label']}"
                )
                running_pods = sum(1 for pod in pods.items if pod.status.phase == "Running")
                
                if running_pods == max_replicas:
                    logger.info(f"Successfully scaled up to {max_replicas} replicas")
                    return
                
                logger.info(f"Waiting for pods to be ready: {running_pods}/{max_replicas}")
                time.sleep(CONFIG['scaling']['scale_check_interval'])
                
            raise AssertionError(f"Timeout waiting for pods to scale up to {max_replicas}")
        else:
            logger.info(f"Deployment already at maximum replicas ({max_replicas})")
            
    except Exception as e:
        pytest.fail(f"Failed to verify maximum replicas: {str(e)}")

@when("I scale down the deployment to minimum replicas")
def scale_down_deployment(k8s_client):
    """Scale down the deployment to minimum replicas."""
    logger.info("Scaling down deployment...")
    apps_api = k8s_client("AppsV1Api")
    min_replicas = CONFIG['scaling']['min_replicas']
    
    try:
        apps_api.patch_namespaced_deployment_scale(
            name=CONFIG['gcs_fuse']['deployment_name'],
            namespace=CONFIG['gcs_fuse']['namespace'],
            body={"spec": {"replicas": min_replicas}}
        )
        logger.info(f"Deployment scaled down to {min_replicas} replicas")
    except Exception as e:
        pytest.fail(f"Failed to scale down deployment: {str(e)}")

@then("the system should start terminating excess pods")
def verify_pod_termination(k8s_client):
    """Verify that excess pods are being terminated."""
    logger.info("Verifying pod termination...")
    core_api = k8s_client("CoreV1Api")
    
    try:
        # Get initial pod count
        initial_pods = core_api.list_namespaced_pod(
            namespace=CONFIG['gcs_fuse']['namespace'],
            label_selector=f"app={CONFIG['gcs_fuse']['app_label']}"
        )
        initial_count = len(initial_pods.items)
        logger.info(f"Initial pod count: {initial_count}")
        
        # Wait and check multiple times for pod termination
        max_retries = 10
        retry_interval = CONFIG['scaling']['interval']
        
        for attempt in range(max_retries):
            time.sleep(retry_interval)
            
            current_pods = core_api.list_namespaced_pod(
                namespace=CONFIG['gcs_fuse']['namespace'],
                label_selector=f"app={CONFIG['gcs_fuse']['app_label']}"
            )
            current_count = len(current_pods.items)
            
            # Check for terminating pods
            terminating_pods = sum(
                1 for pod in current_pods.items 
                if pod.metadata.deletion_timestamp is not None
            )
            
            logger.info(f"Attempt {attempt + 1}: Current pods={current_count}, Terminating={terminating_pods}")
            
            if current_count < initial_count or terminating_pods > 0:
                logger.info(f"Pod termination verified: {initial_count - current_count} pods terminated, "
                          f"{terminating_pods} pods terminating")
                return
        
        raise AssertionError(
            f"Pods are not being terminated after {max_retries} attempts. "
            f"Initial count: {initial_count}, Current count: {current_count}"
        )
        
    except Exception as e:
        pytest.fail(f"Failed to verify pod termination: {str(e)}")

@then("the cluster autoscaler should gradually remove unused nodes")
def verify_node_removal(k8s_client):
    """Verify that unused nodes are being removed."""
    logger.info("Verifying node removal...")
    core_api = k8s_client("CoreV1Api")
    initial_nodes = len(core_api.list_node().items)
    timeout = time.time() + CONFIG['scaling']['scale_down_timeout']
    
    try:
        while time.time() < timeout:
            current_nodes = len(core_api.list_node().items)
            if current_nodes < initial_nodes:
                logger.info(f"Nodes reduced from {initial_nodes} to {current_nodes}")
                return
            time.sleep(CONFIG['scaling']['scale_check_interval'])
        raise AssertionError("Nodes were not removed within timeout")
    except Exception as e:
        pytest.fail(f"Failed to verify node removal: {str(e)}")

@then("within configured timeout minimum pods should be running")
def verify_min_pods_running(k8s_client):
    """Verify minimum number of pods are running within timeout."""
    logger.info("Verifying minimum pods are running...")
    core_api = k8s_client("CoreV1Api")
    timeout = time.time() + CONFIG['scaling']['scale_down_timeout']
    min_replicas = CONFIG['scaling']['min_replicas']
    
    try:
        while time.time() < timeout:
            pods = core_api.list_namespaced_pod(
                namespace=CONFIG['gcs_fuse']['namespace'],
                label_selector=f"app={CONFIG['gcs_fuse']['app_label']}"
            )
            running_pods = sum(1 for pod in pods.items if pod.status.phase == "Running")
            
            if running_pods == min_replicas:
                logger.info(f"Reached target minimum pods: {min_replicas}")
                return
            
            logger.info(f"Current running pods: {running_pods}/{min_replicas}")
            time.sleep(CONFIG['scaling']['scale_check_interval'])
        
        raise AssertionError(f"Failed to scale down to {min_replicas} pods within timeout")
    except Exception as e:
        pytest.fail(f"Failed to verify minimum pods running: {str(e)}")

@then("all remaining pods should still have access to the GCS FUSE mount point")
def verify_gcs_fuse_access(k8s_client):
    """Verify GCS FUSE mount access for all remaining pods."""
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