# HW1 AI Prompts

All prompts entered for homework 1. Labeled as Problem N, Prompt M for each problem.

## Problem 1, Prompt 1

For this assignment, in hw1/prompts, create a file called "AI_prompts.md" which includes all prompts I enter for hw1, inclusive of this prompt

## Problem 1, Prompt 2

As we populate this, I will tell you what Problem we are on. For each new Prompt for that Problem, please label it. For instance, right now we are on Problem 1. This is Problem 1, Prompt 2; the first prompt was Problem 2, Prompt 1

## Problem 2, Prompt 1

Ok we are now on Problem 2. Here is the scenario: we work for "Spoke & Wrench Bicycle Repair" The owner of this shop keeps messy records: receipts, bank and credit card statements, a lease, emails, and handwritten notes (These are all in /Users/robertjohnson/Documents/Yale/AI/hw1/output/hw1_spoke_and_wrench). From these we need to create a January Income Statement. To do this, lets start by creating a script in the output folder called "read_receipts.py" This script should use an LLM to extract one row per purchase receipt PDF from a file in "prompts/receipts_extract.md". These rows should be saved in a JSON Array in "output/receipts.json". Each entry should have the following fields:
- vendor: store or seller name
- date: transaction date
- description: what was purchased
- amount_usd: total for this receipt in dollars
- category: an expense label (e.g. cogs_parts, tools_equipment, shipping)
- source_file: filename of the pdf this row came from.
Put any missing fields as a list in fields_not_found

We should be able to run this using:
python read_receipts.py --docs-dir PATH --out-dir output

## Problem 2, Prompt 2

Can you install pypdf please? Is there a way to invoke an LLM here without Portkey (i.e. within my Cursor account)

## Problem 2, Prompt 3

I have a Portkey API key - [REDACTED] - please securely save this (and when you write to the prompt log please mask the key)

## Problem 2, Prompt 4

let's use GPT-5.6-luna as the model please. Once you change that, let's run it and process the documents

## Problem 3, Prompt 1

Ok now for Problem 3. We need to turn the January bank statement into sturctured rows. Every line needs a business/personal label and an accoutning category before we can reconcile it with receipts and credit card charges. Create a script called "read_bank.py" that calls an LLM using a prompt in "prompts/bank_extract.md" to extract each line from "bank_statement_jan2026.pdg". Save  a JSON array of those rows to "output/bank_transactions.json". Each line should have the following data:
- date: posting or transaction date
- description: text shown on the statement
- amount_usd: dollar amount (positive number)
- classification: business or personal
- direction: credit (money in) or debit (money out) 
- accounting_label: what kind of row this is (e.g. revenue, expense, owner_draw, transfer)
- expense_type: subcategory when the row is a bank expense (e.g. rent, utilities, cogs_parts); omit or null otherwise

We should run this script from:
python read_bank.py --docs-dir PATH --out-dir output

## Problem 3, Prompt 2

ok fantastic. Quick refactor - let's move "read_bank.py" and "read_receipts.py" directly under the hw1 folder. For new scripts, let's please put directly under hw1. Quickly verify that all paths are correct and the files will run correctly from there

## Problem 4, Prompt 1

Ok Problem 4 - Many shop purchases run through the owner's credit card. The credit card statement overlaps with receipt PDFs, but uses issuer category labels (e.g. "Groceries") that are not enough on their own. We will reconcile in the next problem, but for now we just want to extract the credit card transactions. Create a script called "read_card.py" that calls an LLM using a prompt in "prompts/card_extract.md" to extract each charge from "credit_card_jan2026.pdf" and save output as a JSON array in "output/credit_card_transactions.json".
Each credit card charge must include:
- date: charge date
- merchant: name on the statement
- amount_usd: charge amount in dollars
- classification: business or personal
- expense_category: your business expense label for shop charges; use null for personal rows

We should be able to run this script using:
python read_card.py --docs-dir PATH --out-dir output

## Problem 5, Prompt 1

Alright Problem 5 - Now that the receipts, bank lines, and credit card charges are extracted (Problems 2-4), we need to reconcile them before building the income statement. The same purchase may appear on a receipt and a credit card statement; some bank deposits mix business and personal; emails and memos explain amounts that do not match any single PDF.
Let's create a script called "reconcile.py" that calls an LLM using a prompt in "prompts/reconcile.md" to reconcile amounts that appaer in more than one document or need an income statement decision. Each row in the log is just one reconciled amount. Pass in output.receipts.json, output/bank_transactions.json, output/credit_card_transactions.json, plus text from any relevant documents, and save a JSON array of those rows to output/reconciliation_log.json. Every row here should include:
- id: a short slug for this reconciled item (e.g. park_tool_card_vs_receipt)
- sources: list of document filenames used for this row
- amounts_seen: object mapping for each source filename to the dollar amount seen in the document (e.g. "receipt_park_tool.pdf":88.7)
- included_in_income_statement: yes or no; ... i.e. should this row count toward January revenue or expenses
- amount_used_in_income_statment: the dollar amount to book after reconciliation (use 0 if excluded)
- resolution: plain English explaining how you matched the documents and chose the final amount

The script should run wth the following command:
python reconcile.py --docs-dir PATH -- json-dir output --output-dir output

## Problem 6, Prompt 1

Great! Problem 6 - So reconciliation really hides our hardest decisions inside the resolution text. We nee to spell out the calls we were least sure about with the evidence we weighted and how confident we feel.
Create output/judgment_calls.json as a JSON array of three objects. Pick three entries from reconciliationn_log.json where it was hardest to set included_in_income_statement or amount_used_in_income_statment. For each judgment call include:
transaction_id: the reconciliation_id
included_in_income_statement: value from reconciliation log
amount_used_in_income_statment: value from reconciliation log
evidence_for: bulleted list of document names
confidence: high, medium, or low
At least one selection should be low. We do not need a script for this, just run analysis and save JSON file

## Problem 7, Prompt 1

Ok Problem 7 - with the reconciled log, we are going to create the January income statement. Create a script called "income_statement.py" that reads "output/reconciliation_log.json" and rolls every row with "included_in_income_statement" set to "yes" into revenue and expense lines, and saves the January income statement to "output/income_statement_jan2026.json" ... no hardcoded values, we must do math with Python.

The JSON must include:
- period (2026-01)
- revenue_usd
- expense_lines: each with (label, amount_usd, category, sources)
- total_expenses_usd
- net_income_usd

We need to be able to execute using:
python income_statement.py --json-dir output --out-dir output

## Problem 8, Prompt 1

Great - Problem 8. We want to make a webpage for the income statement to make it easier for a human to process the information.

Create a script "report.py" that reads the JSON files from output/ and builds a one-page HTML summary. Save the page to "output/income_statement.html". Only use numbers from the JSON files; do not hard code any numbers in HTML

The site should include:
- January Income Statement
- Personal and business rows we excluded from the income statment
- The three judgement calls we made

Please use Yale Blue as the color palate

We need to be able to run the script using:

python report.py --json-dir output --out output/income_statement.html

## Problem 8, Prompt 2

Please remove all em-dashes

## Problem 8, Prompt 3

can you reformat the web page so Excluded-personal and Excluded-business are not next to each other? Show personal first then business as a separate block below it

## Problem 9, Prompt 1

Great - Problem 9 - we have built a chain of scripts, JSON files, and prompts. Step back and draw the full process so someone else can see how the data moves through this assignment.

Create a one-page HTML file "output/pipeline.html" with a block diagram of our pipeline. Look back at Problems 2-8, create one block per script, plus blocks for key inputs (document pack, PDFs, emails) and outputs (each JSON/HTML file). Show arrows from inputs through scripts to outputs. Mark where the LLM is called. Use whatever library makes this look most professional, and theme with Yale Blue.

The diagram must make clear:
- Each script name and what it reads/writes
- Which steps call the LLM
- The path from the document pack to "income_statement.html"

## Problem 9, Prompt 2

remove "Problems 2-8: from the messy document pack to the January income statement page. Blue script blocks call GPT-5.6-luna through Portkey. White script blocks are Python-only math and HTML."

## Problem 10, Prompt 1

Fantastic - Problem 10 - now package this work so a grader can install dependencies. We need the following:
- All scripts from Problems 2-8
- "prompts/" with the runtime prompt files and our AI_prompts.md file
- a "requirements.txt" file
- README.md with install steps, how to set environment variables (e.g. PORTKEY_API_KEY) in a local .env file, with model name, and how to run each script. Do not include the acutal API key anywhere
- A sample output/ from one succesful run, inclusive of pipeline.html
- A run_all.py script that chains the scripts together

A screenshot is attached of how the file strucure should look. Once this is done, re-run to verify everything works

## Problem 10, Prompt 2

Lastly - zip this as hw1.zip. Exclude the document pack hw1_spoke_and_wrench and the Portkey API key
