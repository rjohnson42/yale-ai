# HW2 AI Prompts

All prompts entered for homework 2. Labeled as Problem N, Prompt M for each problem.

## Problem 1, Prompt 1

Ok for hw2 we are going to create a prompts/AI_prompts.md file for the assignment. Each prompt I enter will follow same format, Labeled as Problem N, Prompt M for each problem. So this is Problem 1, Prompt 1

## Problem 1, Prompt 2

Let's do a test prompt to make sure it populates correctly

## Problem 2, Prompt 1

Problem 2. We are going to create a sales agent to help find leads for a company. I am going to pick sierra.ai. Start by creating a file called assets/seller_brief.md. This needs to include:
- The Name of the Company
- The Company URL
- My rationale for selecting the company. Personally, I think they have very interesting agentic workflows for sales funnels, and I would like to learn more about them.
- Information I want you to collect about the company: what specific products they offer, value props for each, pricing if available, other companies they sell to, anything else which may be useful.
Just create this file right now, do not action anything

## Problem 2, Prompt 2

Please do some research and populate "Information to collect" - in addition to what I told you, please populate anything else which an agent would need to know to find sales targets

## Problem 3, Prompt 1

Problem 3. We are going to build a PydanticAI agent to solve this (although not quite yet). We want to write part of th eprompt for our agent that tells them how to build a company profile when asked by a human. This prompt should live in prompts/sales_agent.md and include the following instructions:
- Profile fields to collect, derived from seller_brief.md
- Information on how to crawl a company website (URLs will be provided via keyword args)
- No inventing of facts - everything needs to come from the company site
- After researching, profiles should be saved to assets/company_profile.json.

## Problem 4, Prompt 1

Problem 4. Now we want to build a PydanticAI agent under hw2 called "sales_agent.py" which loads "sales_agent.md" into its system prompt. This agent needs to look at a company's site using Playwright and write a profile file.

From input query text, the agent should figure out what a human wants. Please make sure there are guardrails to keep agent runs both safe and cost-efficient.

All agent-loop iterations (date and time, thoughts, tool calls, name/args/result summary, when run stops) should be saved to "hw2/output/audit_log.json".

Our first run will be against Sierra (company URL and seller brief are in "prompts/sales_agent.md". The script needs to take a text query and a "--url" and pass both to agent.

Ultimately the agent needs to be called from this terminal command (substittution quoted text and URL with a real URL) "python sales_agent.py "Build a profile of this company." --url https://www.company_url.com"

## Problem 5, Prompt 1

Problem 5 - Now let's update 'prompts/sales_agent.md' to find potential customers and draft outreach emails when the user asks. When the user asks for customer targets for the target company, in one loop our agent should:
- read the company profile
- search the web for potential customer companies
- only keep the company if there is mutual fit. I.e. do not pick a random business, competitor, or famous company
- look through that candidates website for useful business context and a contact email
- draft a targeted outreach email for each target (ever send an email!)

Save the results to 'output/targets.json' (company info + contact emails). Save draft emails to 'output/emails.json' Also be sure to update 'audit_log.json' after each run.

This should be exectutable via 'python sales_agent.py "Find 3 good customer targets for this company and draft outreach emails." --profile assets/company_profile.json'

Use OpenAI for web search via portkey and Playwright. Make sure there are guardrails in place to prevent runaway costs. Then, run this to find three target customers for Sierra

## Problem 6, Prompt 1

Problem 6 - at the project root, create a file called HARNESS.md. This should summarize guardrails we have in place to keep the agent under control. It should include three sections:
- Tools: every tool the agent uses (name, what it does, inputs/outputs)
- Stopping rules: when the agent is done/must stop (max steps, enough targets, failures, etc)
- Guardrails: what it must not do (invent facts, send emails, runaway costs, unsafe actions, etc)

This should be human readable for a non-technical reviewer, but at the same time reflect everything we have built in this project

## Problem 7, Prompt 1

Problem 7 - make me a file called "output/reflection.md" where I can write some reflections in my own words. Please do not add anything to this file, I will populate it

## Problem 8, Prompt 1

Problem 8 - now we want to make a sales dashboard that shows our company profile, target customers, and drafted emails in a way a human can consume it. A human should be able to open the page and see who the seller is, who the targets are, contact info, and our drafted emails (which should be loaded in). Save this as dashboard.html. Create this in a style similar to Sierra's site to keep a consistent corporate brand. Also feel free to use plotly if that is helpful.

## Problem 8, Prompt 2

Change "Better outcomes. Built for the team that has to follow up." to "Sierra AI Sales Platform" ... also remove the "Pipeline at a glance" section, it does not add much here

## Problem 8, Prompt 3

Remove "Drafts only, never sent"

## Problem 8, Prompt 4

Can you add the Sierra logo? It is also a bit dark - please check sierra.ai and look at how vibrant and dynamic the site is. Content is fine

## Problem 9, Prompt 1

Problem 9. Make sure the layout of our assignment matches what is in the attached file for the grader. Once changed, test, and then zip as 'hw2.zip' Please make sure we do not but the .env file in the zip. Include .env.example with PORTKEY_API_KEY/model settings in only as placeholders

