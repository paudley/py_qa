<!-- SPDX-License-Identifier: MIT -->

<!-- Copyright (c) 2025 Blackcat Informatics® Inc. -->

# **A Developer's and Agent's Guide to the google.genai Python SDK**

***

## **1. Foundational Concepts and SDK Migration**

This section establishes the strategic context for the google.genai Python SDK, detailing its role as the unified interface to Google's generative models. It provides a critical migration path for developers transitioning from legacy libraries, ensuring a clear understanding of the SDK's architecture and purpose before delving into specific functionalities.

### **1.1. The Unified google-genai SDK: A Strategic Overview**

The google-genai package is the single, canonical Python SDK for accessing Google's portfolio of generative models, including the Gemini family, Imagen, and others.1 Its introduction represents a significant architectural consolidation, replacing several older, fragmented SDKs such as

google-generativeai and specific generative modules within google-cloud-aiplatform.3 This unification simplifies the developer experience and provides a consistent, modern interface for all generative AI tasks.

A core architectural advantage of the google-genai SDK is its dual support for two distinct API surfaces through a single, consistent client object.6 This design is not merely a technical convenience but a strategic decision to create a seamless pathway for applications to mature from initial experimentation to enterprise-scale deployment. The SDK acts as a bridge between two primary environments:

1. **Gemini Developer API:** Designed for rapid prototyping and development. It uses a simple API key for authentication, allowing developers to get started quickly with minimal setup, often leveraging the free tier available through Google AI Studio.2
2. **Gemini API on Vertex AI:** The enterprise-grade solution integrated within the Google Cloud Platform (GCP). It leverages Google Cloud's robust infrastructure, security, and governance features, using standard GCP authentication mechanisms like Application Default Credentials (ADC) instead of standalone API keys.6

This dual-target capability directly addresses a historical point of friction for developers, who previously had to contend with different SDKs and significant code refactoring when moving an application from a prototyping environment to a production environment on Vertex AI.4 With the unified SDK, this transition is managed by a simple flag during client initialization, allowing the core application logic to remain unchanged.

**Installation**

To install the SDK, a Python version of 3.9+ is required. The package is installed using pip.5

Bash

pip install -q -U google-genai

For applications requiring high-performance asynchronous operations, an optional dependency can be installed to leverage aiohttp as the underlying transport layer, which may offer performance benefits over the default httpx.6

Bash

pip install -q -U "google-genai\[aiohttp]"

### **1.2. Critical Migration Guide: From google-generativeai to google.genai**

The google-generativeai package is officially deprecated. All support, including critical bug fixes, will cease on November 30, 2025. All new feature development, performance enhancements, and access to the latest models are exclusive to the new google-genai SDK.1 Migration is therefore essential for continued access to the latest capabilities and support.

The new SDK introduces a more structured, client-centric paradigm. Whereas the old SDK used a global configuration and model-centric objects, the new SDK centralizes all interactions through a genai.Client instance. This results in a more explicit and stateless API for most operations, improving code clarity and testability.

The following table provides a direct, side-by-side comparison to facilitate the migration of common patterns.

| Feature                 | Old SDK (google-generativeai)            | New SDK (google.genai)                                                                  | Key Changes & Notes                                                                                                      |
| :---------------------- | :--------------------------------------- | :-------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| **Installation**        | pip install google-generativeai          | pip install google-genai                                                                | The package name has changed to reflect the new unified approach.10                                                      |
| **Import**              | import google.generativeai as genai      | from google import genai                                                                | The import path is now from the top-level google package.4                                                               |
| **Authentication**      | genai.configure(api\_key=...)             | client = genai.Client(api\_key=...)                                                      | Authentication is no longer a global setting; it is configured per Client instance.10                                    |
| **Model Instantiation** | model = genai.GenerativeModel(...)       | No direct model instantiation. The model is specified as a parameter in client methods. | The new SDK is largely stateless. The model name is passed directly to methods like client.generate\_content(model=...).2 |
| **Text Generation**     | response = model.generate\_content("...") | response = client.generate\_content(model="...", contents="...")                         | The method is now on the client object, and the prompt is passed via the contents parameter.2                            |
| **Chat Session**        | chat = model.start\_chat()                | chat\_session = client.chats.create(model="...")                                         | Chat functionality is now organized under the client.chats module, with a more explicit create method.13                 |

### **1.3. Client Initialization and Authentication Deep Dive**

Proper client initialization is the first step in using the SDK. The configuration depends on the target environment (Gemini Developer API or Vertex AI). The SDK's authentication mechanisms are designed to support an application's lifecycle, from insecure hardcoded keys in early testing to secure, production-ready service accounts.

**Gemini Developer API**

For development and prototyping, the client is typically initialized directly with an API key obtained from Google AI Studio.7

Python

from google import genai

client = genai.Client(api\_key="YOUR\_API\_KEY")

**Vertex AI API**

For enterprise applications running on Google Cloud, the client is configured to use the Vertex AI backend. This method does not use an API key and instead relies on the environment's Application Default Credentials (ADC), which are typically configured via the gcloud CLI or service account credentials in a cloud environment.16

Python

from google import genai

client = genai.Client(\
vertexai=True,\
project="your-gcp-project-id",\
location="us-central1"\
)

**Environment Variables (Best Practice)**

Hardcoding credentials is a security risk. The recommended approach is to use environment variables, which the SDK automatically detects at runtime.6 This practice decouples the code from the credentials, allowing the same code to run in different environments with different permissions.

* **For Gemini Developer API:** Set either GEMINI\_API\_KEY or GOOGLE\_API\_KEY. If both are set, GOOGLE\_API\_KEY takes precedence.6\
  Bash\
  export GOOGLE\_API\_KEY="your-api-key"

* **For Vertex AI API:** Set three variables to configure the client for Vertex AI.\
  Bash\
  export GOOGLE\_GENAI\_USE\_VERTEXAI=true\
  export GOOGLE\_CLOUD\_PROJECT="your-gcp-project-id"\
  export GOOGLE\_CLOUD\_LOCATION="us-central1"

After setting the appropriate environment variables, the client can be initialized without any arguments:

Python

from google import genai

\# The client will automatically configure itself based on environment variables.\
client = genai.Client()

**API Versioning**

By default, the SDK may use beta API endpoints to provide access to the latest features. For production applications, it is a best practice to explicitly lock the API version to a stable release (e.g., v1) to ensure stability and prevent unexpected breaking changes. This is achieved using the http\_options parameter.6

Python

from google import genai\
from google.genai import types

\# Example for Vertex AI, locking to the 'v1' stable API\
client = genai.Client(\
vertexai=True,\
project="your-gcp-project-id",\
location="us-central1",\
http\_options=types.HttpOptions(api\_version='v1')\
)

***

## **2. Core Scenarios: Generating Content**

This section provides detailed, machine-parsable code examples for the most common use cases of the google.genai SDK. It covers single-turn text generation, streaming for interactive applications, multimodal inputs combining text with media, and asynchronous patterns for building scalable services.

### **2.1. Basic Text Generation (Single-Turn)**

The most fundamental operation is generating content from a text prompt in a single request-response cycle. This is handled by the client.generate\_content() method (also accessible via the client.models submodule).

A simple call involves providing the model name and the prompt text via the contents parameter. The response object contains the generated text, which is accessed through the .text attribute.9

Python

from google import genai

\# Assumes client is initialized via environment variables\
client = genai.Client()

response = client.generate\_content(\
model="gemini-2.5-flash",\
contents="Explain the theory of relativity in three sentences."\
)

print(response.text)

The contents argument is highly flexible. It can accept a simple string, as shown above, or a list of strings. When a list of strings is provided, the SDK automatically combines them into a single "user" role message before sending the request to the API.7 For more complex scenarios, such as defining multi-role conversations, a fully structured

types.Content object can be provided.

### **2.2. Streaming for Real-Time Feedback**

For interactive applications like chatbots, waiting for the full response to be generated can result in poor user experience due to perceived latency. Streaming allows the application to receive the response in chunks as it is being generated by the model. This enables a real-time, "typing" effect.19

The client.generate\_content\_stream() method returns an iterator. The canonical way to process this is with a for loop, printing each chunk's text as it arrives.21

Python

from google import genai

client = genai.Client()

\# The response is an iterator of GenerateContentResponse chunks\
stream = client.generate\_content\_stream(\
model="gemini-2.5-flash",\
contents="Write a short story about a robot who discovers music."\
)

for chunk in stream:\
print(chunk.text, end="")\
print() # For a final newline

### **2.3. Multimodal Interaction: Beyond Text**

Gemini models are inherently multimodal, capable of processing and reasoning over combinations of text, images, audio, and video in a single prompt.12 This is achieved by passing a list of mixed content types to the

contents parameter.

**Text and Image(s)**

For local images, the Pillow (PIL) library is commonly used to open the image file. The resulting Image object can be directly included in the contents list alongside text prompts.25

Python

import PIL.Image\
from google import genai

client = genai.Client()

img = PIL.Image.open("path/to/your/image.jpg")

response = client.generate\_content(\
model="gemini-2.5-flash", # Use a model that supports vision\
contents=\
)

print(response.text)

Multiple images can be included in the same prompt to perform comparison or synthesis tasks.24

**Text and Audio/Video**

While small media files can sometimes be passed directly, the robust and recommended method for larger files like audio and video is to first upload them using the SDK's File API. This API processes the file and returns a reference that can be used in subsequent prompts. This approach is more efficient and reliable for large media.8

Python

from google import genai

client = genai.Client()

\# 1. Upload the file to the Gemini API\
print("Uploading file...")\
video\_file = client.files.upload(\
file="path/to/your/video.mp4",\
display\_name="My Test Video"\
)\
print(f"Completed upload: {video\_file.uri}")

\# 2. Use the file reference in a prompt\
print("Generating content...")\
response = client.generate\_content(\
model="gemini-2.5-flash",\
contents=\["Please provide a summary of this video.", video\_file]\
)

print(response.text)

\# 3. Clean up the file after use\
client.files.delete(file=video\_file)\
print("Deleted file.")

### **2.4. Asynchronous Operations for Scalability**

For high-throughput applications that need to handle many concurrent API calls without being blocked, the SDK provides a complete asynchronous client via the client.aio attribute.11 This client is designed for use with Python's

asyncio library.

A key design principle of the SDK is the direct parity between its synchronous and asynchronous APIs. For nearly every method on the synchronous client, there is a corresponding await-able method on client.aio with the same name and parameters. This consistency dramatically reduces the learning curve for developers transitioning from synchronous to asynchronous code.

**Asynchronous Generation (Non-Streaming)**

The await keyword is used to call the asynchronous version of generate\_content.11

Python

import asyncio\
from google import genai

async def main():\
client = genai.Client()\
response = await client.aio.models.generate\_content(\
model="gemini-2.5-flash",\
contents="Tell a short, futuristic joke."\
)\
print(response.text)

if \_\_name\_\_ == "\_\_main\_\_":\
asyncio.run(main())

**Asynchronous Streaming**

Streaming in an asynchronous context is handled with the async for syntax, which iterates over the asynchronously generated chunks.21

Python

import asyncio\
from google import genai

async def main():\
client = genai.Client()\
stream = await client.aio.models.generate\_content\_stream(\
model="gemini-2.5-flash",\
contents="List three benefits of asynchronous programming."\
)\
async for chunk in stream:\
print(chunk.text, end="")\
print()

if \_\_name\_\_ == "\_\_main\_\_":\
asyncio.run(main())

***

## **3. Advanced Capabilities and Workflows**

This section explores the SDK's advanced features that enable the development of sophisticated, agentic applications. These capabilities move beyond simple content generation to include stateful conversations, interaction with external tools, semantic data processing, and structured data extraction.

### **3.1. Managing Multi-Turn Conversations (Chat)**

To build conversational agents, it is necessary to maintain the context of the dialogue across multiple turns. The SDK manages this state through a ChatSession object.

A new chat session is initiated using client.chats.create(). This returns a chat\_session object that maintains the conversation history. Subsequent messages are sent using chat\_session.send\_message(), and the SDK automatically appends both the user's message and the model's response to the history, providing the necessary context for the next turn.11

Python

from google import genai

client = genai.Client()

chat\_session = client.chats.create(model="gemini-2.5-flash")

response1 = chat\_session.send\_message("Hello, I'm interested in learning about Python.")\
print(f"AI: {response1.text}")

response2 = chat\_session.send\_message("What are the main data types?")\
print(f"AI: {response2.text}")

\# The history now contains the full conversation\
\# print(chat\_session.history)

**Initializing with Existing History**

A conversation can be resumed by providing its history during the creation of the chat session. The history parameter accepts a list of types.UserContent and types.ModelContent objects, allowing an application to reconstruct the state of a previous conversation.14

Python

from google import genai\
from google.genai import types

client = genai.Client()

\# Recreate a conversation history\
previous\_history =),\
types.ModelContent(parts=)\
]

chat\_session = client.chats.create(\
model="gemini-2.5-flash",\
history=previous\_history\
)

response = chat\_session.send\_message("What is a famous landmark there?")\
print(response.text)

**Persisting Chat History**

Persisting chat history across application restarts requires serializing the chat\_session.history object. While this is straightforward for text-only conversations (e.g., using pickle or converting to JSON), it presents a significant challenge for multimodal chats. History that includes references to files uploaded via the File API will fail to load if those file references have expired or been deleted, resulting in PermissionDenied errors. A robust solution must handle these invalid file references, for example, by re-uploading the missing files or stripping the invalid parts from the history before re-initializing the session.31

### **3.2. Function Calling: Giving the Model Tools**

Function calling is a cornerstone of building reliable AI agents. It allows the model to act as a reasoning engine that can intelligently decide to invoke external, deterministic tools (like APIs or local functions) to acquire information or perform actions. This grounds the model in factual data and enables it to interact with external systems, moving beyond simple text generation to task completion.

The process involves four key steps 32:

1. **Define Tools:** The developer provides the model with declarations for available functions, including their names, descriptions, and strongly-typed parameters. The google-genai SDK can automatically generate these declarations from standard Python functions that use type hints and docstrings.2
2. **Model Call & Tool Selection:** The model receives the user's prompt and the list of tool declarations. It analyzes the prompt and, if it determines a tool is needed, returns a genai.types.FunctionCall object instead of a text response. This object contains the name of the function to call and the arguments to use.
3. **Application Execution:** The model *does not execute the function*. The developer's application code is responsible for receiving the FunctionCall object, invoking the corresponding Python function with the provided arguments, and capturing its return value.34
4. **Return Result to Model:** The return value from the function is sent back to the model in the next conversational turn as a genai.types.FunctionResponse object. The model then uses this new information to generate a final, natural-language response for the user.32

The following is a complete, end-to-end example:

Python

from google import genai\
from google.genai import types

\# --- Step 1: Define the tool (a Python function) ---\
def get\_current\_weather(location: str, unit: str = "celsius"):\
"""\
Get the current weather in a given location.

```
Args:
    location: The city and state, e.g., "San Francisco, CA".
    unit: The temperature unit, either "celsius" or "fahrenheit".
"""
\# This is a mock function. In a real application, this would
\# call a weather API.
if "tokyo" in location.lower():
    return {"temperature": 15, "unit": unit, "description": "Cloudy"}
elif "san francisco" in location.lower():
    return {"temperature": 20, "unit": unit, "description": "Sunny"}
else:
    return {"temperature": 22, "unit": unit, "description": "Clear"}
```

\# --- Step 2: Call the model with the tool and a prompt ---\
client = genai.Client()

\# The SDK automatically generates the declaration from the function\
tools = \[get\_current\_weather]

response = client.generate\_content(\
model="gemini-2.5-flash",\
contents="What's the weather like in Tokyo?",\
tools=tools\
)

\# The model returns a FunctionCall object\
tool\_call = response.candidates.content.parts.function\_call\
print(f"Model wants to call function: {tool\_call.name} with args: {dict(tool\_call.args)}")

\# --- Step 3: Execute the function in the application ---\
function\_to\_call = get\_current\_weather\
function\_args = dict(tool\_call.args)\
function\_response\_data = function\_to\_call(\*\*function\_args)\
print(f"Function execution result: {function\_response\_data}")

\# --- Step 4: Return the result to the model ---\
response = client.generate\_content(\
model="gemini-2.5-flash",\
contents=.content, # Model's previous turn (the function call)\
\# The function's result\
types.Part.from\_function\_response(\
name=tool\_call.name,\
response=function\_response\_data,\
)\
],\
tools=tools\
)

\# The model now generates a natural language response based on the tool's output\
print(response.text)

### **3.3. Generating Text Embeddings for Semantic Tasks**

Text embeddings are numerical vector representations of text that capture its semantic meaning. They are a foundational component for tasks like semantic search, clustering, classification, and Retrieval-Augmented Generation (RAG).35

The SDK provides the client.embed\_content() method to generate these embeddings. For optimal performance, it is crucial to specify the intended use case via the task\_type parameter. This allows the model to produce embeddings that are fine-tuned for a specific task, such as distinguishing between a search query and the documents it should be compared against.35

The following example demonstrates generating embeddings for a list of documents and then using scikit-learn to compute the cosine similarity between them, a common measure of semantic relatedness.38

Python

import numpy as np\
from sklearn.metrics.pairwise import cosine\_similarity\
from google import genai\
from google.genai import types

client = genai.Client()

documents =

result = client.embed\_content(\
model="gemini-embedding-001",\
contents=documents,\
task\_type=types.TaskType.RETRIEVAL\_DOCUMENT\
)

\# Extract the embedding vectors\
embeddings = \[np.array(e.values) for e in result.embeddings]\
embeddings\_matrix = np.array(embeddings)

\# Calculate and print the similarity matrix\
similarity\_matrix = cosine\_similarity(embeddings\_matrix)\
print("Cosine Similarity Matrix:")\
print(similarity\_matrix)

### **3.4. Enforcing Structured Output with JSON Mode**

For many applications, it is necessary to receive data from the model in a predictable, structured format rather than as free-form text. Parsing natural language can be brittle and error-prone. The SDK's JSON mode forces the model to output a valid JSON object that conforms to a specified schema.39

The schema can be defined in several ways, but the most Pythonic and recommended approach is to use a Pydantic BaseModel. The SDK automatically converts the Pydantic model into the required JSON schema. The schema is then passed to the generation\_config of the API call.39

Python

from pydantic import BaseModel, Field\
from google import genai\
from google.genai import types\
import json

\# --- Define the desired output structure using Pydantic ---\
class Recipe(BaseModel):\
recipe\_name: str = Field(description="The name of the recipe.")\
ingredients: list\[str] = Field(description="A list of ingredients for the recipe.")\
steps: list\[str] = Field(description="The steps to prepare the recipe.")\
prep\_time\_minutes: int = Field(description="The preparation time in minutes.")

\# --- Make the API call with the schema ---\
client = genai.Client()

response = client.generate\_content(\
model="gemini-2.5-flash",\
contents="Generate a simple recipe for pancakes.",\
generation\_config=types.GenerateContentConfig(\
response\_schema=Recipe\
)\
)

\# The response.text is a JSON string that conforms to the Recipe schema\
recipe\_json = response.text\
print(json.dumps(json.loads(recipe\_json), indent=2))

\# You can now parse it directly with the Pydantic model\
pancake\_recipe = Recipe.model\_validate\_json(recipe\_json)\
print(f"\nRecipe Name: {pancake\_recipe.recipe\_name}")\
print(f"Preparation Time: {pancake\_recipe.prep\_time\_minutes} minutes")

When using structured output, it is a best practice to keep schemas as simple as possible. Overly complex schemas with deep nesting, long property names, or numerous optional fields can increase token usage and may lead to a 400 INVALID\_ARGUMENT error.39

***

## **4. Best Practices, Optimization, and Control**

This section details the operational aspects of using the google.genai SDK effectively. It covers techniques for controlling model output, implementing safety measures, and optimizing for both performance and cost, which are critical for deploying robust and efficient production applications.

### **4.1. Fine-Tuning Model Behavior with GenerationConfig**

The GenerationConfig object provides granular control over the token generation process, allowing developers to tune the model's output to suit specific use cases. These parameters are passed to the config argument of the generate\_content method.11

The most common parameters are 40:

* temperature: A value between 0.0 and 1.0 that controls the degree of randomness in the output. Lower values (e.g., 0.1) make the model more deterministic and are suitable for factual or code-generation tasks. Higher values (e.g., 0.9) encourage more creative and diverse responses. A temperature of 0 is fully deterministic.
* top\_p: Controls nucleus sampling. The model considers only the tokens whose cumulative probability mass adds up to the top\_p value. A typical value is 0.95.
* top\_k: The model selects the next token from the top\_k most probable tokens. A top\_k of 1 is equivalent to greedy decoding.
* max\_output\_tokens: Sets a hard limit on the number of tokens the model can generate in its response. This is a crucial parameter for controlling latency and API costs.
* stop\_sequences: A list of strings that, if generated by the model, will cause the generation process to halt immediately.

Python

from google import genai\
from google.genai import types

client = genai.Client()

\# Configure for a more creative and lengthy response\
creative\_config = types.GenerateContentConfig(\
temperature=0.9,\
top\_p=0.95,\
max\_output\_tokens=1024,\
stop\_sequences=\
)

response = client.generate\_content(\
model="gemini-2.5-flash",\
contents="Write the beginning of a fantasy novel.",\
config=creative\_config\
)

print(response.text)

### **4.2. A Practical Guide to Safety Settings**

The Gemini API includes configurable safety filters to prevent the generation of harmful content. These filters cover categories such as Harassment, Hate Speech, Sexually Explicit content, and Dangerous Content.41 By default, the API blocks content with a medium or higher probability of being unsafe, but this threshold can be adjusted to be more or less restrictive based on the application's needs.41

The thresholds are defined by API enums, which correspond to the settings available in the Google AI Studio UI. Understanding this mapping is essential for correct configuration.

| Threshold (API Enum)   | Description                                                                        | Default For                             |
| :--------------------- | :--------------------------------------------------------------------------------- | :-------------------------------------- |
| BLOCK\_NONE             | Always show content, regardless of the probability of it being unsafe.             | Newer models like gemini-1.5-pro-002 43 |
| BLOCK\_ONLY\_HIGH        | Block content only when there is a high probability of it being unsafe.            | Corresponds to "Block few" in UI 41     |
| BLOCK\_MEDIUM\_AND\_ABOVE | Block content when there is a medium or high probability of it being unsafe.       | Older models 41                         |
| BLOCK\_LOW\_AND\_ABOVE    | Block content when there is a low, medium, or high probability of it being unsafe. | Corresponds to "Block most" in UI 41    |

Safety settings are configured per-request within the GenerationConfig object.

Python

from google import genai\
from google.genai import types

client = genai.Client()

\# Example: Set a less restrictive policy for harassment\
safety\_config = types.GenerateContentConfig(\
safety\_settings=\
)

\# This prompt might be blocked by default but may pass with the custom setting.\
prompt = "Write a script where two characters are roasting each other."

response = client.generate\_content(\
model="gemini-2.5-flash",\
contents=prompt,\
config=safety\_config\
)

\# Check if the prompt or response was blocked\
if response.prompt\_feedback.block\_reason:\
print(f"Prompt was blocked: {response.prompt\_feedback.block\_reason.name}")\
elif response.candidates.finish\_reason.name == 'SAFETY':\
print("Response was blocked for safety reasons.")\
else:\
print(response.text)

### **4.3. Cost and Performance Optimization**

Managing API usage effectively requires a focus on both cost and performance. The SDK provides several mechanisms to optimize these factors.

**Managing the "Thinking" Feature**

Gemini 2.5 series models employ a "thinking" feature, which involves an internal reasoning phase to improve the quality and accuracy of complex responses. This process, however, consumes additional output tokens and increases response latency.9 The

thinking\_budget parameter within ThinkingConfig allows for precise control over this trade-off:

* thinking\_budget=0: Disables the thinking feature entirely. This is ideal for simpler tasks where speed and cost are prioritized over maximum quality.
* thinking\_budget=-1: Enables dynamic thinking, where the model decides how many thinking tokens to use based on the complexity of the prompt. This is the default.
* thinking\_budget=\<positive\_integer>: Sets a specific token budget for the thinking phase.

Python

from google import genai\
from google.genai import types

client = genai.Client()

\# Disable thinking for a fast, low-cost response\
config\_no\_thinking = types.GenerateContentConfig(\
thinking\_config=types.ThinkingConfig(thinking\_budget=0)\
)

response = client.generate\_content(\
model="gemini-2.5-flash",\
contents="What is 2+2?",\
config=config\_no\_thinking\
)\
print(response.text)

**Leveraging Batch Mode for Cost Savings**

For large-scale, non-interactive workloads, such as classifying a dataset or summarizing thousands of documents, the Gemini API offers a Batch Mode. Requests submitted via Batch Mode are processed asynchronously and are priced at a **50% discount** compared to standard synchronous calls.46 This mode offloads the complexity of queuing, rate-limit handling, and retries from the client application. Results are typically available within 24 hours.47 Batch operations are managed through the

genai.batches module.16

**Proactive Token Counting**

To prevent errors from exceeding a model's context window and to accurately forecast costs, it is a best practice to count the number of tokens in a prompt *before* sending it to the API. The client.count\_tokens() method provides this functionality.29

Python

from google import genai

client = genai.Client()

prompt = "This is a long piece of text that we want to send to the model. We should count its tokens first."

token\_count = client.count\_tokens(\
model="gemini-2.5-flash",\
contents=prompt\
)

print(f"Total tokens in prompt: {token\_count.total\_tokens}")

***

## **5. Error Handling and Troubleshooting**

Building resilient applications requires robust error handling to manage transient network issues, API limitations, and invalid requests. This section provides a comprehensive guide to identifying and resolving common errors when using the google.genai SDK.

### **5.1. Common API Errors and Solutions**

API requests can fail for various reasons, each indicated by a standard HTTP status code. Understanding these codes is the first step in diagnosing and resolving issues.

| HTTP Code | Status             | Common Cause(s)                                                                                                                                       | Recommended Action(s)                                                                                                                           |
| :-------- | :----------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------- |
| 400       | INVALID\_ARGUMENT   | Malformed request body (e.g., wrong parameter name), invalid model parameter value (e.g., temperature out of range), or prompt exceeds token limit.48 | Validate the request payload against the API documentation. Use client.count\_tokens() to check prompt length.                                   |
| 403       | PERMISSION\_DENIED  | The API key is invalid, has been revoked, or lacks the necessary permissions for the requested resource (e.g., a tuned model).48                      | Verify the API key is correct and active. For Vertex AI, check the IAM permissions of the service account.                                      |
| 429       | RESOURCE\_EXHAUSTED | The number of requests per minute (RPM) or tokens per minute (TPM) has exceeded the project's rate limit.48                                           | Implement an exponential backoff and retry mechanism. If limits are consistently hit, request a quota increase.                                 |
| 500       | INTERNAL           | An unexpected server-side error occurred. This can sometimes be triggered by an excessively long or complex input context.48                          | This is often a transient issue. Retry the request with exponential backoff. If the error persists, try reducing the prompt complexity or size. |
| 503       | UNAVAILABLE        | The service is temporarily overloaded or unavailable. This indicates a transient capacity issue on Google's side.48                                   | Retry the request after a short delay, using an exponential backoff strategy.                                                                   |

### **5.2. Handling Rate Limits (429 RESOURCE\_EXHAUSTED)**

Rate limits are a fundamental aspect of using any large-scale API. They are enforced per project and are measured in both Requests Per Minute (RPM) and Tokens Per Minute (TPM).51 When a

429 error is received, the application should not immediately retry the request. The standard and most effective strategy is to retry with **exponential backoff and jitter**. This pattern involves waiting for an exponentially increasing amount of time between retries, with a small random delay (jitter) added to prevent multiple clients from retrying in lockstep.

Python

import time\
import random

def make\_request\_with\_backoff(client, max\_retries=5, base\_delay=1.0):\
retries = 0\
while retries < max\_retries:\
try:\
\# Replace with your actual API call\
response = client.generate\_content(\
model="gemini-2.5-flash",\
contents="Generate a response."\
)\
return response\
except Exception as e: # In a real app, catch the specific rate limit exception\
if "429" in str(e): # Simple check for rate limit error\
retries += 1\
if retries >= max\_retries:\
raise e

```
            \# Exponential backoff with jitter
            delay \= (base\_delay \* (2 \*\* retries)) \+ random.uniform(0, 1)
            print(f"Rate limit exceeded. Retrying in {delay:.2f} seconds...")
            time.sleep(delay)
        else:
            \# Re-raise other exceptions immediately
            raise e
```

### **5.3. Resolving Model-Specific Issues**

* **Repetitive Output:** If the model generates repetitive text, especially in structured formats like Markdown tables, it may be attempting to visually align content unnecessarily. Solutions include adding explicit instructions to the prompt (e.g., "Use only three hyphens for table separators"), increasing the temperature to 0.8 or higher, or making all fields in a structured output schema required.48
* **Safety Blocks:** If a request is blocked, the response object will contain information about the reason. Check response.prompt\_feedback.block\_reason for blocked prompts and response.candidates.finish\_reason for blocked responses. If the finish\_reason is SAFETY, the application should handle this gracefully, either by informing the user or by adjusting the prompt or safety settings for a retry.44
* **Recitation Blocks:** A finish\_reason of RECITATION indicates the model's output too closely resembles its training data. To mitigate this, increase the uniqueness of the prompt and use a higher temperature.48

### **5.4. Robust Python Exception Handling**

All API calls should be wrapped in try...except blocks to handle potential failures gracefully and prevent the application from crashing. This is particularly important for transient errors like 500 INTERNAL or 503 UNAVAILABLE, which can often be resolved by simply retrying the request.

The following example combines a try...except block with a simple retry loop to create a more resilient function for making API calls.50

Python

import time\
from google import genai

def generate\_content\_safely(client, prompt: str, max\_retries=3):\
"""\
Makes a request to the Gemini API with a retry mechanism for common\
transient errors.\
"""\
retry\_count = 0\
while retry\_count < max\_retries:\
try:\
response = client.generate\_content(\
model="gemini-2.5-flash",\
contents=prompt\
)\
return response.text\
except Exception as e:\
\# In a production environment, log the specific error.\
\# This example catches a generic exception for simplicity.\
print(f"An error occurred: {e}")\
retry\_count += 1\
if retry\_count >= max\_retries:\
print("Max retries reached. Failing.")\
return None

```
        \# Simple linear backoff for demonstration
        delay \= 2 \* retry\_count
        print(f"Retrying in {delay} seconds...")
        time.sleep(delay)
return None
```

\# --- Usage ---\
client = genai.Client()\
result = generate\_content\_safely(client, "Tell me a fact about space.")\
if result:\
print(result)

#### **Works cited**

1. google-gemini/deprecated-generative-ai-python: This SDK is now deprecated, use the new unified Google GenAI SDK. - GitHub, accessed September 3, 2025, <https://github.com/google-gemini/deprecated-generative-ai-python>
2. Migrating to the new Google Gen AI SDK (Python) | by Maciej Strzelczyk - Medium, accessed September 3, 2025, <https://medium.com/google-cloud/migrating-to-the-new-google-gen-ai-sdk-python-074d583c2350>
3. Vertex AI SDK migration guide - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk>
4. Need clarification about Google AI python packageS (google-genai vs google-generativeai) - Gemini API - Google AI Developers Forum, accessed September 3, 2025, <https://discuss.ai.google.dev/t/need-clarification-about-google-ai-python-packages-google-genai-vs-google-generativeai/61116>
5. Gemini API libraries | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/libraries>
6. googleapis/python-genai: Google Gen AI Python SDK provides an interface for developers to integrate Google's generative models into their Python applications. - GitHub, accessed September 3, 2025, <https://github.com/googleapis/python-genai>
7. google-genai - PyPI, accessed September 3, 2025, <https://pypi.org/project/google-genai/>
8. The Google GenAI SDK: A guide with a Python tutorial - Wandb, accessed September 3, 2025, <https://wandb.ai/byyoung3/gemini-genai/reports/The-Google-GenAI-SDK-A-guide-with-a-Python-tutorial--VmlldzoxMzE2NDIwNA>
9. Gemini API quickstart | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/quickstart>
10. Migrate to the Google GenAI SDK | Gemini API | Google AI for ..., accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/migrate>
11. Google Gen AI SDK documentation, accessed September 3, 2025, <https://googleapis.github.io/python-genai/>
12. deprecated-generative-ai-python - Swift Package Registry, accessed September 3, 2025, <https://swiftpackageregistry.com/google-gemini/deprecated-generative-ai-python>
13. google-gemini/gemini-api-quickstart: Get up and running with the Gemini API in under 5 minutes (with Python) - GitHub, accessed September 3, 2025, <https://github.com/google-gemini/gemini-api-quickstart>
14. Create a chat session with a Generative Model | Generative AI on ..., accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-textgen-chat-with-txt>
15. Using Gemini API keys | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/api-key>
16. Submodules - Google Gen AI SDK documentation, accessed September 3, 2025, <https://googleapis.github.io/python-genai/genai.html>
17. Gemini API in Vertex AI quickstart - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/start/quickstart>
18. Google Gen AI SDK | Generative AI on Vertex AI - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/sdks/overview>
19. Stream answers | AI Applications - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/generative-ai-app-builder/docs/stream-answer>
20. Implementing response streaming from LLMs - Hivekind, accessed September 3, 2025, <https://hivekind.com/blog/implementing-response-streaming-from-llms>
21. Streaming.ipynb - Colab, accessed September 3, 2025, <https://colab.research.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Streaming.ipynb>
22. Generate streaming text content with Generative Model | Generative AI on Vertex AI | Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-textgen-with-txt-stream>
23. Generative AI - Gemini multimodal | Google Cloud Skills Boost, accessed September 3, 2025, <https://www.cloudskillsboost.google/course_templates/593/video/565192?locale=uk>
24. Mastering Multimodality: A Journey with Google's Gemini and ..., accessed September 3, 2025, <https://medium.com/@akashpittalwar107/mastering-multimodality-a-journey-with-googles-gemini-and-multimodal-rag-75325bbf5e1f>
25. Full Tutorial: How to Use Google Generative AI for Text and Image Content Creation in Python - KoshurAI, accessed September 3, 2025, <https://koshurai.medium.com/full-tutorial-how-to-use-google-generative-ai-for-text-and-image-content-creation-in-python-ad5c43c1c761>
26. Generating content | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/api/generate-content>
27. Multimodal AI in action - YouTube, accessed September 3, 2025, <https://www.youtube.com/watch?v=pEmCgIGpIoo>
28. Generate text from multimodal prompt | Generative AI on Vertex AI - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/samples/generativeaionvertexai-gemini-single-turn-multi-image>
29. Google Gen AI Python SDK: A Complete Guide - Analytics Vidhya, accessed September 3, 2025, <https://www.analyticsvidhya.com/blog/2025/08/google-gen-ai-python-sdk-guide/>
30. How to Set Up and Use Google Generative AI in Python - Priyanshu Sharma, accessed September 3, 2025, <https://priyanshu.com.np/genai/>
31. What is the best way to persist chat history into file? - Gemini API ..., accessed September 3, 2025, <https://discuss.ai.google.dev/t/what-is-the-best-way-to-persist-chat-history-into-file/3804>
32. Function calling with the Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/function-calling>
33. Gemini API: Function calling with Python - Colab - Google, accessed September 3, 2025, <https://colab.research.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Function_calling.ipynb>
34. Function calling with Gemma | Google AI for Developers - Gemini API, accessed September 3, 2025, <https://ai.google.dev/gemma/docs/capabilities/function-calling>
35. Gemini API: Getting started with Gemini embedding models - Colab - Google, accessed September 3, 2025, <https://colab.research.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Embeddings.ipynb>
36. Get text embeddings | Generative AI on Vertex AI - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings>
37. Text embeddings API | Generative AI on Vertex AI - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/text-embeddings-api>
38. Embeddings | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/embeddings>
39. Structured output | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/structured-output>
40. Prompt design strategies | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/prompting-strategies>
41. Safety settings | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/safety-settings>
42. Safety and content filters | Generative AI on Vertex AI - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/configure-safety-filters>
43. Migrate \`embedchain/\` from \`google-generativeai\` to \`python-genai\` · Issue #3361 · mem0ai/mem0 - GitHub, accessed September 3, 2025, <https://github.com/mem0ai/mem0/issues/3361>
44. Safety settings | Google AI for Developers - Gemini API, accessed September 3, 2025, <https://ai.google.dev/palm_docs/safety_setting_palm>
45. Gemini thinking | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/thinking>
46. Gemini Developer API Pricing | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/pricing>
47. Batch Mode in the Gemini API: Process more for less - Google ..., accessed September 3, 2025, <https://developers.googleblog.com/en/scale-your-ai-workloads-batch-mode-gemini-api/>
48. Troubleshooting guide | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/troubleshooting>
49. Generative AI on Vertex AI inference API errors | Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/api-errors>
50. Resolving Google Gemini API Error 500 in Python with try-except Loops - Kent McCann MD, accessed September 3, 2025, <https://www.kentmccannmd.com/resolving-google-gemini-api-error-500/>
51. Rate limits | Gemini API | Google AI for Developers, accessed September 3, 2025, <https://ai.google.dev/gemini-api/docs/rate-limits>
52. Generate text from an image with safety settings | Generative AI on Vertex AI - Google Cloud, accessed September 3, 2025, <https://cloud.google.com/vertex-ai/generative-ai/docs/samples/generativeaionvertexai-gemini-safety-settings>
53. Python for AI: Week 10 — Error Handling and Exceptions in Python - Medium, accessed September 3, 2025, <https://medium.com/@ebimsv/python-for-ai-week-10-error-handling-and-exceptions-in-python-296a75c34abe>
