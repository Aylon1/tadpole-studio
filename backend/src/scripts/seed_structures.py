import asyncio
import uuid
import datetime

from tadpole_studio.db.connection import get_db, init_db, close_db

STRUCTURES = {
    "country": (
        "[Steel Guitar Intro]\n\n"
        "[Verse 1] (storytelling)\n{lyrics}\n\n"
        "[Chorus] (big melody)\n{lyrics}\n\n"
        "[Verse 2] (develop story)\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Fiddle Solo] (8 bars)\n\n"
        "[Bridge] (emotional peak)\n{lyrics}\n\n"
        "[Double Chorus] (with harmonies)"
    ),
    "pop": (
        "[Verse 1]\n{lyrics}\n\n"
        "[Pre-Chorus]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Pre-Chorus]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Bridge]\n{lyrics}\n\n"
        "[Final Chorus] (with ad-libs)"
    ),
    "rock": (
        "[Guitar Intro]\n\n"
        "[Verse 1]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Guitar Solo] (8-16 bars)\n\n"
        "[Bridge]\n{lyrics}\n\n"
        "[Double Chorus] (big finish)"
    ),
    "hip hop": (
        "[Intro Hook]\n{lyrics}\n\n"
        "[Verse 1]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Bridge] (optional rap breakdown)\n\n"
        "[Outro] (fade with ad-libs)"
    ),
    "electronic": (
        "[Atmospheric Intro] (16 bars)\n\n"
        "[Build-Up]\n{lyrics}\n\n"
        "[Drop]\n{lyrics}\n\n"
        "[Breakdown Verse]\n{lyrics}\n\n"
        "[Build-Up]\n{lyrics}\n\n"
        "[Drop]\n{lyrics}\n\n"
        "[Outro] (beat fade)"
    ),
    "lofi": (
        "[Ambient Intro] (with vinyl noise)\n\n"
        "[Verse 1]\n{lyrics}\n\n"
        "[Chill Chorus]\n{lyrics}\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Chill Chorus]\n{lyrics}\n\n"
        "[Instrumental Break] (8 bars)\n\n"
        "[Outro] (fade with rain sounds)"
    ),
    "jazz": (
        "[Piano Intro] (improvised)\n\n"
        "[Verse 1]\n{lyrics}\n\n"
        "[Swing Chorus]\n{lyrics}\n\n"
        "[Instrumental Break] (sax solo)\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Swing Chorus]\n{lyrics}\n\n"
        "[Outro] (group improv)"
    ),
    "classical": (
        "[Orchestral Introduction]\n\n"
        "[Theme A]\n{lyrics}\n\n"
        "[Theme B] (variation)\n\n"
        "[Development Section]\n\n"
        "[Recapitulation]\n{lyrics}\n\n"
        "[Coda] (grand finale)"
    ),
    "ambient": (
        "[Textural Intro] (2-4 minutes)\n\n"
        "[Drone Section]\n{lyrics}\n\n"
        "[Modulation]\n\n"
        "[Resolution Section]\n{lyrics}\n\n"
        "[Fade Out] (gradual)"
    ),
    "metal": (
        "[Shredding Intro] (fast picking)\n\n"
        "[Verse 1] (growled vocals)\n{lyrics}\n\n"
        "[Chorus] (clean vocals)\n{lyrics}\n\n"
        "[Guitar Solo] (tapping)\n\n"
        "[Breakdown] (chugging riffs)\n\n"
        "[Final Blast] (double bass)"
    ),
    "reggae": (
        "[Skank Guitar Intro]\n\n"
        "[Verse 1]\n{lyrics}\n\n"
        "[Chorus] (call-and-response)\n{lyrics}\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Dub Section] (instrumental)\n\n"
        "[Final Chorus] (with harmonies)"
    ),
    "blues": (
        "[Guitar Lick Intro] (12-bar)\n\n"
        "[Verse 1]\n{lyrics}\n\n"
        "[Response] (guitar answers vocal)\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Harmonica Solo] (12-bar)\n\n"
        "[Outro] (repeat and fade)"
    ),
    "default": (
        "[Intro]\n{lyrics}\n\n"
        "[Verse 1]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Verse 2]\n{lyrics}\n\n"
        "[Chorus]\n{lyrics}\n\n"
        "[Bridge/Middle 8]\n{lyrics}\n\n"
        "[Chorus] (variation)\n\n"
        "[Outro] (optional vamp)"
    )
}

async def seed_structures():
    await init_db()
    db = await get_db()
    try:
        for name, template in STRUCTURES.items():
            display_name = name.title()
            
            # Check if it already exists to avoid duplicates if run multiple times
            cursor = await db.execute("SELECT id FROM song_structures WHERE name = ? AND is_system = 1", (display_name,))
            existing = await cursor.fetchone()
            
            if not existing:
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                await db.execute(
                    """
                    INSERT INTO song_structures (id, name, genre, template, is_system, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), display_name, display_name if name != 'default' else '', template, 1, now, now)
                )
                print(f"Seeded structure: {display_name}")
            else:
                print(f"Structure already exists: {display_name}")
                
        await db.commit()
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(seed_structures())
