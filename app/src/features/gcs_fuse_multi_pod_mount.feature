Feature: GCS FUSE Multi Pod Mount GKE

  Scenario: Mounting GCS FUSE on multiple GKE pods and they all can access to the mount point
    Given a GKE cluster is running
    And a deployment named "gcs-fuse" exists in the "default" namespace
    When the deployment starts
    Then the GCS FUSE mount should be accessible by all pods in the deployment
