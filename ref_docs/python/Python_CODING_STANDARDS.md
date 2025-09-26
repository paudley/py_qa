<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# **Python 3.12 Code Generation Guidelines**

## **Foundational Principles**

These guidelines establish a non-negotiable framework for generating Python code. They are designed to produce software that is not only functional but also provably correct, robust, and maintainable. All generated code must adhere to these foundational principles without exception.

### **The Four Pillars of Code Generation**

Every line of code generated must be built upon four pillars, which collectively ensure the highest quality standards.

1. **Strictness**: All code must be provably correct through static analysis. Ambiguity is considered an error. This principle is enforced through mandatory compliance with mypy --strict 1 and a zero-tolerance policy for
   pylint warnings.2 The goal is to eliminate an entire class of runtime errors before the code is ever executed.
2. **Explicitness**: Code must be self-documenting. Dependencies, data contracts, and control flow must be immediately obvious from reading the code itself. This aligns with the "Zen of Python" principle, "Explicit is better than implicit" 3, and is the primary justification for forbidding ambiguous patterns like
   typing.Any.
3. **Robustness**: Code must anticipate and gracefully handle failure, especially at system boundaries where it interacts with external data or services. This principle mandates the use of robust parsing libraries like tolerantjson 4 and data validation frameworks like Pydantic 5 to create a secure perimeter around the core application logic.
4. **Testability**: All code must be designed for complete, automated verification. Testability is a primary design constraint, not an afterthought. This is enforced by the mandate for 100% test coverage, which in turn dictates specific architectural patterns.6

The interaction between these pillars is more important than any single rule. For instance, the requirement for 100% test coverage is nearly impossible to achieve for code that tightly couples its components, such as a function that directly instantiates a database connection within its own body.7 This strict testing requirement serves as a forcing function; it makes brittle patterns difficult or impossible to implement correctly, thereby compelling the adoption of superior, decoupled architectural patterns. To achieve full test coverage, components must be testable in isolation. This isolation is most effectively achieved through decoupling, and the designated pattern for this is Dependency Injection.6 Therefore, the 100% test coverage rule implicitly mandates Dependency Injection as a core architectural pattern. The system is designed so that the only path to compliance is through high-quality design.

## **Project and Codebase Structure**

A predictable and consistent project structure is critical for maintainability and reduces the cognitive load for both human developers and other automated systems. The following layout is mandatory.

### **The src Layout Mandate**

All application source code MUST reside within a src directory. This standard practice prevents common Python path and packaging issues and creates a clean separation between the installable source code and project-level configuration files like pyproject.toml.9

An example project structure is as follows:

project\_name/
├──.gitignore
├── pyproject.toml # Central tool configuration
├── README.md
├── src/
│ └── my\_package/
│ ├── \_\_init\_\_.py
│ ├── api/
│ │ ├── \_\_init\_\_.py
│ │ └── endpoints.py
│ ├── core/
│ │ ├── \_\_init\_\_.py
│ │ └── logic.py
│ └── models/
│ ├── \_\_init\_\_.py
│ └── data\_models.py
├── tests/
│ ├── \_\_init\_\_.py
│ ├── test\_logic.py
│ └── test\_endpoints.py
└── scripts/
└── task.py

This structure provides a clear separation of concerns 10, where API definitions (

api/), business logic (core/), and data models (models/) are physically segregated to prevent the creation of monolithic, unmaintainable files.11 The

tests/ directory mirrors the structure of the src/ directory, ensuring a logical mapping between code and its tests.13

### **Naming Conventions**

Adherence to consistent naming conventions is required for readability and predictability.14

* **Packages and Modules**: Use lower\_case\_with\_underscores. Names must be short and descriptive. Dashes (-) are forbidden in module names.11
* **Classes**: Use CapWords (also known as CamelCase).14
* **Functions, Methods, and Variables**: Use lower\_case\_with\_underscores.14
* **Constants**: Use ALL\_CAPS\_WITH\_UNDERSCORES.14
* **Test Files and Functions**: Files must be prefixed with test\_ (e.g., test\_logic.py). Test functions within those files must also be prefixed with test\_.2

### **Modularity and File Size**

To ensure maintainability, code must be modular.

* **File Size**: Source files MUST NOT exceed 2000 lines of code. This is a hard limit.
* **Function Size**: Functions must be small and adhere to the Single Responsibility Principle.15 If a function's logic becomes complex, it MUST be refactored into smaller, private helper functions (e.g.,
  \_helper\_function).
* **Module Cohesion**: Modules must be highly cohesive, grouping related functionality. For instance, all Pydantic models related to a specific domain (e.g., "user") should be grouped in a dedicated module like src/my\_package/models/user\_models.py.11

## **Static Analysis and Type System**

Code correctness is ensured through a rigorous static analysis process. The following rules are the most critical in these guidelines and allow for no deviation.

### **pylint for Code Quality**

All code must pass pylint with zero warnings or errors. The configuration will be based on the Google Python Style Guide's recommendations 2 but adapted for modern tooling, such as setting the max line length to 88 characters to align with the

black code formatter.19

### **mypy for Strict Type Safety**

All code MUST be statically type-checked with mypy --strict enabled.1 This is the cornerstone of the "Strictness" principle. The

mypy.ini configuration file will enforce this flag along with others, such as warn\_redundant\_casts and warn\_unused\_ignores, to maintain a clean and precise typescape.20

### **The No-Any, No-Union Mandate**

To ensure the integrity of the type system, certain ambiguous type hints are strictly forbidden.

* **Prohibition of typing.Any**: The Any type is forbidden. It acts as an escape hatch that silently disables type checking, violating the principles of Strictness and Explicitness.20 Instead, one of the following explicit alternatives MUST be used.
* **Prohibition of typing.Union / |**: The Union type is forbidden for defining collections of different complex object types. This pattern leads to brittle conditional logic (if isinstance(...)) scattered throughout the codebase, making it difficult to maintain and reason about. Specific, more robust alternatives are required.

The type system should be used as a design tool to create explicit data contracts and state machines. For example, a function signature like def process(data: Union) creates a weak contract that forces the implementation to perform runtime checks. A superior approach is to model this as a Pydantic discriminated union, where a common field (e.g., animal\_type: Literal\['cat', 'dog']) is used to distinguish between models. Pydantic handles the validation, and the application logic can use pattern matching (match animal: case Cat():...) on a guaranteed, unambiguous type. This moves the state-checking logic to the data validation boundary, where it belongs.

The following table provides a non-negotiable mapping of forbidden types to their mandatory alternatives.

| Forbidden Type                     | Reason for Prohibition                                                        | Recommended Alternative(s)                                                                                                   | Example                                         |
| :--------------------------------- | :---------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------- |
| typing.Any                         | Defeats static analysis; creates type holes that hide bugs.                   | typing.TypeVar (for generics), typing.Protocol (for structural contracts), object (with mandatory isinstance checks).        | def process(item: T) -> T:                      |
| typing.Union (for complex objects) | Creates ambiguous branching logic (if/else on type); promotes weak contracts. | Pydantic Discriminated Unions (using Literal), typing.Literal (for simple values), or separate functions for distinct types. | class Model(BaseModel): type: Literal\['a', 'b'] |

### **Mandatory Use of Final and Literal**

To further enhance the principles of Strictness and Explicitness, the use of typing.Final and typing.Literal is mandatory wherever applicable.

* **typing.Final for Constants**: Any variable that is not intended to be reassigned after its initial declaration MUST be marked as Final. This applies to all module-level and class-level constants. While Python's convention is to use ALL\_CAPS for constants, typing.Final provides a contract that static type checkers like mypy will enforce, preventing accidental reassignment.21 This transforms a style convention into a verifiable rule.
  Python
  \# MANDATORY PATTERN
  from typing import Final

  API\_ENDPOINT: Final\[str] = "https://api.example.com/v1"
  TIMEOUT\_SECONDS: Final = 30 # Type is inferred as Literal\[21]

  Note that Final only prevents the name from being re-bound; it does not make the assigned value immutable. For mutable collections, use immutable counterparts (e.g., tuple instead of list) where appropriate.21

* **typing.Literal for Specific Choices**: When a function argument or variable is expected to be one of a fixed set of specific string or integer values, typing.Literal MUST be used instead of str or int. This provides a much more precise contract than a simple type hint and allows static analysis tools to catch errors if an invalid value is used.32 It is superior to using enums for simple value sets as it works directly with primitive types.
  Python
  \# MANDATORY PATTERN
  from typing import Literal

  def set\_align(align: Literal\["left", "center", "right"]) -> None:
  ...

  set\_align("center") # OK
  set\_align("top") # ERROR: mypy will flag this

  This practice eliminates ambiguity and makes function signatures self-documenting regarding the exact values they accept.

### **Leveraging Python 3.12+ Typing Features**

All generated code must use modern Python 3.12 typing syntax to improve clarity and leverage new static analysis capabilities.21

* **PEP 695 Type Parameter Syntax**: All generic functions and classes MUST use the new def func(...) and class MyClass: syntax. The older T = TypeVar('T') syntax is disallowed.21
* **@override Decorator**: All methods that intentionally override a method from a parent class MUST be decorated with @typing.override. This allows mypy to catch subtle bugs that arise from refactoring or typos in method names.21
* **Type Aliases**: The type keyword MUST be used for creating type aliases (e.g., type UserID = int). This syntax is clearer and more explicit than a simple variable assignment.21

## **Data Handling: The "Airlock" Pattern**

To ensure robustness, all external data must pass through a two-stage validation process, creating an "airlock" that prevents malformed or untrusted data from reaching the core application logic.

### **Stage 1: Tolerant Syntactic Parsing**

All external JSON data, such as from an API request or a file, MUST first be parsed using tolerantjson.tolerate().4 This initial step handles only syntactic validation, correcting common, real-world formatting errors like trailing commas or single-quoted strings. Its sole responsibility is to produce a syntactically valid Python object (e.g., a

dict or list). A tolerantjson.ParseException must be handled at this boundary and typically result in a client-facing error (e.g., an HTTP 400 Bad Request response). Direct use of json.loads() on external data is forbidden.

### **Stage 2: Strict Semantic Validation**

The Python object produced by tolerantjson MUST be immediately passed to a Pydantic model for full validation using the YourModel.model\_validate() method.24 All complex data structures that represent data transfer objects (DTOs), configuration, or any other defined data contract MUST be defined as Pydantic models inheriting from

BaseModel.5 These models are the canonical definition of data within the application, responsible for type coercion, constraint validation (e.g.,

min\_length, pattern), and generating clear ValidationError messages for invalid data.25 Specialized Pydantic types like

EmailStr should be used where applicable to leverage built-in validation logic.5

This two-stage process effectively decouples syntactic concerns from semantic ones. tolerantjson ensures the data is well-formed JSON, while Pydantic ensures the data has the correct meaning and structure. This "airlock" pattern is a critical security and robustness measure.

## **Application Logic and Design**

The design of core business logic must prioritize clarity, maintainability, and, above all, testability.

### **Function and Class Design**

Functions must adhere to the Single Responsibility Principle, meaning they should be small, focused, and have descriptive names that clearly state their purpose.18 Pure functions, which have no side effects, are preferred as they are inherently easier to test and reason about. Classes should be used to encapsulate state and the behavior that operates on that state. Functions not intended for use outside the module MUST be prefixed with a single underscore (

\_) to mark them as internal or "private" (e.g., \_helper\_function). This convention clearly communicates the function's intended scope and prevents accidental external use. 2

### **Mandatory Dependency Injection**

To facilitate the 100% test coverage requirement, all dependencies—such as database clients, external service connectors, or other business logic components—MUST be injected into the classes or functions that use them. Direct instantiation of dependencies within a method or function is strictly forbidden.

**Constructor Injection** is the only permitted pattern for classes. Dependencies are passed as arguments to the class's \_\_init\_\_ method and stored as private instance attributes.7

Python

\# MANDATORY PATTERN
from some\_db\_library import DatabaseClient
from.models import User

class UserService:
"""Manages user-related operations."""

```
def \_\_init\_\_(self, db\_client: DatabaseClient):
    self.\_db\_client \= db\_client

def get\_user(self, user\_id: int) \-\> User:
    """Retrieves a user from the database.

    Args:
        user\_id: The ID of the user to retrieve.

    Returns:
        The user data model.
    """
    user\_data \= self.\_db\_client.fetch\_user\_by\_id(user\_id)
    return User.model\_validate(user\_data)
```

This pattern decouples the UserService from any concrete DatabaseClient implementation. During testing, a MockDatabaseClient can be injected instead, allowing the UserService to be tested in complete isolation from the actual database.3 This makes Dependency Injection the linchpin of the entire architecture, as it is the practical mechanism that enables the "Testability" and "Explicitness" principles to be realized in code.

## **Testing and Verification**

Automated testing is the final arbiter of code quality and correctness.

### **Framework and Structure**

pytest is the mandatory testing framework. All test files must be placed in the top-level tests/ directory, which should mirror the package structure of the src/ directory.9

pytest fixtures must be used for setting up test preconditions and managing test dependencies, such as creating mock objects.

### **The 100% Coverage Mandate**

Every line of application code within the src/ directory must be covered by automated tests. This will be enforced by CI/CD pipelines using pytest-cov and configured to fail the build if coverage drops below 100% (--cov-fail-under=100).17 Trivial code, such as simple

\_\_repr\_\_ methods or code inside an if TYPE\_CHECKING: block, may be excluded from coverage, but any such exclusion must be explicitly configured and justified.

### **Mocking and Isolation**

The standard unittest.mock library must be used for creating mock objects. In conjunction with the mandatory Dependency Injection pattern, tests MUST mock all external dependencies. This ensures that unit tests are fast, deterministic, and test only a single unit of logic in isolation, which is essential for pinpointing failures and maintaining a healthy test suite.7

## **Documentation and Comments**

Code is read more often than it is written. Therefore, clear and comprehensive documentation is not optional.

### **Google Style Docstrings**

All public modules, functions, classes, and methods MUST have Google-style docstrings.2 Docstrings are the primary form of documentation and must be comprehensive enough for another developer or tool to use the component without reading its source code.

Docstrings must include Args:, Returns: (or Yields: for generators), and Raises: sections where appropriate. While type hints in the function signature are the source of truth for types, the docstring should describe the *meaning*, *purpose*, and any important constraints on parameters and return values.2

Python

"""A brief, one-line summary of the function's purpose.

A more detailed explanation of the function's behavior, its side effects,
and any other relevant information.

Args:
param1 (str): A description of the first parameter's purpose.
param2 (int | None): A description of the second, optional parameter.

Returns:
bool: A description of the return value, e.g., True if the
operation was successful, False otherwise.

Raises:
ValueError: If \`param1\` is an empty string.
"""

### **Inline Comments**

Inline comments (#) should be used sparingly. Their purpose is to explain the "why" behind a piece of code, not the "what." Use them to clarify complex algorithms, document business logic decisions that are not obvious from the code, or explain workarounds for external system quirks.14

* **Bad**: # Loop through items
* **Good**: # Process items in reverse to avoid index shifting on deletion

## **Tooling Configuration**

The following configurations codify the rules outlined in this document and must be used in the project environment.

### **pyproject.toml**

The pyproject.toml file serves as the central configuration hub for project metadata and development tools.

Ini, TOML

\[tool.pytest.ini\_options]
\# Fail the build if test coverage is below 100%
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=100"
testpaths = \["tests"]

\[tool.mypy]
\# Point to the mypy configuration file
config\_file = "mypy.ini"

\[tool.pylint]
\# Point to the pylint configuration file
rcfile = ".pylintrc"

### **mypy.ini**

This file configures mypy to enforce the strict type system.

Ini, TOML

\[mypy]
python\_version = 3.12
strict = True
warn\_unused\_configs = True
warn\_redundant\_casts = True
warn\_unused\_ignores = True

\# Exclude test files from certain strict checks if necessary,
\# as test code often involves patterns that are intentionally
\# dynamic for mocking purposes.
\[mypy-tests.\*]
disallow\_untyped\_defs = False

### **.pylintrc**

A .pylintrc file must be present. It should be configured to align with these guidelines, particularly by setting max-line-length=88 and using plugins to check for Google-style docstring compliance. It should be based on established standards like those from Google.2

The following table summarizes the key tool configurations and their link to the foundational principles.

| Tool   | Configuration File | Key Flags/Settings                 | Purpose (Linked Principle)                                                  |
| :----- | :----------------- | :--------------------------------- | :-------------------------------------------------------------------------- |
| mypy   | mypy.ini           | strict = True                      | Enables all strictness checks to enforce provable correctness (Strictness). |
| pylint | .pylintrc          | good-names=..., max-line-length=88 | Enforces consistent and readable naming and layout (Explicitness).          |
| pytest | pyproject.toml     | addopts = "--cov-fail-under=100"   | Enforces complete test coverage, driving a testable design (Testability).   |

## **Conclusion**

The guidelines presented in this document are not a collection of arbitrary rules but a cohesive and interdependent system. They are designed to work in concert as a "forcing function," guiding the generation of Python code that is correct, robust, maintainable, and testable by default. Adherence to this system in its entirety is the primary directive. Each rule, from the src layout to the No-Any mandate, is a necessary component of a larger strategy to eliminate ambiguity and produce professional-grade software. The ultimate goal is to create codebases that are so clear, well-structured, and rigorously validated that they are as easy to read, maintain, and extend as they are to generate.
