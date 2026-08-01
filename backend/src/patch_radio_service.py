import re

with open("tadpole_studio/services/radio_service.py", "r") as f:
    content = f.read()

# Add SongStructureResponse to imports
content = content.replace(
    "from tadpole_studio.models.radio import StationResponse",
    "from tadpole_studio.models.radio import StationResponse, SongStructureResponse"
)

# Update list_stations
list_stations_old = """    async def list_stations(self) -> list[StationResponse]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM radio_stations ORDER BY is_preset DESC, name ASC"
        )
        rows = await cursor.fetchall()
        return [_row_to_station(row) for row in rows]"""

list_stations_new = """    async def list_stations(self) -> list[StationResponse]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM radio_stations ORDER BY is_preset DESC, name ASC"
        )
        rows = await cursor.fetchall()
        
        # Fetch structures for all stations
        cursor = await db.execute("SELECT station_id, structure_id FROM station_structures")
        struct_rows = await cursor.fetchall()
        station_structs = {}
        for r in struct_rows:
            station_structs.setdefault(r["station_id"], []).append(r["structure_id"])
            
        return [_row_to_station(row, station_structs.get(row["id"], [])) for row in rows]"""
content = content.replace(list_stations_old, list_stations_new)

# Update get_station
get_station_old = """    async def get_station(self, station_id: str) -> Optional[StationResponse]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM radio_stations WHERE id = ?", (station_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_station(row)"""

get_station_new = """    async def get_station(self, station_id: str) -> Optional[StationResponse]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM radio_stations WHERE id = ?", (station_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
            
        cursor = await db.execute("SELECT structure_id FROM station_structures WHERE station_id = ?", (station_id,))
        struct_rows = await cursor.fetchall()
        structure_ids = [r["structure_id"] for r in struct_rows]
            
        return _row_to_station(row, structure_ids)"""
content = content.replace(get_station_old, get_station_new)

# Update create_station
create_station_old = """        await db.commit()

        station = await self.get_station(station_id)
        assert station is not None
        return station"""

create_station_new = """        structure_ids = data.get("structure_ids", [])
        for struct_id in structure_ids:
            await db.execute(
                "INSERT INTO station_structures (station_id, structure_id) VALUES (?, ?)",
                (station_id, struct_id),
            )
            
        await db.commit()

        station = await self.get_station(station_id)
        assert station is not None
        return station"""
content = content.replace(create_station_old, create_station_new)

# Update update_station
update_station_old = """        await db.execute(
            f"UPDATE radio_stations SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        await db.commit()

        return await self.get_station(station_id)"""

update_station_new = """        
        structure_ids = updates.pop("structure_ids", None)
        
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values())
            values.append(station_id)
            await db.execute(
                f"UPDATE radio_stations SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
                values,
            )
            
        if structure_ids is not None:
            await db.execute("DELETE FROM station_structures WHERE station_id = ?", (station_id,))
            for struct_id in structure_ids:
                await db.execute(
                    "INSERT INTO station_structures (station_id, structure_id) VALUES (?, ?)",
                    (station_id, struct_id),
                )
                
        await db.commit()

        return await self.get_station(station_id)"""
# We need a regex or careful replacement here because `updates` is manipulated
with open("tadpole_studio/services/radio_service.py", "w") as f:
    f.write(content)

print("Pass 1 done")
