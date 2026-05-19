"use client";

import { useState, useCallback, useEffect } from "react";
import { Loader2, AlertCircle, RotateCcw, Headphones } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchRadioSettings,
  updateRadioSettings,
  fetchVaeThrottle,
  updateVaeThrottle,
  fetchDitThrottle,
  updateDitThrottle,
  resetThrottle,
  fetchThrottleScope,
  updateThrottleScope,
} from "@/lib/api/radio-client";
import { useSettingsStore } from "@/stores/settings-store";
import { useAmbientStore } from "@/stores/ambient-store";
import type { AmbientEffect } from "@/lib/audio/ambient-noise";

interface RadioSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RadioSettingsDialog({
  open,
  onOpenChange,
}: RadioSettingsDialogProps) {
  const queryClient = useQueryClient();
  const { radioAutoSave, setRadioAutoSave } = useSettingsStore();
  const {
    enabled: ambientEnabled,
    effect: ambientEffect,
    volume: ambientVolume,
    setEnabled: setAmbientEnabled,
    setEffect: setAmbientEffect,
    setVolume: setAmbientVolume,
  } = useAmbientStore();

  // -- LLM settings --
  const {
    data: radioSettings,
    isLoading: isLoadingSettings,
    refetch: refetchSettings,
  } = useQuery({
    queryKey: ["radio-settings"],
    queryFn: fetchRadioSettings,
    enabled: open,
  });

  const [selectedProvider, setSelectedProvider] = useState("none");
  const [selectedModel, setSelectedModel] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [isSavingLLM, setIsSavingLLM] = useState(false);

  useEffect(() => {
    if (radioSettings) {
      setSelectedProvider(radioSettings.active_provider);
      setSelectedModel(radioSettings.active_model);
      setSystemPrompt(
        radioSettings.system_prompt || radioSettings.default_system_prompt,
      );
    }
  }, [radioSettings]);

  const activeProviderInfo = radioSettings?.providers.find(
    (p) => p.name === selectedProvider,
  );
  const availableModels = activeProviderInfo?.models ?? [];
  const isNoneProvider = selectedProvider === "none";

  const handleProviderChange = useCallback(
    (value: string) => {
      setSelectedProvider(value);
      if (value === "none") {
        setSelectedModel("");
        return;
      }
      const newProvider = radioSettings?.providers.find(
        (p) => p.name === value,
      );
      const firstModel = newProvider?.models[0] ?? "";
      setSelectedModel(firstModel);
    },
    [radioSettings],
  );

  const handleResetPrompt = useCallback(() => {
    if (radioSettings) {
      setSystemPrompt(radioSettings.default_system_prompt);
    }
  }, [radioSettings]);

  const handleSaveLLM = useCallback(async () => {
    setIsSavingLLM(true);
    try {
      await updateRadioSettings({
        provider: selectedProvider,
        model: selectedModel,
        system_prompt: systemPrompt,
      });
      toast.success("Radio caption settings updated");
      await refetchSettings();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to update settings";
      toast.error(message);
    }
    setIsSavingLLM(false);
  }, [selectedProvider, selectedModel, systemPrompt, refetchSettings]);

  // -- GPU Throttle --
  const vaeThrottleQuery = useQuery({
    queryKey: ["vae-throttle"],
    queryFn: fetchVaeThrottle,
    enabled: open,
  });

  const ditThrottleQuery = useQuery({
    queryKey: ["dit-throttle"],
    queryFn: fetchDitThrottle,
    enabled: open,
  });

  const throttleScopeQuery = useQuery({
    queryKey: ["throttle-scope"],
    queryFn: fetchThrottleScope,
    enabled: open,
  });

  const vaeThrottleMutation = useMutation({
    mutationFn: updateVaeThrottle,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vae-throttle"] });
      toast.success("VAE throttle saved");
    },
    onError: (err: Error) => toast.error(`Failed to save: ${err.message}`),
  });

  const ditThrottleMutation = useMutation({
    mutationFn: updateDitThrottle,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dit-throttle"] });
      toast.success("DiT throttle saved");
    },
    onError: (err: Error) => toast.error(`Failed to save: ${err.message}`),
  });

  const throttleResetMutation = useMutation({
    mutationFn: resetThrottle,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vae-throttle"] });
      queryClient.invalidateQueries({ queryKey: ["dit-throttle"] });
      queryClient.invalidateQueries({ queryKey: ["throttle-scope"] });
      toast.success("Throttle settings reset to defaults");
    },
    onError: (err: Error) => toast.error(`Failed to reset: ${err.message}`),
  });

  const throttleScopeMutation = useMutation({
    mutationFn: updateThrottleScope,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["throttle-scope"] });
      toast.success("Throttle scope updated");
    },
    onError: (err: Error) => toast.error(`Failed to update: ${err.message}`),
  });

  const [vaeChunkSize, setVaeChunkSize] = useState(128);
  const [vaeSleepMs, setVaeSleepMs] = useState(200);
  const [ditSleepMs, setDitSleepMs] = useState(200);

  useEffect(() => {
    if (vaeThrottleQuery.data) {
      setVaeChunkSize(vaeThrottleQuery.data.chunk_size);
      setVaeSleepMs(vaeThrottleQuery.data.sleep_ms);
    }
  }, [vaeThrottleQuery.data]);

  useEffect(() => {
    if (ditThrottleQuery.data) {
      setDitSleepMs(ditThrottleQuery.data.sleep_ms);
    }
  }, [ditThrottleQuery.data]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Radio Settings</DialogTitle>
          <DialogDescription>
            Configure caption generation, GPU throttle, auto-save, and ambiance.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 overflow-y-auto flex-1 pr-1">
          {/* Caption LLM section */}
          <div className="space-y-4">
            <Label className="text-sm font-medium">Caption LLM</Label>
            <p className="text-xs text-muted-foreground">
              Optionally route captions through a chat LLM for richer, more
              varied prompts. &quot;None&quot; uses simple template-based
              captions (default).
            </p>

            {isLoadingSettings ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <>
                {/* Provider selector — includes "None" option */}
                <div className="space-y-2">
                  <Label htmlFor="radio-provider-select">Provider</Label>
                  <Select
                    value={selectedProvider}
                    onValueChange={handleProviderChange}
                  >
                    <SelectTrigger id="radio-provider-select">
                      <SelectValue placeholder="Select a provider" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">None (template)</SelectItem>
                      {radioSettings?.providers.map((provider) => (
                        <SelectItem key={provider.name} value={provider.name}>
                          <span className="flex items-center gap-2">
                            {provider.name}
                            {!provider.available && (
                              <Badge
                                variant="outline"
                                className="text-[10px] text-red-700 dark:text-red-500 border-red-500/20"
                              >
                                Unavailable
                              </Badge>
                            )}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Availability + reason */}
                {!isNoneProvider && activeProviderInfo && (
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={
                        activeProviderInfo.available
                          ? "border-green-500/20 bg-green-500/10 text-green-700 dark:text-green-500"
                          : "border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-500"
                      }
                    >
                      {activeProviderInfo.available
                        ? "Available"
                        : "Unavailable"}
                    </Badge>
                  </div>
                )}

                {!isNoneProvider &&
                  activeProviderInfo &&
                  !activeProviderInfo.available &&
                  activeProviderInfo.unavailable_reason && (
                    <div className="flex items-start gap-2 rounded-md bg-blue-500/10 p-3 text-sm text-blue-600 dark:text-blue-400">
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>{activeProviderInfo.unavailable_reason}</span>
                    </div>
                  )}

                {!isNoneProvider &&
                  activeProviderInfo?.requires_api_key &&
                  !activeProviderInfo.has_stored_api_key && (
                    <div className="flex items-start gap-2 rounded-md bg-yellow-500/10 p-3 text-sm text-yellow-600 dark:text-yellow-500">
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>
                        This provider requires an API key. Add one on the{" "}
                        <a
                          href="/models"
                          className="underline underline-offset-2 hover:text-yellow-700 dark:hover:text-yellow-400"
                        >
                          Models
                        </a>{" "}
                        page.
                      </span>
                    </div>
                  )}

                {!isNoneProvider &&
                  activeProviderInfo?.name === "openai-compatible" &&
                  !activeProviderInfo.has_api_base && (
                    <div className="flex items-start gap-2 rounded-md bg-yellow-500/10 p-3 text-sm text-yellow-600 dark:text-yellow-500">
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>
                        This provider requires an API base URL. Configure it on the{" "}
                        <a
                          href="/models"
                          className="underline underline-offset-2 hover:text-yellow-700 dark:hover:text-yellow-400"
                        >
                          Models
                        </a>{" "}
                        page.
                      </span>
                    </div>
                  )}

                {/* Model selector */}
                {!isNoneProvider && (
                  <div className="space-y-2">
                    <Label htmlFor="radio-model-select">Model</Label>
                    <Select
                      value={selectedModel}
                      onValueChange={setSelectedModel}
                    >
                      <SelectTrigger id="radio-model-select">
                        <SelectValue placeholder="Select a model" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableModels.map((model) => (
                          <SelectItem key={model} value={model}>
                            {model}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {availableModels.length === 0 && (
                      <p className="text-xs text-muted-foreground">
                        No models available for this provider.
                      </p>
                    )}
                  </div>
                )}

                {/* System prompt */}
                {!isNoneProvider && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="radio-system-prompt">System Prompt</Label>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-auto px-2 py-1 text-xs text-muted-foreground"
                        onClick={handleResetPrompt}
                      >
                        Reset to default
                      </Button>
                    </div>
                    <Textarea
                      id="radio-system-prompt"
                      rows={4}
                      value={systemPrompt}
                      onChange={(e) => setSystemPrompt(e.target.value)}
                      className="font-mono text-xs"
                      placeholder="Enter a custom system prompt..."
                    />
                  </div>
                )}

                {!isNoneProvider && (
                  <div className="flex items-start gap-2 rounded-md bg-blue-500/10 p-3 text-sm text-blue-600 dark:text-blue-400">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      Using a cloud provider (OpenAI, Anthropic) offloads
                      caption generation to the cloud, leaving more local GPU
                      memory for music generation and reducing stuttering during
                      radio playback.
                    </span>
                  </div>
                )}

                <Button
                  size="sm"
                  onClick={handleSaveLLM}
                  disabled={
                    isSavingLLM ||
                    (!isNoneProvider && !selectedProvider) ||
                    (!isNoneProvider && !selectedModel)
                  }
                >
                  {isSavingLLM && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Save Caption Settings
                </Button>
              </>
            )}
          </div>

          <Separator />

          {/* GPU Throttle section */}
          <div className="space-y-4">
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <Label className="text-sm font-medium">GPU Throttle</Label>
                <p className="text-xs text-muted-foreground">
                  Adds pauses between GPU-intensive steps to prevent audio
                  stuttering on Apple Silicon unified memory.
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => throttleResetMutation.mutate()}
                disabled={throttleResetMutation.isPending}
                className="shrink-0"
              >
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                Reset
              </Button>
            </div>

            {throttleScopeQuery.data && (
              <div className="flex items-center justify-between rounded-lg bg-secondary/50 px-3 py-2">
                <div className="space-y-0.5">
                  <Label htmlFor="radio-only-scope">Radio only</Label>
                  <p className="text-xs text-muted-foreground">
                    Only throttle during radio playback.
                  </p>
                </div>
                <Switch
                  id="radio-only-scope"
                  checked={throttleScopeQuery.data.radio_only}
                  onCheckedChange={(checked) =>
                    throttleScopeMutation.mutate({ radio_only: checked })
                  }
                />
              </div>
            )}

            {/* DiT */}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">DiT Diffusion</Label>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Pause between steps</Label>
                <span className="font-mono text-xs text-muted-foreground">
                  {ditSleepMs} ms
                </span>
              </div>
              <Slider
                value={[ditSleepMs]}
                min={0}
                max={500}
                step={25}
                onValueChange={([v]) => setDitSleepMs(v)}
                onValueCommit={([v]) =>
                  ditThrottleMutation.mutate({ sleep_ms: v })
                }
              />
            </div>

            <Separator />

            {/* VAE */}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">VAE Decode</Label>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Chunk size</Label>
                <span className="font-mono text-xs text-muted-foreground">
                  {vaeChunkSize} frames
                </span>
              </div>
              <Slider
                value={[vaeChunkSize]}
                min={128}
                max={2048}
                step={128}
                onValueChange={([v]) => setVaeChunkSize(v)}
                onValueCommit={([v]) =>
                  vaeThrottleMutation.mutate({
                    chunk_size: v,
                    sleep_ms: vaeSleepMs,
                  })
                }
              />
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Pause between chunks</Label>
                <span className="font-mono text-xs text-muted-foreground">
                  {vaeSleepMs} ms
                </span>
              </div>
              <Slider
                value={[vaeSleepMs]}
                min={0}
                max={500}
                step={25}
                onValueChange={([v]) => setVaeSleepMs(v)}
                onValueCommit={([v]) =>
                  vaeThrottleMutation.mutate({
                    chunk_size: vaeChunkSize,
                    sleep_ms: v,
                  })
                }
              />
            </div>
          </div>

          <Separator />

          {/* Auto-save section */}
          <div className="space-y-4">
            <Label className="text-sm font-medium">Auto-save</Label>
            <div className="flex items-center justify-between rounded-lg bg-secondary/50 px-3 py-2">
              <div className="space-y-0.5">
                <Label htmlFor="radio-auto-save-toggle">
                  Auto-save radio tracks
                </Label>
                <p className="text-xs text-muted-foreground">
                  Automatically save each generated track to a playlist matching
                  the station name.
                </p>
              </div>
              <Switch
                id="radio-auto-save-toggle"
                checked={radioAutoSave}
                onCheckedChange={setRadioAutoSave}
              />
            </div>
          </div>

          <Separator />

          {/* Ambiance section */}
          <div className="space-y-4">
            <Label className="text-sm font-medium flex items-center gap-2">
              <Headphones className="h-4 w-4" />
              Ambiance
            </Label>
            <p className="text-xs text-muted-foreground">
              Add atmospheric sound effects during radio playback.
            </p>

            <div className="flex items-center justify-between rounded-lg bg-secondary/50 px-3 py-2">
              <div className="space-y-0.5">
                <Label htmlFor="ambient-enabled-toggle">Enable ambiance</Label>
                <p className="text-xs text-muted-foreground">
                  Play subtle background noise during radio mode.
                </p>
              </div>
              <Switch
                id="ambient-enabled-toggle"
                checked={ambientEnabled}
                onCheckedChange={setAmbientEnabled}
              />
            </div>

            <div className="space-y-2">
              <Label>Effect type</Label>
              <Select
                value={ambientEffect}
                onValueChange={(v) =>
                  setAmbientEffect(v as typeof ambientEffect)
                }
                disabled={!ambientEnabled}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="vinyl-crackle">Vinyl Crackle</SelectItem>
                  <SelectItem value="radio-static">Radio Static</SelectItem>
                  <SelectItem value="brown-noise">Brown Noise</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>Volume</Label>
                <span className="font-mono text-xs text-muted-foreground">
                  {Math.round(ambientVolume * 100)}%
                </span>
              </div>
              <Slider
                value={[ambientVolume]}
                min={0}
                max={0.5}
                step={0.01}
                onValueChange={([v]) => setAmbientVolume(v)}
                disabled={!ambientEnabled}
              />
            </div>
          </div>
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
