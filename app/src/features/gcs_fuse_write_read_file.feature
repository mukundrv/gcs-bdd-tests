Feature: GCS FUSE Write and Read File

  Scenario: Verify GCS FUSE mount supports read and write operations
    Given a GKE cluster is running
    And a deployment named "gcs-fuse" exists in the "default" namespace
    When the deployment starts
    Then a file can be written to and read from the GCS FUSE mount