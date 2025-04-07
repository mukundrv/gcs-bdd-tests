Feature: GCS FUSE Mount GKE Integration

  Scenario: Mounting GCS FUSE on a GKE pod
    Given a GKE cluster is running
    And a deployment named "gcs-fuse" exists in the "default" namespace
    When the deployment starts
    Then the GCS FUSE mount should be accessible 