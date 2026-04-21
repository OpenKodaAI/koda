# Observability Dashboard Guide

Real-time monitoring of agent activity, tools, and costs.

## Key Files
- `aggregator.py` -- DashboardAggregator (record executions, query stats)
- `models.py` -- AgentSummary, ToolStats, CostReport

## Data Flow
`execute_tool()` -> `record_tool_execution()` -> aggregator stores in-memory -> dashboard_* tools query it

## Tools
- `dashboard_agents` -- active agent list
- `dashboard_tools` -- tool usage stats
- `dashboard_costs` -- cost summary by period
- `dashboard_errors` -- recent errors
