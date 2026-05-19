"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query";
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
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { updateStation, fetchStructures } from "@/lib/api/radio-client";
import type { StationResponse } from "@/types/api";

interface EditStationDialogProps {
  station: StationResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpdated?: () => void;
}

interface FormState {
  name: string;
  description: string;
  genre: string;
  mood: string;
  caption_template: string;
  instrumental: boolean;
  bpm_min: string;
  bpm_max: string;
  duration_min: string;
  duration_max: string;
  keyscale: string;
  timesignature: string;
  structure_ids: string[];
  intensity: string;
  lyrics_style_addons: string;
  theme_pool: string;
}

export function EditStationDialog({
  station,
  open,
  onOpenChange,
  onUpdated,
}: EditStationDialogProps) {
  const queryClient = useQueryClient();
  const { data: structures = [] } = useQuery({
    queryKey: ["structures"],
    queryFn: fetchStructures,
    enabled: open,
  });

  const [form, setForm] = useState<FormState>({
    name: "",
    description: "",
    genre: "",
    mood: "",
    caption_template: "",
    instrumental: false,
    bpm_min: "",
    bpm_max: "",
    duration_min: "",
    duration_max: "",
    keyscale: "",
    timesignature: "",
    structure_ids: [],
    intensity: "Moderate",
    lyrics_style_addons: "",
    theme_pool: "",
  });

  useEffect(() => {
    if (station) {
      let intensity = "Moderate";
      let lyrics_style_addons = "";
      let theme_pool = "";
      
      try {
        if (station.advanced_params_json) {
          const params = JSON.parse(station.advanced_params_json);
          intensity = params.intensity || "Moderate";
          lyrics_style_addons = params.lyrics_style_addons || "";
          if (Array.isArray(params.theme_pool)) {
            theme_pool = params.theme_pool.join(", ");
          }
        }
      } catch (e) {
        console.error("Failed to parse advanced params", e);
      }

      setForm({
        name: station.name,
        description: station.description,
        genre: station.genre,
        mood: station.mood,
        caption_template: station.caption_template ?? "",
        instrumental: station.instrumental,
        bpm_min: station.bpm_min !== null ? String(station.bpm_min) : "",
        bpm_max: station.bpm_max !== null ? String(station.bpm_max) : "",
        duration_min: String(station.duration_min),
        duration_max: String(station.duration_max),
        keyscale: station.keyscale,
        timesignature: station.timesignature,
        structure_ids: station.structure_ids || [],
        intensity,
        lyrics_style_addons,
        theme_pool,
      });
    }
  }, [station]);

  const updateField = useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const mutation = useMutation({
    mutationFn: () => {
      if (!station) throw new Error("No station to update");

      const bpmMin = form.bpm_min ? Number(form.bpm_min) : null;
      const bpmMax = form.bpm_max ? Number(form.bpm_max) : null;
      const durationMin = form.duration_min
        ? Number(form.duration_min)
        : undefined;
      const durationMax = form.duration_max
        ? Number(form.duration_max)
        : undefined;

      let advancedParams: any = {};
      try {
        if (station.advanced_params_json) {
          advancedParams = JSON.parse(station.advanced_params_json);
        }
      } catch (e) {}

      advancedParams.intensity = form.intensity;
      advancedParams.lyrics_style_addons = form.lyrics_style_addons;
      advancedParams.theme_pool = form.theme_pool
        ? form.theme_pool.split(",").map((t) => t.trim()).filter(Boolean)
        : [];

      return updateStation(station.id, {
        name: form.name.trim(),
        description: form.description.trim(),
        genre: form.genre.trim(),
        mood: form.mood.trim(),
        caption_template: form.caption_template.trim(),
        instrumental: form.instrumental,
        bpm_min: bpmMin,
        bpm_max: bpmMax,
        duration_min: durationMin,
        duration_max: durationMax,
        keyscale: form.keyscale.trim(),
        timesignature: form.timesignature.trim(),
        structure_ids: form.structure_ids,
        advanced_params_json: JSON.stringify(advancedParams),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stations"] });
      toast.success("Station updated");
      onOpenChange(false);
      onUpdated?.();
    },
    onError: (err) => {
      toast.error(`Failed to update station: ${err.message}`);
    },
  });

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      mutation.mutate();
    },
    [mutation],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit Station</DialogTitle>
          <DialogDescription>
            Update your radio station settings.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="edit-station-name">Name</Label>
            <Input
              id="edit-station-name"
              value={form.name}
              onChange={(e) => updateField("name", e.target.value)}
              required
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label htmlFor="edit-station-description">Description</Label>
            <Input
              id="edit-station-description"
              value={form.description}
              onChange={(e) => updateField("description", e.target.value)}
            />
          </div>

          {/* Genre + Mood */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-genre">Genre</Label>
              <Input
                id="edit-station-genre"
                placeholder="e.g. Jazz, Rock"
                value={form.genre}
                onChange={(e) => updateField("genre", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-mood">Mood</Label>
              <Input
                id="edit-station-mood"
                placeholder="e.g. Chill, Energetic"
                value={form.mood}
                onChange={(e) => updateField("mood", e.target.value)}
              />
            </div>
          </div>

          {/* Caption Template */}
          <div className="space-y-1.5">
            <Label htmlFor="edit-station-caption-template">
              Caption Template
            </Label>
            <Textarea
              id="edit-station-caption-template"
              placeholder="e.g. A {mood} {genre} track with warm textures"
              value={form.caption_template}
              onChange={(e) =>
                updateField("caption_template", e.target.value)
              }
              rows={2}
            />
            <p className="text-xs text-muted-foreground">
              Use {"{mood}"} and {"{genre}"} as placeholders. Leave empty for
              auto-generated captions.
            </p>
          </div>

          {/* Instrumental */}
          <div className="flex items-center justify-between rounded-lg border border-border p-3">
            <Label
              htmlFor="edit-station-instrumental"
              className="cursor-pointer"
            >
              Instrumental
            </Label>
            <Switch
              id="edit-station-instrumental"
              checked={form.instrumental}
              onCheckedChange={(checked) =>
                updateField("instrumental", checked)
              }
            />
          </div>

          {/* BPM Range */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-bpm-min">BPM Min</Label>
              <Input
                id="edit-station-bpm-min"
                type="number"
                placeholder="60"
                value={form.bpm_min}
                onChange={(e) => updateField("bpm_min", e.target.value)}
                min={0}
                max={300}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-bpm-max">BPM Max</Label>
              <Input
                id="edit-station-bpm-max"
                type="number"
                placeholder="180"
                value={form.bpm_max}
                onChange={(e) => updateField("bpm_max", e.target.value)}
                min={0}
                max={300}
              />
            </div>
          </div>

          {/* Duration Range */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-duration-min">
                Duration Min (sec)
              </Label>
              <Input
                id="edit-station-duration-min"
                type="number"
                placeholder="30"
                value={form.duration_min}
                onChange={(e) => updateField("duration_min", e.target.value)}
                min={0}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-duration-max">
                Duration Max (sec)
              </Label>
              <Input
                id="edit-station-duration-max"
                type="number"
                placeholder="240"
                value={form.duration_max}
                onChange={(e) => updateField("duration_max", e.target.value)}
                min={0}
              />
            </div>
          </div>

          {/* Key/Scale + Time Signature */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-keyscale">Key / Scale</Label>
              <Input
                id="edit-station-keyscale"
                placeholder="e.g. C major"
                value={form.keyscale}
                onChange={(e) => updateField("keyscale", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-timesignature">Time Signature</Label>
              <Input
                id="edit-station-timesignature"
                placeholder="e.g. 4/4"
                value={form.timesignature}
                onChange={(e) => updateField("timesignature", e.target.value)}
              />
            </div>
          </div>

          <div className="border-t pt-4 mt-4 space-y-4">
            <h3 className="text-sm font-medium">Advanced Dynamics & Lyrics</h3>
            
            {/* Song Structures */}
            <div className="space-y-2">
              <Label>Song Structures</Label>
              {structures.length > 0 ? (
                <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto p-2 border rounded-md">
                  {structures.map((s) => (
                    <div key={s.id} className="flex items-center space-x-2">
                      <Checkbox
                        id={`edit-structure-${s.id}`}
                        checked={form.structure_ids.includes(s.id)}
                        onCheckedChange={(checked) => {
                          if (checked) {
                            updateField("structure_ids", [...form.structure_ids, s.id]);
                          } else {
                            updateField(
                              "structure_ids",
                              form.structure_ids.filter((id) => id !== s.id)
                            );
                          }
                        }}
                      />
                      <Label htmlFor={`edit-structure-${s.id}`} className="text-sm font-normal cursor-pointer">
                        {s.name}
                      </Label>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No global structures defined yet.</p>
              )}
            </div>

            {/* Intensity + Prompt Style Addons */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Intensity</Label>
                <Select
                  value={form.intensity}
                  onValueChange={(v) => updateField("intensity", v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Intensity" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Low">Low</SelectItem>
                    <SelectItem value="Moderate">Moderate</SelectItem>
                    <SelectItem value="High">High</SelectItem>
                    <SelectItem value="Extreme">Extreme</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-station-lyrics-addons">Prompt Style Addons</Label>
                <Input
                  id="edit-station-lyrics-addons"
                  placeholder="e.g. Poetic, Aggressive"
                  value={form.lyrics_style_addons}
                  onChange={(e) => updateField("lyrics_style_addons", e.target.value)}
                />
              </div>
            </div>

            {/* Theme Pool */}
            <div className="space-y-1.5">
              <Label htmlFor="edit-station-theme-pool">Theme Pool (comma-separated)</Label>
              <Textarea
                id="edit-station-theme-pool"
                placeholder="e.g. Heartbreak, Overcoming adversity, Late night driving"
                value={form.theme_pool}
                onChange={(e) => updateField("theme_pool", e.target.value)}
                rows={2}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!form.name.trim() || mutation.isPending}
            >
              {mutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
