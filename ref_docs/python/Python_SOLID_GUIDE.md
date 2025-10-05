<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# **A Guide to SOLID Software Architecture in Python 3.12+**

## **Introduction: The Philosophy of Maintainable Code**

### **Overview of SOLID**

SOLID is a mnemonic acronym that represents five foundational design principles in object-oriented programming. These principles were introduced by Robert C. Martin in his 2000 paper, "Design Principles and Design Patterns," to guide developers in creating software that is understandable, flexible, and maintainable.1 The acronym itself was later coined by Michael Feathers.1 Adherence to these principles results in systems that are more robust, scalable, and easier to manage over their lifecycle.

The five principles are 1:

* **S** - Single-responsibility Principle (SRP)
* **O** - Open-closed Principle (OCP)
* **L** - Liskov Substitution Principle (LSP)
* **I** - Interface Segregation Principle (ISP)
* **D** - Dependency Inversion Principle (DIP)

### **The Problem SOLID Solves**

In his work, Robert C. Martin discusses the concept of "software rot," a term for the decay that software systems undergo over time as they are modified and extended.3 Without a disciplined approach to design, codebases become increasingly rigid (difficult to change), fragile (a change in one area breaks unrelated areas), and immobile (difficult to reuse). The SOLID principles serve as a direct countermeasure to this degradation. They establish practices that promote clean, modular code, helping developers avoid common design flaws, known as "code smells," and facilitate agile or adaptive software development methodologies.2

### **Relevance in Modern Python**

While the SOLID principles are language-agnostic, their application in a dynamically typed language like Python is particularly crucial for building large-scale, enterprise-grade applications. The evolution of Python's static typing system, especially with the enhancements introduced in version 3.12 and later, provides powerful tools to make these design principles more explicit and enforceable by static analysis tools. This guide will specifically address how modern Python features can be leveraged to implement SOLID principles more effectively, leading to higher-quality software.

### **Guide Roadmap**

This guide provides an exhaustive exploration of each SOLID principle. Each of the first five chapters is dedicated to a single principle, offering a deep analysis of its core concept, practical Python 3.12+ code examples illustrating both violations and compliant solutions, and an examination of its broader architectural implications. The final chapter focuses on the Dependency Inversion Principle's practical implementation through the Dependency Injection pattern, recommending and demonstrating specific Python modules that facilitate cleaner, more SOLID code.

## **Chapter 1: The Single Responsibility Principle (SRP) - The Art of Focus**

### **Core Concept**

The Single Responsibility Principle (SRP) states that "a class should have only one reason to change".1 This is often interpreted to mean that a class should have only one responsibility or job, and it should encapsulate that responsibility entirely.4 If a class assumes more than one responsibility, it becomes coupled; a change related to one of its responsibilities will necessitate modifications that could inadvertently affect its other responsibilities.6

### **Analysis: Defining a "Reason to Change"**

A "reason to change" typically corresponds to a distinct actor or a specific domain of concern within the application. For instance, business logic, persistence logic, and presentation logic are all separate concerns that are likely to change for different reasons and at different times.2 A class that mixes these concerns violates SRP.

Violating SRP leads to several negative consequences. Classes become tightly coupled and difficult to understand, as their purpose is muddled. A change to one responsibility can introduce unintended side effects and bugs in another, leading to a system that is both rigid and fragile.1 Conversely, adhering to SRP yields significant benefits, including improved maintainability, enhanced testability, and greater flexibility.3 In collaborative development environments, SRP reduces the frequency of merge conflicts, as different teams working on different concerns are less likely to modify the same file.7

### **Practical Implementation (with Python 3.12+ Type Hints)**

To illustrate SRP, consider a monolithic class responsible for multiple aspects of order processing.

#### **Violation Example**

The following Order class violates SRP by combining data management with business logic (calculation, discounts), persistence (database saving), and presentation (invoice generation). This class has multiple reasons to change: a new tax law would alter calculation, a database migration would alter persistence, and a new invoice format would alter presentation.1

Python

\# Violation of SRP\
class Order:\
def \_\_init\_\_(self, order\_id: str, items: list\[dict]):\
self.order\_id = order\_id\
self.items = items\
self.total\_price = 0.0

```
def calculate\_total\_price(self) \-\> None:
    """Calculates the total price of the order items."""
    \# Business logic for calculation
    price \= sum(item\['price'\] \* item\['quantity'\] for item in self.items)
    self.total\_price \= price

def apply\_discount(self, discount\_percentage: float) \-\> None:
    """Applies a discount to the total price."""
    \# Business logic for discounts
    self.total\_price \*= (1 \- discount\_percentage / 100)

def save\_to\_database(self) \-\> None:
    """Saves the order details to a database."""
    \# Persistence logic
    print(f"Saving order {self.order\_id} to the database...")
    \# In a real application, this would involve database connection and SQL queries.

def generate\_invoice(self) \-\> str:
    """Generates a string representation of the invoice."""
    \# Presentation logic
    invoice \= f"Invoice for Order ID: {self.order\_id}\\n"
    for item in self.items:
        invoice \+= f"- {item\['name'\]}: {item\['quantity'\]} x ${item\['price'\]}\\n"
    invoice \+= f"Total: ${self.total\_price:.2f}"
    return invoice
```

#### **Adherent Refactoring**

To comply with SRP, the monolithic Order class is decomposed into smaller, more focused classes. The Order class itself is simplified to a data container, while its former responsibilities are delegated to dedicated service classes.4

Python

\# Adherence to SRP\
from typing import Protocol

\# Protocol can be used to define the structure of item data\
class OrderItem(Protocol):\
name: str\
price: float\
quantity: int

class Order:\
"""Data class responsible only for holding order information."""\
def \_\_init\_\_(self, order\_id: str, items: list\[OrderItem]):\
self.order\_id = order\_id\
self.items = items\
self.total\_price: float | None = None # Price is calculated externally

class OrderCalculator:\
"""Responsible solely for order-related calculations."""\
@staticmethod\
def calculate\_total(order: Order) -> float:\
price = sum(item\['price'] \* item\['quantity'] for item in order.items)\
order.total\_price = price\
return price

class OrderPersistence:\
"""Responsible solely for saving and retrieving orders from a database."""\
def save(self, order: Order) -> None:\
print(f"Saving order {order.order\_id} with total ${order.total\_price:.2f} to the database...")\
\# Database logic would go here

class InvoiceGenerator:\
"""Responsible solely for generating invoices."""\
@staticmethod\
def generate(order: Order) -> str:\
if order.total\_price is None:\
raise ValueError("Total price has not been calculated for this order.")

```
    invoice \= f"Invoice for Order ID: {order.order\_id}\\n"
    for item in order.items:
        invoice \+= f"- {item\['name'\]}: {item\['quantity'\]} x ${item\['price'\]}\\n"
    invoice \+= f"Total: ${order.total\_price:.2f}"
    return invoice
```

This refactored design is more maintainable. A change in database technology now only affects OrderPersistence, while a change in invoice formatting only affects InvoiceGenerator.6

### **SRP as a Foundation for Microservices Architecture**

The discipline of applying the Single Responsibility Principle at the class level has profound implications for system-level architecture. The process of identifying and isolating distinct business capabilities—such as invoicing, order management, or customer notifications—into separate classes is a microcosm of the process used to design microservices.4 A microservices architecture is fundamentally about creating small, autonomous services, where each service owns a single, well-defined business capability.

When SRP is applied rigorously within a monolithic application, it naturally leads to the identification of these bounded contexts. For example, the InvoiceGenerator and OrderPersistence classes from the refactored code represent distinct business concerns. In a growing system, these classes could evolve into the core logic of independent microservices. The InvoiceGenerator could become the heart of an "Invoicing Service," and OrderPersistence could be part of an "Order Management Service." Therefore, SRP is not merely a class-level design principle; it is a foundational concept that scales up to system architecture, providing a clear and logical pathway from a well-structured monolith to a more scalable microservices-based system.

## **Chapter 2: The Open/Closed Principle (OCP) - Designing for Growth**

### **Core Concept**

The Open/Closed Principle (OCP) dictates that "software entities (classes, modules, functions, etc.) should be open for extension, but closed for modification".1 In practical terms, this means that it should be possible to add new functionality to a system without altering existing, tested source code.7 By adhering to OCP, developers can extend a system's behavior while minimizing the risk of introducing new bugs into stable, production-ready code.3

### **Analysis: The Power of Abstraction**

The key to achieving OCP is the strategic use of abstraction.8 Instead of depending on concrete implementations, code should depend on abstract base classes or interfaces. This allows new functionality to be introduced by creating new subclasses that conform to the established abstraction. The client code, which is programmed against the abstraction, can then use these new subclasses without any modification. In Python, the primary tool for creating these abstractions is the

abc (Abstract Base Classes) module, which allows for the definition of formal interfaces.10

### **Practical Implementation**

Consider a system that needs to apply various types of discounts to an order total.

#### **Violation Example**

An initial, naive implementation might place the discount logic directly within the Order class using a series of if/elif/else blocks. This design violates OCP because adding a new type of discount (e.g., a "Holiday" discount) requires modifying the calculate\_total method, thereby opening up existing, working code to potential errors.9

Python

\# Violation of OCP\
class Order:\
def \_\_init\_\_(self, total: float, discount\_type: str | None = None):\
self.total = total\
self.discount\_type = discount\_type

```
def get\_final\_price(self) \-\> float:
    final\_price \= self.total
    if self.discount\_type \== 'student':
        \# 20% discount for students
        final\_price \*= 0.8
    elif self.discount\_type \== 'bulk':
        \# 10% discount for bulk orders over $100
        if self.total \>= 100:
            final\_price \*= 0.9
    \# Adding a new discount type requires modifying this method.
    return final\_price
```

#### **Adherent Refactoring**

A compliant solution employs the Strategy design pattern. An abstract Discount class defines a common interface for applying discounts. Concrete discount types are then implemented as separate subclasses. The Order class is modified to accept a list of Discount objects, iterating through them to apply their logic without needing to know the specifics of each implementation.9

Python

\# Adherence to OCP\
from abc import ABC, abstractmethod

class Discount(ABC):\
"""Abstract base class for all discount strategies."""\
@abstractmethod\
def apply(self, total: float) -> float:\
"""Applies the discount and returns the new total."""\
pass

class StudentDiscount(Discount):\
"""A concrete discount strategy for students."""\
def apply(self, total: float) -> float:\
return total \* 0.8 # 20% discount

class BulkDiscount(Discount):\
"""A concrete discount strategy for bulk orders."""\
def apply(self, total: float) -> float:\
if total >= 100:\
return total \* 0.9 # 10% discount\
return total

class Order:\
def \_\_init\_\_(self, total: float, discounts: list):\
self.total = total\
self.discounts = discounts

```
def get\_final\_price(self) \-\> float:
    final\_price \= self.total
    for discount in self.discounts:
        final\_price \= discount.apply(final\_price)
    return final\_price
```

\# To add a new discount, we create a new class without modifying Order.\
class HolidayDiscount(Discount):\
def apply(self, total: float) -> float:\
return total \* 0.95 # 5% holiday discount

With this design, the Order class is closed for modification but open for extension. New discount types can be added simply by creating new subclasses of Discount, promoting maintainability and seamless feature introduction.9

### **Leveraging Python 3.12+ for OCP**

Python 3.12 introduced a new, more ergonomic syntax for defining generic classes and functions via PEP 695.12 This simplifies the creation of abstractions, which are central to OCP. The new syntax allows for defining type parameters directly in the class or function signature, eliminating the need to import

TypeVar.

Python

\# Python 3.12+ syntax for a generic abstract class\
from abc import ABC, abstractmethod

\# Define a generic type alias for exportable items\
type ExportableItem = dict\[str, str | int]

class Exporter(ABC):\
"""A generic abstract exporter, open for extension."""\
@abstractmethod\
def export(self, data: list) -> str:\
pass

class JsonExporter(Exporter):\
"""A concrete implementation for JSON export."""\
def export(self, data: list) -> str:\
import json\
return json.dumps(data)

class CsvExporter(Exporter):\
"""A new extension for CSV export, added without modifying existing code."""\
def export(self, data: list) -> str:\
\# CSV export logic...\
return "csv,data"

### **OCP and Plugin Architectures**

The Open/Closed Principle is not just a guideline for class design; it is the foundational principle that enables plugin-based architectures. A plugin architecture consists of a core application that defines specific extension points (abstractions or interfaces), allowing external modules (plugins) to be added to extend its functionality. The core application can load and interact with these plugins without needing to be recompiled or modified.

The Discount example serves as a simple illustration of this concept. The Order class acts as the core application, the abstract Discount class is the defined extension point, and concrete classes like StudentDiscount and HolidayDiscount are the plugins. This model can be scaled significantly. For instance, a system could be designed to dynamically discover and load all subclasses of Discount from a designated "plugins" directory. In such a system, adding a new discount would be as simple as dropping a new Python file into that folder. This demonstrates that OCP provides the essential architectural decoupling required for a core system to safely and dynamically interact with unknown future extensions, making it a cornerstone of flexible and extensible software design.

## **Chapter 3: The Liskov Substitution Principle (LSP) - Ensuring Behavioral Integrity**

### **Core Concept**

The Liskov Substitution Principle (LSP), named after Barbara Liskov, states that "subtypes must be substitutable for their base types without altering the correctness of the program".1 This means that any instance of a derived class should be able to replace an instance of its base class without causing errors or unexpected behavior.15 The principle is often explained with analogies: a toy duck that quacks and floats but requires batteries is not a true substitute for a real duck, because its behavior (requiring batteries) is inconsistent with the base concept of "duck".16

### **Analysis: Beyond Structural Typing - The Rules of Behavior**

LSP is fundamentally about behavioral subtyping, which goes beyond simply matching method signatures. A subclass must honor the implicit "contract" established by its superclass to ensure that it behaves in a way that clients of the superclass would expect.16 This contract includes several key rules 17:

* **Pre-conditions cannot be strengthened:** A subclass method should not demand more from its inputs than the base class method. For example, if a base method accepts any integer, a subclass override cannot require that the integer be positive.
* **Post-conditions cannot be weakened:** A subclass method must fulfill all the promises of the base class method. If a base method guarantees it will return a list of items, a subclass override cannot return None or a single item.
* **Invariants must be preserved:** Invariants are conditions or properties of the class that must always hold true. A subclass must not violate any invariants established by its base class.
* **No new exception types:** A subclass method should not throw types of exceptions that the base class method is not declared to throw. A common violation of LSP is overriding a method only to raise a NotImplementedError, which signals a broken abstraction.16

### **Practical Implementation**

Violations of LSP often arise from abstractions that are based on taxonomic relationships from the real world but fail to hold up behaviorally within the program's logic.

#### **Violation Example**

The classic example of an LSP violation is the Rectangle/Square problem. Mathematically, a square "is-a" rectangle. However, if a Square class inherits from a Rectangle class that has separate setters for width and height, the substitution fails. A function designed to work with a Rectangle might set the width and height independently, but for a Square, setting the width must also change the height to maintain its "squareness." This violates the expected behavior of a rectangle, where width and height are independent properties.14

Another common example involves a Bird class with a fly method. If an Ostrich class inherits from Bird, it cannot meaningfully implement the fly method, as ostriches cannot fly. Raising a NotImplementedError in the Ostrich.fly method is a direct violation of LSP, as it breaks any client code that expects all Bird objects to be able to fly.16

Python

\# Violation of LSP\
class Bird:\
def fly(self):\
print("This bird is flying.")

class Ostrich(Bird):\
def fly(self):\
\# Ostriches cannot fly. This breaks the contract of the Bird superclass.\
raise NotImplementedError("Ostriches cannot fly!")

def make\_bird\_fly(bird: Bird):\
\# This function works for a generic Bird, but will crash for an Ostrich.\
bird.fly()

\# make\_bird\_fly(Ostrich()) # This would raise NotImplementedError

#### **Adherent Refactoring**

An LSP violation is a strong indicator that the abstraction is flawed. The solution is not to patch the subclass but to rethink the class hierarchy. For the Bird/Ostrich problem, the ability to fly should be segregated into a separate, more specific abstraction. This can be done by creating a FlyingBird interface that inherits from Bird.17

Python

\# Adherence to LSP\
from abc import ABC, abstractmethod

class Bird:\
"""A base class for all birds, without assuming flight."""\
def eat(self):\
print("This bird is eating.")

class FlyingBird(Bird, ABC):\
"""An abstract class for birds that can fly."""\
@abstractmethod\
def fly(self):\
pass

class Eagle(FlyingBird):\
"""An eagle is a flying bird."""\
def fly(self):\
print("The eagle is soaring high.")

class Ostrich(Bird):\
"""An ostrich is a bird, but not a flying one."""\
def run(self):\
print("The ostrich is running fast.")

def make\_flying\_bird\_fly(bird: FlyingBird):\
\# This function now correctly operates only on birds that can fly.\
bird.fly()

\# Client code\
eagle = Eagle()\
ostrich = Ostrich()

make\_flying\_bird\_fly(eagle) # Works correctly\
\# make\_flying\_bird\_fly(ostrich) # This would correctly cause a static type error.

### **The Role of @override in Python 3.12**

Python 3.12 introduced the @typing.override decorator as part of PEP 698.13 This decorator serves to make a developer's intent explicit: it signals to static type checkers (like Mypy) that a method is

*intended* to override a method from a parent class.

While @override does not enforce LSP at runtime, it is a powerful tool for maintaining it during development. It helps prevent accidental LSP violations that occur due to refactoring. For example, if a method in the base class is renamed or its signature changes, any subclass method decorated with @override that no longer matches will trigger a static analysis error. This immediately alerts the developer that the subclass is no longer correctly implementing the superclass contract, allowing them to fix the issue before it becomes a runtime bug.

Python

from typing import override

class Document:\
def save(self, content: str) -> None:\
print("Saving document...")

class PdfDocument(Document):\
@override # Explicitly marks this method as an override\
def save(self, content: str) -> None:\
print("Saving PDF document...")

\# If Document.save were renamed to Document.persist, a type checker would flag\
\# an error on PdfDocument.save because it no longer overrides anything.

### **LSP as a Litmus Test for Abstractions**

The Liskov Substitution Principle should be viewed as more than just a rule for inheritance; it is a critical diagnostic tool for validating the quality of abstractions. When developers create class hierarchies, they often model them on real-world "is-a" relationships (e.g., "a square is a rectangle"). However, LSP violations reveal that the *behavioral* "is-a" relationship does not hold true within the context of the program's logic.14

When a subclass is forced to throw a NotImplementedError or fundamentally alter the expected behavior of its parent, it is a clear signal that the abstraction defined by the parent class is flawed—it is either incorrect or too specific for its intended use. Therefore, an LSP violation is not just a bug in the subclass but a design smell that points to a deeper issue in the parent class's abstraction. By using LSP as a litmus test during the design phase, developers are forced to consider behavior over simple taxonomy, which leads to the creation of more robust, correct, and truly substitutable class hierarchies.

## **Chapter 4: The Interface Segregation Principle (ISP) - Lean and Focused Contracts**

### **Core Concept**

The Interface Segregation Principle (ISP) states that "clients should not be forced to depend upon interfaces that they do not use".3 This principle advocates for the creation of small, cohesive, and client-specific interfaces, often referred to as "fine-grained" or "role" interfaces.21 The core idea is that a class should not be burdened with implementing methods it does not need or use.22

### **Analysis: The Problem with "Fat" Interfaces**

Large, general-purpose interfaces, often called "fat" or "polluted" interfaces, are a primary source of unnecessary coupling in a system.3 When a client class depends on a fat interface, it becomes coupled to all the methods defined within that interface, even if it only uses a small subset of them. This is problematic because a change to one of the unused methods in the interface can still force the client class to be recompiled or redeployed, creating a fragile design.

In Python, interfaces are typically defined using abstract base classes from the abc module or, for a more structural typing approach, typing.Protocol.21 ISP guides the design of these abstractions to be as lean and focused as possible.

### **Practical Implementation**

Consider a system designed to interact with various office machines.

#### **Violation Example**

A single, "fat" IMachine interface is created with methods for print, scan, and fax. A SimplePrinter class, which can only print, is forced to implement this interface. This requires the SimplePrinter to provide empty or exception-raising implementations for the scan and fax methods, which it does not support. This is a clear violation of ISP, as the SimplePrinter is forced to depend on methods it does not use.20

Python

\# Violation of ISP\
from abc import ABC, abstractmethod

class IMachine(ABC):\
"""A fat interface for all office machines."""\
@abstractmethod\
def print\_document(self, document):\
pass

```
@abstractmethod
def scan\_document(self, document):
    pass

@abstractmethod
def fax\_document(self, document):
    pass
```

class SimplePrinter(IMachine):\
def print\_document(self, document):\
print(f"Printing {document}...")

```
def scan\_document(self, document):
    \# This printer cannot scan. Forced implementation.
    raise NotImplementedError("This device cannot scan.")

def fax\_document(self, document):
    \# This printer cannot fax. Forced implementation.
    raise NotImplementedError("This device cannot fax.")
```

#### **Adherent Refactoring**

To comply with ISP, the fat IMachine interface is broken down into smaller, role-based interfaces. Each interface defines a single, cohesive set of behaviors: IPrinter, IScanner, and IFax. A MultiFunctionDevice can then implement all three interfaces, while the SimplePrinter only needs to implement the IPrinter interface, which is directly relevant to its capabilities.19

Python

\# Adherence to ISP\
from abc import ABC, abstractmethod

class IPrinter(ABC):\
"""A focused interface for printing."""\
@abstractmethod\
def print\_document(self, document):\
pass

class IScanner(ABC):\
"""A focused interface for scanning."""\
@abstractmethod\
def scan\_document(self, document):\
pass

class IFax(ABC):\
"""A focused interface for faxing."""\
@abstractmethod\
def fax\_document(self, document):\
pass

class SimplePrinter(IPrinter):\
"""Implements only the interface it needs."""\
def print\_document(self, document):\
print(f"Printing {document}...")

class MultiFunctionDevice(IPrinter, IScanner, IFax):\
"""A device that can perform multiple roles."""\
def print\_document(self, document):\
print(f"Printing {document} from MFD...")

```
def scan\_document(self, document):
    print(f"Scanning {document} from MFD...")

def fax\_document(self, document):
    print(f"Faxing {document} from MFD...")
```

This design is more flexible and decoupled. Clients can now depend only on the specific functionality they require. For example, a document management system might only need to interact with the IScanner interface, completely unaware of printing or faxing capabilities.

### **ISP's Relationship to SRP**

The Interface Segregation Principle and the Single Responsibility Principle are closely related and mutually reinforcing. While SRP applies to classes, stating they should have a single reason to change, ISP applies the same philosophy to interfaces.

Consider the "fat" IMachine interface from the violation example. This interface has multiple responsibilities: printing, scanning, and faxing. It violates the spirit of single responsibility at the interface level. When this interface is segregated into IPrinter, IScanner, and IFax, each new interface now has a single, well-defined responsibility. IPrinter is solely concerned with the role of printing, IScanner with scanning, and so on.

Therefore, ISP can be understood as the application of the Single Responsibility Principle to interfaces. By creating small, cohesive interfaces, each defining a single role or responsibility, developers naturally create a foundation that allows implementing classes to adhere more easily to SRP. A class that implements a single, focused interface is less likely to be burdened with multiple, unrelated responsibilities.

## **Chapter 5: The Dependency Inversion Principle (DIP) - Inverting Control**

### **Core Concept**

The Dependency Inversion Principle (DIP) is arguably the most critical for creating decoupled, modular architectures. It is defined by two key rules 1:

1. High-level modules should not depend on low-level modules. Both should depend on abstractions.
2. Abstractions should not depend on details. Details should depend on abstractions.

This principle fundamentally inverts the traditional, top-down flow of dependency in software design. Instead of high-level policy modules (e.g., business logic) depending directly on low-level implementation modules (e.g., database access, API clients), the low-level modules are made to conform to an abstraction that is defined and owned by the high-level modules.24

### **Analysis: Decoupling Through Abstraction**

DIP is the capstone principle that enables true loose coupling in a system.3 By enforcing that both high-level and low-level modules depend on a shared abstraction, it makes the high-level modules independent of the specific implementation details of the low-level modules. This allows the core business logic of an application to be reused with different databases, user interfaces, or external services without modification. The "abstraction" is the central element; in Python, this is typically an abstract base class (

abc.ABC) or a typing.Protocol that is defined by the high-level module to suit its own needs.23

### **Practical Implementation**

Consider a high-level module responsible for sending notifications to users.

#### **Violation Example**

In a design that violates DIP, a high-level NotificationService class directly instantiates and uses a concrete, low-level EmailClient class. This creates a tight coupling; the NotificationService is now completely dependent on the specific implementation of the EmailClient. If the business decides to switch to sending notifications via SMS or Slack, the NotificationService class itself must be modified.23

Python

\# Violation of DIP\
class EmailClient:\
"""A low-level module for sending emails."""\
def send\_email(self, recipient: str, message: str):\
print(f"Sending email to {recipient}: {message}")

class NotificationService:\
"""A high-level module containing business logic."""\
def \_\_init\_\_(self):\
\# Direct dependency on a concrete, low-level module.\
self.client = EmailClient()

```
def send\_notification(self, user\_email: str, message: str):
    self.client.send\_email(user\_email, message)
```

#### **Adherent Refactoring**

To adhere to DIP, the dependency is inverted.

1. **Define an Abstraction:** The high-level NotificationService defines an interface, IMessageClient, that meets its needs for sending messages.
2. **Depend on the Abstraction:** The NotificationService is refactored to depend on the IMessageClient interface, not a concrete class. The specific client is now passed in from an external source (this is Dependency Injection, covered in the next chapter).
3. **Implement the Abstraction:** The low-level modules (EmailClient and a new SmsClient) are modified to implement the IMessageClient interface.

Python

\# Adherence to DIP\
from abc import ABC, abstractmethod

\# 1. Abstraction defined by the high-level module's needs.\
class IMessageClient(ABC):\
@abstractmethod\
def send(self, recipient: str, message: str) -> None:\
pass

\# 2. High-level module depends on the abstraction.\
class NotificationService:\
def \_\_init\_\_(self, client: IMessageClient):\
self.client = client

```
def send\_notification(self, user: str, message: str):
    self.client.send(user, message)
```

\# 3. Low-level details conform to the abstraction.\
class EmailClient(IMessageClient):\
def send(self, recipient: str, message: str) -> None:\
print(f"Sending email to {recipient}: {message}")

class SmsClient(IMessageClient):\
def send(self, recipient: str, message: str) -> None:\
print(f"Sending SMS to {recipient}: {message}")

\# The system can now be configured with different low-level modules\
\# without changing the NotificationService.\
email\_notifier = NotificationService(EmailClient())\
sms\_notifier = NotificationService(SmsClient())

email\_notifier.send\_notification("test@example.com", "Hello via Email!")\
sms\_notifier.send\_notification("+1234567890", "Hello via SMS!")

This design is highly flexible. The NotificationService is completely decoupled from the specific delivery mechanism, making the system easier to maintain, test, and extend.23

### **DIP Enables the "Hexagonal" or "Ports and Adapters" Architecture**

The Dependency Inversion Principle is not just a pattern for decoupling individual classes; it is the fundamental principle that enables modern, resilient architectural patterns like the Hexagonal Architecture, also known as Ports and Adapters. This architectural style aims to completely isolate an application's core business logic from external concerns such as databases, user interfaces, or third-party APIs.

The architecture is structured as follows:

* The **"ports"** are the interfaces defined by the application's core (the high-level module). These ports represent the needs of the business logic. For example, the core might define a UserRepositoryPort interface with methods like find\_by\_id and save. These ports are the abstractions that DIP refers to.
* The **"adapters"** are the concrete implementations of these ports that interact with the outside world (the low-level modules). For instance, a SqlUserRepositoryAdapter and an InMemoryUserRepositoryAdapter could both implement the UserRepositoryPort. The former would translate method calls into SQL queries, while the latter would use an in-memory dictionary for testing purposes.

DIP is the principle that enforces this structure. The flow of dependencies is inverted to always point inwards, towards the application core. The core logic depends only on the ports (abstractions) it defines. The adapters, which contain all the messy details of external technologies, also depend on these ports by implementing them. This allows the core business logic of an application to be developed and tested in complete isolation from its delivery mechanisms and infrastructure, leading to a highly maintainable and technology-agnostic system.

## **Chapter 6: Implementing DIP with Dependency Injection (DI)**

### **From Principle to Pattern**

It is essential to distinguish between the Dependency Inversion Principle (DIP) and Dependency Injection (DI). DIP is the high-level design principle that states high-level modules should depend on abstractions, not concretions. Dependency Injection, on the other hand, is a set of software design patterns that provide a mechanism for achieving DIP.24 DI is the process by which an object's dependencies (the services or components it needs to function) are provided to it from an external source, rather than the object creating them itself.27

Using DI provides numerous benefits that directly support SOLID design: it promotes loose coupling, dramatically improves testability by allowing mock or stub dependencies to be "injected" during tests, and enhances overall system modularity.27

### **DI Techniques in Python**

Python's dynamic nature and support for keyword arguments make implementing DI straightforward. The most common techniques are:

* **Constructor Injection:** This is the most common, explicit, and generally preferred form of DI. Dependencies are passed as arguments to the class's \_\_init\_\_ method and assigned to instance variables. This pattern ensures that an object is created in a fully valid and operational state, as all its required dependencies are provided upon instantiation.27 The\
  NotificationService example in the previous chapter uses constructor injection.
* **Setter Injection:** With this pattern, dependencies are provided through a dedicated public setter method after the object has been created. This is useful for optional dependencies or for situations where a dependency might need to be changed during the object's lifecycle. However, it can lead to objects existing in an incomplete state before the setter is called, which can be a source of bugs.27

### **DI Frameworks: Automating Assembly**

For small projects, manually wiring dependencies (i.e., creating instances and passing them into constructors) is often sufficient. However, in larger applications with complex dependency graphs, this manual process can become cumbersome and error-prone. Dependency Injection frameworks automate this assembly process, managing the lifecycle of objects and injecting them where needed based on a defined configuration.29 Two popular and powerful DI frameworks in the Python ecosystem are

dependency-injector and injector.

#### **Table: Comparison of Python DI Frameworks**

The following table provides a structured comparison to help in selecting an appropriate framework based on project requirements. This analysis is based on the core paradigms and features highlighted by their respective documentation.30

| Feature           | dependency-injector                                                                                                                                        | injector                                                                                                                                                     |
| :---------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Core Paradigm** | Utilizes declarative **Containers** to define and manage **Providers** (e.g., Factory, Singleton) that assemble objects.31                                 | Inspired by Google's Guice, it uses **Modules** to configure **Bindings** between interfaces (types) and their concrete implementations.30                   |
| **Performance**   | High performance. The core is written in **Cython**, making it significantly faster, which is beneficial for performance-critical applications.31          | A standard, pure Python implementation. Performance is generally sufficient for most applications but may not match Cython-based alternatives.30             |
| **Syntax**        | Relies on an explicit wiring mechanism using the @inject decorator and a Provide marker. Configuration is centralized in container classes.31              | Employs a more "magical" approach, using the @inject decorator on \_\_init\_\_ and relying heavily on type hints to automatically resolve dependencies.30    |
| **Key Features**  | Extensive provider types (Factory, Singleton, Configuration, Resource), built-in support for async, and a powerful override() mechanism for testing.31     | Supports scopes (e.g., singleton), provider methods, and modular configuration. It is designed to be non-intrusive and avoids global state.30                |
| **Best For**      | Large, complex, and performance-sensitive applications. Excellent for projects that require deep integration with web frameworks like Django or FastAPI.31 | Projects that prioritize simplicity, a clean and Pythonic API, and strong integration with static type checking without the need for a compiled extension.30 |

#### **In-Depth Example with dependency-injector**

Let's expand on the NotificationService example from the previous chapter to demonstrate how dependency-injector can automate the assembly and provide powerful features like configuration management and test-time overriding.

Python

import os\
from dependency\_injector import containers, providers\
from dependency\_injector.wiring import inject, Provide\
from unittest.mock import Mock

\# --- Application Components (from Chapter 5) ---

from abc import ABC, abstractmethod

class IMessageClient(ABC):\
@abstractmethod\
def send(self, recipient: str, message: str) -> None:\
pass

class NotificationService:\
def \_\_init\_\_(self, client: IMessageClient):\
self.client = client

```
def send\_notification(self, user: str, message: str):
    self.client.send(user, message)
```

class EmailClient(IMessageClient):\
def \_\_init\_\_(self, api\_key: str):\
self.api\_key = api\_key\
print(f"EmailClient initialized with API key:...{api\_key\[-4:]}")

```
def send(self, recipient: str, message: str) \-\> None:
    print(f"Sending email to {recipient}: {message}")
```

class SmsClient(IMessageClient):\
def \_\_init\_\_(self, account\_sid: str):\
self.account\_sid = account\_sid\
print(f"SmsClient initialized with Account SID:...{account\_sid\[-4:]}")

```
def send(self, recipient: str, message: str) \-\> None:
    print(f"Sending SMS to {recipient}: {message}")
```

\# --- Dependency Injection Container ---

class AppContainer(containers.DeclarativeContainer):\
"""Defines the application's dependency graph."""

```
\# Configuration provider reads from environment variables, YAML, etc.
config \= providers.Configuration()

\# Singleton provider for EmailClient, configured via config.
email\_client \= providers.Singleton(
    EmailClient,
    api\_key=config.email.api\_key
)

\# Factory provider for SmsClient, creating a new instance each time.
sms\_client \= providers.Factory(
    SmsClient,
    account\_sid=config.sms.account\_sid
)

\# Selector provider chooses a client based on configuration.
message\_client \= providers.Selector(
    config.default\_client,
    email=email\_client,
    sms=sms\_client,
)

\# Factory provider for our high-level NotificationService.
\# It will be injected with the client chosen by the selector.
notification\_service \= providers.Factory(
    NotificationService,
    client=message\_client
)
```

\# --- Main Application Logic ---

@inject\
def main(service: NotificationService = Provide\[AppContainer.notification\_service]):\
"""Main function with dependencies injected by the container."""\
service.send\_notification("user@example.com", "Your order has shipped!")

if \_\_name\_\_ == "\_\_main\_\_":\
\# Create the container instance\
container = AppContainer()

```
\# Load configuration (here, from a dictionary for simplicity)
container.config.from\_dict({
    "default\_client": "email",
    "email": {"api\_key": "EMAIL\_API\_KEY\_1234"},
    "sms": {"account\_sid": "SMS\_ACCOUNT\_SID\_5678"}
})

\# Wire the container to the modules that need injection
container.wire(modules=\[\_\_name\_\_\])

print("--- Running main application \---")
main()

\# \--- Testing Scenario \---
print("\\n--- Running in test mode with a mock client \---")

\# The override() feature is extremely powerful for testing.
\# It replaces the configured provider with a mock object.
mock\_client \= Mock(spec=IMessageClient)
with container.message\_client.override(mock\_client):
    \# When main() is called now, the mock\_client is injected instead.
    main()

\# Verify the mock was called, proving the override worked.
mock\_client.send.assert\_called\_once\_with(
    "user@example.com", "Your order has shipped\!"
)
print("Mock client was called successfully.")
```

This example demonstrates the power of a DI framework. The AppContainer centralizes the object creation logic. The main function is completely decoupled from how the NotificationService is created or which IMessageClient it uses. Most importantly, the override() context manager allows for seamless substitution of dependencies during testing, a cornerstone of building reliable, loosely coupled systems.31

## **Conclusion: A Synthesis for Architectural Excellence**

### **Synergy of Principles**

The SOLID principles are not isolated rules but a cohesive set of guidelines that work in synergy to promote robust software architecture. The Single Responsibility Principle lays the groundwork by creating small, focused classes that are easy to understand and maintain. The Open/Closed and Interface Segregation Principles then leverage abstraction to make systems extensible and lean, allowing new functionality to be added without modifying core components and ensuring that clients are not burdened with unnecessary dependencies. The Liskov Substitution Principle ensures that these abstractions are behaviorally sound, guaranteeing that subtypes can be used interchangeably with their base types without error. Finally, the Dependency Inversion Principle uses these well-defined abstractions to decouple the entire system, allowing high-level business logic to remain independent of low-level implementation details.

### **SOLID in the Python 3.12+ Era**

The continuous evolution of Python's static typing capabilities, particularly the enhancements in version 3.12 and later, provides developers with more powerful tools to apply these principles. The new, more ergonomic syntax for generics (PEP 695) simplifies the creation of the abstractions that are central to OCP, ISP, and DIP. The @override decorator (PEP 698) makes the intent of inheritance explicit, helping to prevent accidental violations of the Liskov Substitution Principle. These features are not merely syntactic sugar; they are practical tools that make adherence to SOLID principles more explicit, less error-prone, and easier to enforce with static analysis, bridging the gap between design theory and practical implementation.

### **Final Word**

Applying the SOLID principles, facilitated by modern language features and implemented through patterns like Dependency Injection, is a hallmark of professional software engineering. This disciplined approach transforms code from being merely functional to being truly robust, scalable, and, most importantly, maintainable over its entire lifecycle. For any system intended to grow and adapt over time, a solid foundation is not an option—it is a necessity.

#### **Works cited**

1. What is SOLID? Principles for Better Software Design - freeCodeCamp, accessed September 3, 2025, <https://www.freecodecamp.org/news/solid-principles-for-better-software-design/>
2. SOLID Design Principles Explained: Building Better Software Architecture - DigitalOcean, accessed September 3, 2025, <https://www.digitalocean.com/community/conceptual-articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design>
3. SOLID - Wikipedia, accessed September 3, 2025, <https://en.wikipedia.org/wiki/SOLID>
4. Single Responsibility Principle in Python | by shailesh jadhav - nonstopio, accessed September 3, 2025, <https://blog.nonstopio.com/single-responsibility-principle-in-python-429dc93c7fd5>
5. The Single Responsibility Principle (SRP) | SOLID Principles in Python, accessed September 3, 2025, <https://yakhyo.github.io/solid-python/solid_python/srp/>
6. SOLID Principles explained in Python with examples. · GitHub, accessed September 3, 2025, <https://gist.github.com/dmmeteo/f630fa04c7a79d3c132b9e9e5d037bfd>
7. The SOLID Principles of Object-Oriented Programming Explained in Plain English, accessed September 3, 2025, <https://www.freecodecamp.org/news/solid-principles-explained-in-plain-english/>
8. Open–closed principle - Wikipedia, accessed September 3, 2025, <https://en.wikipedia.org/wiki/Open%E2%80%93closed_principle>
9. Open/Closed Principle with Python | by Amar Shukla | Medium, accessed September 3, 2025, <https://medium.com/@amarshukla/open-closed-principle-with-python-f13e1b6b41a4>
10. Python Open Closed Principle Design Pattern - Clean Code Studio, accessed September 3, 2025, <https://www.cleancode.studio/python/design-patterns-in-python/python-open-closed-principle-design-pattern>
11. Open closed principle implementation python - Stack Overflow, accessed September 3, 2025, <https://stackoverflow.com/questions/75814531/open-closed-principle-implementation-python>
12. Python 3.12 Preview: Static Typing Improvements – Real Python, accessed September 3, 2025, <https://realpython.com/python312-typing/>
13. What's New In Python 3.12 — Python 3.13.7 documentation, accessed September 3, 2025, <https://docs.python.org/3/whatsnew/3.12.html>
14. The Liskov Substitution Principle (LSP) | SOLID Principles in Python, accessed September 3, 2025, <https://yakhyo.github.io/solid-python/solid_python/lsp/>
15. Python Liskov Substitution Principle, accessed September 3, 2025, <https://www.pythontutorial.net/python-oop/python-liskov-substitution-principle/>
16. Liskov Substitution Principle in Python | by shailesh jadhav - nonstopio, accessed September 3, 2025, <https://blog.nonstopio.com/liskov-substitution-principle-in-python-b68d62924f7b>
17. Liskov substitution principle in Python - Ropali's Blog, accessed September 3, 2025, <https://ropali.hashnode.dev/liskovs-substitution-principle-explained-using-python>
18. What's New in Python 3.12 - Type Hint Improvements - Andy Pearce, accessed September 3, 2025, <https://www.andy-pearce.com/blog/posts/2023/Dec/whats-new-in-python-312-type-hint-improvements/>
19. Interface Segregation Principle (ISP) with Python | by Amar Shukla - Medium, accessed September 3, 2025, <https://medium.com/@amarshukla/interface-segregation-principle-isp-with-python-9e64734c0ab9>
20. Interface Segregation Principle in Python | by shailesh jadhav - nonstopio, accessed September 3, 2025, <https://blog.nonstopio.com/interface-segregation-principle-in-python-cf45771c9f33>
21. Python Interface Segregation Principle - Python Tutorial, accessed September 3, 2025, <https://www.pythontutorial.net/python-oop/python-interface-segregation-principle/>
22. Interface Segregation Principle (ISP) | SOLID Principles in Python, accessed September 3, 2025, <https://yakhyo.github.io/solid-python/solid_python/isp/>
23. Python Dependency Inversion Principle - Python Tutorial, accessed September 3, 2025, <https://www.pythontutorial.net/python-oop/python-dependency-inversion-principle/>
24. From Dependency Inversion to Dependency Injection in Python ..., accessed September 3, 2025, <https://dev.to/markoulis/from-dependency-inversion-to-dependency-injection-in-python-2h70>
25. Dependency Inversion Principle (SOLID) - GeeksforGeeks, accessed September 3, 2025, <https://www.geeksforgeeks.org/system-design/dependecy-inversion-principle-solid/>
26. SOLID Principles: Improve Object-Oriented Design in Python, accessed September 3, 2025, <https://realpython.com/solid-principles-python/>
27. Dependency Injection in Python: A Complete Guide to Cleaner, Scalable Code - Medium, accessed September 3, 2025, <https://medium.com/@rohanmistry231/dependency-injection-in-python-a-complete-guide-to-cleaner-scalable-code-9c6b38d1b924>
28. Python Dependency Injection: How to Do It Safely - Xygeni, accessed September 3, 2025, <https://xygeni.io/blog/python-dependency-injection-how-to-do-it-safely/>
29. Dependency injection in Python | Snyk, accessed September 3, 2025, <https://snyk.io/blog/dependency-injection-python/>
30. injector · PyPI, accessed September 3, 2025, <https://pypi.org/project/injector/>
31. dependency-injector · PyPI, accessed September 3, 2025, <https://pypi.org/project/dependency-injector/>
32. Dependency Injector — Dependency injection framework for Python — Dependency Injector 4.48.1 documentation, accessed September 3, 2025, <https://python-dependency-injector.ets-labs.org/>
33. Injector Library and Exploring Dependency Injection in Python | by Luke Garzia | Medium, accessed September 3, 2025, <https://medium.com/@garzia.luke/injector-library-and-exploring-dependency-injection-in-python-4ce10560cd24>
34. ets-labs/python-dependency-injector: Dependency injection framework for Python - GitHub, accessed September 3, 2025, <https://github.com/ets-labs/python-dependency-injector>
