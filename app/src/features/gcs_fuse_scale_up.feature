Feature: GCS FUSE Scale Up Tests GKE

  Scenario: Scale up GCS FUSE deployment with cluster autoscaling
    Given a GKE cluster is running
    And a deployment named "gcs-fuse" exists in the "default" namespace
    And the cluster autoscaler is configured properly

    When I scale the "gcs-fuse" deployment to configured target replicas
    Then the system should start scaling up the deployment
    And within configured timeout all pods should be running
    And all pods should have access to the GCS FUSE mount point
    And the cluster should have sufficient nodes to handle the load