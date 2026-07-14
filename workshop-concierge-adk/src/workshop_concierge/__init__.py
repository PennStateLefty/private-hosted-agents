"""Workshop Concierge — a net-new Google ADK agent adapted to the Foundry
Hosted Agent Responses protocol.

Package layout:
  catalog      -- loads the version-controlled track catalog + recommendation matrix
  recommend    -- deterministic recommend_track() tool and input normalization
  session      -- session-state schema and stage-transition rules
  agent        -- the ADK LlmAgent, FunctionTool, and before/after callbacks
  cards        -- Adaptive Card builders (intake + recommendation)
"""

__all__ = ["catalog", "recommend", "session", "cards"]
