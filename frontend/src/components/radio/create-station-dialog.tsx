"use client";

import { useState, useCallback } from "react";
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
import { createStation, fetchStructures } from "@/lib/api/radio-client";

interface CreateStationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

const INITIAL_FORM = {
  name: "",
  description: "",
  genre: "",
  mood: "",
  caption_template: "",
  instrumental: false,
  vocal_language: "en",
  audio_format: "flac",
  bpm_min: "",
  bpm_max: "",
  duration_min: "",
  duration_max: "",
  keyscale: "",
  timesignature: "",
  structure_ids: [] as string[],
  intensity: "Moderate",
  lyrics_style_addons: "",
  theme_pool: "",
} as const;

type FormState = {
  name: string;
  description: string;
  genre: string;
  mood: string;
  caption_template: string;
  instrumental: boolean;
  vocal_language: string;
  audio_format: string;
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
};

export function CreateStationDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateStationDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>({ ...INITIAL_FORM });

  const { data: structures = [] } = useQuery({
    queryKey: ["structures"],
    queryFn: fetchStructures,
    enabled: open,
  });

  const updateField = useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const mutation = useMutation({
    mutationFn: () => {
      const bpmMin = form.bpm_min ? Number(form.bpm_min) : undefined;
      const bpmMax = form.bpm_max ? Number(form.bpm_max) : undefined;
      const durationMin = form.duration_min
        ? Number(form.duration_min)
        : undefined;
      const durationMax = form.duration_max
        ? Number(form.duration_max)
        : undefined;

      const advancedParams = {
        audio_format: form.audio_format,
        intensity: form.intensity,
        lyrics_style_addons: form.lyrics_style_addons,
        theme_pool: form.theme_pool
          ? form.theme_pool.split(",").map((t) => t.trim()).filter(Boolean)
          : [],
      };

      return createStation({
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        genre: form.genre.trim() || undefined,
        mood: form.mood.trim() || undefined,
        instrumental: form.instrumental,
        caption_template: form.caption_template.trim() || undefined,
        vocal_language: form.vocal_language,
        bpm_min: bpmMin ?? null,
        bpm_max: bpmMax ?? null,
        duration_min: durationMin,
        duration_max: durationMax,
        keyscale: form.keyscale.trim() || undefined,
        timesignature: form.timesignature.trim() || undefined,
        advanced_params_json: JSON.stringify(advancedParams),
        structure_ids: form.structure_ids,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stations"] });
      toast.success("Station created");
      setForm({ ...INITIAL_FORM });
      onOpenChange(false);
      onCreated?.();
    },
    onError: (err) => {
      toast.error(`Failed to create station: ${err.message}`);
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
          <DialogTitle>Create Station</DialogTitle>
          <DialogDescription>
            Configure a new radio station that generates music based on your
            preferences.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="station-name">Name</Label>
            <Input
              id="station-name"
              placeholder="My Station"
              value={form.name}
              onChange={(e) => updateField("name", e.target.value)}
              required
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label htmlFor="station-description">Description</Label>
            <Input
              id="station-description"
              placeholder="Optional description"
              value={form.description}
              onChange={(e) => updateField("description", e.target.value)}
            />
          </div>

          {/* Genre + Mood */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="station-genre">Genre</Label>
              <Input
                id="station-genre"
                placeholder="e.g. Jazz, Rock"
                value={form.genre}
                onChange={(e) => updateField("genre", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="station-mood">Mood</Label>
              <Input
                id="station-mood"
                placeholder="e.g. Chill, Energetic"
                value={form.mood}
                onChange={(e) => updateField("mood", e.target.value)}
              />
            </div>
          </div>

          {/* Caption Template */}
          <div className="space-y-1.5">
            <Label htmlFor="station-caption-template">Caption Template</Label>
            <Textarea
              id="station-caption-template"
              placeholder="e.g. A {mood} {genre} track with warm textures"
              value={form.caption_template}
              onChange={(e) => updateField("caption_template", e.target.value)}
              rows={2}
            />
            <p className="text-xs text-muted-foreground">
              Use {"{mood}"} and {"{genre}"} as placeholders. Leave empty for
              auto-generated captions.
            </p>
          </div>

          {/* Instrumental + Audio Format */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <Label htmlFor="station-instrumental" className="cursor-pointer">
                Instrumental
              </Label>
              <Switch
                id="station-instrumental"
                checked={form.instrumental}
                onCheckedChange={(checked) =>
                  updateField("instrumental", checked)
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label>Audio Format</Label>
              <Select
                value={form.audio_format}
                onValueChange={(v) => updateField("audio_format", v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Format" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="flac">FLAC</SelectItem>
                  <SelectItem value="mp3">MP3</SelectItem>
                  <SelectItem value="wav">WAV</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Language */}
          <div className="space-y-1.5">
            <Label>Vocal Language</Label>
            <Select
              value={form.vocal_language}
              onValueChange={(v) => updateField("vocal_language", v)}
              disabled={form.instrumental}
            >
              <SelectTrigger>
                <SelectValue placeholder="Language" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="ja">Japanese</SelectItem>
                <SelectItem value="ko">Korean</SelectItem>
                <SelectItem value="zh">Chinese</SelectItem>
                <SelectItem value="es">Spanish</SelectItem>
                <SelectItem value="fr">French</SelectItem>
                <SelectItem value="de">German</SelectItem>
                <SelectItem value="unknown">Auto / Any</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* BPM Range */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="station-bpm-min">BPM Min</Label>
              <Input
                id="station-bpm-min"
                type="number"
                placeholder="60"
                value={form.bpm_min}
                onChange={(e) => updateField("bpm_min", e.target.value)}
                min={0}
                max={300}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="station-bpm-max">BPM Max</Label>
              <Input
                id="station-bpm-max"
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
              <Label htmlFor="station-duration-min">Duration Min (sec)</Label>
              <Input
                id="station-duration-min"
                type="number"
                placeholder="30"
                value={form.duration_min}
                onChange={(e) => updateField("duration_min", e.target.value)}
                min={0}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="station-duration-max">Duration Max (sec)</Label>
              <Input
                id="station-duration-max"
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
              <Label htmlFor="station-keyscale">Key / Scale</Label>
              <Input
                id="station-keyscale"
                placeholder="e.g. C major"
                value={form.keyscale}
                onChange={(e) => updateField("keyscale", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="station-timesignature">Time Signature</Label>
              <Input
                id="station-timesignature"
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
                        id={`structure-${s.id}`}
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
                      <Label htmlFor={`structure-${s.id}`} className="text-sm font-normal cursor-pointer">
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
                <Label htmlFor="station-lyrics-addons">Prompt Style Addons</Label>
                <Input
                  id="station-lyrics-addons"
                  placeholder="e.g. Poetic, Aggressive"
                  value={form.lyrics_style_addons}
                  onChange={(e) => updateField("lyrics_style_addons", e.target.value)}
                />
              </div>
            </div>

            {/* Theme Pool */}
            <div className="space-y-1.5">
              <Label htmlFor="station-theme-pool">Theme Pool (comma-separated)</Label>
              <Textarea
                id="station-theme-pool"
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
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
