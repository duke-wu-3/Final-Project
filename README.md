# StudFinder

**Describe a LEGO build in plain English. Get the exact parts. Send the list to BrickLink.**

New MOC builders know what they want to build ("a coffee shop with sand green walls and a striped
awning") but not what the parts are called, and BrickLink makes you search for every part one at a
time. StudFinder's agents turn the description into a checked parts list and a BrickLink Wanted
List file you can upload in one step.

## Run it (about 3 minutes)

You need Python 3.10+ and an internet connection (part photos load from Rebrickable's CDN).

1. Put your key in a `.env` file. The app looks in **this folder first, then the folder above it**:
   ```
   PORTKEY_API_KEY=your-key-here
   ```
   (`OPENAI_API_KEY` also works. See `.env.example`.)
2. Install and start:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
3. Your browser opens **http://localhost:8000**. If it doesn't, open that address yourself.

## Use it

1. **Describe your build**, or click an example such as *Coffee shop storefront*, then click **Find my parts**.
2. Watch the **Finder** agent search the catalog and the **Checker** agent review the list (right panel).
3. Fix things by chatting with the **Refiner**: "make the walls dark tan", "add 2 lamp posts".
   Or use the + / − buttons and the **Swap** button on the Checker's suggestions.
4. Click **Download Wanted List** (or **Copy XML**). On BrickLink go to **Want → Upload**, add the file,
   and use **Buy All** to pick stores.

## How it works

| Agent | Job | Tools |
|---|---|---|
| Finder | Turns the description into sections and parts | `search_parts`, `part_colors`, `add_part` |
| Checker | Flags hard-to-find parts, suggests swaps, notes missing pieces | `find_substitutes`, `suggest_swap`, `add_note` |
| Refiner | Edits the list from chat messages | `search_parts`, `part_colors`, `add_part`, `change_color`, `set_quantity`, `remove_item`, `replace_part` |

- **Model:** `gpt-6-luna` through Portkey (OpenAI Responses API with function tools).
- **Data:** `data/catalog.db` has about 27,000 LEGO parts and 59,000 part-and-color combinations, built from
  [Rebrickable's free downloads](https://rebrickable.com/downloads/). Rarity is the number of official sets
  a part has appeared in, in that color.
- **Cost:** every model call's tokens and cost show in the app and are logged to `logs/usage.jsonl`.

## Safety limits

- Agents can only change the list through tools, and every tool checks the real catalog. A made-up part
  number or a color the part was never made in is rejected and shown in the **Safety log**.
- Caps: 300 per part, 3,000 pieces, 60 different parts per list. Each agent gets a limited number of model
  calls per request. Each session has a 250,000-token budget, and the whole app has a daily budget.
- Obvious prompt-injection text ("ignore previous instructions…") is blocked before it reaches the model.
- StudFinder never buys anything. It makes a list, and you decide what to order on BrickLink.

## Project layout

```
app.py                  web server (FastAPI) + API routes
studfinder/agents.py    the three agents, their prompts, tools, and the tool loop
studfinder/catalog.py   catalog search, colors, rarity, substitutes
studfinder/state.py     one session's parts list, caps, and token accounting
studfinder/export.py    BrickLink Wanted List XML
studfinder/config.py    keys, model, prices, guardrail limits
static/                 the web page (HTML/CSS/JS)
data/catalog.db         prebuilt parts catalog (committed, so no download needed)
data/bricklink_colors.csv  Rebrickable -> BrickLink color ids
scripts/build_catalog.py   rebuilds catalog.db from Rebrickable CSVs (optional)
```

## Known limits

- Part numbers come from Rebrickable. They match BrickLink for most standard parts, but a few differ.
  BrickLink's upload page flags any it does not recognize.
- Colors without a BrickLink match (rare Modulex and Opal colors) are left out of the export, and the app
  lists them.

LEGO® is a trademark of the LEGO Group, which does not sponsor or endorse this project.
Part data and images © Rebrickable.
