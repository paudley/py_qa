<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# **A Guide to High-Quality Python Module Design**

## **The Pillars of Modular Design: Cohesion and Coupling**

The foundational principles of high-quality software architecture are high cohesion and low coupling.1 These concepts are not merely abstract ideals but are the primary determinants of a module's maintainability, scalability, and reliability.3 A module, in this context, refers to a single Python file (

.py) containing a collection of related functions, classes, and variables. In a large codebase with numerous modules, adherence to these principles is paramount for managing complexity.

### **High Cohesion: The Principle of Singular Purpose**

Cohesion refers to the degree to which the elements within a single module are functionally related and work together to fulfill a single, well-defined purpose.3 A module with high cohesion has a clear, focused responsibility. Its contents—classes, functions, and constants—are all directly related to that one purpose. This focus makes the module easier to understand, test, and maintain.4

The principle of high cohesion is the practical measure of a module's adherence to the Single Responsibility Principle (SRP). A module with low cohesion, by definition, serves multiple, unrelated purposes. For example, a module that handles both database persistence and API data formatting has two distinct responsibilities. It will need to be changed if either the database schema is altered or the API format is updated. This violates SRP, which states that a class or module should have only one reason to change.5 Conversely, a module with high cohesion, such as one dedicated solely to JSON serialization, has a single responsibility and thus a single primary reason to change. Achieving high cohesion is therefore a direct implementation of SRP at the module level.

To better assess and design for cohesion, it is useful to understand the different types, ranked from most to least desirable.

#### **Types of Cohesion**

* **Functional Cohesion (Ideal):** This is the highest and most desirable level of cohesion. Every element within the module is essential for the performance of a single, specific task.3 For instance, a module named\
  image\_filters.py that contains only functions for applying various filters (e.g., apply\_grayscale, apply\_blur) to image data exhibits functional cohesion.
* **Sequential Cohesion (Acceptable):** Elements are grouped because the output of one element serves as the input for another, forming a chain of operations.3 A module that defines a pipeline for processing data—for example, reading raw data from a file, cleaning it, and then transforming it into a structured format—demonstrates sequential cohesion.
* **Communicational Cohesion (Acceptable):** Elements are grouped because they operate on the same data structure.3 For example, a module\
  user\_profile\_manager.py might contain functions like get\_user\_email, update\_user\_address, and validate\_user\_permissions, all of which operate on a User object.
* **Logical Cohesion (Code Smell):** Elements are grouped because they are logically related by category, but their actual functions are different and may not be used together.3 A common anti-pattern is a\
  utils.py module that contains a mix of unrelated helper functions for string manipulation, date formatting, and network requests. Such modules tend to become bloated and violate the Single Responsibility Principle.
* **Coincidental Cohesion (Anti-Pattern):** This is the lowest form of cohesion, where the elements within a module have no discernible relationship to one another.3 They are grouped together arbitrarily. This type of module is difficult to understand and maintain and must be avoided.

To illustrate, consider a class responsible for processing a student's graduation. A low-cohesion version might include methods unrelated to the core task.

Python

\# Low Cohesion Example\
class StudentGraduationProcessor:\
"""A class with low cohesion, mixing graduation logic with unrelated data retrieval."""

```
def \_\_init\_\_(self, student\_data: dict):
    self.student\_data \= student\_data

def validate\_credits(self) \-\> bool:
    """Validates if the student has enough credits to graduate."""
    \#... logic to check credits...
    return True

def process\_offboarding(self) \-\> bool:
    """Handles student offboarding tasks like deactivating ID cards."""
    \#... logic for offboarding...
    return True

def process\_graduation(self) \-\> str:
    """Processes the student's graduation."""
    if self.validate\_credits() and self.process\_offboarding():
        return "Graduation Completed"
    return "Graduation Failed"

\# These methods reduce cohesion as they are not directly related to the graduation process.
def get\_student\_age(self) \-\> int:
    """Retrieves the student's age."""
    return self.student\_data.get("age", 0)

def get\_student\_gender(self) \-\> str:
    """Retrieves the student's gender."""
    return self.student\_data.get("gender", "unknown")
```

The methods get\_student\_age and get\_student\_gender do not contribute to the single purpose of processing a graduation.7 They belong in a different module or class focused on student data management. A high-cohesion version would exclusively contain methods related to the graduation process.

### **Low Coupling: The Principle of Independence**

Coupling describes the degree of interdependence between different modules.3 The goal of a well-architected system is to achieve low coupling (or loose coupling), meaning that modules are as independent of each other as possible.8 When modules are loosely coupled, a change made to one module will have a minimal impact on other modules. This independence is critical for maintainability, as it prevents a "ripple effect" where a small change in one part of the system necessitates extensive changes throughout the codebase.2

Low coupling is the desired architectural state, and Dependency Injection (DI) is the primary design pattern used to achieve it. A module that creates its own dependencies (e.g., instantiating a database connection class directly) is tightly coupled to that specific implementation.7 If the database connection logic changes, this module must also be modified. DI breaks this tight coupling by providing dependencies from an external source, allowing the module to depend on an abstraction rather than a concrete implementation.9 Therefore, the pursuit of low coupling naturally leads to the adoption of DI patterns.

Understanding the different forms of coupling helps in identifying and mitigating dependencies.

#### **Types of Coupling**

* **Data Coupling (Ideal):** Modules interact by passing only the necessary data through parameters.3 The modules do not need to know anything about each other's internal workings. This is the most desirable form of coupling as it maximizes independence.
* **Stamp Coupling (Acceptable with Caution):** One module passes a complete data structure (e.g., a Pydantic model or a large dictionary) to another, even if the receiving module only needs a fraction of that data.3 While often a pragmatic choice for convenience, it can introduce hidden dependencies. If the structure of the data object changes for reasons unrelated to the receiving module, the receiving module might still be affected.
* **Control Coupling (Code Smell):** One module passes a flag or command to another that controls its internal logic.3 For example, passing a boolean\
  is\_summary\_mode to a function dictates which execution path it takes. This entangles the logic of the two modules, as the calling module must be aware of the internal branching of the called module.
* **Common Coupling (High Risk):** Two or more modules share access to the same global data or mutable state.3 A change to this shared state by one module can have unforeseen consequences for all other modules that depend on it, making the system difficult to reason about and debug.
* **Content Coupling (Anti-Pattern):** This is the worst and most severe form of coupling. It occurs when one module directly modifies or relies on the internal implementation details of another module.1 Examples include accessing another module's "private" variables (those prefixed with\
  \_) or monkey-patching its functions. This violates encapsulation and creates an extremely brittle system that is nearly impossible to maintain safely.

The following table provides a summary for identifying and addressing different coupling types.

| Coupling Type        | Description                                                   | Python Example                                  | Maintainability Risk | Recommendation                                                                                                           |
| :------------------- | :------------------------------------------------------------ | :---------------------------------------------- | :------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| **Data Coupling**    | Modules communicate by passing primitive data via parameters. | process\_data(user\_id: int, item\_name: str)      | Low                  | Ideal; use whenever possible.                                                                                            |
| **Stamp Coupling**   | Modules communicate by passing a whole data structure.        | process\_user(user: UserData)                    | Low-Medium           | Acceptable, especially with Pydantic models. Prefer passing only required data if the structure is complex and volatile. |
| **Control Coupling** | One module passes a control flag to another.                  | generate\_report(data: list, mode: str)          | Medium               | Refactor to use separate functions or the Strategy pattern to avoid passing control flags.                               |
| **Common Coupling**  | Modules share a global mutable state.                         | import config; config.SETTINGS\['mode'] = 'prod' | High                 | Avoid global mutable state. Use explicit configuration objects or dependency injection instead.                          |
| **Content Coupling** | One module modifies the internal state of another.            | other\_module.\_internal\_variable = 10           | Extreme              | Anti-pattern; strictly forbidden. Interact only through the defined public API of a module.                              |

The refactoring of a vehicle registration application provides a clear example of reducing coupling. Initially, a single Application class is responsible for everything, including generating vehicle IDs and calculating taxes, making it highly coupled to the implementation details of these processes.4

Python

\# High Coupling Example\
class Application:\
def register\_vehicle(self, brand: str):\
registry = VehicleRegistry()\
\# The Application class knows too much about how to create a vehicle.\
vehicle\_id = registry.generate\_vehicle\_id(12)\
license\_plate = registry.generate\_vehicle\_license(vehicle\_id)\
\#... more logic for price and tax calculation...

A loosely coupled design abstracts these details into other classes. The Application class interacts with a simplified, high-level interface, delegating the complex work.4

Python

\# Low Coupling Example\
class Application:\
def register\_vehicle(self, brand: str):\
registry = VehicleRegistry()\
\# The Application class only needs to know about the high-level interface.\
vehicle = registry.create\_vehicle(brand)\
vehicle.print()

In the improved version, the Application module is decoupled from the specifics of vehicle creation. It can be changed or tested independently of the VehicleRegistry's internal logic, demonstrating the maintainability benefits of low coupling.

## **Applying SOLID Principles to Module Architecture**

The SOLID principles are five design principles that are fundamental to building understandable, maintainable, and flexible software.5 While often discussed in the context of object-oriented class design, they apply equally to the architecture of Python modules. Adhering to these principles guides the development of a clean, decoupled, and robust module structure.

The principles are not an arbitrary checklist but rather form a logical progression for designing high-quality software. The process starts with the **Single Responsibility Principle (SRP)**, which forces the creation of a focused, cohesive module. To extend this module with new functionality without breaking its existing contract, the **Open/Closed Principle (OCP)** mandates the use of abstractions. The **Liskov Substitution Principle (LSP)** and the **Interface Segregation Principle (ISP)** then serve as quality controls, ensuring these abstractions and their implementations are behaviorally sound and well-defined. Finally, the **Dependency Inversion Principle (DIP)** provides the master plan for connecting these abstraction-driven modules, ensuring that high-level policy is not coupled to low-level implementation details.

### **S – Single Responsibility Principle (SRP)**

The Single Responsibility Principle states that a class or module should have one, and only one, reason to change.5 This principle is a direct corollary to high cohesion. A module that adheres to SRP has a single, well-defined responsibility.

**Violation Example:** A single FileManager module that handles both standard file I/O and ZIP archive compression violates SRP. It has two reasons to change: a change in the file system API or a change in the ZIP compression algorithm.11

Python

\# srp\_violation.py\
from pathlib import Path\
from zipfile import ZipFile

class FileManager:\
"""This class violates SRP by having two responsibilities."""\
def \_\_init\_\_(self, filename: str):\
self.path = Path(filename)

```
def read(self, encoding: str \= "utf-8") \-\> str:
    return self.path.read\_text(encoding)

def write(self, data: str, encoding: str \= "utf-8") \-\> None:
    self.path.write\_text(data, encoding)

def compress(self) \-\> None:
    with ZipFile(self.path.with\_suffix(".zip"), mode="w") as archive:
        archive.write(self.path)
```

**Adherence Example:** To comply with SRP, the responsibilities are segregated into two distinct modules, file\_io.py and zip\_archiver.py. Each module now has only one reason to change.11

Python

\# file\_io.py\
from pathlib import Path

class FileIO:\
"""This class has the single responsibility of file I/O."""\
def \_\_init\_\_(self, filename: str):\
self.path = Path(filename)

```
def read(self, encoding: str \= "utf-8") \-\> str:
    return self.path.read\_text(encoding)

def write(self, data: str, encoding: str \= "utf-8") \-\> None:
    self.path.write\_text(data, encoding)
```

\# zip\_archiver.py\
from pathlib import Path\
from zipfile import ZipFile

class ZipArchiver:\
"""This class has the single responsibility of ZIP compression."""\
def \_\_init\_\_(self, filename: str):\
self.path = Path(filename)

```
def compress(self) \-\> None:
    with ZipFile(self.path.with\_suffix(".zip"), mode="w") as archive:
        archive.write(self.path)
```

### **O – Open/Closed Principle (OCP)**

The Open/Closed Principle dictates that software entities (modules, classes, etc.) should be open for extension but closed for modification.11 This means it should be possible to add new functionality without changing existing code. This is typically achieved by programming to abstractions (e.g., Abstract Base Classes) rather than concrete implementations.

**Violation Example:** A module that calculates the area of different shapes using a series of if/elif statements is closed for extension. To add a new shape, one must modify the existing calculate\_area function, which risks introducing bugs into the existing logic.11

Python

\# ocp\_violation.py\
from math import pi

class AreaCalculator:\
"""This class violates OCP because it must be modified to add new shapes."""\
def calculate*area(self, shape\_type: str, \*\*kwargs) -> float:\
if shape\_type == "rectangle":\
return kwargs\["width"] \* kwargs\["height"]\
elif shape*type == "circle":\
return pi \* kwargs\["radius"] \*\* 2\
\# To add a triangle, this function must be modified.\
return 0.0

**Adherence Example:** A compliant design uses an abstract Shape interface. The area calculation logic is open for extension—new shapes can be added as new classes that implement the interface—but the core calculation module is closed for modification.11

Python

\# shapes/base.py\
from abc import ABC, abstractmethod

class Shape(ABC):\
"""Abstract base class for shapes (the abstraction)."""\
@abstractmethod\
def calculate\_area(self) -> float:\
pass

\# shapes/concrete.py\
from math import pi\
from.base import Shape

class Rectangle(Shape):\
"""Concrete implementation for a rectangle."""\
def \_\_init\_\_(self, width: float, height: float):\
self.width = width\
self.height = height

```
def calculate\_area(self) \-\> float:
    return self.width \* self.height
```

class Circle(Shape):\
"""Concrete implementation for a circle."""\
def \_\_init\_\_(self, radius: float):\
self.radius = radius

```
def calculate\_area(self) \-\> float:
    return pi \* self.radius \*\* 2
```

\# A new shape, like Triangle, can be added in a new file or here\
\# without modifying any existing code.

### **L – Liskov Substitution Principle (LSP)**

The Liskov Substitution Principle asserts that subtypes must be substitutable for their base types without altering the correctness of the program.11 This means that if a program is designed to work with a base class, it should continue to work correctly if an instance of a subclass is provided instead.

**Violation Example:** A classic violation occurs with the rectangle and square problem. Mathematically, a square is a rectangle. However, in code, if Square inherits from Rectangle and overrides the setters for width and height to keep them equal, it breaks the expected behavior of a Rectangle, which assumes independent width and height properties.11

Python

\# lsp\_violation.py\
class Rectangle:\
def \_\_init\_\_(self, width: float, height: float):\
self.width = width\
self.height = height

```
def set\_width(self, width: float):
    self.width \= width

def set\_height(self, height: float):
    self.height \= height
```

class Square(Rectangle):\
def \_\_init\_\_(self, side: float):\
super().\_\_init\_\_(side, side)

```
def set\_width(self, width: float):
    self.width \= width
    self.height \= width

def set\_height(self, height: float):
    self.width \= height
    self.height \= height
```

A function expecting a Rectangle might not work correctly with a Square instance, as setting the width would unexpectedly change the height.

**Adherence Example:** The correct design avoids this problematic inheritance relationship. Instead, both Rectangle and Square can be siblings that implement a common Shape interface, as shown in the OCP example.11 This ensures that there is no incorrect behavioral assumption, and both classes correctly fulfill the contract of the

Shape abstraction.

### **I – Interface Segregation Principle (ISP)**

The Interface Segregation Principle states that clients should not be forced to depend on methods they do not use.11 This suggests that large, monolithic interfaces should be broken down into smaller, more specific ones. In Python, this applies to the design of Abstract Base Classes (ABCs).

**Violation Example:** A single MultiFunctionDevice ABC that includes print, fax, and scan methods forces any implementing class to provide implementations for all three, even if it doesn't support them. An OldPrinter class would have to raise NotImplementedError for fax and scan, which is a sign of a poor interface design.11

Python

\# isp\_violation.py\
from abc import ABC, abstractmethod

class MultiFunctionDevice(ABC):\
@abstractmethod\
def print\_doc(self, document: str) -> None: pass\
@abstractmethod\
def fax\_doc(self, document: str) -> None: pass\
@abstractmethod\
def scan\_doc(self, document: str) -> None: pass

class OldPrinter(MultiFunctionDevice):\
def print\_doc(self, document: str) -> None:\
print(f"Printing {document}")

```
def fax\_doc(self, document: str) \-\> None:
    raise NotImplementedError("Fax not supported")

def scan\_doc(self, document: str) \-\> None:
    raise NotImplementedError("Scan not supported")
```

**Adherence Example:** A better design segregates the interfaces into smaller, role-based ABCs. Classes can then inherit from only the interfaces they actually implement.11

Python

\# interfaces.py\
from abc import ABC, abstractmethod

class Printable(ABC):\
@abstractmethod\
def print\_doc(self, document: str) -> None: pass

class Faxable(ABC):\
@abstractmethod\
def fax\_doc(self, document: str) -> None: pass

class Scannable(ABC):\
@abstractmethod\
def scan\_doc(self, document: str) -> None: pass

\# concrete\_devices.py\
from.interfaces import Printable, Faxable, Scannable

class OldPrinter(Printable):\
def print\_doc(self, document: str) -> None:\
print(f"Printing {document}")

class ModernPrinter(Printable, Faxable, Scannable):\
def print\_doc(self, document: str) -> None:\
print(f"Printing {document} in color")

```
def fax\_doc(self, document: str) \-\> None:
    print(f"Faxing {document}")

def scan\_doc(self, document: str) \-\> None:
    print(f"Scanning {document}")
```

### **D – Dependency Inversion Principle (DIP)**

The Dependency Inversion Principle is a cornerstone of decoupled architecture. It consists of two parts:

1. High-level modules should not depend on low-level modules. Both should depend on abstractions.
2. Abstractions should not depend on details. Details should depend on abstractions.11

This principle effectively "inverts" the traditional dependency flow, where high-level policy code would typically depend directly on low-level utility code.

**Violation Example:** A high-level FrontEnd module that directly imports and instantiates a low-level BackEnd module for data retrieval is tightly coupled. If the data source changes (e.g., from a database to a REST API), the FrontEnd module must be modified.11

Python

\# dip\_violation.py\
class BackEnd:\
"""Low-level module for data retrieval."""\
def get\_data\_from\_database(self) -> str:\
return "Data from the database"

class FrontEnd:\
"""High-level module that depends directly on the low-level module."""\
def \_\_init\_\_(self):\
self.back\_end = BackEnd()

```
def display\_data(self) \-\> None:
    data \= self.back\_end.get\_data\_from\_database()
    print(f"Displaying: {data}")
```

**Adherence Example:** To comply with DIP, an abstraction (a DataSource ABC) is introduced. The high-level FrontEnd module depends on this abstraction. The low-level data retrieval modules (Database, API) also depend on this abstraction by implementing it. This decouples the FrontEnd from the specific data source implementation.11

Python

\# data\_sources/interfaces.py\
from abc import ABC, abstractmethod

class DataSource(ABC):\
"""The abstraction that both high-level and low-level modules depend on."""\
@abstractmethod\
def get\_data(self) -> str:\
pass

\# data\_sources/implementations.py\
from.interfaces import DataSource

class Database(DataSource):\
"""A low-level detail implementation."""\
def get\_data(self) -> str:\
return "Data from the database"

class API(DataSource):\
"""Another low-level detail implementation."""\
def get\_data(self) -> str:\
return "Data from the API"

\# ui/frontend.py\
from data\_sources.interfaces import DataSource

class FrontEnd:\
"""The high-level module, now depending only on the abstraction."""\
def \_\_init\_\_(self, data\_source: DataSource):\
self.data\_source = data\_source

```
def display\_data(self) \-\> None:
    data \= self.data\_source.get\_data()
    print(f"Displaying: {data}")
```

## **Implementing Dependency Injection for Ultimate Decoupling**

Dependency Injection (DI) is the primary design pattern for implementing the Dependency Inversion Principle and achieving low coupling.9 The core idea of DI is that a component's dependencies (the objects it needs to perform its function) are provided to it from an external source, rather than being created by the component itself.12 This externalization breaks the hard-coded dependency between a component and its concrete collaborators, making the system more modular, flexible, and testable.13

In Python, the language's dynamic nature makes implementing DI straightforward and explicit, often obviating the need for complex DI frameworks. Unlike in some statically compiled languages where frameworks are essential for managing object graphs, manual DI in Python is often clearer and aligns with the language's philosophy of "explicit is better than implicit".10 Over-reliance on frameworks can introduce unnecessary complexity, obscure the application's flow, and lead to hard-to-diagnose runtime errors.13 Therefore, for module design, direct and manual DI patterns are strongly preferred.

### **DI Implementation Patterns in Python**

There are two primary patterns for implementing DI in Python.

#### **Constructor Injection (Preferred)**

In this pattern, dependencies are passed as arguments to the class's \_\_init\_\_ method.9 This is the most common and explicit form of DI. It makes a class's dependencies immediately clear from its constructor signature, ensuring that an object cannot be created in an invalid state (i.e., without its required dependencies).

Python

\# services.py\
class EmailService:\
"""A concrete service for sending emails."""\
def send\_email(self, recipient: str, message: str) -> None:\
print(f"Sending email to {recipient}: {message}")

\# components.py\
from.services import EmailService

class UserController:\
"""\
This component depends on an EmailService. The dependency is injected\
via the constructor.\
"""\
def \_\_init\_\_(self, email\_service: EmailService):\
self.\_email\_service = email\_service

```
def register\_user(self, username: str, email: str) \-\> None:
    \#... user registration logic...
    self.\_email\_service.send\_email(
        recipient=email,
        message=f"Welcome, {username}\!"
    )
```

\# main.py\
from components import UserController\
from services import EmailService

\# The 'injector' or 'assembler' part of the application creates\
\# the dependency and injects it into the component.\
email\_provider = EmailService()\
user\_controller = UserController(email\_service=email\_provider)\
user\_controller.register\_user("ada\_lovelace", "ada@example.com")

This design clearly decouples UserController from the concrete EmailService class. The UserController only knows that it needs an object that behaves like an EmailService (ideally, this would be formalized with an ABC), not how to create one.10

#### **Setter Injection**

With setter injection, dependencies are provided through a dedicated public method after the object has been instantiated.9 This pattern is useful for optional dependencies or when a dependency might need to be changed during the object's lifecycle.

Python

\# services.py\
class Logger:\
"""A service for logging messages."""\
def log(self, message: str) -> None:\
print(f"\[LOG]: {message}")

\# components.py\
from typing import Optional\
from.services import Logger

class TaskProcessor:\
"""\
This component has an optional dependency on a Logger, which can be\
injected via a setter method.\
"""\
def \_\_init\_\_(self):\
self.\_logger: Optional\[Logger] = None

```
def set\_logger(self, logger: Logger) \-\> None:
    """Injects the logger dependency."""
    self.\_logger \= logger

def process\_task(self, task\_id: int) \-\> None:
    if self.\_logger:
        self.\_logger.log(f"Starting task {task\_id}")

    \#... task processing logic...

    if self.\_logger:
        self.\_logger.log(f"Finished task {task\_id}")
```

\# main.py\
from components import TaskProcessor\
from services import Logger

\# The dependency is created and injected after the object is instantiated.\
processor = TaskProcessor()\
console\_logger = Logger()\
processor.set\_logger(console\_logger)\
processor.process\_task(101)

While flexible, setter injection can make it less obvious what an object's dependencies are and can allow an object to exist in a partially configured state. It should be used judiciously for dependencies that are genuinely optional.

### **DI and Testability**

One of the most significant benefits of DI is the dramatic improvement in testability.9 Because dependencies are injected, test code can easily substitute mock objects or test doubles for real dependencies. This allows for testing a component in isolation, without needing to set up heavy external resources like databases, network services, or file systems.10

Consider testing the UserController from the constructor injection example. Without DI, testing it would be difficult because it would be hard-wired to the EmailService, and a real email would be sent during the test run. With DI, we can inject a mock service.

Python

\# tests/test\_components.py\
import unittest\
from unittest.mock import Mock\
from components import UserController

class TestUserController(unittest.TestCase):\
def test\_register\_user\_sends\_welcome\_email(self):\
"""\
Verify that registering a user calls the email service's\
send\_email method with the correct arguments.\
"""\
\# 1. Create a mock object for the dependency.\
mock\_email\_service = Mock()

```
    \# 2\. Inject the mock object into the component under test.
    user\_controller \= UserController(email\_service=mock\_email\_service)

    \# 3\. Execute the method being tested.
    test\_username \= "grace\_hopper"
    test\_email \= "grace@example.com"
    user\_controller.register\_user(test\_username, test\_email)

    \# 4\. Assert that the component interacted with the dependency correctly.
    mock\_email\_service.send\_email.assert\_called\_once\_with(
        recipient=test\_email,
        message=f"Welcome, {test\_username}\!"
    )
```

if \_\_name\_\_ == '\_\_main\_\_':\
unittest.main()

This test verifies the behavior of UserController in complete isolation, without any side effects. DI is the key enabler of this powerful testing strategy, leading to more robust and reliable modules.

## **Crafting the Module's Public and Private API**

Because Python does not enforce strict privacy for object attributes, clear communication of intent is essential for creating a maintainable module API.1 A well-designed module explicitly declares what is public and intended for external use, and what is private and considered an internal implementation detail. This is achieved through a combination of language features and established conventions.

This dual-signal approach, using both a positive declaration of the public API (\_\_all\_\_) and a negative declaration for non-public members (\_), creates a robust system for communicating API intent. A member listed in \_\_all\_\_ that also has a leading underscore is a logical contradiction and a code smell that should be corrected. Similarly, a public-looking member (no underscore) that is omitted from \_\_all\_\_ may indicate an oversight. This redundancy helps keep the module's declared API in sync with its implementation, addressing a common maintenance challenge.15

### **Defining the Public Contract with \_\_all\_\_**

The \_\_all\_\_ dunder is a list of strings defined at the module level that explicitly specifies which names should be imported when a wildcard import (from \<module> import \*) is performed.15

While the use of wildcard imports is generally discouraged in production code because it can pollute the local namespace and reduce readability, defining \_\_all\_\_ serves a critical secondary purpose: it acts as a clear, machine-readable declaration of the module's public API.16 It provides an unambiguous contract for other developers and tools about which functions, classes, and variables are intended for public consumption.

Best Practice:\
Every module that exposes a public API should define \_\_all\_\_ at the top of the file. This list must be kept in sync with the public objects defined in the module.

Python

\# string\_utils.py

"""A module for various string manipulation utilities."""

\_\_all\_\_ = \['is\_palindrome', 'truncate\_string']

import re

\# Internal helper function, not part of the public API.\
def \_count\_words(text: str) -> int:\
return len(re.findall(r'\w+', text))

\# Public API function.\
def is\_palindrome(text: str) -> bool:\
"""Checks if a string is a palindrome."""\
normalized = "".join(filter(str.isalnum, text)).lower()\
return normalized == normalized\[::-1]

\# Public API function.\
def truncate\_string(text: str, max\_length: int) -> str:\
"""Truncates a string to a maximum length."""\
if len(text) <= max\_length:\
return text\
return text\[:max\_length-3] + "..."

\# Another internal function, not exported.\
def \_log\_operation(op\_name: str) -> None:\
print(f"Operation performed: {op\_name}")

In this example, only is\_palindrome and truncate\_string are considered public. An attempt to use from string\_utils import \* would only import these two names.18

### **The Convention of Internal Use: Single Underscore (\_)**

The primary convention for indicating that a name (variable, function, or method) is not part of a module's public API is to prefix it with a single leading underscore (\_).14 This is a universally understood signal among Python developers that the prefixed name is intended for internal use only.20

This convention is not enforced by the Python interpreter (the name is still accessible), but it carries a strong implication: "This is an implementation detail. Do not rely on it. Its behavior, signature, or existence may change without warning in any future version".14 Adhering to this convention is crucial for maintaining low coupling and allowing module authors the freedom to refactor internal logic without breaking client code.

**Effect:**

* Names with a leading underscore are not imported by a wildcard import (from module import \*).19
* It clearly separates the stable, public interface from the volatile, internal implementation.

Python

\# data\_processor.py

\_\_all\_\_ = \['process\_records']

class \_DataRecord:\
"""Internal data structure, not for external use."""\
def \_\_init\_\_(self, raw\_data: dict):\
self.data = raw\_data

def \_clean\_record(record: \_DataRecord) -> \_DataRecord:\
"""Internal helper to clean a single record."""\
\#... cleaning logic...\
return record

def process\_records(records\_data: list\[dict]) -> list\[dict]:\
"""\
Public function to process a list of raw data records.

```
This function provides a stable public interface, while its internal
workings (\_DataRecord, \_clean\_record) can be changed freely.
"""
cleaned\_records \=
for raw\_record in records\_data:
    record\_obj \= \_DataRecord(raw\_record)
    cleaned\_obj \= \_clean\_record(record\_obj)
    cleaned\_records.append(cleaned\_obj.data)
return cleaned\_records
```

### **Name Mangling for Inheritance: Double Underscore (\_\_)**

The double leading underscore (\_\_) has a specific, and often misunderstood, purpose in Python. When used on a class attribute (e.g., \_\_my\_var), it invokes a mechanism called "name mangling".14 The interpreter automatically renames the attribute to

\_ClassName\_\_my\_var before the code is executed.19

Correct Use Case:\
The sole purpose of name mangling is to avoid name clashes in inheritance hierarchies. If a base class has an attribute \_\_value, and a subclass also defines an attribute named \_\_value, name mangling ensures they do not collide because they will be renamed to \_BaseClass\_\_value and \_SubClass\_\_value, respectively.21\
Misuse and Best Practice:\
It is a common anti-pattern to use the double underscore to create "truly private" attributes. This is incorrect for several reasons:

* It does not provide true privacy; the mangled name is still easily accessible from outside the class if you know the convention.14
* It can make debugging more difficult because the attribute name in the code does not match its name at runtime.
* It makes subclassing and overriding the attribute intentionally more cumbersome.

**Guideline:** Do not use the double leading underscore for privacy. The single leading underscore (\_) is the correct and standard convention for indicating non-public, internal-use attributes. Use \_\_ only when you have a specific need to prevent name collisions in a complex inheritance chain, which is a relatively rare scenario in modern Python design that favors composition over inheritance.

## **Architecting for Dependency Flow to Prevent Circular Imports**

Circular imports are a common and frustrating problem in large Python codebases. An ImportError stating "cannot import name... from partially initialized module" is a clear sign that two or more modules depend on each other, creating a dependency loop that the Python importer cannot resolve.22

This error should not be treated as a simple syntactic bug to be patched with a quick fix. A circular import is a critical "architectural smell"—a symptom of a deeper design flaw in the module structure.22 The need for two modules to import each other indicates that they are tightly coupled and likely have poorly defined responsibilities, violating the principles of high cohesion and low coupling. The fact that they share a dependency often means that this shared component has not been properly abstracted. Therefore, encountering a circular import should trigger an immediate design review to address the root cause, not just the symptom.

### **Primary Strategy: Unidirectional Dependency Graphs**

The most robust and correct solution to a circular import is to refactor the code to establish a clear, unidirectional flow of dependencies. Dependencies should flow from higher-level modules (which define application policy and business logic) to lower-level modules (which provide general-purpose utilities or abstractions). A low-level module should never import a high-level module.

This refactoring almost always involves the following steps 22:

1. **Identify the Shared Dependency:** Determine the specific class, function, or constant that both modules are trying to access from each other.
2. **Extract to a New Module:** Move this shared dependency into a new, lower-level module (often named common.py, base.py, or interfaces.py).
3. **Update Imports:** Modify the original two modules to import the shared dependency from the new module.

This process breaks the circular dependency and creates a healthier, hierarchical dependency graph where both original modules depend on the new, lower-level module, but not on each other. This is a direct application of the Dependency Inversion Principle, where the new module serves as an abstraction that both higher-level modules can depend on.

**Example:** Consider a web application where models.py defines data structures and services.py contains business logic that operates on those models. A circular import arises when a model needs a utility function from the services layer.

Python

\# models.py (Problematic)\
from services import generate\_unique\_slug # <-- Causes circular import

class Article:\
def \_\_init\_\_(self, title: str):\
self.title = title\
self.slug = generate\_unique\_slug(title)

\# services.py (Problematic)\
from models import Article # <-- Depends on models

def generate\_unique\_slug(text: str) -> str:\
\#... logic to create a slug...\
return "some-slug"

def get\_article\_by\_slug(slug: str) -> Article:\
\#... database logic to fetch an article...\
return Article(title="An Article")

Here, models.py imports services.py, and services.py imports models.py.

**Refactored Solution:** The shared dependency, generate\_unique\_slug, is a general-purpose utility. It should be extracted to a lower-level utils.py module.

Python

\# utils.py (New Module)\
def generate\_unique\_slug(text: str) -> str:\
\#... logic to create a slug...\
return "some-slug"

\# models.py (Refactored)\
from utils import generate\_unique\_slug # <-- Now depends on utils

class Article:\
def \_\_init\_\_(self, title: str):\
self.title = title\
self.slug = generate\_unique\_slug(title)

\# services.py (Refactored)\
from models import Article # <-- Still depends on models (which is fine)\
\# No longer needs to define or import the slug function.

def get\_article\_by\_slug(slug: str) -> Article:\
\#... database logic to fetch an article...\
return Article(title="An Article")

The dependency graph is now services.py -> models.py -> utils.py, which is a clean, unidirectional flow.

### **Tactical Solutions (When Refactoring is Infeasible)**

While architectural refactoring is always the preferred solution, it may not be immediately feasible in a large, legacy codebase. In such cases, tactical solutions can be used as a temporary workaround. These should be considered technical debt and marked for future refactoring.

The following table outlines the available strategies, distinguishing between the ideal architectural fix and temporary tactical solutions.

| Strategy                        | Description                                                                                                                  | Pros                                                                                                                      | Cons                                                                                                                                        | When to Use                                                                                                                            |
| :------------------------------ | :--------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------- |
| **Refactor to a Shared Module** | Extract the common dependency into a new, lower-level module that both original modules can import from.                     | Resolves the underlying architectural flaw. Improves cohesion and reduces coupling. Creates a clear dependency hierarchy. | Requires code reorganization and a deeper understanding of the architecture.                                                                | **Best Practice.** This is the preferred, long-term solution for all circular dependencies.                                            |
| **Local (In-Function) Import**  | Move the import statement from the top level of the module into the specific function or method where it is needed.          | Quick to implement. Avoids import-time errors by delaying the import until runtime.                                       | Hides the design flaw. Can make dependencies harder to track. May slightly impact performance on the first function call.                   | As a **temporary fix** when a dependency is only needed at runtime in one specific location and immediate refactoring is not possible. |
| **typing.TYPE\_CHECKING Block**  | Place imports used only for type annotations inside an if typing.TYPE\_CHECKING: block. These imports are ignored at runtime. | Resolves circular dependencies that exist only at the type-hinting level, without affecting runtime behavior.             | Does not solve runtime circular dependencies. Can be confusing if the distinction between type-time and run-time dependencies is not clear. | To resolve cycles caused **exclusively by type hints**, where the modules do not have a circular dependency at runtime.                |

**Example of a Local Import:**

Python

\# services.py (Using local import as a temporary fix)\
def some\_service\_function():\
\# Import is delayed until this function is called.\
from models import SomeModel\
\#... logic using SomeModel...

This approach breaks the import-time cycle but should be used with caution, as it obscures the module's true dependencies and fails to address the underlying tight coupling.22

## **Enforcing Contracts with Typing and Pydantic**

To build robust and maintainable modules, it is essential to have explicit, enforceable contracts at their boundaries. These contracts define the expected shape and type of data that flows between modules. In modern Python, this is achieved through a two-layer approach: static type hints for developer-time checks and Pydantic models for runtime validation and coercion.

This methodology enables the "Parse, Don't Validate" paradigm. Instead of scattering validation logic (e.g., isinstance checks, try/except KeyError) throughout a module's internal code, validation is consolidated into a single parsing step at the module's public interface. When external, untrusted data (like a dict from an API call) enters a module, it is immediately parsed into a strict Pydantic model.25 If this parsing step succeeds, the rest of the module's code can operate on the resulting object with full confidence in its structure and types, eliminating defensive code and making the internal logic cleaner and more robust. If parsing fails, a

ValidationError is raised immediately at the boundary, preventing malformed data from corrupting the system's state.26

### **Type Hints as a Foundational Contract**

PEP 484 introduced type hints, which form the foundational layer of a module's contract.27 Strong typing is mandatory. Every function and method signature must include type annotations for all arguments and the return value.

Type hints provide several key benefits 28:

* **Static Analysis:** Tools like MyPy can analyze the code before runtime to catch a wide range of type-related errors.
* **Improved Readability:** Explicit types make the code self-documenting, clarifying the intent of functions and the nature of the data they handle.29
* **Enhanced IDE Support:** Editors can provide more intelligent autocompletion, refactoring support, and inline error checking.28

Python

\# A function signature with strong typing.\
def process\_user\_data(\
user\_id: int,\
metadata: dict\[str, str | int]\
) -> bool:\
"""Processes user data and returns a success flag."""\
\#... implementation...\
return True

While essential, standard type hints are not enforced by the Python runtime; they are merely annotations.30

### **Pydantic Models as Runtime-Enforced Data Contracts**

Pydantic elevates type hints from static suggestions to runtime-enforced contracts.31 By defining data structures as classes that inherit from

pydantic.BaseModel, modules can parse, validate, and coerce incoming data, guaranteeing its integrity.25

When data needs to be passed from one module to another, it should be encapsulated in a Pydantic model. The receiving module's function signature should then type-hint that model, creating an explicit and validated data contract between the two modules.26

**Example:** Imagine a user\_processing module that receives user data from an api\_handler module.

Python

\# data\_contracts.py\
from pydantic import BaseModel, EmailStr, Field

class UserData(BaseModel):\
"""\
A runtime-enforced data contract for user information.\
This model guarantees the structure and types of the data.\
"""\
user\_id: int = Field(gt=0, description="The unique user identifier.")\
username: str = Field(min\_length=3, max\_length=50)\
email: EmailStr\
is\_active: bool = True

\# user\_processing.py\
from.data\_contracts import UserData

def activate\_user(user: UserData) -> None:\
"""\
This function operates on a validated UserData object.\
It does not need to perform any internal validation.\
"""\
if not user.is\_active:\
print(f"Activating user {user.username} (ID: {user.user\_id}).")\
\#... logic to update user status in the database...\
else:\
print(f"User {user.username} is already active.")

\# api\_handler.py\
from.data\_contracts import UserData\
from.user\_processing import activate\_user\
from pydantic import ValidationError

def handle\_api\_request(raw\_data: dict) -> None:\
"""\
Handles an incoming API request. It parses the raw data into the\
UserData contract before passing it to the business logic layer.\
"""\
try:\
\# The "Parse, Don't Validate" step.\
user\_contract = UserData.model\_validate(raw\_data)\
activate\_user(user=user\_contract)\
except ValidationError as e:\
print(f"Invalid API data received: {e}")

In this example, api\_handler is responsible for enforcing the contract. The user\_processing module receives a UserData object that is guaranteed to be valid, simplifying its internal logic.

### **Pydantic for Parameter Objects**

When a function or method requires a large number of parameters, especially if they are conceptually related, the signature can become long and unwieldy. This increases the risk of passing arguments in the wrong order. The "Parameter Object" pattern resolves this by grouping related parameters into a single Pydantic model.

**Violation Example:**

Python

def generate\_financial\_report(\
start\_date: date,\
end\_date: date,\
client\_id: int,\
report\_type: Literal\["summary", "detailed"],\
include\_projections: bool,\
currency: str = "USD"\
) -> str:\
\#... complex implementation...\
return "report\_content"

**Adherence Example:** The parameters are grouped into a ReportParams model, which serves as a single, validated parameter object.

Python

\# report\_contracts.py\
from datetime import date\
from typing import Literal\
from pydantic import BaseModel, Field

class ReportParams(BaseModel):\
"""A parameter object for financial report generation."""\
start\_date: date\
end\_date: date\
client\_id: int = Field(gt=0)\
report\_type: Literal\["summary", "detailed"]\
include\_projections: bool\
currency: str = "USD"

\# report\_generator.py\
from.report\_contracts import ReportParams

def generate\_financial\_report(params: ReportParams) -> str:\
"""\
Generates a financial report using a validated parameter object.\
The function signature is clean and the parameters are self-documenting.\
"""\
print(f"Generating {params.report\_type} report for client {params.client\_id}...")\
\#... implementation uses params.start\_date, etc....\
return "report\_content"

This approach not only simplifies the function signature but also makes the parameters reusable and easier to test.

## **Module-Level Documentation Standards**

Comprehensive documentation is critical for the long-term health of a large codebase. For each module, a dual-documentation approach is required to serve two distinct audiences: the *consumer* of the module's API and the future *maintainer* of the module's code. The module docstring serves the consumer, providing API-level details, while a module-specific README.md file serves the maintainer, providing architectural context and design rationale.

### **The Module Docstring (Google Style)**

Every Python module (.py file) must begin with a module-level docstring that adheres to the Google Python Style Guide.33 This docstring is the primary source of API documentation and is accessible via tools like Python's built-in

help() function and IDEs.34

Content Requirements:\
The module docstring must contain the following sections 35:

* **One-Line Summary:** A brief, imperative sentence summarizing the module's purpose.
* **Extended Description:** A more detailed paragraph (or paragraphs) explaining the module's responsibilities and functionality.
* **Attributes Section:** Documentation for any module-level constants that are part of the public API.
* **Public Object Summary:** A list of all public classes and functions exported by the module, each with a one-line summary.

**Example Module Docstring:**

Python

\# custom\_exceptions.py\
"""Defines custom exceptions for the data processing pipeline.

This module contains a set of specialized exception classes that are used\
throughout the application to signal specific error conditions during\
data validation and processing. Using these exceptions allows for more\
granular error handling compared to using generic built-in exceptions.

Attributes:\
MAX\_RETRIES (int): The default maximum number of retries for operations\
that raise a TransientError.

"""

\_\_all\_\_ =

MAX\_RETRIES: int = 3

class ValidationError(Exception):\
"""Raised when input data fails validation checks."""\
pass

class TransientError(Exception):\
"""Raised for temporary errors that may be resolved by retrying."""\
pass

class ConfigurationError(Exception):\
"""Raised when the application configuration is invalid or missing."""\
pass

### **The Module-Specific README.md**

In addition to the docstring, each module (or a small, tightly-coupled group of modules within a sub-package) must be accompanied by a README.md file located in the same directory. This document is intended for developers who need to understand, maintain, or extend the module. It provides the architectural "why" that is not captured in the API-focused docstring.37

Content Requirements:\
The module README.md must include the following sections 38:

* **Purpose and Scope:** A clear, high-level explanation of why the module exists, the problem it solves within the larger system, and its boundaries of responsibility.
* **Design Principles and Patterns:** A brief discussion of the key architectural decisions made in the module. This should mention any specific design patterns used (e.g., "This module implements the Factory pattern to create different data parsers") and explain the rationale for significant design trade-offs.
* **Dependencies and Interactions:** A description of the module's key dependencies on other internal modules. It should explain the nature of these interactions (e.g., "This module consumes UserData contracts from the data\_contracts module and passes them to the persistence layer").
* **Usage Example:** A concise, practical code snippet demonstrating the most common use case for the module. This serves as a quick-start guide for other developers who need to interact with the module.40
* **Contribution Notes:** Any specific guidance for developers who will be modifying this particular module, such as notes on testing strategies, potential pitfalls, or areas planned for future refactoring.

By mandating both a docstring and a README.md, the documentation strategy ensures that the module is well-documented for both its external contract (the API) and its internal architecture, which is essential for sustainable development in a large, collaborative environment.

#### **Works cited**

1. Python and content coupling - Reddit, accessed September 5, 2025, <https://www.reddit.com/r/Python/comments/2wgpud/python_and_content_coupling/>
2. How Design Principles Help You Write Better Python Code - Amsterdam Tech, accessed September 5, 2025, <https://amsterdam.tech/how-design-principles-help-you-write-better-python-code/>
3. Coupling and Cohesion - Software Engineering - GeeksforGeeks, accessed September 5, 2025, <https://www.geeksforgeeks.org/software-engineering/software-engineering-coupling-and-cohesion/>
4. Cohesion vs Coupling - Important Python topics, accessed September 5, 2025, <https://pythonexpert.hashnode.dev/cohesion-and-coupling-in-python>
5. SOLID Design Principles Explained: Building Better Software Architecture - DigitalOcean, accessed September 5, 2025, <https://www.digitalocean.com/community/conceptual-articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design>
6. SOLID Principles explained in Python with examples. - GitHub Gist, accessed September 5, 2025, <https://gist.github.com/dmmeteo/f630fa04c7a79d3c132b9e9e5d037bfd>
7. Design Principles: High Cohesion and Low Coupling | by Paul Chuang - Medium, accessed September 5, 2025, <https://paul-d-chuang.medium.com/design-principles-high-cohesion-and-low-coupling-fc15c05b6a2c>
8. What does 'low in coupling and high in cohesion' mean - Stack Overflow, accessed September 5, 2025, <https://stackoverflow.com/questions/14000762/what-does-low-in-coupling-and-high-in-cohesion-mean>
9. Dependency Injection in Python Programming - Custom Software Development - NG Logic, accessed September 5, 2025, <https://nglogic.com/dependency-injection-python/>
10. Dependency Injection in Python: A Complete Guide to Cleaner ..., accessed September 5, 2025, <https://medium.com/@rohanmistry231/dependency-injection-in-python-a-complete-guide-to-cleaner-scalable-code-9c6b38d1b924>
11. SOLID Principles: Improve Object-Oriented Design in Python – Real ..., accessed September 5, 2025, <https://realpython.com/solid-principles-python/>
12. Dependency Injector Design Pattern — Python - Code Like A Girl, accessed September 5, 2025, <https://code.likeagirl.io/dependancy-injector-design-pattern-python-ec9f7ebe3e4a>
13. Dependency injection in Python | Snyk, accessed September 5, 2025, <https://snyk.io/blog/dependency-injection-python/>
14. Python Private Methods Explained | DataCamp, accessed September 5, 2025, <https://www.datacamp.com/tutorial/python-private-methods-explained>
15. Documenting the public interface - public 6.0.1 documentation, accessed September 5, 2025, <https://public.readthedocs.io/en/latest/using.html>
16. Demystifying \_\_all\_\_ in Python: A Closer Look at Module Exports | by Akshat Gadodia, accessed September 5, 2025, <https://medium.com/@akshatgadodia/demystifying-all-in-python-a-closer-look-at-module-exports-f4d818a12bb6>
17. How to use \_\_all\_\_ in Python packages | LabEx, accessed September 5, 2025, <https://labex.io/tutorials/python-how-to-use-all-in-python-packages-450976>
18. Understanding \_\_all\_\_ in Python Modules with Examples - eSparkBiz, accessed September 5, 2025, <https://www.esparkinfo.com/qanda/python/what-does-all-mean-in-python>
19. python - What is the meaning of single and double underscore before an object name?, accessed September 5, 2025, <https://stackoverflow.com/questions/1301346/what-is-the-meaning-of-single-and-double-underscore-before-an-object-name>
20. When should I prefix class private attributes/methods with single underscore instead of double underscore? : r/learnpython - Reddit, accessed September 5, 2025, <https://www.reddit.com/r/learnpython/comments/12mybox/when_should_i_prefix_class_private/>
21. Private Methods - Single or Double Underscore : r/learnpython - Reddit, accessed September 5, 2025, <https://www.reddit.com/r/learnpython/comments/18j1ws2/private_methods_single_or_double_underscore/>
22. Python Circular Import: Causes, Fixes, and Best Practices | DataCamp, accessed September 5, 2025, <https://www.datacamp.com/tutorial/python-circular-import>
23. Python Circular Import Error Solved - Built In, accessed September 5, 2025, <https://builtin.com/articles/python-circular-import>
24. How to Fix a Circular Import in Python - Rollbar, accessed September 5, 2025, <https://rollbar.com/blog/how-to-fix-circular-import-in-python/>
25. Models - Pydantic, accessed September 5, 2025, <https://docs.pydantic.dev/latest/concepts/models/>
26. Data Validation and Versioned Data Contracts with Pydantic - Data Gluons, accessed September 5, 2025, <https://www.datagluons.io/blog/pydantic-data-contract-manager>
27. PEP 484 – Type Hints | peps.python.org, accessed September 5, 2025, <https://peps.python.org/pep-0484/>
28. Python Types Intro - FastAPI, accessed September 5, 2025, <https://fastapi.tiangolo.com/python-types/>
29. What the hell is going on with type hinting these days : r/Python - Reddit, accessed September 5, 2025, <https://www.reddit.com/r/Python/comments/1itzac1/what_the_hell_is_going_on_with_type_hinting_these/>
30. typing — Support for type hints — Python 3.13.7 documentation, accessed September 5, 2025, <https://docs.python.org/3/library/typing.html>
31. Welcome to Pydantic - Pydantic, accessed September 5, 2025, <https://docs.pydantic.dev/latest/>
32. An Introduction to Pydantic: the powerful Data Validation for your REST APIs, accessed September 5, 2025, <https://engineering.projectagora.com/an-introduction-to-pydantic-the-powerful-data-validation-for-your-rest-apis-a6edfb46b0e8>
33. Google Python Style Guide, accessed September 5, 2025, <https://google.github.io/styleguide/pyguide.html>
34. Python Docstrings Tutorial : Examples & Format for Pydoc, Numpy, Sphinx Doc Strings, accessed September 5, 2025, <https://www.datacamp.com/tutorial/docstrings-python>
35. Example Google Style Python Docstrings — Solutions 0.0.1 documentation, accessed September 5, 2025, <https://iw3.math.rutgers.edu/solutions/example_google.html>
36. Example Google Style Python Docstrings — napoleon 0.7 documentation, accessed September 5, 2025, <https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html>
37. Creating Great README Files for Your Python Projects - Real Python, accessed September 5, 2025, <https://realpython.com/readme-python-project/>
38. README File Guidelines and Resources — Python Packaging Guide - pyOpenSci, accessed September 5, 2025, <https://www.pyopensci.org/python-package-guide/documentation/repository-files/readme-file-best-practices.html>
39. Make a README, accessed September 5, 2025, <https://www.makeareadme.com/>
40. What in your opinion makes for a great README file? : r/opensource - Reddit, accessed September 5, 2025, <https://www.reddit.com/r/opensource/comments/1kk1wd8/what_in_your_opinion_makes_for_a_great_readme_file/>
