# Tadpole Studio Lyrics Generation System — Deep Strategic Analysis

> Generated: 2026-08-02
> Scope: Complete analysis of the lyrics generation pipeline, root cause identification for four reported problems, and a prioritized fix strategy.
> Status: Strategy only — no code changes made.

---

## Table of Contents

1. [Current Lyrics Generation Flow](#1-current-lyrics-generation-flow)
2. [Root Cause Analysis](#2-root-cause-analysis)
3. [New Model Testing Strategy](#3-new-model-testing-strategy-koboldcppgemma)
4. [Proposed Fixes Prioritized by Impact](#4-proposed-fixes-prioritized-by-impact)
5. [Custom Station Quality Issues](#5-custom-station-quality-issues)
6. [Testing Plan](#6-testing-plan)
7. [Recommended Action Order](#7-recommended-action-order)

---

## 1. Current Lyrics Generation Flow

### Complete Pipeline (Station Request → Final Audio)

```
User clicks station card
  ↓
frontend: useRadio.startStation(stationId)
  ↓
  ├─ abortRadioRequests() + forceReleaseGenLock()
  ├─ radioEngine.stop() + clearBuffers() + warmup()
  ├─ acquireGenLock() + setGPUHolder("radio")
  ↓
┌─ GENERATE SONG 1 (blocking) ──────────────────────────────┐
│ POST /radio/generate/{station_id}                           │
│   → set_radio_active(True)                                   │
│   → radio_service.generate_next_track(station_id):          │
│     ├─ Step 1: Get station from DB                           │
│     ├─ Step 2: _generate_caption_with_llm() → caption       │
│     ├─ Step 3: _generate_lyrics_with_llm() → lyrics         │
│     ├─ Step 4: gpu_lock.await_acquire("radio")              │
│     ├─ Step 5: Randomize BPM, duration                       │
│     ├─ Step 6: generation_service.generate(params) → audio  │
│     ├─ Step 7: _generate_title_with_llm() → title           │
│     ├─ Step 8: gpu_lock.release("radio")                    │
│     └─ Step 9: Save song to DB, copy audio file             │
│   → set_radio_active(False)                                   │
│   → Returns { success: true, song: SongResponse }            │
└─────────────────────────────────────────────────────────────┘
  ↓
decodeAndCacheAudio(song1.id)
radioEngine.play(song1.id)
  ↓
GENERATE SONG 2 (pre-buffer) → same pipeline
  ↓
useRadioPlayback (continuous, in AppShell) keeps generating
```

### Step-by-Step Breakdown

#### Step 1: Station Retrieval ([`radio_service.py:605`](backend/src/tadpole_studio/services/radio_service.py:605))

Station loaded from DB including all fields: `genre`, `mood`, `instrumental`, `vocal_language`, `structure_ids`, `advanced_params_json`, `caption_template`, `description`.

#### Step 2: Caption Generation ([`radio_service.py:380-426`](backend/src/tadpole_studio/services/radio_service.py:380))

- If LLM available: `_generate_caption_with_llm()` sends station parameters as a user message with system prompt `RADIO_DEFAULT_SYSTEM_PROMPT`
- LLM call: `provider.chat(messages, model_name, temperature=0.7)` — default max_tokens=1024
- If no LLM or failure: falls back to `station.caption_template` with `{mood}`/`{genre}` variable substitution, or auto-generates `"A {genre} {mood} track"`

**System prompt (default):**
```
You are a music caption generator. Given station parameters, write a creative, 
detailed caption for an AI music generator. Describe instrumentation, texture, 
atmosphere, and sonic qualities. Be specific and varied — each caption should 
feel unique. Output ONLY the caption text, nothing else.
```

**User message format:**
```
Generate a unique music caption for these station parameters:
Genre: {genre}
Mood: {mood}
Instrumental: yes/no
Vocal language: {language}
BPM range: {min}-{max}
Key/scale: {keyscale}
Time signature: {timesignature}
Style reference: {caption_template}
```

#### Step 3: Lyrics Generation ([`radio_service.py:494-597`](backend/src/tadpole_studio/services/radio_service.py:494))

This is the CRITICAL step for all reported problems.

**Early exits:**
- Returns `""` if `station.instrumental` is `True` (line 498-499)
- Returns `""` if no LLM provider available (line 501-502)

**Parameters gathered:**
- Parses `advanced_params_json` for `theme_pool`, `lyrics_style_addons`, `intensity`
- Selects random theme from pool (or built-in 20-theme pool of pop-centric themes if empty)
- Selects structure from station's `structure_ids` (or hardcoded default: `[Verse 1]\n[Chorus]\n[Verse 2]\n[Chorus]\n[Bridge]\n[Chorus]\n[Outro]`)
- `vocal_lang` defaults to "English" if "unknown"
- `genre` defaults to "Pop" if empty
- `mood` defaults to "Standard" if empty

**Prompt built (lines 557-577):**
```
Write a {genre} song in {language} about '{theme}' using this exact structure:
{structure_template}

STRICT REQUIREMENTS:
1. Write ONLY the song lyrics - no translations, no explanations, no notes
2. Use ONLY the specified language: {language}
3. Follow the structure EXACTLY as shown
4. Format each section header exactly as shown (e.g. [Verse 1])
5. Never include any text outside the lyrics structure
6. Target Duration: {duration}s
7. Musical Key: {keyscale}

STYLE GUIDELINES:
- {lyrics_style_addons}
- {intensity} feel
- {mood} mood
- Concept/Description: {station.description}
- Use vivid imagery and emotional resonance
- Match the rhythm and phrasing to {genre} conventions

BACKGROUND VIBE/CAPTION (For Optional Context):
{caption}
```

**LLM call (lines 579-588):**
```python
messages = [
    {"role": "user", "content": prompt_text},
]
raw = await provider.chat(messages, model=model_name, max_tokens=800, temperature=0.8)
```

**CRITICAL OBSERVATION: No system prompt is sent.** Only a user message.

**Response cleaning (line 590):**
```python
cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
```

**Only think tags are stripped. No other cleaning is performed.**

#### Step 4: GPU Lock & Music Generation ([`radio_service.py:634-689`](backend/src/tadpole_studio/services/radio_service.py:634))

- Acquires GPU lock with `gpu_lock.await_acquire("radio")`
- Builds `params_dict` including `caption`, `lyrics`, `instrumental`, `vocal_language`, `duration`, `bpm`, `keyscale`, `timesignature`
- Calls `generation_service.generate(params_dict)` which routes to active backend

#### Step 5: Backend Processing

**ACE-Step path** ([`ace_step_backend.py:322-399`](backend/src/tadpole_studio/backends/ace_step_backend.py:322)):
- `params_dict` converted to `GenerationParams` dataclass
- Lyrics + caption passed to ACE-Step's internal 5Hz LM which tokenizes them into conditioning tokens
- The LM processes structural tags like `[Verse]`, `[Chorus]` to understand song structure
- If structural tags are malformed (e.g., `(Verse)` instead of `[Verse]`), the LM may not recognize section boundaries
- Poor LM tokenization → poor DiT conditioning → poor music output

**HeartMuLa path** ([`heartmula_backend.py:447-567`](backend/src/tadpole_studio/backends/heartmula_backend.py:447)):
- Lyrics passed directly as `inputs["lyrics"]` alongside `inputs["tags"]` to `HeartMuLaGenPipeline`
- HeartMuLa has "superior lyrics controllability" per its docstring
- Also expects proper structural tag formatting

#### Step 6: Title Generation ([`radio_service.py:693-714`](backend/src/tadpole_studio/services/radio_service.py:693))

- Runs under GPU lock
- Tries LLM-based title first (`_generate_title_with_llm()`), falls back to `generate_random_title()`

#### Step 7: Post-Generation ([`radio_service.py:733-828`](backend/src/tadpole_studio/services/radio_service.py:733))

- Saves song to DB with lyrics in the `lyrics` field (line 799)
- Copies audio file to library
- Links song to station via `radio_station_songs` table

### LLM Call Summary

| Call | System Prompt | Temperature | Max Tokens | Notes |
|------|--------------|-------------|------------|-------|
| Caption | `RADIO_DEFAULT_SYSTEM_PROMPT` (or custom from settings) | 0.7 | 1024 | System + user messages |
| Lyrics | **NONE** | 0.8 | 800 | User message only — this is a critical gap |
| Title | System prompt with title instructions | 0.7 | 50 | System + user messages |

### MedievalCore Station Configuration

From [`schema.py:317-327`](backend/src/tadpole_studio/db/schema.py:317):

| Field | Value |
|-------|-------|
| name | "Medievalcore" |
| description | "Bardcore and tavernwave — medieval instruments meet modern songwriting" |
| genre | "medievalcore, bardcore, tavernwave" |
| mood | "chill" |
| instrumental | **False** (always generates lyrics) |
| vocal_language | "unknown" (defaults to "English" in lyrics generation) |
| bpm_min | 60 |
| bpm_max | 130 |
| duration_min | 60.0 |
| duration_max | 180.0 |
| caption_template | "Music as if played in medieval times, using instruments like lutes, harps, flutes" |
| advanced_params_json | `"{}"` (empty — falls back to defaults everywhere) |
| structure_ids | Not assigned (uses hardcoded default structure) |

**Note on user clarification:** The user clarified that MedievalCore should NOT always have lyrics — it should randomly alternate between instrumental and lyrical songs. Currently `instrumental=False` means it ALWAYS generates lyrics. This needs a new mechanism for random instrumental/vocal selection.

---

## 2. Root Cause Analysis

### Problem 1: Some Songs Are Instrumental (No Lyrics) When They Should Have Lyrics

**Multiple contributing causes:**

#### Cause 1A: LLM Provider Unavailable

The lyrics generation at [`radio_service.py:501-502`](backend/src/tadpole_studio/services/radio_service.py:501) returns `""` immediately if no LLM is available:
```python
provider, model_name, _prompt = await self._get_radio_llm()
if provider is None:
    return ""
```

On Linux, the built-in MLX provider is unavailable (Apple Silicon only). The fallback chain in `_get_radio_llm()` ([`radio_service.py:337-378`](backend/src/tadpole_studio/services/radio_service.py:337)):
1. Try configured provider from settings
2. If unavailable → try Ollama
3. If unavailable → return `(None, "", system_prompt)`

If none of these work, lyrics generation silently returns empty string.

#### Cause 1B: LLM Call Fails Silently

Any exception during the chat call at [`radio_service.py:594-596`](backend/src/tadpole_studio/services/radio_service.py:594):
```python
except Exception as e:
    logger.warning(f"Radio LLM lyrics generation failed ({provider.name}): {e}")
    return ""
```

Common failures: network timeout (for cloud/KoboldCpp), model crash (for local models), context length exceeded.

#### Cause 1C: LLM Returns Empty or Think-Tag-Only Response

The raw response is stripped of think tags. If the model outputs mostly thinking content:
```
<think>Let me write a medieval song...
[long thinking process]
</think>
```
After stripping, `cleaned` becomes `""`.

#### Cause 1D: max_tokens=800 Truncation

For complex structures, 800 tokens may truncate the response mid-song. If the truncation point leaves only a partial first section, the music backend may not recognize it as valid lyrics.

#### Cause 1E: MedievalCore Always Has instrumental=False

Currently MedievalCore has `instrumental=False` hardcoded, meaning it ALWAYS attempts lyrics. The user wants this to be random — some songs instrumental, some with lyrics. Without this randomness, every failure to generate lyrics is noticed as a bug rather than being one variation of intended behavior.

**Likely primary cause for the user's environment:** Cause 1A (LLM provider unavailable) or Cause 1C (model returns mostly think tags).

---

### Problem 2: Model Includes Full Prompt Text Inside Lyrics Output

#### Cause 2A: No System Prompt for Lyrics Generation (PRIMARY)

The lyrics LLM call at [`radio_service.py:579-584`](backend/src/tadpole_studio/services/radio_service.py:579) sends ONLY a user message:
```python
messages = [
    {"role": "user", "content": prompt_text},
]
```

Without a system prompt establishing the model's role and output format, the model has no strong guardrails. Caption and title generation BOTH use system prompts — lyrics does not. This is the single biggest gap.

#### Cause 2B: Overly Verbose Prompt with Numbered Instructions

The prompt includes:
- 7 numbered "STRICT REQUIREMENTS"
- 7 bullet-point "STYLE GUIDELINES"
- Background caption context

Small models (especially Gemma-family models via KoboldCpp) are notorious for parrot-back behavior when faced with complex, structured prompts. The model sees numbered lists and feels compelled to respond to each point.

#### Cause 2C: Minimal Output Cleaning

At [`radio_service.py:590`](backend/src/tadpole_studio/services/radio_service.py:590), only think-tag stripping is done:
```python
cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
```

No cleaning of:
- Preamble text ("Here's your song...", "Sure, I'll write...")
- Repeated instructions ("STRICT REQUIREMENTS:", "STYLE GUIDELINES:")
- Markdown code fences (````lyrics\n...\n````)
- Post-lyrics commentary ("I hope you enjoy this song!")
- Bold/italic formatting from the model

#### Cause 2D: Gemma Model Behavior

Gemma models (particularly smaller ones like Gemma 2 2B/9B) have a tendency to:
- Echo back prompt instructions
- Add conversational filler before and after the requested content
- Use parenthetical annotations `(Verse 1)` instead of bracket annotations `[Verse 1]`
- Wrap output in markdown when prompted with structured content

**Likely primary cause:** Cause 2A (no system prompt) combined with Cause 2C (no output cleaning).

---

### Problem 3: Model Prefers `()` Instead of `[]` for Structural Tags

#### Cause 3A: Gemma Model Formatting Preference

Gemma-family models are trained on data where parenthetical annotations are more common for structural markers. When the prompt shows `[Verse 1]`, the model may output `(Verse 1)` as its natural formatting habit.

#### Cause 3B: No Reinforcement in System Prompt

Since there's no system prompt, there's no place to reinforce: "Use square brackets for ALL section headers."

#### Cause 3C: No Post-Processing Normalization

The output cleaning step doesn't normalize `()` to `[]`, so whatever the model outputs passes through unchanged.

#### Impact on Music Generation

The ACE-Step 5Hz LM expects structural tags in `[]` format. When it receives `(Verse)` instead of `[Verse]`:
- The LM may not recognize the tag as a section boundary
- Lyrics are treated as a flat text block without structure
- The DiT model receives poor structural conditioning
- Result: music that doesn't follow the intended song structure, potentially with vocals at wrong times

**Likely primary cause:** Cause 3A (model preference) amplified by Cause 3C (no normalization).

---

### Problem 4: Custom Stations Produce Poor Lyrics AND Worse Music

#### Cause 4A: Empty or Generic Station Parameters

Custom stations created by users often have:
- Empty `genre` → defaults to "Pop" at [`radio_service.py:554`](backend/src/tadpole_studio/services/radio_service.py:554)
- Empty `mood` → defaults to "Standard" at [`radio_service.py:555`](backend/src/tadpole_studio/services/radio_service.py:555)
- Empty `description` → no concept guidance in style guidelines
- Default `instrumental=True` in [`radio_service.py:96`](backend/src/tadpole_studio/services/radio_service.py:96) if frontend doesn't send the field

#### Cause 4B: No Assigned Structures

Custom stations don't get `structure_ids` automatically assigned. They use the hardcoded default structure (`[Verse 1]\n[Chorus]\n[Verse 2]\n[Chorus]\n[Bridge]\n[Chorus]\n[Outro]`), which may not match the genre.

#### Cause 4C: Generic Advanced Params

Custom stations inherit `advanced_params_json="{}"`, meaning:
- Falls back to pop-centric theme pool (20 built-in themes)
- `lyrics_style_addons = "Standard style"`
- `intensity = "Moderate"`

#### Cause 4D: Poor Caption Quality

Without a good `caption_template`:
- The fallback caption `"A {genre} track"` (or even worse `"A music track"`) is too thin
- LLM caption generation may also produce generic captions for stations with sparse parameters

#### Cause 4E: Music Quality Cascade

The ACE-Step pipeline is:
```
caption + lyrics → 5Hz LM tokenization → conditioning tokens → DiT generation → audio
```

Poor quality in ANY input degrades the final output:
- Poor caption → poor instrumentation/texture understanding
- Poor lyrics → poor vocal timing and content
- Malformed structural tags → poor song form understanding
- Generic genre/mood → generic sounding music

**All four causes compound:** bad caption + bad lyrics + bad structure + bad parameters = very poor music.

---

## 3. New Model Testing Strategy (KoboldCpp/Gemma)

### Phase 1: Direct LLM Prompt Testing (Isolation)

**Goal:** Test the lyrics prompt directly without the music generation pipeline, to understand model behavior in isolation.

**Setup:**
1. Configure KoboldCpp as radio LLM provider via `openai-compatible` provider type
2. Set `api_base` to the KoboldCpp endpoint (e.g., `http://localhost:5001/v1`)
3. Verify via `GET /radio/settings` that the provider shows as available

**Test Prompts:**

| Test | Prompt | Purpose |
|------|--------|---------|
| A | Current MedievalCore prompt (exact) | Baseline — reproduce the problem |
| B | Same prompt with system prompt added | Test fix #1 |
| C | Simplified prompt + system prompt | Test fix #1 + #3 |
| D | Simple one-line prompt + system prompt | Test minimal instruction set |
| E | Empty prompt + system prompt only | Test system prompt alone |

**For each test, send 5-10 requests and record:**
- Raw response (full text)
- Response length (characters and tokens)
- Time to first token
- Total generation time
- Whether response includes preamble
- Whether response echoes prompt instructions
- Bracket format used (`[]` vs `()`)
- Whether structure is followed
- Think tag usage
- Markdown formatting usage

**Evaluation criteria per response:**

| Criterion | Weight | Check |
|-----------|--------|-------|
| No preamble before first section | High | First non-empty line starts with `[` or `(` |
| No prompt instructions echoed | High | No "STRICT REQUIREMENTS", "STYLE GUIDELINES", "Write a" in output |
| Uses `[]` for section tags | High | Zero instances of `(Verse`, `(Chorus`, `(Bridge` as section headers |
| Follows structure template | Medium | All sections from template present in output |
| No post-lyrics commentary | Medium | Last non-empty line is lyrics, not commentary |
| No markdown fences | Low | No ```` in output |
| Genre-appropriate content | Medium | Medieval imagery, language, themes for MedievalCore |
| Language compliance | High | All lyrics in requested language |

---

### Phase 2: Output Cleaning Validation

**Goal:** Verify the proposed output cleaning pipeline handles all failure modes.

**Procedure:**
1. Collect 30+ raw outputs from the Gemma model using the current prompt
2. Run each through the proposed cleaning function (see Fix #2 below)
3. Score each cleaned output:

| Score | Criteria |
|-------|----------|
| ✅ Clean | No prompt leakage, proper `[]` brackets, all sections present |
| ⚠️ Partial | Some leakage remains OR minor bracket issues |
| ❌ Broken | Too much content removed OR still heavily contaminated |

4. Target: ≥90% ✅ Clean, ≤5% ❌ Broken

---

### Phase 3: Full Integration Test

**Goal:** End-to-end testing with the complete pipeline.

**Procedure:**
1. Configure KoboldCpp as the active LLM
2. Select MedievalCore station
3. Generate 10 tracks via `POST /radio/generate/{station_id}`
4. For each track:
   - Check backend logs for raw LLM output (`Radio LLM raw lyrics output:`)
   - Check cleaned lyrics (`Radio LLM lyrics generated via`)
   - Query DB for saved song's `lyrics` field
   - Listen to generated audio
   - Score against rubric below

**Audio quality rubric:**

| Score | Lyrics | Music |
|-------|--------|-------|
| 5/5 | Present, clean, proper tags | Vocals at right times, good quality, genre-appropriate |
| 4/5 | Present, mostly clean | Vocals mostly correct, minor timing issues |
| 3/5 | Present, some leakage | Vocals present but timing/quality issues |
| 2/5 | Heavily contaminated | Poor vocals or vocals at wrong times |
| 1/5 | Missing (instrumental) | No vocals when expected |
| 0/5 | Generation failed | Error or crash |

**Target:** Average score ≥4.0 across 10 tracks.

---

## 4. Proposed Fixes (Prioritized by Impact)

### Fix 1: Add System Prompt for Lyrics Generation

**Priority:** 1 — Do First
**Impact:** Very High
**Effort:** Low (~10 lines)
**Risk:** Low
**Addresses:** Problem 2 (prompt leakage), Problem 3 (bracket format)

**Rationale:** Every other LLM call in the system (caption, title) uses a system prompt. Lyrics generation is the only one that doesn't. System prompts provide the strongest guardrails for model behavior.

**Proposed system prompt:**
```
You are a professional songwriter. When given song parameters and a structure, 
write ONLY the song lyrics output. Use square brackets for ALL section headers: 
[Verse 1], [Chorus], [Bridge], [Outro], [Intro], etc. Never use parentheses 
for section headers — always use square brackets. Output only the lyrics with 
section tags. No preamble, no explanations, no commentary, no notes, no 
translations. Start directly with the first section header.
```

**Implementation location:** [`radio_service.py:579`](backend/src/tadpole_studio/services/radio_service.py:579)

**Current code:**
```python
messages = [
    {
        "role": "user",
        "content": prompt_text,
    },
]
```

**Proposed code:**
```python
LYRICS_SYSTEM_PROMPT = (
    "You are a professional songwriter. When given song parameters and a structure, "
    "write ONLY the song lyrics output. Use square brackets for ALL section headers: "
    "[Verse 1], [Chorus], [Bridge], [Outro], [Intro]. Never use parentheses for "
    "section headers. Output only the lyrics with section tags. No preamble, no "
    "explanations, no commentary, no notes."
)

messages = [
    {"role": "system", "content": LYRICS_SYSTEM_PROMPT},
    {"role": "user", "content": prompt_text},
]
```

**Notes:**
- Make `LYRICS_SYSTEM_PROMPT` a module-level constant so it can be overridden
- Consider storing in settings table as `radio_lyrics_system_prompt` for runtime configurability (see Fix 6)

---

### Fix 2: Add Comprehensive Output Cleaning Pipeline

**Priority:** 1 — Do First
**Impact:** Very High
**Effort:** Medium (~80 lines for the cleaning function)
**Risk:** Low (post-processing step, can be bypassed)
**Addresses:** Problem 2 (prompt leakage), Problem 3 (bracket format), Problem 1 (partial — catches some empty outputs)

**Rationale:** The current cleaning at [`radio_service.py:590`](backend/src/tadpole_studio/services/radio_service.py:590) only strips think tags. A comprehensive cleaning pipeline catches all known failure modes.

**Proposed cleaning function** (to be added as a module-level function in `radio_service.py`):

```python
import re

def _clean_lyrics_output(raw: str) -> str:
    """Clean raw LLM lyrics output for use with music backends.
    
    Handles:
    - Think tag removal
    - Markdown code fence removal
    - Preamble stripping (text before first section tag)
    - Post-lyrics commentary removal
    - () to [] bracket normalization for section headers
    - Prompt leakage line removal
    - Multiple blank line collapsing
    """
    if not raw or not raw.strip():
        return ""
    
    cleaned = raw
    
    # Step 1: Strip think tags
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL)
    
    # Step 2: Strip markdown code fences
    cleaned = re.sub(r'^```[\w]*\n?', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\n?```$', '', cleaned)
    
    # Step 3: Remove preamble before first section tag
    # Match [SectionName] or (SectionName) at start of line
    section_pattern = (
        r'[^\S\n]*[\[\(]'
        r'(?:Verse|Chorus|Pre[- ]Chorus|Bridge|Outro|Intro|'
        r'Interlude|Solo|Hook|Drop|Build[- ]Up|Breakdown|'
        r'Final\s*\w+|Double\s*\w+|'
        r'Guitar\s*\w+|Fiddle\s*\w+|Piano\s*\w+|'
        r'Steel\s*Guitar\s*\w+|'
        r'Atmospheric\s*\w+|Ambient\s*\w+|'
        r'Orchestral\s*\w+|Shredding\s*\w+|'
        r'Skank\s*\w+|Harmonica\s*\w+|'
        r'Swing\s*\w+|Chill\s*\w+|'
        r'Textural\s*\w+|Drone\s*\w+|'
        r'Theme\s*[AB]|Development|Recapitulation|Coda|'
        r'Response|Dub\s*\w+|'
        r'Instrumental\s*\w+|Fade\s*\w+|'
        r'Big\s*\w+|With\s*\w+)'
        r'[\]\)]'
    )
    match = re.search(section_pattern, cleaned, re.IGNORECASE)
    if match:
        cleaned = cleaned[match.start():]
    
    # Step 4: Remove post-lyrics commentary
    lines = cleaned.split('\n')
    last_section_idx = -1
    for i, line in enumerate(lines):
        if re.match(r'\s*[\[\(]\w+', line, re.IGNORECASE):
            last_section_idx = i
    
    if last_section_idx >= 0:
        # Keep content up to ~20 lines after last section header
        end_idx = min(last_section_idx + 20, len(lines))
        for i in range(end_idx, last_section_idx, -1):
            if lines[i].strip():
                end_idx = i + 1
                break
        cleaned = '\n'.join(lines[:end_idx])
    
    # Step 5: Normalize (Section) to [Section]
    bracket_replacements = [
        (r'\((Verse(?:\s*\d+)?)\)', r'[\1]'),
        (r'\((Chorus(?:\s*\w+)?)\)', r'[\1]'),
        (r'\((Pre[- ]?Chorus)\)', r'[\1]'),
        (r'\((Bridge)\)', r'[\1]'),
        (r'\((Outro)\)', r'[\1]'),
        (r'\((Intro)\)', r'[\1]'),
        (r'\((Interlude)\)', r'[\1]'),
        (r'\((Solo)\)', r'[\1]'),
        (r'\((Hook)\)', r'[\1]'),
        (r'\((Drop)\)', r'[\1]'),
        (r'\((Build[- ]?Up)\)', r'[\1]'),
        (r'\((Breakdown)\)', r'[\1]'),
        (r'\((Final\s*\w+)\)', r'[\1]'),
        (r'\((Double\s*\w+)\)', r'[\1]'),
        (r'\((Guitar\s*\w+)\)', r'[\1]'),
        (r'\((Fiddle\s*Solo)\)', r'[\1]'),
        (r'\((Piano\s*\w+)\)', r'[\1]'),
        (r'\((Steel\s*Guitar\s*\w+)\)', r'[\1]'),
        (r'\((Atmospheric\s*\w+)\)', r'[\1]'),
        (r'\((Ambient\s*\w+)\)', r'[\1]'),
        (r'\((Orchestral\s*\w+)\)', r'[\1]'),
        (r'\((Shredding\s*\w+)\)', r'[\1]'),
        (r'\((Swing\s*\w+)\)', r'[\1]'),
        (r'\((Chill\s*\w+)\)', r'[\1]'),
        (r'\((Theme\s*[AB])\)', r'[\1]'),
        (r'\((Dub\s*\w+)\)', r'[\1]'),
        (r'\((Instrumental\s*\w+)\)', r'[\1]'),
    ]
    for pattern, replacement in bracket_replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    
    # Step 6: Remove lines that are clearly prompt leakage
    leakage_patterns = [
        r'^\s*STRICT\s*REQUIREMENTS',
        r'^\s*STYLE\s*GUIDELINES',
        r'^\s*BACKGROUND\s*VIBE',
        r'^\s*Target\s*Duration',
        r'^\s*Musical\s*Key',
        r'^\s*Write\s+a+\s+\w+\s+song',
        r'^\s*Format\s+each\s+section',
        r'^\s*Follow\s+the\s+structure',
        r'^\s*Use\s+ONLY\s+the\s+specified',
        r'^\s*Never\s+include',
        r'^\s*\d+\.\s*(?:Write|Use|Follow|Format|Never)',
    ]
    lines = cleaned.split('\n')
    cleaned_lines = []
    skip_until_blank = False
    for line in lines:
        is_leakage = any(re.search(p, line, re.IGNORECASE) for p in leakage_patterns)
        if is_leakage:
            skip_until_blank = True
            continue
        if skip_until_blank:
            if line.strip():
                continue
            else:
                skip_until_blank = False
        cleaned_lines.append(line)
    cleaned = '\n'.join(cleaned_lines)
    
    # Step 7: Collapse multiple blank lines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    # Step 8: Strip leading/trailing whitespace
    cleaned = cleaned.strip()
    
    return cleaned
```

**Usage in `_generate_lyrics_with_llm()`:**
```python
# Replace line 590:
# cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

# With:
cleaned = _clean_lyrics_output(raw)
```

---

### Fix 3: Simplify the Lyrics User Prompt

**Priority:** 2 — Do After Fix 1 & 2
**Impact:** Medium
**Effort:** Low (~15 lines of prompt text change)
**Risk:** Low
**Addresses:** Problem 2 (prompt leakage)

**Rationale:** With Fix 1 providing system-level guardrails, the user prompt can focus on creative direction rather than format enforcement. Fewer instructions = fewer opportunities for the model to echo them.

**Current prompt structure** (lines 557-577): ~20 lines with 7 numbered requirements, 7 style bullets, caption context

**Proposed simplified prompt:**
```python
prompt_text = (
    f"Write a {genre} song in {vocal_lang} about '{station_chosen_theme}'.\n\n"
    f"Station: {station.name}\n"
    f"Structure:\n{station_chosen_structure}\n\n"
    f"Style: {mood} mood, {intensity} feel. {lyrics_style_addons}.\n"
    f"Concept: {station.description}\n"
    f"Match {genre} conventions with vivid imagery and emotional resonance.\n\n"
    f"Background context: {caption}\n\n"
    "Output only the lyrics with section tags."
)
```

**Changes from current:**
- Removed all 7 numbered "STRICT REQUIREMENTS" (moved to system prompt)
- Removed 7 bullet-point "STYLE GUIDELINES" (condensed to one line)
- Added station name for thematic context
- Simplified "BACKGROUND VIBE/CAPTION" to "Background context"
- Removed "Target Duration" and "Musical Key" (these are backend params, not lyrics guidance)
- Final instruction is a single sentence

---

### Fix 4: Add Random Instrumental/Vocal Toggle for MedievalCore (and Similar Stations)

**Priority:** 2 — Do After Fix 1 & 2
**Impact:** Medium
**Effort:** Medium (~20 lines)
**Risk:** Low
**Addresses:** User's clarification about MedievalCore randomization

**Rationale:** The user clarified that MedievalCore should randomly alternate between instrumental and lyrical songs. Currently `instrumental=False` means always lyrics. We need a mechanism for probabilistic instrumental/vocal selection.

**Implementation approach:**

Add a new field to `advanced_params_json`:
```json
{
  "lyrics_probability": 0.7
}
```

This means 70% of songs will have lyrics, 30% will be instrumental.

**Implementation in `_generate_lyrics_with_llm()`** (before line 498):
```python
# Check for probabilistic instrumental/vocal toggle
lyrics_probability = 1.0  # Default: always lyrics for non-instrumental stations
try:
    advanced = json.loads(station.advanced_params_json) if station.advanced_params_json else {}
    lyrics_probability = advanced.get("lyrics_probability", 1.0)
except (json.JSONDecodeError, AttributeError):
    pass

if random.random() > lyrics_probability:
    logger.info(f"Radio lyrics: randomly skipping lyrics for station '{station.name}' (probability={lyrics_probability})")
    return ""
```

**For MedievalCore preset**, set in [`schema.py`](backend/src/tadpole_studio/db/schema.py):
```python
"advanced_params_json": json.dumps({
    "lyrics_probability": 0.65,  # ~65% of songs have lyrics
    "theme_pool": [ ... ],  # (see Fix 5)
}),
```

**Alternative approach:** Add `lyrics_probability` as a direct field in the `radio_stations` table. This would require a schema migration but would be more visible in the UI.

---

### Fix 5: Genre-Adaptive Theme Pool for Preset Stations

**Priority:** 2 — Do After Fix 1 & 2
**Impact:** Medium
**Effort:** Medium (update seed data in schema.py)
**Risk:** Low
**Addresses:** Problem 4 (custom station quality), MedievalCore quality

**Rationale:** The current built-in theme pool at [`radio_service.py:520-525`](backend/src/tadpole_studio/services/radio_service.py:520) is pop-centric:
```python
random_themes = [
    "heartbreak", "youthful rebellion", "changing seasons", "a late night drive",
    "finding oneself", "overcoming adversity", "falling in love", "nostalgia",
    ...
]
```

For MedievalCore, these themes are mismatched. The preset should have genre-appropriate themes.

**Proposed MedievalCore advanced_params_json:**
```python
"advanced_params_json": json.dumps({
    "lyrics_probability": 0.65,
    "theme_pool": [
        "a tavern ballad about camaraderie and ale",
        "a knight's journey home from a long war",
        "a medieval love story between a lord and a peasant",
        "life in a bustling medieval marketplace",
        "a bard's tale of a great adventure on the road",
        "a harvest festival celebration in a small village",
        "a dragon's legend told by a village elder",
        "a wandering minstrel seeking fortune and glory",
        "a royal wedding in a grand cathedral",
        "a hard-fought battle and the victory feast afterward",
        "enchantment and magic in an ancient forest",
        "a king's lament for a lost kingdom",
        "rowing a boat on a misty river at dawn",
        "a blacksmith's song about crafting a legendary sword",
        "a Christmas carol in medieval style",
        "sailors singing on a medieval trading vessel",
        "a jester's foolhardy prank at court",
        "two archers competing in a royal tournament",
        "a pilgrimage to a sacred shrine",
        "a quiet evening by the hearth in a stone cottage"
    ],
    "lyrics_style_addons": "Use archaic language, poetic meter, medieval imagery. Reference lutes, taverns, castles, knights, nature, and ancient traditions.",
    "intensity": "Warm and storytelling"
})
```

**For other presets**, consider adding appropriate `advanced_params_json` to:
- Hip-Hop, Pop, R&B (vocal-friendly presets that should also have lyrics)
- Rock, Metal (could benefit from genre-specific themes)

---

### Fix 6: Store Lyrics System Prompt in Settings (Configurability)

**Priority:** 3 — Nice to Have
**Impact:** Low (flexibility improvement)
**Effort:** Medium
**Risk:** Low
**Addresses:** Long-term maintainability

**Rationale:** Make the lyrics system prompt configurable through the Radio Settings UI, like the caption system prompt already is.

**Implementation:**
1. Add `radio_lyrics_system_prompt` to settings table queries in [`radio_service.py:216-220`](backend/src/tadpole_studio/services/radio_service.py:216)
2. Add to `update_settings()` at [`radio_service.py:280-335`](backend/src/tadpole_studio/services/radio_service.py:280)
3. Add to `RadioSettingsResponse` and `RadioSettingsUpdate` models in [`models/radio.py`](backend/src/tadpole_studio/models/radio.py)
4. Add UI field in `radio-settings-dialog.tsx`

---

### Fix 7: Increase max_tokens for Lyrics Generation

**Priority:** 3 — Quick Win
**Impact:** Medium
**Effort:** Trivial (one number change)
**Risk:** Low
**Addresses:** Problem 1 (truncated lyrics)

**Rationale:** Complex structures with multiple sections can exceed 800 tokens. Changing to 1500 provides headroom.

**Change at [`radio_service.py:588`](backend/src/tadpole_studio/services/radio_service.py:588):**
```python
# Current:
raw = await provider.chat(messages, model=model_name, max_tokens=800, temperature=0.8)

# Proposed:
raw = await provider.chat(messages, model=model_name, max_tokens=1500, temperature=0.8)
```

---

### Fix 8: Add LLM Availability Warning for Vocal Stations

**Priority:** 3 — UX Improvement
**Impact:** Low
**Effort:** Low
**Risk:** None
**Addresses:** Problem 1 (silent fallback)

**Rationale:** When lyrics generation silently returns `""` because no LLM is available, the user has no indication that lyrics are being skipped. A warning in the log and potentially a frontend notification would help.

**Implementation:**
```python
# In _generate_lyrics_with_llm(), replace lines 501-502:
if provider is None:
    logger.warning(
        f"Radio lyrics: no LLM provider available for non-instrumental station "
        f"'{station.name}' — song will be generated as instrumental"
    )
    return ""
```

---

### Fix 9: Add Pre-Backend Lyrics Validation (Safety Net)

**Priority:** 3 — Safety Net
**Impact:** Medium (prevents garbage from reaching music model)
**Effort:** Medium (~20 lines)
**Risk:** Low
**Addresses:** All problems (as a final safety check)

**Rationale:** Before sending lyrics to the music backend, validate that they're actually usable.

**Implementation in `generate_next_track()`** after line 631 (after `llm_lyrics = await self._generate_lyrics_with_llm(...)`):

```python
# Validate lyrics quality before generation
if llm_lyrics and not station.instrumental:
    import re as _re
    has_tags = bool(_re.search(
        r'\[(?:Verse|Chorus|Bridge|Outro|Intro)\b',
        llm_lyrics, _re.IGNORECASE
    ))
    has_leakage = any(
        kw in llm_lyrics.upper()
        for kw in ['STRICT REQUIREMENTS', 'STYLE GUIDELINES', 'WRITE A']
    )
    if not has_tags:
        logger.warning(
            f"Radio lyrics: no structural tags found for station '{station.name}', "
            f"lyrics may not produce structured music"
        )
    if has_leakage:
        logger.warning(
            f"Radio lyrics: prompt leakage detected for station '{station.name}', "
            f"output cleaning may have failed"
        )
```

**Note:** This is a warning-only safety net. Aggressive rejection (dropping contaminated lyrics) risks causing Problem 1 again. The logging allows operators to detect ongoing issues.

---

### Fix 10: Add Station Name to Lyrics Prompt

**Priority:** 3 — Quick Win
**Impact:** Medium
**Effort:** Trivial (one line addition)
**Risk:** None
**Addresses:** Generic lyrics that don't match station theme

**Rationale:** Including the station name gives the LLM additional thematic context. For MedievalCore, the name itself hints at the aesthetic.

**Already included in Fix 3** (simplified prompt includes `f"Station: {station.name}"`).

---

## 5. Custom Station Quality Issues

### Complete Data Flow Analysis for Custom Stations

| Stage | What Happens | Problem |
|-------|-------------|---------|
| **Station creation** | `create_station()` at [`radio_service.py:76-113`](backend/src/tadpole_studio/services/radio_service.py:76) | `instrumental` defaults to `True` if not provided. `advanced_params_json` defaults to `"{}"`. No `structure_ids` auto-assigned. |
| **Caption generation** | Falls back to `station.caption_template` or auto-generated caption | Empty `caption_template` → thin fallback like `"A music track"` |
| **Lyrics generation** | `_generate_lyrics_with_llm()` | Empty `genre` → "Pop". Empty `mood` → "Standard". Empty `description` → no concept. Pop-centric theme pool. |
| **Music generation** | `generation_service.generate(params_dict)` | Poor caption + poor lyrics → poor LM tokenization → poor DiT conditioning → poor audio |

### Specific Problems by Field

| Field | Default When Empty | Impact |
|-------|-------------------|--------|
| `genre` | "Pop" | Wrong genre styling for non-pop stations |
| `mood` | "Standard" | Generic emotional tone |
| `description` | `""` → empty concept line | No thematic anchor for lyrics |
| `caption_template` | `""` → thin fallback | Weak conditioning for music model |
| `instrumental` | `True` | Accidental instrumental stations |
| `vocal_language` | "unknown" → "English" | Usually fine but could be wrong |
| `structure_ids` | `[]` → hardcoded default | May not match genre |
| `advanced_params_json` | `"{}"` | Pop themes, generic style |

### Music Quality Cascade (Detailed)

```
User creates custom station with:
  name: "My Folk Station"
  genre: "" (empty)
  mood: "" (empty)
  description: "" (empty)
  caption_template: "" (empty)
  instrumental: False (user unchecked it)

↓ Station saved to DB with all empty fields

↓ User plays station

↓ Caption generation:
  LLM receives: "Genre: \nMood: \nInstrumental: no\n..."
  LLM produces generic caption OR falls back to "A music track"

↓ Lyrics generation:
  genre = "Pop" (default)
  mood = "Standard" (default)
  theme = random pop theme (e.g., "heartbreak")
  Structure = default verse-chorus structure
  Prompt asks for a "Pop song about heartbreak"
  User expected folk music

↓ Music generation:
  Caption: "A music track" (thin)
  Lyrics: Pop-style heartbreak song (wrong genre)
  Result: Music that's neither good folk nor good pop

↓ User hears poor quality and concludes "custom stations are broken"
```

### Phase 2 Recommendations for Custom Stations

| Fix | Description | Effort |
|-----|-------------|--------|
| A | **Auto-assign structures by genre**: When creating a station, match genre to appropriate structure templates | Medium |
| B | **Genre inference from station name**: If genre is empty, try to infer from name (LLM-based or keyword matching) | Medium |
| C | **Minimum parameter validation**: Warn users if creating a vocal station with empty genre/description | Low |
| D | **Richer fallback caption**: Generate a better default caption using all available station data | Low |
| E | **Genre-specific structure templates**: Expand `seed_structures.py` with more genre-specific options | Medium |
| F | **Frontend UI improvements**: Make genre, mood, and description fields more prominent with better defaults | Medium |

---

## 6. Testing Plan

### Test Matrix

| ID | Test Name | Configuration | Pass Criteria |
|----|-----------|--------------|---------------|
| T1 | Basic lyrics generation | MedievalCore, KoboldCpp LLM | Lyrics non-empty in DB, audio has vocals |
| T2 | No prompt leakage | Same as T1 | Lyrics contain zero instances of "STRICT REQUIREMENTS", "STYLE GUIDELINES", "Write a" |
| T3 | Proper bracket format | Same as T1 | All section tags use `[]`, zero instances of `(Verse` or `(Chorus` as headers |
| T4 | Structure following | MedievalCore with 3 assigned structures | Output follows one of the assigned structures |
| T5 | Instrumental fallback | Station with instrumental=True | Empty lyrics, instrumental music, no error |
| T6 | No LLM fallback | LLM provider set to "none" | Empty lyrics, generation completes without crash |
| T7 | LLM failure recovery | LLM endpoint unreachable (kill server mid-generation) | Empty lyrics, generation continues, no crash |
| T8 | Custom station vocals | Custom station, genre="folk", instrumental=False | Lyrics present, genre-appropriate themes |
| T9 | HeartMuLa + lyrics | HeartMuLa backend active, non-instrumental station | Lyrics passed correctly via `inputs["lyrics"]`, audio has vocals |
| T10 | ACE-Step + lyrics | ACE-Step backend active, non-instrumental station | Lyrics pass through LM tokenization, audio has vocals at correct times |
| T11 | Long structures | Structure with 10+ sections (e.g., metal with multiple solos) | All sections present in final lyrics |
| T12 | Non-English lyrics | Station with vocal_language="Latin" | Lyrics primarily in Latin |
| T13 | Think tag handling | Model that outputs `<think>...</think>` blocks | Think tags stripped, lyrics preserved cleanly |
| T14 | Markdown handling | Model that wraps output in \`\`\` fences | Code fences stripped, lyrics preserved |
| T15 | Empty response handling | Model returns empty or whitespace-only | Graceful empty-string return, no crash |
| T16 | Random instrumental toggle | MedievalCore with `lyrics_probability: 0.65` | ~65% of 20 generated tracks have lyrics, ~35% instrumental |
| T17 | MedievalCore theme quality | MedievalCore with genre-specific theme pool | Lyrics contain medieval imagery (tavern, knight, castle, lute, etc.) |
| T18 | Output cleaning edge cases | Feed known-bad outputs through `_clean_lyrics_output()` | All test cases produce clean output |

### Testing Procedure

**Setup:**
1. Configure the target LLM provider in settings (`PATCH /radio/settings`)
2. Verify provider is available via `GET /radio/settings`
3. Note the active model name and provider type

**For each integration test (T1-T17):**
1. Create or select the target station configuration
2. Generate one track via `POST /radio/generate/{station_id}`
3. Check backend logs for:
   - `Radio LLM raw lyrics output:` — captures raw model response (line 589)
   - `Radio LLM lyrics generated via` — captures cleaned output (line 592)
   - Any warnings about LLM failures or validation issues
4. Query the DB: `SELECT lyrics FROM songs ORDER BY created_at DESC LIMIT 1`
5. Listen to the generated audio
6. Score against pass criteria

**For unit test T18 (output cleaning):**
1. Create a test file with known-bad outputs (prompt leakage, wrong brackets, think tags, markdown)
2. Run each through `_clean_lyrics_output()`
3. Verify output matches expected clean version

### Rollback Plan

All fixes are independently reversible:

| Fix | Rollback Method |
|-----|----------------|
| Fix 1 (system prompt) | Set `LYRICS_SYSTEM_PROMPT = ""` or remove system message from messages list |
| Fix 2 (output cleaning) | Replace `_clean_lyrics_output(raw)` with original regex: `re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()` |
| Fix 3 (simplified prompt) | Restore original prompt text from git |
| Fix 4 (random toggle) | Remove `lyrics_probability` check, revert to `if station.instrumental` only |
| Fix 5 (theme pools) | Remove `advanced_params_json` from preset definitions |
| Fix 7 (max_tokens) | Change `1500` back to `800` |

### Success Criteria for Deployment

| Metric | Target |
|--------|--------|
| T1-T4 pass rate | 100% across 10 consecutive generations |
| T5-T7 graceful degradation | 100% (no crashes) |
| Audio quality average score | ≥4.0/5.0 across 10 tracks |
| Generation failure rate | No increase from current baseline |
| Generation time (LLM call) | Under 30 seconds per call |
| Output cleaning success rate | ≥90% ✅ Clean, ≤5% ❌ Broken |

---

## 7. Recommended Action Order

| Priority | Fix | Effort | Impact | Risk | Addresses |
|----------|-----|--------|--------|------|-----------|
| **1** | Fix 1: Add system prompt for lyrics | Low | Very High | Low | Problems 2, 3 |
| **1** | Fix 2: Add output cleaning pipeline | Medium | Very High | Low | Problems 1, 2, 3 |
| **2** | Fix 3: Simplify lyrics user prompt | Low | Medium | Low | Problem 2 |
| **2** | Fix 4: Random instrumental toggle | Medium | Medium | Low | User clarification |
| **2** | Fix 5: Genre-adaptive theme pools | Medium | Medium | Low | Problem 4, MedievalCore quality |
| **3** | Fix 7: Increase max_tokens to 1500 | Trivial | Medium | None | Problem 1 |
| **3** | Fix 8: LLM availability warning | Low | Low (UX) | None | Problem 1 |
| **3** | Fix 9: Pre-backend lyrics validation | Medium | Safety net | Low | All |
| **3** | Fix 10: Station name in prompt | Trivial | Medium | None | Generic lyrics |
| **4** | Fix 6: Store lyrics system prompt in settings | Medium | Low (flexibility) | Low | Maintainability |
| **Phase 2** | Custom station smart defaults (A-F above) | High | Medium | Medium | Problem 4 |

### Expected Outcomes

**After Fix 1 + Fix 2 (Priority 1):**
- Problem 2 (prompt leakage): **Resolved** — system prompt prevents echo, output cleaning catches any leakage
- Problem 3 (`()` vs `[]`): **Resolved** — system prompt reinforces brackets, output cleaning normalizes
- Problem 1 (no lyrics): **Partially resolved** — catches cases where model returns think-tag-only or preamble-only output

**After Fix 3 + Fix 4 + Fix 5 (Priority 2):**
- Problem 1 (no lyrics): **Resolved** — simplified prompt reduces LLM confusion, max_tokens increase prevents truncation
- MedievalCore randomization: **Resolved** — `lyrics_probability` provides controlled randomness
- MedievalCore quality: **Improved** — genre-specific themes and style addons

**After all Priority 1-3 fixes:**
- Problems 1, 2, 3: **Fully resolved**
- Problem 4 (custom stations): **Partially improved** (better defaults, but needs Phase 2 for full resolution)

**After Phase 2 (custom station improvements):**
- Problem 4: **Fully resolved** — smart defaults, genre inference, validation, richer fallbacks

---

## Appendix A: File Reference Index

| File | Lines of Interest | Purpose |
|------|------------------|---------|
| [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py) | 494-597 | Lyrics generation — the core of all issues |
| [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py) | 579-584 | LLM messages — missing system prompt |
| [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py) | 590 | Output cleaning — only strips think tags |
| [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py) | 557-577 | Prompt template — overly verbose |
| [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py) | 588 | `max_tokens=800` — may be too low |
| [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py) | 337-378 | LLM provider selection — fallback chain |
| [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py) | 96 | Custom station `instrumental` default |
| [`backend/src/tadpole_studio/services/llm_provider.py`](backend/src/tadpole_studio/services/llm_provider.py) | 42 | `chat()` interface — max_tokens, temperature params |
| [`backend/src/tadpole_studio/services/llm_provider.py`](backend/src/tadpole_studio/services/llm_provider.py) | 330-412 | `OpenAICompatibleProvider` — for KoboldCpp |
| [`backend/src/tadpole_studio/backends/ace_step_backend.py`](backend/src/tadpole_studio/backends/ace_step_backend.py) | 322-399 | ACE-Step generation — lyrics flow through LM |
| [`backend/src/tadpole_studio/backends/heartmula_backend.py`](backend/src/tadpole_studio/backends/heartmula_backend.py) | 447-567 | HeartMuLa generation — lyrics in inputs dict |
| [`backend/src/tadpole_studio/db/schema.py`](backend/src/tadpole_studio/db/schema.py) | 317-327 | MedievalCore preset definition |
| [`backend/src/tadpole_studio/db/schema.py`](backend/src/tadpole_studio/db/schema.py) | 73-94 | `radio_stations` table schema |
| [`backend/src/tadpole_studio/models/radio.py`](backend/src/tadpole_studio/models/radio.py) | 7-28 | `StationResponse` model |
| [`backend/src/tadpole_studio/models/generation.py`](backend/src/tadpole_studio/models/generation.py) | 5-75 | `GenerateRequest` — lyrics field structure |
| [`backend/src/scripts/seed_structures.py`](backend/src/scripts/seed_structures.py) | 1-123 | Structure templates — all use `[]` format |
| [`LYRICS_STRATEGY.md`](LYRICS_STRATEGY.md) | 1-109 | Previous strategy document |
| [`RADIO-STATIONS-ANALYSIS.md`](RADIO-STATIONS-ANALYSIS.md) | 1-764 | Previous comprehensive analysis |

## Appendix B: Current Built-in Theme Pool

From [`radio_service.py:520-525`](backend/src/tadpole_studio/services/radio_service.py:520):

```python
random_themes = [
    "heartbreak",
    "youthful rebellion",
    "changing seasons",
    "a late night drive",
    "finding oneself",
    "overcoming adversity",
    "falling in love",
    "nostalgia",
    "a distant memory",
    "a fleeting moment",
    "the beauty of nature",
    "city life",
    "a quiet morning",
    "an epic journey",
    "betrayal",
    "hope for the future",
    "a secret romance",
    "dancing in the rain",
    "a farewell",
    "a new beginning"
]
```

These are ALL pop-centric themes. None are appropriate for medieval, metal, classical, ambient, or electronic genres. This is a significant contributor to Problem 4.

## Appendix C: Current Default Structure Template

From [`radio_service.py:541`](backend/src/tadpole_studio/services/radio_service.py:541):

```python
station_chosen_structure = "[Verse 1]\n[Chorus]\n[Verse 2]\n[Chorus]\n[Bridge]\n[Chorus]\n[Outro]"
```

This is a standard pop structure. It's used for ALL stations that don't have `structure_ids` assigned, including:
- MedievalCore (should use a structure with lute solos, tavern choruses)
- Electronic (should use builds, drops, breakdowns)
- Metal (should include guitar solos, breakdowns, blast sections)
- Ambient (may not need verse/chorus at all)