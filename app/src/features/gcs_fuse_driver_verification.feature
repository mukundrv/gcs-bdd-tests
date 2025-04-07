Feature: GCS FUSE Driver Verification

  Scenario: Verifying GCS FUSE CSI driver is enabled on GKE cluster
    Given a GKE cluster is running
    Then the GCS FUSE CSI driver should be installed on the cluster
    And all GCS FUSE CSI node pods should be running with all containers ready 