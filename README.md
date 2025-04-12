# GCS FUSE Integration Tests

This repository contains automated tests for verifying GCS FUSE CSI Driver functionality in a GKE cluster using Python and pytest-bdd.

## Overview

The test suite verifies:
1. GCS FUSE CSI Driver installation and functionality
2. Mount directory permissions and operations
3. Pod deployment with GCS FUSE volumes

## Test Scenarios

### 1. GCS FUSE Driver Verification
- Checks if the GKE cluster is accessible
- Verifies GCS FUSE CSI driver pods are running in kube-system namespace
- Confirms all containers in driver pods are ready (3/3)

### 2. Mount Directory Permissions
- Checks read permissions on mounted directory
- Verifies write permissions on mounted directory
- Tests actual file operations (create, read, write, delete)

### 3. Multi-Pod Mount Verification
- Verifies mount accessibility across multiple pods
- Tests file sharing between pods
- Validates concurrent access capabilities

### 4. Write-Read Operations
- Tests file creation and writing
- Verifies file reading capabilities
- Ensures data consistency across operations

### 5. Performance Metrics Verification
- Monitors IOPS (Input/Output Operations per Second)
- Tracks throughput for read operations
- Measures latency of file operations
- Monitors error rates

## Prerequisites

1. Access to a GKE cluster with GCS FUSE CSI Driver installed
2. Python 3.7 or higher
3. kubectl configured with access to your cluster
4. Required Python packages (see requirements.txt)

## Project Structure

```bash
app/
├── config/
│   └── settings.toml         # Configuration settings
├── src/
│   ├── features/            # BDD feature files
│   │   └── gcs_fuse_driver_verification.feature
│   ├── tests/              # Test implementations
│   │   └── gcs_fuse_driver_verification.py
│   └── utils/              # Utility modules
│       ├── k8s_client.py
│       ├── config_util.py
│       └── logging_util.py
├── requirements.txt
└── README.md
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd gcs-bdd
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set PYTHONPATH:
```bash
# Linux/Mac
export PYTHONPATH=./app:$PYTHONPATH

# Windows
set PYTHONPATH=.\app;%PYTHONPATH%
```

## Configuration

Update `config/settings.toml` with your environment settings:

```toml
[gcs_fuse]
namespace = "default"
deployment_name = "gcs-fuse"
app_label = "gcs-fuse-csi-example"
mount_path = "/data"
driver_namespace = "kube-system"
replicas = 2
retry_count = 5
retry_interval = 5
```

## Running the Tests

1. Ensure your kubectl context is set to the correct cluster:
```bash
kubectl config current-context
```

2. Run all tests:
```bash
cd app
pytest src/tests/ -v --log-cli-level=INFO
```

3. Run specific test scenarios:
```bash
# Run only driver verification tests
pytest src/tests/gcs_fuse_driver_verification.py -v -k "driver"

# Run only mount permission tests
pytest src/tests/test_gcs_fuse_mount_feature.py -v -k "mount"

# Run multi-pod tests
pytest src/tests/test_gcs_fuse_multi_pod_mount_feature.py -v

# Run write-read tests
pytest src/tests/test_gcs_fuse_write_read_feature.py -v
```

## Test Reports

1. Install pytest-html:
```bash
pip install pytest-html
```

2. Generate HTML test report:
```bash
mkdir -p reports
pytest src/tests/ --html=reports/report.html --self-contained-html
```

## Common Issues and Troubleshooting

### 1. Pod Access Issues
- Verify RBAC permissions
- Check kubectl configuration
- Ensure correct namespace settings

### 2. Mount Permission Issues
- Verify GCS bucket permissions
- Check pod security context
- Validate service account permissions

### 3. Driver Pod Issues
- Check kube-system namespace for driver pods
- Verify node pool configuration
- Check pod logs for errors

### 4. Import Issues
- Verify PYTHONPATH is set correctly
- Check virtual environment activation
- Validate package installations

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Support

For issues and support:
- Create an issue in the repository
- Contact the maintainers

---

**Note:** This test suite is designed to verify the proper installation and functionality 
of the GCS FUSE CSI Driver in your GKE environment. Please ensure all prerequisites 
are met before running the tests.


