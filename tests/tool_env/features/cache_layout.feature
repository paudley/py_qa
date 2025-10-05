Feature: Tool cache respects project roots

  Scenario: Working inside the py_qa repository root
    Given a simulated py_qa repository root
    When command preparation runs with the repository root
    Then tool caches are created underneath the expected root
    And no tool cache directories exist under the forbidden paths

  Scenario: Running in an external host project
    Given an external project workspace
    When command preparation runs with the external project root
    Then tool caches are created underneath the expected root
    And no tool cache directories exist under the forbidden paths

  Scenario: Root overridden to a writable mount
    Given a container mount workspace
    When command preparation runs with the overridden root
    Then tool caches are created underneath the expected root
    And no tool cache directories exist under the forbidden paths

  Scenario: Running from inside the py_qa src tree
    Given a simulated py_qa repository root
    When command preparation runs from a repository subdirectory but with the repository root
    Then tool caches are created underneath the expected root
    And no tool cache directories exist under the forbidden paths
