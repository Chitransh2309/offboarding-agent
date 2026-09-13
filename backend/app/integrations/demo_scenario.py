"""The demo scenario_prompt from docs/Arga_Labs_Sandbox_Setup.pdf, kept as
code so the sandbox-connect flow and any seed/demo script use the exact
same text instead of two copies drifting apart."""

OFFBOARDING_DEMO_SCENARIO_PROMPT = """\
A mid-size software company. One employee, Priya Nair (priya@acme-demo.com),
is a senior backend engineer on the Payments team, reporting to manager
Daniel Osei.

GitHub: Priya is a member of the "acme-demo" org with write access to
repos "payments-api" and "billing-worker", and read access to "infra".
She has 2 open pull requests and 1 pending review request on payments-api.

Slack: Priya is a member of #payments-eng, #incidents, and #general, with
recent messages in #payments-eng about a billing bug.

Notion: Priya owns a "Payments Runbook" page and a "Q3 Refund Postmortem"
page, both shared with the Payments team space.

Linear: Priya has 4 assigned issues in the "Payments" project, 3 open and
1 in-progress, plus one issue assigned to her manager Daniel Osei for
context.\
"""
