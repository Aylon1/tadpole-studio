# Caption Generation Strategy for ACE-Step

> Generated: 2026-08-03
> Goal: Fix caption generation to produce ACE-Step-compatible keyword lists while preserving per-track creativity and variety, incorporating ALL custom station data.

---

## Problem Statement

ACE-Step expects the `tags` (caption) field to be a **comma-separated keyword list of 5-12 specific tags**, not prose descriptions. Our current system generates prose, which ACE-Step cannot properly parse, leading to poor music quality — especially for custom stations.

### ACE-Step Caption Format Requirements

```
[genre], [mood], [2-3 specific instruments], [vocal type], [production style], [BPM] bpm
```

**Key rules:**
1. Comma-separated keywords, 5-12 total
2. Genre always first
3. Specific instrument names (e.g., "fingerpicked lute", not "lute")
4. Production tags control mix quality (hi-fi, lo-fi, dusty, analog warmth)
5. Always include BPM as last tag
6. NO prose, NO sentences, NO adjectives without nouns
7. No contradictory tags

---

## Current System — What Data Is Available

### Station Fields (from StationResponse model)

| Field | Example (Golden 60s) | Currently Passed to LLM? |
|-------|---------------------|--------------------------|
| name | "Golden 60s Evergreens_v2" | ❌ No |
| description | "Timeless 1960s pop, sweet soul, and vintage girl-group harmonies" | ❌ No |
| genre | "1960s pop, doo-wop, soul, wall of sound" | ✅ Yes |
| mood | "nostalgic, romantic, wistful, sweet" | ✅ Yes |
| instrumental | False | ✅ Yes |
| vocal_language | "unknown" | ✅ Yes |
| bpm_min/bpm_max | 65 / 135 | ✅ Yes |
| keyscale | "" | ✅ Yes (if present) |
| timesignature | "" | ✅ Yes (if present) |
| caption_template | "A classic {genre} song featuring sweet female lead vocals..." | ✅ Yes |
| advanced_params_json | {} (from UI: intensity, style_addons) | ❌ No |

### Missing Data in Current LLM Caption Prompt

The current `_generate_caption_with_llm()` at [`radio_service.py:524-542`](backend/src/tadpole_studio/services/radio_service.py:524) passes: genre, mood, instrumental, vocal_language, BPM range, keyscale, timesignature, caption_template.

**Missing:** station name, description, intensity, prompt_style_addons from advanced_params_json.

For a rich custom station like "Golden 60s Evergreens", the description and caption_template contain critical info: "sweet female lead vocals, lush backing harmonies, vintage orchestral arrangement, warm analog vinyl sound." Without this, the LLM has no way to know to include female vocal or orchestral tags.

---

## Recommended Solution: Option D (Enhanced)

### Part 1: New System Prompt (Keyword-Format Enforcement)

Replace `RADIO_DEFAULT_SYSTEM_PROMPT` with:

```
You are a music tag generator for the ACE-Step AI music model.
Given station parameters, generate a comma-separated keyword list
(5-12 keywords) that controls audio generation.

FORMULA: [genre], [mood], [2-3 specific instruments], [vocal type],
[production style], [BPM] bpm

RULES:
- Genre must be first (pick the most specific genre from the provided list)
- Use SPECIFIC instrument names (fingerpicked lute, felt piano,
  supersaw synth — not generic "guitar" or "piano")
- Vary your tag selection each time — pick different instruments,
  production styles, and BPMs within the given range
- Include 1-2 production tags (hi-fi, lo-fi, dusty, polished,
  analog warmth, tape saturation, wide stereo, intimate, etc.)
- Always end with BPM as the last tag (pick a specific value
  within the given BPM range)
- If the station has a description or caption template, extract
  instrument/vocal/production details from it and include as tags
- Output ONLY the comma-separated keywords — no prose, no
  sentences, no explanations
- 5-12 keywords total
- Avoid contradictory tags
```

### Part 2: Pass ALL Station Data to the LLM

Update the user message builder in `_generate_caption_with_llm()` to include:

```python
parts = []
if station.name:
    parts.append(f"Station name: {station.name}")
if station.genre:
    parts.append(f"Genre: {station.genre}")
if station.mood:
    parts.append(f"Mood: {station.mood}")
parts.append(f"Instrumental: {'yes' if station.instrumental else 'no'}")
if station.vocal_language and station.vocal_language != "unknown":
    parts.append(f"Vocal language: {station.vocal_language}")
if station.bpm_min is not None and station.bpm_max is not None:
    parts.append(f"BPM range: {station.bpm_min}-{station.bpm_max}")
if station.keyscale:
    parts.append(f"Key/scale: {station.keyscale}")
if station.timesignature:
    parts.append(f"Time signature: {station.timesignature}")
if station.description:
    parts.append(f"Description: {station.description}")
if station.caption_template:
    parts.append(f"Caption template: {station.caption_template}")

# Parse advanced_params_json for intensity and style addons
try:
    advanced = json.loads(station.advanced_params_json) if station.advanced_params_json else {}
    if advanced.get("intensity"):
        parts.append(f"Intensity: {advanced['intensity']}")
    if advanced.get("lyrics_style_addons"):
        parts.append(f"Style addons: {advanced['lyrics_style_addons']}")
except (json.JSONDecodeError, AttributeError):
    pass

user_message = "Generate ACE-Step music tags (comma-separated keywords) for these station parameters:\n" + "\n".join(parts)
```

**Example user message for Golden 60s station:**
```
Generate ACE-Step music tags (comma-separated keywords) for these station parameters:
Station name: Golden 60s Evergreens_v2
Genre: 1960s pop, doo-wop, soul, wall of sound
Mood: nostalgic, romantic, wistful, sweet
Instrumental: no
BPM range: 65-135
Description: Timeless 1960s pop, sweet soul, and vintage girl-group harmonies
Caption template: A classic {genre} song featuring sweet female lead vocals, lush backing harmonies, and a vintage orchestral arrangement. The mood is {mood} with a warm analog vinyl sound.
Intensity: High
Style addons: dreamy, innocent, intimate, romantic
```

**Expected LLM output:**
```
1960s pop, nostalgic, sweet female lead vocal, lush backing harmonies, orchestral strings, analog warmth, vinyl crackle, 92 bpm
```

**Another generation (variation):**
```
doo-wop, romantic, girl group harmonies, wall of sound, tambourine, vintage piano, warm production, 88 bpm
```

### Part 3: Post-Processing Safety Net (`_clean_caption_output`)

```python
def _clean_caption_output(raw: str, station: StationResponse) -> str:
    """Clean and validate LLM caption output for ACE-Step compatibility.
    
    Ensures: comma-separated keywords, 5-12 tags, BPM at end.
    """
    if not raw or not raw.strip():
        return _build_fallback_caption(station)
    
    # Split by comma and trim
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    
    if len(tags) < 2:
        return _build_fallback_caption(station)
    
    # Enforce 5-12 limit
    if len(tags) > 12:
        tags = tags[:12]
    
    # Ensure BPM tag at the end
    has_bpm = any("bpm" in t.lower() for t in tags)
    if not has_bpm:
        bpm_val = 80  # default
        if station.bpm_min and station.bpm_max:
            bpm_val = random.randint(station.bpm_min, station.bpm_max)
        tags.append(f"{bpm_val} bpm")
    
    return ", ".join(tags)
```

### Part 4: Update Caption Templates in schema.py

Convert existing prose templates to keyword-style with `{bpm}` placeholder:

| Station | Current Template | New Template |
|---------|-----------------|--------------|
| Lo-Fi Chill | `A {mood} {genre} track with warm textures and gentle rhythms` | `lo-fi hip-hop, chill, sampled piano, dusty, vinyl crackle, tape saturation, {bpm} bpm` |
| Jazz Club | `A {mood} {genre} piece with expressive melodies and rich harmonies` | `smooth jazz, sophisticated, upright bass, grand piano, brushed drums, intimate, {bpm} bpm` |
| EDM Energy | `A {mood} {genre} track with driving beats and soaring synths` | `progressive house, energetic, supersaw synth, wide stereo, sidechain pumping, driving kick, {bpm} bpm` |
| Classical Piano | `A {mood} {genre} piece with expressive dynamics and flowing melodies` | `classical piano, elegant, felt piano, expressive, intimate, polished, {bpm} bpm` |
| Ambient | `An {mood} {genre} soundscape with lush textures and subtle movement` | `ambient, dreamy, lush synthesizer, atmospheric pads, wide stereo, generative, {bpm} bpm` |
| Hip-Hop | `A {mood} {genre} track with punchy drums and deep bass` | `hip-hop, confident, punchy 808, deep sub bass, crisp snare, hi-fi, clean, {bpm} bpm` |
| Pop | `A {mood} {genre} song with memorable melodies and modern production` | `pop, catchy, synth, bright vocal, polished, clean, wide stereo, {bpm} bpm` |
| R&B | `A {mood} {genre} track with lush chords and silky grooves` | `R&B, soulful, smooth, lush chords, silky vocal, warm bass, clean, {bpm} bpm` |
| Rock | `A {mood} {genre} track with distorted guitars and driving drums` | `indie rock, powerful, distorted guitar, driving drums, raw, compressed, {bpm} bpm` |
| Metal | `An {mood} {genre} track with crushing riffs and thunderous percussion` | `metal, aggressive, distorted guitar, thunderous drums, deep vocal, compressed, {bpm} bpm` |
| Medievalcore | `Music as if played in medieval times, using instruments like lutes, harps, flutes` | `bardcore, chill, fingerpicked lute, harp, wooden flute, intimate vocal, acoustic percussion, {bpm} bpm` |

**Note:** Templates use `{bpm}` placeholder which gets resolved at runtime to a random value within the station's BPM range.

### Part 5: Update Auto-Generated Fallback

Replace the prose fallback at [`radio_service.py:762-767`](backend/src/tadpole_studio/services/radio_service.py:762) with a keyword-style fallback function that builds from available data.

---

## How Custom Station Data Flows Into Captions (Full Example)

For "Golden 60s Evergreens_v2":

```
Station name: Golden 60s Evergreens_v2          → Era context (1960s)
Genre: 1960s pop, doo-wop, soul, wall of sound  → First tags: "1960s pop" or "doo-wop"
Mood: nostalgic, romantic, wistful, sweet       → Mood tags
Instrumental: no                                → Include vocal type
Description: "...sweet soul, vintage girl-group harmonies" → Girl group harmonies tag
Caption template: "...female lead vocals, lush backing harmonies, 
                   vintage orchestral arrangement, warm analog vinyl sound" 
                   → Female vocal, backing harmonies, orchestral, analog, vinyl tags
Intensity: High                                 → Bold production tags
Style addons: dreamy, innocent, intimate, romantic → Additional mood/production tags
BPM: 65-135                                     → Pick specific BPM like 92 or 88
```

**LLM distills all of this into:**
```
1960s pop, nostalgic, sweet female lead vocal, lush backing harmonies, orchestral strings, analog warmth, vinyl crackle, 92 bpm
```

---

## Implementation Plan

| Step | File | Change | Lines |
|------|------|--------|-------|
| 1 | `radio_service.py` | Replace `RADIO_DEFAULT_SYSTEM_PROMPT` | ~10 lines |
| 2 | `radio_service.py` | Update user message builder in `_generate_caption_with_llm()` to include name, description, intensity, style_addons | ~15 lines added |
| 3 | `radio_service.py` | Add `_clean_caption_output()` + `_build_fallback_caption()` functions | ~40 lines |
| 4 | `radio_service.py` | Call `_clean_caption_output()` on LLM result | 1 line change |
| 5 | `radio_service.py` | Update auto-generated fallback path at line 762 | ~10 lines |
| 6 | `schema.py` | Update all 11 caption_template values to keyword format | 11 lines |
