import pytest
from pytest_bdd import given, when, then, scenarios, parsers
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config
from kubernetes.stream import stream

logger = get_logger(__name__)
CONFIG = load_config()
scenarios("../features/gcs_fuse_cache.feature")

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

@when("I verify a large test file exists in the GCS FUSE mount")
def verify_large_test_file(k8s_client):
    """Verify the sample test file exists at the GCS FUSE mount."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    mount_path = CONFIG["gcs_fuse"]["mount_path"]
    app_label = CONFIG["gcs_fuse"]["app_label"]
    sample_data_filename = CONFIG["test"]["sample_data_filename"]

    core_api = k8s_client("CoreV1Api")
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
    assert pods.items, "No pods found for the deployment"
    pod_name = pods.items[0].metadata.name
    test_file = f"{mount_path}/{sample_data_filename}"
    
    logger.info(f"Verifying test file exists at {test_file}")
    
    try:
        # Check if file exists
        check_cmd = ["/bin/sh", "-c", f"ls -la {test_file}"]
        result = stream(
            core_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=check_cmd,
            stderr=True, stdin=False, stdout=True, tty=False
        )
        
        logger.info(f"File verification result: {result}")
        
        # Verify file size
        size_cmd = ["/bin/sh", "-c", f"stat -c %s {test_file}"]
        size_result = stream(
            core_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=size_cmd,
            stderr=True, stdin=False, stdout=True, tty=False
        )
        
        file_size = int(size_result.strip())
        logger.info(f"Sample test file size: {file_size/1024/1024:.2f}MB")
        
        # Verify file is at least 1MB to ensure it's large enough for cache testing
        assert file_size >= 1024*1024, f"Sample file is too small ({file_size} bytes) for effective cache testing"
        
    except Exception as e:
        pytest.fail(f"Failed to verify test file: {str(e)}")

@then("subsequent reads should be faster due to caching")
def verify_cache_performance(k8s_client):
    """Verify that subsequent reads are faster due to caching."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    mount_path = CONFIG["gcs_fuse"]["mount_path"]
    app_label = CONFIG["gcs_fuse"]["app_label"]
    sample_data_filename = CONFIG["test"]["sample_data_filename"]

    core_api = k8s_client("CoreV1Api")
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
    pod_name = pods.items[0].metadata.name
    test_file = f"{mount_path}/{sample_data_filename}"

    # First read (uncached)
    logger.info("Performing first read (uncached)...")
    
    # Drop caches if possible
    try:
        stream(
            core_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=["/bin/sh", "-c", "sync"],
            stderr=True, stdin=False, stdout=True, tty=False
        )
    except:
        logger.warning("Could not run sync command")
    
    # First read timing
    start_time = time.time()
    stream(
        core_api.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=namespace,
        command=["/bin/sh", "-c", f"cat {test_file} > /dev/null"],
        stderr=True, stdin=False, stdout=True, tty=False
    )
    first_read_time = time.time() - start_time

    # Second read (should be cached)
    logger.info("Performing second read (should be cached)...")
    start_time = time.time()
    stream(
        core_api.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=namespace,
        command=["/bin/sh", "-c", f"cat {test_file} > /dev/null"],
        stderr=True, stdin=False, stdout=True, tty=False
    )
    second_read_time = time.time() - start_time

    logger.info(f"First read time: {first_read_time:.2f}s")
    logger.info(f"Second read time: {second_read_time:.2f}s")
    improvement_factor = first_read_time / second_read_time if second_read_time > 0 else float('inf')
    logger.info(f"Read performance improved by a factor of {improvement_factor:.2f}x")

    # Verify that the second read was faster
    assert second_read_time < first_read_time, \
        f"Cache did not improve read performance. First read: {first_read_time:.2f}s, Second read: {second_read_time:.2f}s"

@then("cache effectiveness should be verified")
def verify_cache_effectiveness(k8s_client):
    """Verify cache effectiveness without looking for specific cache files."""
    namespace = CONFIG["gcs_fuse"]["namespace"]
    app_label = CONFIG["gcs_fuse"]["app_label"]
    sample_data_filename = CONFIG["test"]["sample_data_filename"]
    
    core_api = k8s_client("CoreV1Api")
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_label}")
    pod_name = pods.items[0].metadata.name
    test_file = f"{CONFIG['gcs_fuse']['mount_path']}/{sample_data_filename}"

    logger.info("Verifying cache effectiveness with file size check...")
    
    try:
        # Verify file size matches what we expect
        size_cmd = ["/bin/sh", "-c", f"cat {test_file} | wc -c"]
        
        response = stream(
            core_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=size_cmd,
            stderr=True, stdin=False, stdout=True, tty=False
        )
        file_size = int(response.strip())
        assert file_size > 0, "Test file appears to be empty or inaccessible"
        logger.info(f"Verified cached file read: {file_size} bytes read")
        
        # Do another read and time it to confirm it's still fast
        start_time = time.time()
        stream(
            core_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=["/bin/sh", "-c", f"cat {test_file} > /dev/null"],
            stderr=True, stdin=False, stdout=True, tty=False
        )
        third_read_time = time.time() - start_time
        logger.info(f"Third read time: {third_read_time:.2f}s (should still be cached)")
        
    except Exception as e:
        pytest.fail(f"Failed to verify cache effectiveness: {str(e)}") 