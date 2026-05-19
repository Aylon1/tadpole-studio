"use client";

import { useState } from "react";
import { Loader2, Plus, Pencil, Trash2 } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  fetchStructures,
  createStructure,
  updateStructure,
  deleteStructure,
} from "@/lib/api/radio-client";
import type { SongStructure } from "@/types/api";

interface StructuresSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function StructuresSettingsDialog({
  open,
  onOpenChange,
}: StructuresSettingsDialogProps) {
  const queryClient = useQueryClient();

  const { data: structures = [], isLoading } = useQuery({
    queryKey: ["structures"],
    queryFn: fetchStructures,
    enabled: open,
  });

  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<Partial<SongStructure>>({
    name: "",
    format_description: "",
  });

  const createMutation = useMutation({
    mutationFn: (data: Partial<SongStructure>) => createStructure(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["structures"] });
      toast.success("Structure created");
      setEditingId(null);
      setFormData({ name: "", format_description: "" });
    },
    onError: (err) => {
      toast.error(`Failed to create: ${err.message}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<SongStructure> }) =>
      updateStructure(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["structures"] });
      toast.success("Structure updated");
      setEditingId(null);
      setFormData({ name: "", format_description: "" });
    },
    onError: (err) => {
      toast.error(`Failed to update: ${err.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteStructure(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["structures"] });
      toast.success("Structure deleted");
    },
    onError: (err) => {
      toast.error(`Failed to delete: ${err.message}`);
    },
  });

  const handleSave = () => {
    if (!formData.name || !formData.format_description) {
      toast.error("Name and format description are required");
      return;
    }
    if (editingId && editingId !== "new") {
      updateMutation.mutate({ id: editingId, data: formData });
    } else {
      createMutation.mutate(formData);
    }
  };

  const handleEdit = (structure: SongStructure) => {
    setEditingId(structure.id);
    setFormData({
      name: structure.name,
      format_description: structure.format_description,
    });
  };

  const handleDelete = (id: string) => {
    if (window.confirm("Are you sure you want to delete this structure?")) {
      deleteMutation.mutate(id);
    }
  };

  const handleAddNew = () => {
    setEditingId("new");
    setFormData({ name: "", format_description: "" });
  };

  const handleCancel = () => {
    setEditingId(null);
    setFormData({ name: "", format_description: "" });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Song Structures</DialogTitle>
          <DialogDescription>
            Manage global song structures that stations can randomly select from.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto pr-1 space-y-4">
          {isLoading ? (
            <div className="flex justify-center p-4">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : (
            <>
              {editingId ? (
                <div className="space-y-4 p-4 border rounded-md">
                  <div className="space-y-2">
                    <Label htmlFor="structure-name">Name</Label>
                    <Input
                      id="structure-name"
                      value={formData.name || ""}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          name: e.target.value,
                        }))
                      }
                      placeholder="e.g., Pop AABA"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="structure-format">Format Description</Label>
                    <Textarea
                      id="structure-format"
                      value={formData.format_description || ""}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          format_description: e.target.value,
                        }))
                      }
                      placeholder="[Verse 1]&#10;...&#10;[Chorus]&#10;..."
                      rows={6}
                      className="font-mono text-sm"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={handleCancel}>
                      Cancel
                    </Button>
                    <Button
                      onClick={handleSave}
                      disabled={createMutation.isPending || updateMutation.isPending}
                    >
                      {(createMutation.isPending || updateMutation.isPending) && (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      )}
                      Save
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <Button onClick={handleAddNew} className="w-full">
                    <Plus className="mr-2 h-4 w-4" />
                    Add New Structure
                  </Button>
                  {structures.map((structure) => (
                    <div
                      key={structure.id}
                      className="flex items-center justify-between p-3 border rounded-md"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium truncate">{structure.name}</p>
                        <p className="text-xs text-muted-foreground truncate font-mono">
                          {structure.format_description.split("\n")[0]}...
                        </p>
                      </div>
                      <div className="flex items-center gap-1 ml-4">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleEdit(structure)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-red-500"
                          onClick={() => handleDelete(structure.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                  {structures.length === 0 && (
                    <p className="text-sm text-center text-muted-foreground py-4">
                      No structures found. Create one to get started.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
