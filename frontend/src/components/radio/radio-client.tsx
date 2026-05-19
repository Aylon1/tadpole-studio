"use client";

// Radio station feature -- inspired by nalexand/ACE-Step-1.5-OPTIMIZED (MusicBox jukebox)
// and PasiKoodaa/ACE-Step-RADIO (radio station mode with memory optimization)

import { useState, useCallback } from "react";
import { Radio, Plus, Loader2, Settings } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { fetchStations, deleteStation } from "@/lib/api/radio-client";
import { useRadio } from "@/hooks/use-radio";
import type { StationResponse } from "@/types/api";
import { StationGrid } from "./station-grid";
import { StationNowPlaying } from "./station-now-playing";
import { CreateStationDialog } from "./create-station-dialog";
import { EditStationDialog } from "./edit-station-dialog";
import { RadioSettingsDialog } from "./radio-settings-dialog";
import { StructuresSettingsDialog } from "./structures-settings-dialog";
import { ListMusic } from "lucide-react";

export function RadioClient() {
  const queryClient = useQueryClient();
  const { activeStationId } = useRadio();

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [structuresOpen, setStructuresOpen] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editingStation, setEditingStation] = useState<StationResponse | null>(
    null,
  );
  const [deletingStation, setDeletingStation] =
    useState<StationResponse | null>(null);

  const { data: stations = [], isLoading } = useQuery({
    queryKey: ["stations"],
    queryFn: fetchStations,
  });

  const activeStation = activeStationId
    ? stations.find((s) => s.id === activeStationId)
    : undefined;

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteStation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stations"] });
      toast.success("Station deleted");
      setDeletingStation(null);
    },
    onError: (err) => {
      toast.error(`Failed to delete station: ${err.message}`);
    },
  });

  const handleEdit = useCallback((station: StationResponse) => {
    setEditingStation(station);
  }, []);

  const handleDelete = useCallback(
    (station: StationResponse) => {
      setDeletingStation(station);
      deleteMutation.mutate(station.id);
    },
    [deleteMutation],
  );

  const handleRefetch = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["stations"] });
  }, [queryClient]);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Radio className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-semibold">Radio</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            className="gap-1.5"
            onClick={() => setCreateDialogOpen(true)}
          >
            <Plus className="h-4 w-4" />
            Create Station
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setStructuresOpen(true)}
            title="Manage Song Structures"
          >
            <ListMusic className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>

      {/* Now Playing panel */}
      <AnimatePresence mode="wait">
        {activeStation && (
          <motion.div
            key={activeStation.id}
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{
              opacity: 1,
              y: 0,
              scale: 1,
              transition: {
                type: "spring",
                stiffness: 260,
                damping: 28,
                mass: 0.8,
                opacity: { duration: 0.4, ease: "easeOut" },
              },
            }}
            exit={{
              opacity: 0,
              y: 8,
              transition: { duration: 0.3, ease: [0.25, 0.1, 0.25, 1] },
            }}
          >
            <StationNowPlaying station={activeStation} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Station grid */}
      <StationGrid
        stations={stations}
        isLoading={isLoading}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />

      {/* Create dialog */}
      <CreateStationDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={handleRefetch}
      />

      {/* Edit dialog */}
      <EditStationDialog
        station={editingStation}
        open={editingStation !== null}
        onOpenChange={(open) => {
          if (!open) setEditingStation(null);
        }}
        onUpdated={handleRefetch}
      />

      {/* Settings dialog */}
      <RadioSettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
      />

      {/* Structures dialog */}
      <StructuresSettingsDialog
        open={structuresOpen}
        onOpenChange={setStructuresOpen}
      />
    </div>
  );
}
