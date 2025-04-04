Feature: GCS FUSE Scale Down Tests GKE

  Scenario: Scale down GCS FUSE deployment with cluster autoscaling
    Given a GKE cluster is running
    And a deployment named "gcs-fuse" exists in the "default" namespace
    And the cluster autoscaler is configured properly
    And the deployment "gcs-fuse" is running with maximum replicas
    When I scale down the deployment to minimum replicas
    Then the system should start terminating excess pods
    And within configured timeout minimum pods should be running
    And all remaining pods should still have access to the GCS FUSE mount point
