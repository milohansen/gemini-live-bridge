# Architecture Overview

The current architecture consists of two parts: a home assistant custom component and a home assistant add-on. The custom component is responsible for fetching configuration information from home assistant and sending that to the add-on. The add on proxies audio between the device and the cloud, additionally it provides the final context and handles tool calls.


## Bridge (addon):

```mermaid
sequenceDiagram
    autonumber
    participant Device
    box rgba(33,66,99,0.5) Home Assistant
    participant Addon
    participant Component
    end
    participant Gemini API
    Device->>Addon: Open UDP stream
    Addon->>Component: Get context
    Addon->>Gemini API: Connect via Websocket
    Note over Addon,Gemini API: Session Communication
    Addon->>Device: Return audio UDP stream
    Addon-->>Component: Invoke tool calls

```

## Direct connect:

[docs](https://ai.google.dev/gemini-api/docs/ephemeral-tokens)

```mermaid
sequenceDiagram
    autonumber
    participant Device
    box rgba(33,66,99,0.5) Home Assistant
    participant Component
    end
    participant Gemini API
    Device->>Component: Request session
    Component->>Gemini API: Request token
    Note right of Component: Context sent with request
    Gemini API->>Component: Return token
    Component->>Device: Send token
    Device->>Gemini API: Connect via Websocket
    Note over Device,Gemini API: Session Communication
    Device-->>Component: Invoke tool calls

```