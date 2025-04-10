Feature: GCS FUSE Cache Functionality

  Scenario: Verify GCS FUSE cache improves read performance
    Given a GKE cluster is running
    And a deployment named "gcs-fuse" exists in the "default" namespace
    When I verify a large test file exists in the GCS FUSE mount
    Then subsequent reads should be faster due to caching
    And cache effectiveness should be verified