<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# **Comprehensive Mandate for the Repair and Enhancement of the Project pytest Suite**

## **Preamble: Mission Objective and Guiding Principles**

Your primary directive is to conduct a thorough analysis of the pytest test suite located in the current project directory. You will identify all existing failures and execute a comprehensive repair and enhancement plan. The ultimate goal is to transform the current suite from a failing state into a robust, maintainable, and state-of-the-art testing asset that adheres to the highest standards of modern software engineering.

This mission is governed by a set of non-negotiable principles that must guide every action you take.

### **Guiding Principles**

1. **Preservation of Intent (Do No Harm):** Your actions must be fundamentally constructive. Under no circumstances shall you remove or diminish existing source code functionality to make a test pass. The functional intent of every test must be preserved or enhanced. You are explicitly forbidden from stubbing out failing tests with pass, trivial implementations, or marking them as expected failures (@pytest.mark.xfail) as a means of avoiding a fix. The objective is to repair underlying issues, not to circumvent them.
2. **Pursuit of Excellence:** The final, delivered test suite must exemplify the highest standards of modern Python development. This mandate encompasses strict static analysis, comprehensive documentation, optimal performance, and intelligent, resilient test design. Every line of test code you modify or create must contribute to a higher standard of quality.
3. **Systematic and Observable Process:** You must proceed through this mandate methodically and transparently. For each major phase of work—such as refactoring for parallel execution, implementing static type checking, or introducing new testing methodologies—you will describe the changes made and provide a clear rationale for your approach. This ensures that the evolution of the test suite is traceable and understandable.

## **Section 1: Foundational Quality and Style Requirements**

This section establishes the baseline code quality standards for all test code you modify or create. These are not suggestions; they are mandatory requirements that form the foundation of the enhanced test suite.

### **1.1. Static Type Analysis (mypy)**

**Requirement:** All new or modified test code must be fully and explicitly type-annotated in accordance with PEP 484. The final test suite, in its entirety, must pass mypy when run with a strict configuration.

**Implementation:** You will ensure the pyproject.toml file contains a \[tool.mypy] section with a comprehensive set of strict checks enabled. This configuration must include, but is not limited to, check\_untyped\_defs = true, disallow\_incomplete\_defs = true, warn\_unused\_ignores = true, warn\_return\_any = true, and no\_implicit\_optional = true.1 The primary goal of this configuration is to eliminate the implicit use of the

Any type, thereby maximizing the benefits of static analysis.

**Context:** Integrating strict type checking into the test suite is a strategic imperative for long-term maintainability and robustness. It prevents a wide class of runtime errors, clarifies the data structures and types expected by tests and fixtures, and makes the test suite itself a form of executable documentation.5 The

pytest-mypy plugin will be used to integrate these static analysis checks directly into the pytest execution pipeline, ensuring that type errors are treated as test failures.7 This proactive approach to type safety makes the test suite less brittle and significantly easier to refactor, as the type checker acts as a powerful safety net against the incorrect use of fixtures, helper functions, and mocked objects.

### **1.2. Linting and Code Style (pylint)**

**Requirement:** All new or modified test code must be free of pylint errors, warnings, and convention messages, as defined by the configuration specified in pyproject.toml.

**Implementation:** You will adhere to a pylint configuration that enforces Python best practices while remaining pragmatic for the specific context of test code. Certain pylint checks that are often counterproductive in tests may be disabled. These include protected-access (W0212), as tests frequently need to inspect the internal state of objects, and too-few-public-methods (R0903), which is not relevant for test classes that serve as organizational namespaces.8 The complete configuration will be specified within the

\[tool.pylint.\*] sections of the pyproject.toml file.9

**Context:** Consistent adherence to a high-quality linter configuration is essential for maintaining code readability and consistency, particularly in a collaborative development environment.10 By integrating

pylint checks directly into the test run via the pytest-pylint plugin, code quality becomes an automated and enforceable standard, preventing stylistic and conventional debt from accumulating in the test suite.12

### **1.3. Documentation Standards (Google Style)**

**Requirement:** All new or refactored functions, methods, and classes within the test suite must be documented with comprehensive docstrings that strictly adhere to the Google Python Style Guide.13

**Implementation:** Docstrings must be structured with a concise summary line, followed by a more detailed description where necessary. They must include the standard sections: Args:, Returns: (or Yields: for generator fixtures), and Raises:. Each argument in the Args: section should be listed with its name and a clear description. Since all code will be fully type-annotated per Section 1.1, the type information within the docstring is supplementary; the type hints in the function signature are the canonical source of truth. However, including types in docstrings can enhance readability and is permitted.15

**Context:** High-quality documentation is as critical for test code as it is for application code. Well-documented tests, fixtures, and helper functions are essential for long-term maintainability. They allow other developers to quickly understand the purpose of a test, the specific setup it requires, what conditions it verifies, and what exceptions it is expected to handle. This clarity is a cornerstone of a high-quality, professional test suite.

## **Section 2: Core Repair and Refactoring Protocol**

This section details the primary task of fixing the failing tests. The focus is not merely on making them pass, but on fundamentally re-architecting them for independence, parallelism, and maintainability.

### **2.1. Test Failure Triage and Root Cause Analysis**

**Requirement:** You must begin by executing the test suite to catalogue all failing tests. For each failure, you must perform a root cause analysis by examining the test's implementation, its dependencies, and the pytest traceback.

**Implementation:** Your repair strategy must address the underlying bug. This may involve correcting faulty logic within a test function, updating an assertion to reflect a valid and intentional change in the source code's behavior, or fixing a broken or misconfigured fixture. You are not to modify the application's source code unless a failure is unequivocally caused by a bug within that code, and fixing it is the only correct path forward. Your primary focus is the test suite itself.

### **2.2. Principles of Test Isolation for Parallel Execution (pytest-xdist)**

**Requirement:** The most critical refactoring task is to ensure every test is completely independent. Each test must be able to run in any order and concurrently with any other test without causing or being affected by side effects. The final, repaired suite must pass reliably when executed with pytest -n auto.17

**Implementation Protocol:** A systematic approach is required to achieve robust parallelization. A test that fails under parallel execution is merely a symptom of a deeper architectural flaw, such as shared state or an implicit dependency on execution order. You will follow this protocol to diagnose and resolve these flaws:

1. **Diagnose Order Dependencies:** The first step is to uncover and eliminate any implicit dependencies on test execution order. To do this, you will integrate the pytest-random-order plugin and run the suite with the --random-order flag. Failures that appear under this randomized execution, but not under sequential execution, are direct evidence of order dependencies.17 You must resolve these issues by making each test fully self-contained, ensuring it sets up its own state and does not rely on the artifacts of a previously run test.
2. **Identify and Eliminate Shared State:** After resolving order dependencies, you must scrutinize the test suite for any shared resources that could create race conditions or state corruption when accessed concurrently. Common sources of shared state include:
   * **Filesystem:** Any test that reads from or writes to a hardcoded file path is not parallel-safe. These tests must be refactored to use the built-in tmp\_path fixture. This fixture provides a unique, empty temporary directory for each test function, guaranteeing filesystem isolation.21
   * **Database:** Tests that modify a shared database are a primary source of flakiness in parallel runs. These must be refactored to ensure complete isolation. This can be achieved by ensuring each test runs within its own database transaction that is rolled back upon completion, or by using fixtures that create and tear down a unique test database or schema for each test worker.
   * **Global State:** Any test that relies on or modifies mutable global variables, module-level state, or class-level state is inherently unsafe for parallel execution. This pattern must be eliminated entirely. All state required by a test must be created and managed within the scope of that test, typically via fixtures.

### **2.3. Refactoring for Maintainability (DRY Principle)**

**Requirement:** You must actively seek out and eliminate code duplication throughout the entire test suite, adhering to the "Don't Repeat Yourself" (DRY) principle.

**Implementation:**

* **Helper Functions:** Identify any repeated patterns of logic within your tests. This could include complex object instantiation, multi-step data preparation, or recurring sequences of validation checks. Extract this logic into well-documented, fully-typed helper functions. These functions should be organized into a dedicated module, such as tests/helpers.py, to create a reusable library of testing utilities.22
* **Shared Fixtures (conftest.py):** Identify common setup and teardown procedures that are used across multiple tests. These are ideal candidates for conversion into shared fixtures. Place these fixtures in the appropriate conftest.py file to make them available to the relevant tests. You must use fixture scopes (function, class, module, session) judiciously to optimize test suite performance.23 For example, an expensive, read-only resource like a database connection pool can be session-scoped to be created only once. In contrast, a fixture that provides a specific piece of mutable test data for a single test should be function-scoped to ensure isolation.

## **Section 3: Implementation of Advanced pytest Tooling**

This section mandates the integration of specific pytest plugins to elevate the quality, robustness, and diagnostic capabilities of the test suite.

### **3.1. Comprehensive Assertion with pytest-check**

**Requirement:** Refactor tests to report all assertion failures within a single test run, rather than stopping at the first failure.

**Implementation:** You will identify test functions that perform multiple, independent checks on a single object or state. These tests must be refactored to use the pytest-check plugin. For clarity and readability, you should prefer using the explicit helper functions provided by the plugin (e.g., check.equal(), check.is\_in(), check.greater()). For more complex or custom validation logic that cannot be expressed with the built-in helpers, you may use the with check: context manager.35

**Context:** Standard assert statements cause a test to fail and exit immediately. This can hide other potential failures within the same test, leading to a slow, iterative process of fixing one issue, re-running the tests, and only then discovering the next. By using pytest-check, you gather a comprehensive list of all failures in a single run, providing much richer diagnostic feedback and accelerating the debugging cycle.35

### **3.2. Managing External Dependencies and I/O**

**Requirement:** All tests must be fully deterministic and completely independent of the availability or state of external services and non-deterministic data generation.

**Implementation - A Two-Pronged Approach:** The user's intent for deterministic I/O will be fulfilled by using the correct tool for each specific job: one for network interactions and another for validating deterministic data outputs.

1. **Network Operations (pytest-recording):** For all tests that make external HTTP or HTTPS requests, you will use the pytest-recording plugin, which provides a seamless integration for vcrpy. On the first execution of such a test, the plugin will perform the real network request and record the full interaction (request and response) into a human-readable YAML file known as a "cassette." On all subsequent test runs, the plugin will intercept the network call and replay the saved response from the cassette, eliminating any dependency on the network or the external service. This ensures tests are fast, repeatable, and can run offline. A critical part of this implementation is configuring pytest-recording to filter sensitive data, such as Authorization headers or API keys, from the cassettes before they are saved. This prevents secrets from being committed to version control.36
2. **Deterministic File/Data Output (pytest-snapshot):** For tests that generate complex but deterministic output—such as a large JSON object, an XML file, a CSV, or a formatted text report—you will use the pytest-snapshot plugin. This plugin captures the expected output in a separate snapshot file. On subsequent runs, it compares the new output to the saved snapshot. If there are any differences, the test fails. This is an exceptionally powerful technique for regression testing of data transformation pipelines, serializers, or any function that produces complex, structured output.36

### **3.3. Enforcing Performance with pytest-timeout**

**Requirement:** No single test execution, including its associated setup and teardown phases, should exceed a 15-second time limit.

**Implementation:** You will configure the pytest-timeout plugin to enforce a global timeout of 15 seconds for every test. This configuration will be set in the pyproject.toml file. In the rare event that a specific test legitimately requires more time to execute (for example, a complex end-to-end integration test), you may apply a local override using the @pytest.mark.timeout() decorator on that specific test function. However, any such override must be accompanied by a source code comment that clearly justifies the need for an extended timeout.45

**Context:** This strict performance requirement serves as a critical safeguard for the CI/CD pipeline. It prevents hung, deadlocked, or inefficiently written tests from stalling the entire test run, thereby ensuring that developers receive rapid feedback on their changes.46

## **Section 4: Strategic Expansion of Test Coverage**

Beyond repairing existing tests, you are tasked with strategically expanding the test suite using advanced methodologies. The goal is to improve not just the quantity but the quality of test coverage, with the aspirational target of 100% code coverage.

### **4.1. Behavior-Driven Development with pytest-bdd**

**Requirement:** Where appropriate, you will introduce new Behavior-Driven Development (BDD) tests to explicitly link the application's behavior to its requirements.

**Implementation:**

* **Candidate Identification:** You will analyze the application's functionality to identify user-facing features, complex business logic workflows, or API endpoints that would benefit from being described in plain, unambiguous language. You will use the **Test Strategy Selection Guide** (Table 1) below to make these decisions.
* **Structure:** New BDD tests will be organized according to best practices. You will create a tests/features/ directory to house the Gherkin .feature files and a corresponding tests/step\_defs/ directory for the Python step definition implementation files.48
* **Gherkin Scenarios:** Within the .feature files, you will write clear, declarative scenarios using the standard Gherkin syntax (Given, When, Then). These scenarios should describe a feature from the perspective of a user or stakeholder.49
* **Step Definitions:** You will implement the Python functions that correspond to each Gherkin step. A key aspect of this implementation is to maximize code reuse by leveraging existing fixtures from the test suite for setting up the state described in the Given steps.

### **4.2. Property-Based Testing with hypothesis**

**Requirement:** Where appropriate, you will add new property-based tests to automatically discover edge cases and bugs in data processing and validation logic.

**Implementation:**

* **Candidate Identification:** You will identify functions within the codebase that are pure or semi-pure and perform data processing, parsing, validation, or mathematical calculations. These functions are prime candidates for property-based testing. You will use the **Test Strategy Selection Guide** (Table 1) below to make these decisions.
* **Property Definition:** For each candidate function, you will define a "property"—an invariant or a rule that should hold true for all valid inputs. For example, a property of a serialization function might be that "for any valid input object x, deserialize(serialize(x)) is equal to x".
* **Strategies:** You will use the hypothesis.strategies module to define how to generate a wide range of valid (and sometimes invalid) input data for the function under test. You should use Hypothesis's rich library of built-in strategies (st.integers(), st.text(), st.builds(), etc.) wherever possible to cover a vast input space with minimal code.53

Deciding when to use a standard test versus a more advanced methodology like BDD or property-based testing is crucial for building an effective and maintainable test suite. A standard test is excellent for verifying a single, known condition. BDD excels at describing and testing multi-step user behaviors. Hypothesis is unparalleled at finding unknown edge cases in data-handling logic. The following guide provides a clear heuristic framework for selecting the most appropriate testing strategy for a given scenario.

### **Table 1: Test Strategy Selection Guide**

| Test Type                | Primary Goal                                                                                            | Use When...                                                                                                                                                 | Example Scenario                                                                                                                       |
| :----------------------- | :------------------------------------------------------------------------------------------------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------- |
| **Standard pytest Test** | Verify a specific, known outcome for a single unit of code.                                             | You are testing a single, well-defined input-output pair or a specific error condition.                                                                     | def test\_add\_positive\_numbers(): assert add(2, 3) == 5                                                                                 |
| **pytest-bdd**           | Document and verify application behavior from a user or stakeholder perspective.                        | The functionality represents a user story or a business rule that can be described in plain language. The test covers a multi-step interaction.             | Testing a login flow: Given a user is on the login page, When they enter valid credentials, Then they are redirected to the dashboard. |
| **hypothesis**           | Discover edge cases and bugs by testing properties of a function across a wide range of generated data. | The function performs data processing, parsing, validation, or mathematical calculations. You want to ensure its logic is robust against unexpected inputs. | Testing a sort() function: "For any list of integers L, the output sort(L) should have the same length as L and be ordered."           |

## **Section 5: Project Configuration and Final Verification**

This final section details the necessary configuration changes to the project's pyproject.toml file and outlines the final verification steps you must perform to ensure all requirements of this mandate have been successfully met.

### **5.1. pyproject.toml Management**

**Requirement:** All project dependencies, build configurations, and tool settings must be consolidated within the pyproject.toml file, establishing it as the single source of truth for the project's configuration.

**Implementation:**

1. **Dependencies:** You will add all new testing dependencies—including pytest-check, pytest-recording, pytest-bdd, hypothesis, pytest-random-order, and pytest-sugar—to the \[project.optional-dependencies] table under the test key. This ensures that all tools required to run the test suite are clearly declared and can be installed with a single command.55
2. **Tool Configuration:** You will populate the pyproject.toml file with the comprehensive tool configurations detailed in the table below. This centralized approach to configuration is a modern Python best practice that improves project clarity and maintainability.59

### **Table 2: pyproject.toml Tool Configuration**

Ini, TOML

\[tool.pytest.ini\_options]\
\# Add common pytest command-line options to be used by default.\
addopts =

\# Set the default timeout for all tests to 15 seconds.\
timeout = 15

\# Configure test discovery to look only in the 'tests' directory.\
testpaths = \["tests"]

\# Register custom markers to avoid warnings and enable selective runs.\
markers =

\[tool.mypy]\
\# Specify the source directory for type checking.\
mypy\_path = "src"

\# Enable a strict suite of type checking options for maximum safety.\
check\_untyped\_defs = true\
disallow\_any\_generics = true\
disallow\_incomplete\_defs = true\
disallow\_untyped\_defs = true\
ignore\_missing\_imports = true # A pragmatic choice for projects with untyped 3rd-party dependencies.\
no\_implicit\_optional = true\
warn\_redundant\_casts = true\
warn\_return\_any = true\
warn\_unused\_ignores = true

\# Include error codes in output for easier debugging and suppression.\
show\_error\_codes = true

\# Disable messages that are often noisy or counterproductive in a pytest suite.\
disable =

\# Allow short variable names that are common and idiomatic in test contexts.\
good-names = \["i", "j", "k", "e", "f", "db", "ex"]

### **5.2. Final Verification and Execution**

**Requirement:** Before concluding your work, you must perform a final, comprehensive verification run to ensure all objectives have been met and the test suite is in a fully operational and enhanced state.

**Implementation:**

1. **Install Dependencies:** From the project root, execute uv pip install -e.\[test]. This command will use the newly configured pyproject.toml to create an editable install of the project and install all required testing dependencies into the virtual environment.
2. **Execute Full Suite:** Run the complete, enhanced test suite using the command uv run pytest. This command must execute without any command-line arguments (relying on the pyproject.toml configuration) and must exit with a status code of 0. A zero exit code signifies that all tests passed, including all integrated mypy and pylint checks.
3. **Self-Correction Checklist:** You must perform a final review of your changes against every requirement detailed in this document. If any requirement has not been fully and correctly met, you must iterate on your solution until it is 100% compliant.
4. **Final Report:** As your final output, provide a concise summary of the fixes implemented, the refactoring performed, and the enhancements and new tests that have been added to the suite.
