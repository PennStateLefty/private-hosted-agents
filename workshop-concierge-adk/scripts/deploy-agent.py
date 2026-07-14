#!/usr/bin/env python
"""Deploy the Workshop Concierge as a Foundry Hosted Agent (Responses protocol)
using the azure-ai-projects SDK create_version path.

This is the architecture-preserving deploy path documented in
"Deploy a hosted agent" (Python SDK pivot). It targets the EXISTING landing-zone
Foundry project — it does not create infrastructure. `azd deploy` from this same
directory is the alternative one-command path (see azure.yaml).

Requires: on the private network (P2S VPN) so the private project endpoint
resolves, and `az login` with the Foundry Project Manager role on the project.

Env:
  FOUNDRY_PROJECT_ENDPOINT   project endpoint (required)
  AGENT_IMAGE                full ACR image ref e.g. crXXXX.azurecr.io/workshop-concierge:v1 (required)
  AGENT_NAME                 default "workshop-concierge"
  MODEL_DEPLOYMENT_NAME      default "chat"
"""
from __future__ import annotations

import os
import sys
import time


def main() -> int:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    image = os.environ.get("AGENT_IMAGE")
    agent_name = os.environ.get("AGENT_NAME", "workshop-concierge")
    model = os.environ.get("MODEL_DEPLOYMENT_NAME", "chat")
    if not endpoint or not image:
        print("ERROR: set FOUNDRY_PROJECT_ENDPOINT and AGENT_IMAGE", file=sys.stderr)
        return 2

    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        HostedAgentDefinition,
        ProtocolVersionRecord,
        AgentProtocol,
        ContainerConfiguration,
    )
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(
        endpoint=endpoint, credential=DefaultAzureCredential(), allow_preview=True
    )

    print(f"Creating version of '{agent_name}' from image {image} ...")
    agent = project.agents.create_version(
        agent_name=agent_name,
        definition=HostedAgentDefinition(
            protocol_versions=[
                ProtocolVersionRecord(protocol=AgentProtocol.RESPONSES, version="1.0.0")
            ],
            cpu="1",
            memory="2Gi",
            container_configuration=ContainerConfiguration(image=image),
            environment_variables={"MODEL_DEPLOYMENT_NAME": model},
        ),
    )
    print(f"Created: name={agent.name} version={agent.version}")

    # Poll to active.
    while True:
        info = project.agents.get_version(agent_name=agent_name, agent_version=agent.version)
        status = info["status"] if isinstance(info, dict) else getattr(info, "status", "?")
        print(f"status={status}")
        if status == "active":
            print("Agent is ACTIVE.")
            break
        if status == "failed":
            err = info.get("error") if isinstance(info, dict) else getattr(info, "error", "")
            print(f"Provisioning FAILED: {err}", file=sys.stderr)
            return 1
        time.sleep(5)

    # Smoke test the Responses endpoint.
    client = project.get_openai_client(agent_name=agent_name)
    resp = client.responses.create(input="I'm a Developer and I want to Build an agent")
    print("Smoke response:", getattr(resp, "output_text", resp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
